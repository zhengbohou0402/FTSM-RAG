# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 文件
打包命令：pyinstaller ftsm_rag.spec
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 前端模板和静态文件
        (str(ROOT / "web"), "web"),
        # 配置文件
        (str(ROOT / "config"), "config"),
        # 提示词
        (str(ROOT / "prompts"), "prompts"),
        # Chroma 向量库
        (str(ROOT / "chroma_db_ftsm"), "chroma_db_ftsm"),
        # 知识库数据
        (str(ROOT / "data"), "data"),
    ],
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
        "pymysql",          # 保留，部分依赖链可能引用
        "sqlite3",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # 保留控制台窗口，方便看日志；改 False 则无命令行窗口
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
