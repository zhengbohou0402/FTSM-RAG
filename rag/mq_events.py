"""
RabbitMQ 事件通道（aio-pika）。

事件契约对齐 ftsm-knowledge 的拓扑（见 docs/架构对齐改造模板.md §4.1）：
- doc.index.requested  （ftsm-knowledge 发布，本模块消费）
- doc.index.succeeded / doc.index.failed（本模块发布，ftsm-knowledge 原子迁移状态）
- doc.deleted          （本模块发布，ftsm-knowledge 删除记录）
- retrieval.logged     （本模块 fire-and-forget 发布，ftsm-knowledge 落查询日志）

所有发布都带 publisher confirms；连接失败一律降级为日志，不阻塞主链路。
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Awaitable, Callable

import aio_pika

from utils.logger_handler import logger

RABBITMQ_URL = os.getenv("FTSM_RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/")
EXCHANGE = "ftsm.doc.exchange"

INDEX_REQUEST_QUEUE = "doc.index.request.queue"
KEY_INDEX_REQUESTED = "doc.index.requested"
KEY_INDEX_SUCCEEDED = "doc.index.succeeded"
KEY_INDEX_FAILED = "doc.index.failed"
KEY_DOC_DELETED = "doc.deleted"
KEY_RETRIEVAL_LOGGED = "retrieval.logged"


_channel: aio_pika.abc.AbstractChannel | None = None
_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel_loop: asyncio.AbstractEventLoop | None = None
_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_lock = threading.Lock()
# 与当前事件循环绑定的建连锁：asyncio.Lock 不能跨 loop 复用，loop 变化时重建
_connect_lock: asyncio.Lock | None = None
_connect_lock_loop: asyncio.AbstractEventLoop | None = None


def _get_connect_lock(loop: asyncio.AbstractEventLoop) -> asyncio.Lock:
    """返回与 loop 绑定的建连锁（单线程事件循环内同步取用，无竞态）。"""
    global _connect_lock, _connect_lock_loop
    if _connect_lock is None or _connect_lock_loop is not loop:
        _connect_lock = asyncio.Lock()
        _connect_lock_loop = loop
    return _connect_lock


async def _ensure_channel() -> aio_pika.abc.AbstractChannel:
    global _channel, _connection, _channel_loop
    loop = asyncio.get_running_loop()
    if _channel is not None and not _channel.is_closed and _channel_loop is loop:
        return _channel
    # 双重检查锁：channel 未初始化/断线时，多个 publish_soon 协程可能并发进入，
    # 用锁保证同一时刻只有一个协程执行 connect_robust，避免重复建连覆盖全局连接
    async with _get_connect_lock(loop):
        if _channel is not None and not _channel.is_closed and _channel_loop is loop:
            return _channel
        _connection = await aio_pika.connect_robust(RABBITMQ_URL)
        # Publisher confirms are a channel constructor option in aio-pika 9.x
        # (RobustChannel has no set_publisher_confirms method).
        _channel = await _connection.channel(publisher_confirms=True)
        _channel_loop = loop
        await _channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    return _channel


def _get_bg_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop
    with _bg_lock:
        if _bg_loop is None or _bg_loop.is_closed():
            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, daemon=True, name="mq-publisher-loop").start()
            _bg_loop = loop
        return _bg_loop


async def _raw_publish(routing_key: str, payload: dict) -> bool:
    """在后台事件循环内部执行真正的发布。"""
    try:
        channel = await _ensure_channel()
        message = aio_pika.Message(
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            timestamp=int(time.time()),
        )
        exchange = await channel.declare_exchange(
            EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        await exchange.publish(message, routing_key=routing_key)
        return True
    except Exception as exc:
        logger.warning(f"[mq] publish {routing_key} failed (degraded): {exc}")
        return False


async def publish(routing_key: str, payload: dict) -> bool:
    """发布事件并等待确认。统一调度到后台发布循环，避免多事件循环竞争同一全局连接。"""
    bg_loop = _get_bg_loop()
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is bg_loop:
        return await _raw_publish(routing_key, payload)

    future = asyncio.run_coroutine_threadsafe(_raw_publish(routing_key, payload), bg_loop)
    try:
        return await asyncio.wrap_future(future)
    except Exception as exc:
        logger.warning(f"[mq] publish {routing_key} failed: {exc}")
        return False


def publish_soon(routing_key: str, payload: dict) -> None:
    """从同步代码触发的 fire-and-forget 发布（统一投递到常驻后台发布线程的事件循环）。"""
    bg_loop = _get_bg_loop()
    asyncio.run_coroutine_threadsafe(_raw_publish(routing_key, payload), bg_loop)



async def consume(
    queue: str,
    routing_key: str,
    handler: Callable[[dict], Awaitable[None]],
    *,
    on_ready: Callable[[], None] | None = None,
) -> None:
    """常驻消费者：处理完再 ack；未处理异常 nack 且不重回队列（由死信/失败事件接管）。

    on_ready 在「已连上并开始监听」时回调一次，供调用方判断 MQ 链路是否可用
    （上传流程据此决定走事件链路还是本地训练兜底）。
    """
    # Startup retry: at container boot RabbitMQ may not be resolvable/reachable
    # yet (DNS + listener race). Retry the *initial* connect; connect_robust
    # handles reconnects after the first success.
    connection = None
    for attempt in range(1, 11):
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            break
        except Exception as exc:
            logger.warning(f"[mq] connect attempt {attempt}/10 failed for {queue}: {exc}")
            await asyncio.sleep(3)
    if connection is None:
        raise RuntimeError(f"[mq] rabbit unreachable after 10 attempts (queue={queue})")
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    # Arguments MUST mirror the Java-side declaration (RabbitTopology) — a mismatch
    # makes RabbitMQ reject the declare with 406 PRECONDITION_FAILED.
    declare_kwargs = {"durable": True}
    if queue == "doc.index.request.queue":
        declare_kwargs["arguments"] = {
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": "doc.index.dlq",
            "x-message-ttl": 86_400_000,
        }
    queue_obj = await channel.declare_queue(queue, **declare_kwargs)
    await queue_obj.bind(EXCHANGE, routing_key=routing_key)
    logger.info(f"[mq] consuming {queue} (routing {routing_key})")
    if on_ready is not None:
        on_ready()

    async with queue_obj.iterator() as iterator:
        async for message in iterator:
            try:
                payload = json.loads(message.body.decode("utf-8"))
            except Exception:
                logger.warning(f"[mq] malformed message on {queue}: {message.body[:120]!r}")
                await message.ack()
                continue
            try:
                await handler(payload)
                await message.ack()
            except Exception as exc:
                logger.error(f"[mq] handler failed on {queue}: {exc}")
                await message.nack(requeue=False)
