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


async def _ensure_channel() -> aio_pika.abc.AbstractChannel:
    global _channel
    if _channel is not None and not _channel.is_closed:
        return _channel
    global _connection
    _connection = await aio_pika.connect_robust(RABBITMQ_URL)
    _channel = await _connection.channel()
    await _channel.set_publisher_confirms(True)
    await _channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    return _channel


_channel: aio_pika.abc.AbstractChannel | None = None
_connection: aio_pika.abc.AbstractRobustConnection | None = None


async def publish(routing_key: str, payload: dict) -> bool:
    """发布事件。失败返回 False（调用方降级），绝不抛出。"""
    try:
        channel = await _ensure_channel()
        message = aio_pika.Message(
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            timestamp=int(time.time()),
        )
        await channel.default_exchange.publish(message, routing_key=routing_key, exchange=EXCHANGE)
        return True
    except Exception as exc:
        logger.warning(f"[mq] publish {routing_key} failed (degraded): {exc}")
        return False


def publish_soon(routing_key: str, payload: dict) -> None:
    """从同步代码触发的 fire-and-forget 发布（自带事件循环线程）。"""
    def _run() -> None:
        try:
            asyncio.run(publish(routing_key, payload))
        except Exception as exc:
            logger.warning(f"[mq] publish_soon {routing_key} failed (degraded): {exc}")

    try:
        asyncio.get_running_loop()
        asyncio.get_running_loop().create_task(publish(routing_key, payload))
    except RuntimeError:
        threading.Thread(target=_run, daemon=True, name=f"mq-{routing_key}").start()


async def consume(queue: str, routing_key: str, handler: Callable[[dict], Awaitable[None]]) -> None:
    """常驻消费者：处理完再 ack；未处理异常 nack 且不重回队列（由死信/失败事件接管）。"""
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    queue_obj = await channel.declare_queue(queue, durable=True)
    await queue_obj.bind(EXCHANGE, routing_key=routing_key)
    logger.info(f"[mq] consuming {queue} (routing {routing_key})")

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
