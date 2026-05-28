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

    for file in files:
        fname = Path(file.filename or "").name
        if not fname:
            errors.append({"name": file.filename or "(unknown)", "error": "Invalid filename"})
            continue

        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in allowed_extensions:
            errors.append({"name": fname, "error": f"Unsupported file type: .{ext}"})
            continue

        try:
            content = await file.read()
            if len(content) > max_bytes:
                errors.append({"name": fname, "error": f"File exceeds {max_upload_size_mb} MB limit"})
                continue
            (data_dir / fname).write_bytes(content)
            saved.append(fname)
        except Exception as exc:
            errors.append({"name": fname, "error": str(exc)})
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
        current_hash = file_sha256(path)
        indexed = bool(record)
        stale = bool(record and record.get("hash") != current_hash)
        extra = (record or {}).get("extra") or {}
        docs.append(
            {
                "name": rel_name,
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
                "indexed": indexed and not stale,
                "stale": stale,
                "chunks": len((record or {}).get("chunk_ids", [])),
                "source_type": (record or {}).get("source_type"),
                "source_trust_label": extra.get("source_trust_label"),
                "indexed_at": (record or {}).get("indexed_at"),
            }
        )

    docs.sort(key=lambda item: (not item["indexed"], item["modified"]), reverse=True)
    return docs


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

    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext not in allowed_extensions:
        raise ValueError(f"File type not allowed: .{ext}")

    cleanup: dict[str, Any] = {"manifest_found": False, "deleted_chunks": 0}
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
    return {"deleted": safe_name, **cleanup}
