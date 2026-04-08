"""
定时任务调度器
--------------
功能：
  - 周期性自动爬取 FTSM 官网，将最新内容增量写入 Chroma 向量库
  - 随 FastAPI 应用启动/关闭，后台线程运行，不阻塞主服务

配置（通过 config/scheduler.yml 或默认值）：
  interval_hours: 168   # 爬取间隔，单位小时，默认 168h = 1 周
  max_pages: 60         # 每次最多爬取页面数
  enabled: true         # 是否启用定时任务
"""

import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path

from utils.logger_handler import logger

# 尝试读取配置，没有则用默认值
try:
    import yaml
    from utils.path_tool import get_abs_path
    with open(get_abs_path("config/scheduler.yml"), "r", encoding="utf-8") as _f:
        _sched_conf = yaml.safe_load(_f) or {}
except Exception:
    _sched_conf = {}

INTERVAL_HOURS: int = int(_sched_conf.get("interval_hours", 168))  # 默认 1 周
MAX_PAGES: int = int(_sched_conf.get("max_pages", 60))
ENABLED: bool = bool(_sched_conf.get("enabled", True))

# 记录上次更新时间（持久化到文件）
_LAST_RUN_FILE = Path(__file__).resolve().parents[1] / "data" / "ukm_ftsm" / ".last_crawl"


def _read_last_run() -> float:
    try:
        return float(_LAST_RUN_FILE.read_text().strip())
    except Exception:
        return 0.0


def _write_last_run() -> None:
    _LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LAST_RUN_FILE.write_text(str(time.time()))


def _run_crawl_and_update() -> None:
    """执行一次完整的爬取 + 增量训练"""
    logger.info("[Scheduler] 开始定时爬取任务...")
    try:
        # 动态导入，避免循环依赖
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from scripts.scrape_ftsm_website import crawl
        from rag.vector_store import VectorStoreService

        # 爬取（同步调用异步函数）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        txt_file = loop.run_until_complete(crawl(max_pages=MAX_PAGES, headless=True))
        loop.close()

        if not txt_file:
            logger.warning("[Scheduler] 爬取结果为空，跳过训练")
            return

        logger.info(f"[Scheduler] 爬取完成: {txt_file}，开始增量训练...")

        # 增量训练（MD5 去重，只新增文件才会被写入）
        vs = VectorStoreService()
        vs.load_document()

        _write_last_run()
        logger.info(f"[Scheduler] 定时任务完成 @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        logger.error(f"[Scheduler] 定时任务失败: {e}", exc_info=True)


def _scheduler_loop() -> None:
    """后台线程循环"""
    interval_secs = INTERVAL_HOURS * 3600
    logger.info(f"[Scheduler] 已启动，间隔 {INTERVAL_HOURS}h，max_pages={MAX_PAGES}")

    # 首次启动时检查是否需要立即爬取
    last_run = _read_last_run()
    elapsed = time.time() - last_run
    if elapsed >= interval_secs:
        logger.info(f"[Scheduler] 距上次爬取已过 {elapsed/3600:.1f}h，立即执行一次")
        _run_crawl_and_update()
    else:
        next_run_in = interval_secs - elapsed
        logger.info(f"[Scheduler] 距上次爬取 {elapsed/3600:.1f}h，下次执行在 {next_run_in/3600:.1f}h 后")

    while True:
        time.sleep(interval_secs)
        logger.info("[Scheduler] 触发定时爬取...")
        _run_crawl_and_update()


# 全局后台线程（daemon=True，主进程退出时自动结束）
_scheduler_thread: threading.Thread | None = None


def start_scheduler() -> None:
    """随应用启动，启动后台定时线程"""
    global _scheduler_thread
    if not ENABLED:
        logger.info("[Scheduler] 定时任务已禁用（enabled=false）")
        return
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("[Scheduler] 定时线程已在运行，跳过重复启动")
        return
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        name="ftsm-scheduler",
        daemon=True,
    )
    _scheduler_thread.start()
    logger.info("[Scheduler] 后台定时线程已启动")


def stop_scheduler() -> None:
    """应用关闭时调用（daemon 线程会自动结束，此处仅打印日志）"""
    logger.info("[Scheduler] 定时任务已随应用停止")


def get_status() -> dict:
    """返回调度器状态"""
    last_run = _read_last_run()
    interval_secs = INTERVAL_HOURS * 3600
    next_run_at = last_run + interval_secs if last_run else None
    return {
        "enabled": ENABLED,
        "interval_hours": INTERVAL_HOURS,
        "max_pages": MAX_PAGES,
        "last_run": datetime.fromtimestamp(last_run).isoformat() if last_run else None,
        "next_run": datetime.fromtimestamp(next_run_at).isoformat() if next_run_at else None,
        "thread_alive": _scheduler_thread.is_alive() if _scheduler_thread else False,
    }
