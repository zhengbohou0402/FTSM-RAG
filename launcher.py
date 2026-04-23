"""
桌面版启动入口。双击 FTSM-RAG.exe 会弹出一个原生窗口（Windows 使用 Edge WebView2），
用户无需手动打开浏览器。

首次运行：
- 自动在 exe 同级目录创建 chroma_db_ftsm / data / config / .env 等资源
- 若 DASHSCOPE_API_KEY 未配置，窗口会自动进入 /settings 引导用户填入千问 API Key

可通过环境变量 FTSM_BROWSER_MODE=1 强制走浏览器模式（跳过 pywebview）。
"""
import io
import os
import shutil
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path


# PyInstaller windowed mode (console=False) sets sys.stdout / sys.stderr to None.
# Third-party libs (uvicorn's logging, pywebview, etc.) call stdout.isatty() and crash.
# Provide a harmless writable stream early, before importing anything that logs.
class _NullStream(io.TextIOBase):
    def isatty(self) -> bool:  # type: ignore[override]
        return False

    def writable(self) -> bool:  # type: ignore[override]
        return True

    def write(self, s):  # type: ignore[override]
        return len(s) if isinstance(s, str) else 0

    def flush(self) -> None:  # type: ignore[override]
        return None


if sys.stdout is None:
    sys.stdout = _NullStream()
if sys.stderr is None:
    sys.stderr = _NullStream()


HOST = "127.0.0.1"
LOG_FILE: Path | None = None


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        if LOG_FILE is not None:
            with LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, file=sys.stderr)
    except Exception:
        pass

WINDOW_TITLE = "FTSM-RAG Assistant"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 820
WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 600
SERVER_START_TIMEOUT = 60.0


# ── 首次启动：把 bundle 里的只读资源拷贝到 exe 同级目录 ──

def _ensure_writable_resource(meipass: Path, target: Path, name: str) -> None:
    if target.exists():
        return
    src = meipass / name
    if not src.exists():
        return
    try:
        if src.is_dir():
            shutil.copytree(src, target)
        else:
            shutil.copy2(src, target)
    except Exception as exc:
        print(f"[launcher] Failed to copy {name}: {exc}", file=sys.stderr)


def _prepare_runtime_dir() -> None:
    global LOG_FILE
    if not getattr(sys, "frozen", False):
        LOG_FILE = Path(__file__).parent / "logs" / "launcher.log"
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        return
    exe_dir = Path(sys.executable).parent
    os.chdir(exe_dir)
    LOG_FILE = exe_dir / "logs" / "launcher.log"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
    _ensure_writable_resource(meipass, exe_dir / "chroma_db_ftsm", "chroma_db_ftsm")
    _ensure_writable_resource(meipass, exe_dir / "data", "data")
    _ensure_writable_resource(meipass, exe_dir / "config", "config")
    _ensure_writable_resource(meipass, exe_dir / ".env.example", ".env.example")


def _resolve_window_icon() -> Path | None:
    """
    优先用项目根目录的 app.ico（多尺寸高质量）；
    打包后从 _MEIPASS bundle 中查找；
    兜底用 favicon.ico。
    """
    if getattr(sys, "frozen", False):
        dirs = [Path(sys.executable).parent, Path(getattr(sys, "_MEIPASS", ""))]
    else:
        dirs = [Path(__file__).parent]

    for d in dirs:
        for name in ("app.ico", "web/static/assets/favicon.ico"):
            p = d / name
            if p.exists():
                return p
    return None


# ── 后台 uvicorn ──

def _find_free_port() -> int:
    """自动挑一个空闲端口，避免 8000 被占用导致启动失败。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.3)
    return False


def _run_server(port: int) -> None:
    try:
        _log(f"importing web_app; port={port}")
        import uvicorn
        from web_app import app
        _log("web_app imported; starting uvicorn")
        uvicorn.run(
            app,
            host=HOST,
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None,  # avoid ColourizedFormatter.isatty() crash in windowed mode
        )
    except Exception:
        _log("server thread crashed:\n" + traceback.format_exc())


# ── 窗口 ──

def _open_in_browser(url: str) -> None:
    """pywebview 不可用时的降级方案：直接拉起默认浏览器。"""
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass
    # 前台阻塞，防止主进程退出导致 daemon 后台线程被杀
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def _open_in_webview(url: str) -> None:
    import webview  # pywebview
    icon_path = _resolve_window_icon()
    _log(f"window icon: {icon_path}")

    # pywebview 6.x 通过 _state["icon"] 设置窗口/任务栏图标
    if icon_path is not None:
        try:
            webview._state["icon"] = str(icon_path)
        except Exception:
            _log("failed to set webview icon via _state")

    window = webview.create_window(
        WINDOW_TITLE,
        url,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT),
        confirm_close=False,
    )
    # gui=None 让 pywebview 自动选择（Windows 优先 Edge WebView2）
    webview.start(gui=None, debug=False)
    # webview.start() 是阻塞调用；窗口关闭后代码继续往下走
    _ = window  # keep reference


# ── 主流程 ──

def main() -> None:
    _prepare_runtime_dir()
    _log(f"=== launcher start (frozen={getattr(sys, 'frozen', False)}) ===")

    port = _find_free_port()
    url = f"http://{HOST}:{port}"
    _log(f"chose url={url}")

    server_thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    server_thread.start()

    if not _wait_for_server(url, SERVER_START_TIMEOUT):
        _log("server failed to start within timeout")
        # 把错误显示给用户；打包模式下 console=False 看不到 stderr
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None,
                "Server failed to start within 60 seconds.\nCheck the logs folder for details.",
                WINDOW_TITLE,
                0x10,  # MB_ICONERROR
            )
        except Exception:
            print("[launcher] Server did not start in time.", file=sys.stderr)
        sys.exit(1)

    _log("server up; about to open window")
    force_browser = os.getenv("FTSM_BROWSER_MODE", "").strip() == "1"
    if force_browser:
        _log("FTSM_BROWSER_MODE=1; opening in browser")
        _open_in_browser(url)
        return

    try:
        _open_in_webview(url)
        _log("webview window closed; exiting")
    except ImportError as exc:
        _log(f"pywebview not available: {exc}; falling back to browser")
        _open_in_browser(url)
    except Exception:
        _log("webview failed:\n" + traceback.format_exc())
        _open_in_browser(url)


if __name__ == "__main__":
    main()
