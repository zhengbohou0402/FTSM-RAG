import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.path_tool import get_abs_path, get_project_root

MANIFEST_PATH = Path(get_abs_path("data/ukm_ftsm/ingestion_manifest.json"))

SOURCE_TRUST_PROFILES = {
    "official": {
        "label": "Official material",
        "note": "Curated from official UKM/FTSM material or structured academic documents.",
        "priority": 1,
    },
    "community_guide": {
        "label": "Student guide",
        "note": "Practical guide or student-facing notes; useful but should be verified for formal decisions.",
        "priority": 3,
    },
    "scraped_website": {
        "label": "Scraped official website",
        "note": "Captured from the public FTSM website by the scheduled crawler.",
        "priority": 2,
    },
    "generated_summary": {
        "label": "Generated summary",
        "note": "Generated or consolidated index/summary derived from other project material.",
        "priority": 4,
    },
}

GENERATED_SUMMARY_FILES = {
    "advisors_expertise_index.txt",
    "student_portal_search_index.txt",
    "student_portal_system_cards.txt",
    "background_and_positioning.txt",
}

COMMUNITY_GUIDE_PATTERNS = (
    "student_portal",
    "registration_renewal",
    "campus_bus",
    "chinese_student",
    "china_student",
    "international_student",
)

OFFICIAL_PATTERNS = (
    "academic_calendar",
    "advisors_and_academic_staff",
    "coursework_timetable",
    "facilities_and_services",
    "graduation_certification",
    "industrial_training",
    "malaysian_public_holidays",
    "master_coursemode",
    "programmes_and_admissions",
    "semester2_exam_schedule",
)


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


def classify_source(path: str | Path) -> dict[str, Any]:
    filename = Path(path).name.lower()
    stem = Path(path).stem.lower()

    if filename == "ftsm_official_website.txt":
        source_type = "scraped_website"
    elif filename in GENERATED_SUMMARY_FILES or stem.endswith("_index"):
        source_type = "generated_summary"
    elif any(pattern in stem for pattern in COMMUNITY_GUIDE_PATTERNS):
        source_type = "community_guide"
    elif any(pattern in stem for pattern in OFFICIAL_PATTERNS):
        source_type = "official"
    else:
        source_type = "community_guide"

    profile = SOURCE_TRUST_PROFILES[source_type]
    return {
        "source_type": source_type,
        "source_trust_label": profile["label"],
        "source_trust_note": profile["note"],
        "source_priority": profile["priority"],
    }


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
    inferred = classify_source(file_path)
    if source_type == "local_file":
        source_type = inferred["source_type"]
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
            "source_trust_label": inferred["source_trust_label"],
            "source_trust_note": inferred["source_trust_note"],
            "source_priority": inferred["source_priority"],
        },
    )


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"documents": {}, "index": default_index_state()}
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest.setdefault("documents", {})
        manifest.setdefault("index", default_index_state())
        return manifest
    except Exception:
        return {"documents": {}, "index": default_index_state()}


def default_index_state() -> dict[str, Any]:
    return {
        "version": 0,
        "updated_at": None,
        "document_count": 0,
        "total_chunks": 0,
        "source_type_counts": {},
        "last_error": None,
        "pipeline_fingerprint": None,
    }


def compute_index_state(
    manifest: dict[str, Any],
    *,
    previous_state: dict[str, Any] | None = None,
    last_error: str | None = None,
    bump_version: bool = False,
    pipeline_fingerprint: str | None = None,
) -> dict[str, Any]:
    docs = manifest.get("documents", {})
    total_chunks = sum(len(record.get("chunk_ids", [])) for record in docs.values())
    source_type_counts: dict[str, int] = {}
    last_indexed: str | None = None
    for record in docs.values():
        source_type = str(record.get("source_type") or "unknown")
        if source_type in {"", "local_file", "unknown"}:
            extra = record.get("extra") or {}
            filename = extra.get("filename") or record.get("file_path") or record.get("title") or ""
            inferred = classify_source(str(filename))
            source_type = inferred["source_type"]
            record["source_type"] = source_type
            extra.setdefault("source_trust_label", inferred["source_trust_label"])
            extra.setdefault("source_trust_note", inferred["source_trust_note"])
            extra.setdefault("source_priority", inferred["source_priority"])
            record["extra"] = extra
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        indexed_at = record.get("indexed_at")
        if indexed_at and (last_indexed is None or indexed_at > last_indexed):
            last_indexed = indexed_at

    previous = previous_state or manifest.get("index") or default_index_state()
    previous_version = int(previous.get("version") or 0)
    version = previous_version + 1 if bump_version else previous_version
    return {
        "version": version,
        "updated_at": utc_now_iso(),
        "last_indexed": last_indexed,
        "document_count": len(docs),
        "total_chunks": total_chunks,
        "source_type_counts": source_type_counts,
        "last_error": last_error,
        "pipeline_fingerprint": (
            pipeline_fingerprint
            if pipeline_fingerprint is not None
            else previous.get("pipeline_fingerprint")
        ),
    }


def update_manifest_index_state(
    manifest: dict[str, Any],
    *,
    last_error: str | None = None,
    bump_version: bool = False,
    pipeline_fingerprint: str | None = None,
) -> None:
    previous_state = manifest.get("index") or default_index_state()
    manifest["index"] = compute_index_state(
        manifest,
        previous_state=previous_state,
        last_error=last_error,
        bump_version=bump_version,
        pipeline_fingerprint=pipeline_fingerprint,
    )


def save_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest.setdefault("documents", {})
    manifest.setdefault("index", compute_index_state(manifest))
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def source_to_manifest_record(
    source: SourceDocument,
    chunk_ids: list[str],
    *,
    index_fingerprint: str = "",
    index_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = asdict(source)
    record["chunk_ids"] = chunk_ids
    record["index_fingerprint"] = index_fingerprint
    record["index_config"] = index_config or {}
    record["indexed_at"] = utc_now_iso()
    return record
