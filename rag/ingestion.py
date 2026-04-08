import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.path_tool import get_abs_path, get_project_root

MANIFEST_PATH = Path(get_abs_path("data/ukm_ftsm/ingestion_manifest.json"))


@dataclass
class SourceDocument:
    doc_id: str
    source_type: str
    source_url: str | None
    title: str
    file_path: str | None
    updated_at: str
    hash: str
    permission_scope: str
    extra: dict[str, Any] = field(default_factory=dict)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_file_doc_id(path: str | Path) -> str:
    root = Path(get_project_root()).resolve()
    resolved = Path(path).resolve()
    try:
        rel = resolved.relative_to(root).as_posix()
    except ValueError:
        rel = resolved.as_posix()
    return f"file:{rel}"


def build_file_source_document(
    path: str | Path,
    *,
    source_type: str = "local_file",
    permission_scope: str = "public",
    source_url: str | None = None,
    title: str | None = None,
) -> SourceDocument:
    file_path = Path(path).resolve()
    stat = file_path.stat()
    return SourceDocument(
        doc_id=stable_file_doc_id(file_path),
        source_type=source_type,
        source_url=source_url,
        title=title or file_path.stem.replace("_", " "),
        file_path=str(file_path),
        updated_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        hash=file_sha256(file_path),
        permission_scope=permission_scope,
        extra={
            "filename": file_path.name,
            "extension": file_path.suffix.lstrip(".").lower(),
            "size_bytes": stat.st_size,
        },
    )


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"documents": {}}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"documents": {}}


def save_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def source_to_manifest_record(source: SourceDocument, chunk_ids: list[str]) -> dict[str, Any]:
    record = asdict(source)
    record["chunk_ids"] = chunk_ids
    record["indexed_at"] = utc_now_iso()
    return record
