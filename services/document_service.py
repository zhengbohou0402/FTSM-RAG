from pathlib import Path
from typing import Any

from fastapi import UploadFile

from rag.ingestion import file_sha256, load_manifest, stable_file_doc_id


async def save_uploads(
    files: list[UploadFile],
    data_dir: Path,
    allowed_extensions: set[str],
    max_upload_size_mb: int,
) -> tuple[list[str], list[dict[str, str]]]:
    data_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    errors: list[dict[str, str]] = []
    max_bytes = max_upload_size_mb * 1024 * 1024

    # P0-2 安全修复：用户上传一律隔离到 uploads/ 子目录，且禁止覆盖已有文件，
    # 官方语料（DATA_DIR 根级）从此不可能被同名上传覆盖。
    uploads_dir = data_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        fname = Path(file.filename or "").name
        if not fname:
            errors.append({"name": file.filename or "(unknown)", "error": "Invalid filename"})
            continue

        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in allowed_extensions:
            errors.append({"name": fname, "error": f"Unsupported file type: .{ext}"})
            continue

        rel_name = f"uploads/{fname}"
        target = uploads_dir / fname
        try:
            content = await file.read()
            if len(content) > max_bytes:
                errors.append({"name": rel_name, "error": f"File exceeds {max_upload_size_mb} MB limit"})
                continue
            if target.exists():
                errors.append({"name": rel_name, "error": "File already exists — rename and retry"})
                continue
            target.write_bytes(content)
            saved.append(rel_name)
        except Exception as exc:
            errors.append({"name": rel_name, "error": str(exc)})
        finally:
            await file.close()

    return saved, errors


def list_knowledge_documents(
    data_dir: Path,
    allowed_extensions: set[str],
) -> list[dict[str, Any]]:
    data_dir.mkdir(parents=True, exist_ok=True)
    docs: list[dict[str, Any]] = []
    manifest = load_manifest()
    indexed_docs = manifest.get("documents", {})

    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lstrip(".").lower()
        if ext not in allowed_extensions:
            continue
        stat = path.stat()
        rel_name = path.relative_to(data_dir).as_posix()
        doc_id = stable_file_doc_id(path)
        record = indexed_docs.get(doc_id)
        covered_by = None
        if not record and ext == "pdf":
            transcript_path = path.with_suffix(".txt")
            if transcript_path.exists():
                transcript_id = stable_file_doc_id(transcript_path)
                if transcript_id in indexed_docs:
                    covered_by = transcript_path.relative_to(data_dir).as_posix()
        # P1-7：按 (mtime_ns, size) 缓存哈希，文件没变就不重算全量 SHA-256
        current_hash = _cached_file_sha256(path)
        indexed = bool(record)
        stale = bool(record and record.get("hash") != current_hash)
        extra = (record or {}).get("extra") or {}
        docs.append(
            {
                "name": rel_name,
                "source": "upload" if rel_name.startswith("uploads/") else "official",
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
                "indexed": indexed and not stale,
                "stale": stale,
                "chunks": len((record or {}).get("chunk_ids", [])),
                "source_type": (record or {}).get("source_type"),
                "source_trust_label": extra.get("source_trust_label"),
                "indexed_at": (record or {}).get("indexed_at"),
                "covered_by": covered_by,
                "index_note": (
                    f"Covered by indexed transcript {covered_by}"
                    if covered_by
                    else None
                ),
            }
        )

    docs.sort(
        key=lambda item: (
            not item["indexed"] and not item.get("covered_by"),
            item["modified"],
        ),
        reverse=True,
    )
    return docs


# P1-7：文件哈希缓存 —— 键为绝对路径，值为 (mtime_ns, size, sha256)。
# 知识库列表/统计接口每次轮询都会扫描全部文件；文件未变时直接复用哈希，
# 避免每次请求都对所有 PDF/图片做全量读取。
_HASH_CACHE: dict[str, tuple[int, int, str]] = {}


def _cached_file_sha256(path: Path) -> str:
    st = path.stat()
    key = str(path)
    cached = _HASH_CACHE.get(key)
    if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return cached[2]
    digest = file_sha256(path)
    _HASH_CACHE[key] = (st.st_mtime_ns, st.st_size, digest)
    return digest


def _safe_document_path(filename: str, data_dir: Path) -> Path:
    rel = Path(filename.replace("\\", "/"))
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise ValueError("Invalid document path")
    resolved = (data_dir / rel).resolve()
    root = data_dir.resolve()
    if not (resolved == root or root in resolved.parents):
        raise ValueError("Invalid document path")
    return resolved


def delete_knowledge_document(
    filename: str,
    data_dir: Path,
    allowed_extensions: set[str],
) -> dict[str, Any]:
    safe_name = filename.replace("\\", "/").strip("/")
    file_path = _safe_document_path(safe_name, data_dir)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(safe_name)

    # P0-2 安全修复：只允许删除用户上传（uploads/ 子目录）的文件。
    # 官方语料是知识库基础，任何会话身份都不得物理删除（管理员可走文件系统）。
    uploads_root = (data_dir / "uploads").resolve()
    if uploads_root not in file_path.resolve().parents:
        raise PermissionError(
            f"Only uploaded documents (uploads/) can be deleted: {safe_name}"
        )

    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext not in allowed_extensions:
        raise ValueError(f"File type not allowed: .{ext}")

    cleanup: dict[str, Any] = {"manifest_found": False, "deleted_chunks": 0}
    # 第二轮复审 P1：向量清理 + manifest 变更 + 文件删除整体持有 indexing_lock，
    # 防止与 MQ 消费者/调度器的索引任务并发时读到半删除状态。
    from utils.indexing_lock import indexing_lock

    with indexing_lock:
        try:
            from rag.vector_store import VectorStoreService

            cleanup = VectorStoreService().delete_document_by_path(file_path)
            if cleanup.get("vector_delete_ok") is False:
                raise RuntimeError("Vector index cleanup failed")
        except Exception as exc:
            raise RuntimeError(
                f"Document was not deleted because index cleanup failed: {exc}"
            ) from exc

        file_path.unlink()

    # 哈希缓存里该文件的条目已失效，直接弹出（key 可能是 resolve 前或后的路径，两个都清）
    _HASH_CACHE.pop(str(file_path), None)
    _HASH_CACHE.pop(str(data_dir / safe_name), None)
    return {"deleted": safe_name, **cleanup}
