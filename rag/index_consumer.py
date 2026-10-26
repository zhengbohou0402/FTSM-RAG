"""
索引消费者：消费 doc.index.requested，对单个文件执行切块/向量化，并回发结果事件。

- 成功 -> doc.index.succeeded {docId, chunkIds}
- 失败 -> doc.index.failed {docId, error}（chunk_ids 保留在 manifest 供下次清理）
阻塞的向量化放到线程池执行，避免卡住事件循环。
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from rag.ingestion import load_manifest
from rag.mq_events import (
    KEY_INDEX_FAILED,
    KEY_INDEX_REQUESTED,
    KEY_INDEX_SUCCEEDED,
    INDEX_REQUEST_QUEUE,
    consume,
    publish,
)
from rag.vector_store import VectorStoreService
from utils.config_handler import chroma_conf
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

DATA_DIR = Path(get_abs_path(chroma_conf["data_path"]))

# 「MQ 链路可用」的进程内信号：上传流程据此决定走事件链路还是本地训练兜底。
# 只在真正连上并开始监听后置位，连接断开/消费循环退出时清除。
_CONSUMER_READY = threading.Event()


def consumer_ready() -> bool:
    return _CONSUMER_READY.is_set()


# VectorStoreService opens its own Chroma/Qdrant clients and embedding model;
# constructing one per MQ message wastes both memory and connection churn.
_service: VectorStoreService | None = None


def _get_service() -> VectorStoreService:
    global _service
    if _service is None:
        _service = VectorStoreService()
    return _service


def _index_and_collect(doc_id: str, target: Path) -> tuple[dict, list]:
    """P1-5：向量化 + manifest 读取整体持有 indexing_lock。

    本消费者跑在 web_app 进程内（web_app._run_index_consumer），与
    _training_worker 共享同一个 threading.Lock —— manifest 的并发写竞态就此消除。
    """
    from utils.indexing_lock import indexing_lock

    with indexing_lock:
        result = _get_service().load_document([str(target)])
        record = (load_manifest().get("documents") or {}).get(doc_id) or {}
        return result, list(record.get("chunk_ids") or [])


async def handle_index_requested(payload: dict) -> None:
    doc_id = str(payload.get("docId") or "")
    file_path = str(payload.get("filePath") or "")
    if not doc_id or not file_path:
        logger.warning(f"[mq] index request missing fields: {payload}")
        return

    target = _resolve_target(file_path)
    if target is None:
        await publish(
            KEY_INDEX_FAILED,
            {"kind": "failed", "docId": doc_id, "error": f"unsafe or missing filePath: {file_path!r}"},
        )
        logger.error(f"[mq] rejected unsafe filePath={file_path!r} for docId={doc_id}")
        return

    try:
        result, chunk_ids = await asyncio.to_thread(_index_and_collect, doc_id, target)
        if not result.get("success"):
            raise RuntimeError(result.get("error_summary") or "Indexing failed")
        await publish(
            KEY_INDEX_SUCCEEDED,
            {"kind": "succeeded", "docId": doc_id, "chunkIds": chunk_ids},
        )
        logger.info(f"[mq] indexed {doc_id} ({len(chunk_ids)} chunks)")
        # P1-5：索引完成后使本进程的 RAG 单例（含 BM25 快照）失效，下次查询重建。
        try:
            from agent.tools.agent_tools import reset_rag_service

            reset_rag_service()
        except Exception as reset_exc:  # 重置失败不阻塞事件回发
            logger.warning(f"[mq] reset_rag_service after index failed: {reset_exc}")
    except Exception as exc:
        await publish(KEY_INDEX_FAILED, {"kind": "failed", "docId": doc_id, "error": str(exc)[:900]})
        logger.error(f"[mq] indexing failed for {doc_id}: {exc}")


def _resolve_target(file_path: str) -> Path | None:
    """把事件里的 filePath 解析为 DATA_DIR 内的真实路径。

    filePath 来自事件负载（由 ftsm-knowledge 转发上传时的文件名），属于外部输入，
    必须做包含性校验：绝对路径或 ../ 逃逸会让索引器读取 DATA_DIR 之外的文件
    （后缀白名单只能限制到 .txt/.pdf/图片，不能阻止越界读取）。
    与 services/document_service._safe_document_path 保持同一套判定。
    """
    raw = Path(str(file_path).replace("\\", "/"))
    if raw.is_absolute() or any(part == ".." for part in raw.parts):
        return None
    root = DATA_DIR.resolve()
    resolved = (root / raw).resolve()
    if not (resolved == root or root in resolved.parents):
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


async def start_consumer() -> None:
    try:
        await consume(
            INDEX_REQUEST_QUEUE,
            KEY_INDEX_REQUESTED,
            handle_index_requested,
            on_ready=_CONSUMER_READY.set,
        )
    finally:
        _CONSUMER_READY.clear()
