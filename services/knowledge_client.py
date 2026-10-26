"""Client for the Java ftsm-knowledge service — authoritative index-state write-backs.

Why this module exists: the MQ path (`doc.index.succeeded`) is the *only* way
ftsm-knowledge learns that a document finished indexing. When RabbitMQ is
unreachable the rag service degrades to the in-process training thread
(`web_app._training_worker`), which never publishes that event — so the `doc`
rows stick at INDEXING forever and `/api/knowledge/stats` reports a growing
`indexing_count` that never resolves.

`sync_training_result` closes that loop: after a local training run it pushes the
authoritative manifest state (docId -> chunk count) so the state machine
reaches READY regardless of whether the MQ link is up.

All calls are best-effort: failures are logged, never raised.
"""
from __future__ import annotations

import os
from typing import Any

import requests

from utils.logger_handler import logger

_TIMEOUT = 5
_MAX_DOCS_PER_CALL = 200

_warned = False


def _base_url() -> str:
    return os.environ.get("FTSM_KNOWLEDGE_URL", "http://127.0.0.1:8103").rstrip("/")


def _warn_once(message: str) -> None:
    global _warned
    if _warned:
        return
    _warned = True
    logger.warning(message)


def collect_manifest_states() -> list[dict[str, Any]]:
    """从本地 manifest 汇总 (docId, chunkCount, name, title, sourceType, size, fileHash)——索引的真实结果。"""
    from rag.ingestion import load_manifest

    manifest = load_manifest()
    rows: list[dict[str, Any]] = []
    for doc_id, record in (manifest.get("documents") or {}).items():
        if not str(doc_id).startswith("file:"):
            continue  # 只回写文件类文档；抓取类由各自的发布路径负责
        extra = record.get("extra") or {}
        # doc_id 形如 "file:data/ukm_ftsm/uploads/foo.txt"，而 extra.filename 只是
        # "foo.txt"。Java 端 KnowledgeController 靠 doc.getName().startsWith("uploads/")
        # 区分用户上传与官方资料，因此优先取相对 data/ukm_ftsm/ 的子路径作为 name，
        # 避免冷启动回写时丢失 "uploads/" 前缀导致误判为 official。
        relative = ""
        if str(doc_id).startswith("file:data/ukm_ftsm/"):
            relative = str(doc_id)[len("file:data/ukm_ftsm/"):].strip()
        name = relative or extra.get("filename") or str(doc_id).split(":")[-1]
        rows.append(
            {
                "docId": doc_id,
                "chunkCount": len(record.get("chunk_ids") or []),
                "name": name,
                "title": record.get("title") or name,
                "sourceType": record.get("source_type") or "official",
                "size": extra.get("size_bytes") or 0,
                "fileHash": record.get("hash") or "",
            }
        )
    return rows


def sync_training_result(rows: list[dict[str, Any]] | None = None) -> int:
    """把本地索引结果回写为 READY。返回成功上报的文档数（失败返回 0）。"""
    rows = collect_manifest_states() if rows is None else rows
    if not rows:
        return 0

    updated = 0
    base = _base_url()
    for start in range(0, len(rows), _MAX_DOCS_PER_CALL):
        batch = rows[start : start + _MAX_DOCS_PER_CALL]
        try:
            res = requests.post(
                f"{base}/internal/docs/ready",
                json={"docs": batch},
                timeout=_TIMEOUT,
            )
            if res.status_code != 200:
                _warn_once(
                    "[knowledge_client] ready 回写失败（索引状态将滞留在 INDEXING）："
                    f"{res.status_code} {res.text[:200]}"
                )
                continue
            updated += len((res.json() or {}).get("updated") or [])
        except Exception as exc:
            _warn_once(
                f"[knowledge_client] ready 回写异常（索引状态将滞留在 INDEXING）：{exc}"
            )
    if updated:
        logger.info(f"[knowledge_client] synced {updated} document state(s) to READY.")
    return updated
