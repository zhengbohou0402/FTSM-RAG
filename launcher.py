"""
单机启动入口：打包成 exe 后双击运行，自动在本机启动 Web 服务并打开浏览器。
"""
import os
import sys
import time
import threading
import webbrowser
from pathlib import Path

import uvicorn


def open_browser():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    # 打包后把工作目录切到 exe 所在目录，确保数据库、配置都在正确位置
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).parent)

    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "web_app:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
