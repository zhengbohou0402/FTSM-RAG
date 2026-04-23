# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec (onedir mode).

打包命令：
    pyinstaller ftsm_rag.spec

产物：
    dist/FTSM-RAG/FTSM-RAG.exe  + dist/FTSM-RAG/_internal/
整个 dist/FTSM-RAG 文件夹可以直接压缩分发给用户。
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)

# 含 C 扩展的大包用 collect_all 全量收集，避免 hidden import 遗漏
numpy_datas,  numpy_bins,  numpy_hiddens  = collect_all("numpy")
chroma_datas, chroma_bins, chroma_hiddens = collect_all("chromadb")
onnx_datas,   onnx_bins,   onnx_hiddens   = collect_all("onnxruntime")
# pywebview 会在 runtime 选择合适的 GUI 后端（Windows=EdgeChromium），需要带上相关子模块
webview_datas, webview_bins, webview_hiddens = collect_all("webview")

datas = [
    (str(ROOT / "web"),             "web"),
    (str(ROOT / "config"),          "config"),
    (str(ROOT / "prompts"),         "prompts"),
    (str(ROOT / "chroma_db_ftsm"),  "chroma_db_ftsm"),
    (str(ROOT / "data"),            "data"),
    (str(ROOT / ".env.example"),    "."),
    (str(ROOT / "app.ico"),         "."),   # window icon
] + numpy_datas + chroma_datas + onnx_datas + webview_datas

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=numpy_bins + chroma_bins + onnx_bins + webview_bins,
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.main",
        "fastapi",
        "starlette",
        "anyio",
        "anyio.lowlevel",
        "chromadb",
        "langchain",
        "langchain_community",
        "langchain_chroma",
        "dashscope",
        "opencc",
        "numpy._core._exceptions",
        "numpy._core._multiarray_umath",
        "numpy._core.multiarray",
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr_loader",
        "pythonnet",
    ] + numpy_hiddens + chroma_hiddens + onnx_hiddens + webview_hiddens,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pymysql",       # 单机版改用 JSON 存储，不需要 MySQL
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "playwright",    # 爬虫在运行期不需要；如需爬取请用源码运行
        "selenium",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FTSM-RAG",
    icon=str(ROOT / "app.ico"),     # exe 文件图标（多尺寸 ICO）
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 桌面模式不显示黑色控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FTSM-RAG",
)
