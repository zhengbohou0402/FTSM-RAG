"""
Check text files for decoding problems before they are indexed into Chroma.

Typical usage:
    python scripts/encoding_health.py
    python scripts/encoding_health.py --paths data/ukm_ftsm scripts utils rag
    python scripts/encoding_health.py --json results/encoding_health.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.text_encoding import read_text_safely  # noqa: E402

DEFAULT_PATHS = [
    ROOT / "data" / "ukm_ftsm",
    ROOT / "config",
    ROOT / "scripts",
    ROOT / "utils",
    ROOT / "rag",
]

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".py",
    ".json",
    ".yml",
    ".yaml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
}

IGNORED_RELATIVE_FILES = {
    "utils/text_encoding.py",
}


def iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            files.append(path)
            continue
        if path.is_dir():
            files.extend(
                p for p in path.rglob("*")
                if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES
            )
    return sorted(set(files))


def scan_file(path: Path) -> dict[str, Any]:
    rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    if rel in IGNORED_RELATIVE_FILES:
        return {
            "path": rel,
            "encoding": "utf-8",
            "mojibake_score": 0,
            "chars": path.stat().st_size,
            "status": "ignored",
        }

    decoded = read_text_safely(path)
    return {
        "path": rel,
        "encoding": decoded.encoding,
        "mojibake_score": decoded.mojibake_score,
        "chars": len(decoded.text),
        "status": "warning" if decoded.mojibake_score else "ok",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check project text encoding health.")
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Files or directories to scan. Defaults to data/config/scripts/utils/rag.",
    )
    parser.add_argument("--json", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit with status 1 if any mojibake warning is found.",
    )
    args = parser.parse_args()

    paths = [Path(p).resolve() for p in args.paths] if args.paths else DEFAULT_PATHS
    files = iter_files(paths)
    results = [scan_file(path) for path in files]
    warnings = [r for r in results if r["status"] == "warning"]

    print("| Status | Encoding | Score | File |")
    print("| --- | --- | ---: | --- |")
    for row in results:
        if row["status"] != "warning":
            continue
        print(f"| warning | {row['encoding']} | {row['mojibake_score']} | {row['path']} |")
    if not warnings:
        print("| ok | - | 0 | No mojibake markers detected |")

    print()
    print(f"Scanned files : {len(results)}")
    print(f"Warnings      : {len(warnings)}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {"scanned_files": len(results), "warnings": warnings, "results": results},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {args.json}")

    return 1 if args.fail_on_warning and warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
