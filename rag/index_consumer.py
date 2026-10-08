"""
索引消费者：消费 doc.index.requested，对单个文件执行切块/向量化，并回发结果事件。

- 成功 -> doc.index.succeeded {docId, chunkIds}
- 失败 -> doc.index.failed {docId, error}（chunk_ids 保留在 manifest 供下次清理）
阻塞的向量化放到线程池执行，避免卡住事件循环。
"""

from __future__ import annotations

import asyncio
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


async def handle_index_requested(payload: dict) -> None:
    doc_id = str(payload.get("docId") or "")
    file_path = str(payload.get("filePath") or "")
    if not doc_id or not file_path:
        logger.warning(f"[mq] index request missing fields: {payload}")
        return

    target = str((DATA_DIR / file_path).resolve())
    try:
        service = VectorStoreService()
        result = await asyncio.to_thread(service.load_document, [target])
        if not result.get("success"):
            raise RuntimeError(result.get("error_summary") or "Indexing failed")
        record = (load_manifest().get("documents") or {}).get(doc_id) or {}
        chunk_ids = list(record.get("chunk_ids") or [])
        await publish(
            KEY_INDEX_SUCCEEDED,
            {"kind": "succeeded", "docId": doc_id, "chunkIds": chunk_ids},
        )
        logger.info(f"[mq] indexed {doc_id} ({len(chunk_ids)} chunks)")
    except Exception as exc:
        await publish(KEY_INDEX_FAILED, {"kind": "failed", "docId": doc_id, "error": str(exc)[:900]})
        logger.error(f"[mq] indexing failed for {doc_id}: {exc}")


async def start_consumer() -> None:
    await consume(INDEX_REQUEST_QUEUE, KEY_INDEX_REQUESTED, handle_index_requested)
