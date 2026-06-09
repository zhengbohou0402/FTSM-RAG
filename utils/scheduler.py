"""
Background and manual runners for the FTSM website crawler.

Packaged EXE builds keep the scheduled runner disabled, but manual updates can
still use the lightweight crawler fallback when Playwright/Chromium is absent.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.indexing_lock import indexing_lock
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

try:
    import yaml

    with open(get_abs_path("config/scheduler.yml"), "r", encoding="utf-8") as _f:
        _sched_conf = yaml.safe_load(_f) or {}
except Exception:
    _sched_conf = {}

INTERVAL_HOURS: int = int(_sched_conf.get("interval_hours", 168))
MAX_PAGES: int = int(_sched_conf.get("max_pages", 60))
ENABLED: bool = bool(_sched_conf.get("enabled", True))

_LAST_RUN_FILE = Path(get_abs_path("data/ukm_ftsm/.last_crawl"))
_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()
_status_lock = threading.RLock()
_on_index_updated: Callable[[], None] | None = None

_STATE: dict[str, Any] = {
    "running": False,
    "mode": None,
    "phase": "idle",
    "last_success": None,
    "last_attempt": None,
    "last_error": None,
    "last_output_file": None,
    "pages_crawled": 0,
}


def _runtime_enabled() -> bool:
    import sys

    return ENABLED and not getattr(sys, "frozen", False)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _read_last_run() -> float:
    try:
        return float(_LAST_RUN_FILE.read_text().strip())
    except Exception:
        return 0.0


def _write_last_run(ts: float | None = None) -> float:
    value = ts or time.time()
    _LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LAST_RUN_FILE.write_text(str(value), encoding="utf-8")
    return value


def _iso_from_timestamp(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts).isoformat()


def _begin_run(mode: str) -> bool:
    with _status_lock:
        if _STATE["running"]:
            return False
        _STATE["running"] = True
        _STATE["mode"] = mode
        _STATE["phase"] = "crawling"
        _STATE["last_attempt"] = _now_iso()
        _STATE["last_error"] = None
        return True


def _mark_success(result: Any) -> None:
    last_run = _write_last_run()
    with _status_lock:
        _STATE["running"] = False
        _STATE["mode"] = None
        _STATE["phase"] = "idle"
        _STATE["last_success"] = _iso_from_timestamp(last_run)
        _STATE["last_error"] = None
        _STATE["last_output_file"] = str(getattr(result, "output_file", "") or "")
        _STATE["pages_crawled"] = int(getattr(result, "pages_crawled", 0) or 0)


def _mark_error(exc: Exception | str) -> None:
    with _status_lock:
        _STATE["running"] = False
        _STATE["mode"] = None
        _STATE["phase"] = "idle"
        _STATE["last_error"] = str(exc)


def _mark_indexing(result: Any) -> None:
    with _status_lock:
        _STATE["phase"] = "indexing"
        _STATE["last_output_file"] = str(getattr(result, "output_file", "") or "")
        _STATE["pages_crawled"] = int(getattr(result, "pages_crawled", 0) or 0)


def _run_crawl_and_update(
    max_pages: int | None = None,
    mode: str = "scheduled",
    marked: bool = False,
    reindex: bool = True,
) -> None:
    """Run one scrape cycle, optionally followed by a vector-store update."""
    if not marked and not _begin_run(mode):
        logger.info("[Scheduler] Crawl skipped because another update is already running.")
        return

    crawl_max_pages = max_pages or MAX_PAGES
    logger.info("[Scheduler] Starting %s FTSM crawl. max_pages=%s", mode, crawl_max_pages)
    try:
        from rag.vector_store import VectorStoreService
        from scripts.scrape_ftsm_website import crawl

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(crawl(max_pages=crawl_max_pages, headless=True))
        finally:
            asyncio.set_event_loop(None)
            loop.close()

        if result is None:
            raise RuntimeError("Crawler returned no content; existing knowledge file was preserved.")

        logger.info(
            "[Scheduler] Crawl complete: pages=%s output=%s reindex=%s.",
            getattr(result, "pages_crawled", 0),
            getattr(result, "output_file", ""),
            reindex,
        )

        if reindex:
            _mark_indexing(result)
            target_paths = [getattr(result, "output_file")] if getattr(result, "output_file", None) else None
            with indexing_lock:
                index_result = VectorStoreService().load_document(target_paths=target_paths)
            if not index_result["success"]:
                raise RuntimeError(index_result["error_summary"] or "Indexing crawled content failed")

            if _on_index_updated is not None:
                _on_index_updated()

        _mark_success(result)
        logger.info(
            "[Scheduler] %s crawl%s completed.",
            mode.capitalize(),
            " and index update" if reindex else "",
        )
    except Exception as exc:
        _mark_error(exc)
        logger.error("[Scheduler] %s crawl failed: %s", mode.capitalize(), exc, exc_info=True)


def _seconds_until_next_run(now: float | None = None) -> float:
    interval_secs = max(1, INTERVAL_HOURS * 3600)
    last_run = _read_last_run()
    if not last_run:
        return 0.0
    elapsed = (now or time.time()) - last_run
    return max(0.0, interval_secs - elapsed)


def _scheduler_loop() -> None:
    logger.info("[Scheduler] Started. interval=%sh max_pages=%s", INTERVAL_HOURS, MAX_PAGES)

    while not _stop_event.is_set():
        wait_secs = _seconds_until_next_run()
        if wait_secs > 0:
            logger.info("[Scheduler] Next crawl in %.2fh.", wait_secs / 3600)
            if _stop_event.wait(wait_secs):
                break

        if _stop_event.is_set():
            break

        logger.info("[Scheduler] Triggering scheduled crawl.")
        _run_crawl_and_update(mode="scheduled")

    logger.info("[Scheduler] Stopped.")


def start_scheduler(on_index_updated: Callable[[], None] | None = None) -> None:
    """Start the background scheduler if enabled for this runtime."""
    global _scheduler_thread, _on_index_updated
    import sys

    _on_index_updated = on_index_updated

    if getattr(sys, "frozen", False):
        logger.info("[Scheduler] Packaged mode: scheduled crawler disabled.")
        return
    if not ENABLED:
        logger.info("[Scheduler] Disabled by config.")
        return
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("[Scheduler] Already running.")
        return

    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        name="ftsm-scheduler",
        daemon=True,
    )
    _scheduler_thread.start()
    logger.info("[Scheduler] Background thread started.")


def trigger_manual_crawl(max_pages: int | None = None, reindex: bool = True) -> dict:
    """Start a user-triggered crawl in the background."""
    crawl_max_pages = max_pages or MAX_PAGES
    if not _begin_run("manual"):
        return {
            "started": False,
            "message": "Knowledge update is already running.",
            "max_pages": crawl_max_pages,
        }

    thread = threading.Thread(
        target=_run_crawl_and_update,
        kwargs={
            "max_pages": crawl_max_pages,
            "mode": "manual",
            "marked": True,
            "reindex": reindex,
        },
        name="ftsm-manual-crawler",
        daemon=True,
    )
    thread.start()
    return {
        "started": True,
        "message": "Website crawl and index update started." if reindex else "Website crawl started.",
        "max_pages": crawl_max_pages,
        "reindex": reindex,
    }


def stop_scheduler() -> None:
    """Signal the scheduler thread to stop and wait briefly for it."""
    _stop_event.set()
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=5)
    logger.info("[Scheduler] Stop requested.")


def get_status() -> dict:
    """Return scheduler status. Existing fields are kept for frontend compatibility."""
    last_run = _read_last_run()
    interval_secs = max(1, INTERVAL_HOURS * 3600)
    next_run_at = last_run + interval_secs if last_run else time.time()

    with _status_lock:
        state = dict(_STATE)

    if state["last_success"] is None:
        state["last_success"] = _iso_from_timestamp(last_run)

    return {
        "enabled": _runtime_enabled(),
        "manual_available": True,
        "interval_hours": INTERVAL_HOURS,
        "max_pages": MAX_PAGES,
        "last_run": _iso_from_timestamp(last_run),
        "next_run": _iso_from_timestamp(next_run_at),
        "thread_alive": _scheduler_thread.is_alive() if _scheduler_thread else False,
        **state,
    }
