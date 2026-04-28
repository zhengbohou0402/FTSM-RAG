from pathlib import Path
from typing import Any

from fastapi import UploadFile


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

    for path in data_dir.iterdir():
        if not path.is_file():
            continue
        ext = path.suffix.lstrip(".").lower()
        if ext not in allowed_extensions:
            continue
        stat = path.stat()
        docs.append({"name": path.name, "size": stat.st_size, "modified": int(stat.st_mtime)})

    docs.sort(key=lambda item: item["modified"], reverse=True)
    return docs


def delete_knowledge_document(
    filename: str,
    data_dir: Path,
    allowed_extensions: set[str],
) -> dict[str, Any]:
    safe_name = Path(filename).name
    file_path = data_dir / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(safe_name)

    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext not in allowed_extensions:
        raise ValueError(f"File type not allowed: .{ext}")

    cleanup: dict[str, Any] = {"manifest_found": False, "deleted_chunks": 0}
    try:
        from rag.vector_store import VectorStoreService

        cleanup = VectorStoreService().delete_document_by_path(file_path)
    except Exception as exc:
        cleanup = {
            "manifest_found": False,
            "deleted_chunks": 0,
            "cleanup_error": str(exc),
        }

    file_path.unlink()
    return {"deleted": safe_name, **cleanup}

