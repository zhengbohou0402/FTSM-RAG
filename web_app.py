import hashlib
import hmac
import os
import secrets
import shutil
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# ── 打包路径处理 ──
# 打包后 sys.frozen=True；_MEIPASS 是 PyInstaller 临时解压目录，只读
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent           # 可写（exe 所在目录）
    _BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))  # 只读资源根
else:
    BASE_DIR = Path(__file__).resolve().parent
    _BUNDLE_DIR = BASE_DIR

# 首次启动：若本地没有 .env，从 bundle 里的 .env.example 复制一份
_env_path = BASE_DIR / ".env"
if not _env_path.exists():
    example = _BUNDLE_DIR / ".env.example"
    if example.exists():
        shutil.copy2(example, _env_path)

load_dotenv(_env_path)

# ── 必须在 load_dotenv 之后再 import agent / 模型工厂（它们读环境变量）──
from agent.react_agent import ReactAgent  # noqa: E402
from services.chat_service import stream_chat_answer  # noqa: E402
from services.document_service import (  # noqa: E402
    delete_knowledge_document,
    list_knowledge_documents,
    save_uploads,
)
from services.settings_service import (  # noqa: E402
    apply_runtime_env,
    parse_env_file,
    write_env_file,
)
from utils.config_handler import chroma_conf  # noqa: E402
from utils.conversation_store import ConversationStore  # noqa: E402
from utils.path_tool import get_abs_path  # noqa: E402
from utils.scheduler import get_status as scheduler_status  # noqa: E402
from utils.scheduler import start_scheduler, stop_scheduler  # noqa: E402
from utils.semantic_cache import SemanticCache  # noqa: E402

WEB_DIR = _BUNDLE_DIR / "web"

# ── 知识库 ──
DATA_DIR = Path(get_abs_path(chroma_conf["data_path"]))
ALLOWED_UPLOAD_EXTENSIONS: set[str] = set(
    chroma_conf.get(
        "allow_knowledge_file_type", ["txt", "pdf", "png", "jpg", "jpeg", "webp", "gif"]
    )
)
MAX_UPLOAD_SIZE_MB = 50

MAX_EXPOSED_CONVERSATIONS = 50
MAX_HISTORY_TURNS = 5
CHAR_STREAM_DELAY_SECONDS = 0.006

conv_store = ConversationStore(DATA_DIR)


# ── 训练 worker ──
_TRAINING_LOCK = threading.Lock()
_TRAINING_STATE: dict[str, Any] = {
    "running": False,
    "pending": False,
    "last_result": None,
    "last_error": None,
}


def _training_worker() -> None:
    while True:
        with _TRAINING_LOCK:
            if _TRAINING_STATE["running"]:
                return
            _TRAINING_STATE["running"] = True
            _TRAINING_STATE["pending"] = False
            _TRAINING_STATE["last_result"] = None
            _TRAINING_STATE["last_error"] = None

        should_continue = False
        try:
            from rag.vector_store import VectorStoreService
            vs = VectorStoreService()
            vs.load_document()
            # 知识库更新后重置 RAG 单例，确保 BM25 索引随新文档重建
            from agent.tools.agent_tools import reset_rag_service
            reset_rag_service()
            with _TRAINING_LOCK:
                _TRAINING_STATE["running"] = False
                _TRAINING_STATE["last_result"] = "success"
                should_continue = _TRAINING_STATE["pending"]
        except Exception as exc:
            with _TRAINING_LOCK:
                _TRAINING_STATE["running"] = False
                _TRAINING_STATE["last_error"] = str(exc)
            break

        if not should_continue:
            break


def _start_training() -> bool:
    with _TRAINING_LOCK:
        if _TRAINING_STATE["running"]:
            _TRAINING_STATE["pending"] = True
            return False
    t = threading.Thread(target=_training_worker, daemon=True)
    t.start()
    return True


# ── FastAPI app ──
app = FastAPI(title="FTSM-RAG")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

_agent: ReactAgent | None = None
_agent_lock = threading.Lock()
semantic_cache = SemanticCache(threshold=0.92)


def _get_agent() -> ReactAgent:
    """懒加载 agent，避免 DASHSCOPE_API_KEY 缺失时启动失败。"""
    global _agent
    with _agent_lock:
        if _agent is None:
            _agent = ReactAgent()
        return _agent


def _reset_agent() -> None:
    """保存设置后调用，下次聊天时会用新 key/模型重新创建 agent。"""
    global _agent
    from agent.tools.agent_tools import reset_rag_service
    from model.factory import reset_models
    reset_models()
    reset_rag_service()
    semantic_cache.clear()
    with _agent_lock:
        _agent = None


def _dashscope_configured() -> bool:
    return bool(os.getenv("DASHSCOPE_API_KEY", "").strip())


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = Field(default=None)
    new_chat: bool = Field(default=False)


# ── 生命周期 ──

@app.on_event("startup")
async def _startup() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    start_scheduler()


@app.on_event("shutdown")
async def _shutdown() -> None:
    stop_scheduler()


# ── 路由 ──

@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api/config/status")
async def config_status() -> JSONResponse:
    """前端用来判断是否需要引导用户去设置 API Key。"""
    return JSONResponse({"dashscope_configured": _dashscope_configured()})


@app.get("/api/scheduler/status")
async def scheduler_status_api() -> JSONResponse:
    return JSONResponse(scheduler_status())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # 若未配置 API Key，自动跳转到设置页
    if not _dashscope_configured():
        return RedirectResponse("/settings", status_code=302)
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/manage", response_class=HTMLResponse)
async def manage(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin.html", {})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html", {})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings.html", {})


# ── 设置（单机版，无保护） ──

def _parse_env_file(env_path: Path) -> dict[str, str]:
    return parse_env_file(env_path)


def _write_env_file(env_path: Path, updates: dict[str, str]) -> None:
    write_env_file(env_path, updates)


class SettingsPayload(BaseModel):
    dashscope_api_key: str = Field(default="")
    dashscope_base_url: str = Field(default="")
    chat_model_name: str = Field(default="")


def _mask_api_key(key: str) -> str:
    """返回掩码形式，仅保留末 4 位，如 sk-****abcd"""
    if not key:
        return ""
    visible = key[-4:] if len(key) >= 4 else key
    return f"sk-****{visible}"


@app.get("/api/settings")
async def get_settings() -> JSONResponse:
    env = _parse_env_file(_env_path)
    from model.factory import resolve_chat_model_name
    raw_key = env.get("DASHSCOPE_API_KEY", "")
    return JSONResponse({
        "dashscope_api_key":  _mask_api_key(raw_key),
        "dashscope_base_url": env.get("DASHSCOPE_BASE_URL", ""),
        "chat_model_name":    env.get("CHAT_MODEL_NAME", "") or resolve_chat_model_name(),
    })


@app.post("/api/settings")
async def save_settings(payload: SettingsPayload) -> JSONResponse:
    updates: dict[str, str] = {}
    raw_key = payload.dashscope_api_key.strip()
    # 如果前端回传的仍是掩码（sk-****xxxx），说明用户未修改，跳过覆盖
    is_masked = raw_key.startswith("sk-****") and len(raw_key) <= 12
    if raw_key and not is_masked:
        updates["DASHSCOPE_API_KEY"] = raw_key
    # 空字符串表示恢复默认（base_url 不设 = 国内版；模型名不设 = rag.yml 默认值）
    updates["DASHSCOPE_BASE_URL"] = payload.dashscope_base_url.strip()
    updates["CHAT_MODEL_NAME"] = payload.chat_model_name.strip()

    _write_env_file(_env_path, updates)
    apply_runtime_env(updates)

    _reset_agent()
    return JSONResponse({"ok": True})


# ── 本地密码锁 ──────────────────────────────────────────────────────────────
# 密码哈希格式：pbkdf2_sha256$<hex-salt>$<hex-hash>  存在 .env APP_PASSWORD_HASH

_HASH_PREFIX = "pbkdf2_sha256$"
_ITERATIONS = 260_000
# 会话令牌集合（进程内存；窗口关闭/重启后清空，相当于自动注销）
_session_tokens: set[str] = set()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(32)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{_HASH_PREFIX}{salt.hex()}${h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if not stored.startswith(_HASH_PREFIX):
        return False
    try:
        _, salt_hex, hash_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
        return hmac.compare_digest(h.hex(), hash_hex)
    except Exception:
        return False


def _get_password_hash() -> str:
    return _parse_env_file(_env_path).get("APP_PASSWORD_HASH", "")


class PasswordPayload(BaseModel):
    password: str = Field(default="")
    new_password: str = Field(default="")
    token: str = Field(default="")


@app.get("/api/auth/status")
async def auth_status() -> JSONResponse:
    """密码是否已设置。"""
    return JSONResponse({"has_password": bool(_get_password_hash())})


@app.post("/api/auth/setup")
async def auth_setup(payload: PasswordPayload) -> JSONResponse:
    """首次设置密码（仅当尚未设置时有效）。"""
    if _get_password_hash():
        raise HTTPException(status_code=400, detail="Password already set. Use /api/auth/change.")
    if len(payload.password) < 4:
        raise HTTPException(status_code=422, detail="Password must be at least 4 characters.")
    _write_env_file(_env_path, {"APP_PASSWORD_HASH": _hash_password(payload.password)})
    token = secrets.token_hex(32)
    _session_tokens.add(token)
    return JSONResponse({"ok": True, "token": token})


@app.post("/api/auth/unlock")
async def auth_unlock(payload: PasswordPayload) -> JSONResponse:
    """验证密码，成功后返回会话令牌。"""
    stored = _get_password_hash()
    if not stored:
        token = secrets.token_hex(32)
        _session_tokens.add(token)
        return JSONResponse({"ok": True, "token": token})
    if not _verify_password(payload.password, stored):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    token = secrets.token_hex(32)
    _session_tokens.add(token)
    return JSONResponse({"ok": True, "token": token})


@app.post("/api/auth/verify")
async def auth_verify(payload: PasswordPayload) -> JSONResponse:
    """前端页面切换时校验 sessionStorage 里的令牌。"""
    return JSONResponse({"valid": payload.token in _session_tokens})


@app.post("/api/auth/change")
async def auth_change(payload: PasswordPayload) -> JSONResponse:
    """修改密码：需提供旧密码。"""
    stored = _get_password_hash()
    if stored and not _verify_password(payload.password, stored):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    if len(payload.new_password) < 4:
        raise HTTPException(status_code=422, detail="New password must be at least 4 characters.")
    _write_env_file(_env_path, {"APP_PASSWORD_HASH": _hash_password(payload.new_password)})
    _session_tokens.clear()
    token = secrets.token_hex(32)
    _session_tokens.add(token)
    return JSONResponse({"ok": True, "token": token})


@app.post("/api/auth/remove")
async def auth_remove(payload: PasswordPayload) -> JSONResponse:
    """移除密码锁：需验证当前密码。"""
    stored = _get_password_hash()
    if stored and not _verify_password(payload.password, stored):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    _write_env_file(_env_path, {"APP_PASSWORD_HASH": ""})
    _session_tokens.clear()
    return JSONResponse({"ok": True})


@app.post("/api/auth/reset")
async def auth_reset() -> JSONResponse:
    """
    忘记密码：删除所有对话记录，清除密码哈希，恢复到首次使用状态。
    此操作不可逆，无需旧密码（因为用户已无法输入）。
    """
    import shutil as _shutil

    # 清除密码
    _write_env_file(_env_path, {"APP_PASSWORD_HASH": ""})
    _session_tokens.clear()

    # 删除所有对话文件
    conv_dir = DATA_DIR / "conversations"
    if conv_dir.exists():
        _shutil.rmtree(conv_dir, ignore_errors=True)
    legacy = DATA_DIR / "conversations.json"
    if legacy.exists():
        legacy.unlink(missing_ok=True)

    return JSONResponse({"ok": True})


@app.get("/api/models")
async def list_models() -> JSONResponse:
    """
    返回按地区精选的 Qwen 对话模型列表，并用一次轻量 completions 调用验证 API Key 是否有效。
    DashScope 的 compatible-mode 不支持 /v1/models 端点，所以用官方文档整理的静态列表。
    """
    import httpx

    env = _parse_env_file(_env_path)
    api_key = env.get("DASHSCOPE_API_KEY", "").strip() or os.getenv("DASHSCOPE_API_KEY", "").strip()
    base_url = env.get("DASHSCOPE_BASE_URL", "").strip() or os.getenv("DASHSCOPE_BASE_URL", "").strip()

    is_intl = bool(base_url and "intl" in base_url)

    # ── 官方文档整理的精选列表（2026-04，来自 help.aliyun.com/zh/model-studio/getting-started/models）
    _CHINA_MODELS = [
        # Qwen3 系列（2025 最新旗舰）
        "qwen3-max",
        "qwen3-max-latest",
        "qwen3-max-preview",
        "qwen3.6-max-preview",
        # 经典旗舰
        "qwen-max",
        "qwen-max-latest",
        # Plus 系列
        "qwen3.6-plus",
        "qwen3.5-plus",
        "qwen-plus",
        "qwen-plus-latest",
        # Turbo 系列（快速低成本）
        "qwen-turbo",
        "qwen-turbo-latest",
        # Long 系列（超长上下文）
        "qwen-long",
        "qwen-long-latest",
    ]
    _INTL_MODELS = [
        # 国际版独有 / 同步可用
        "qwen3.6-max-preview",
        "qwen3.6-plus",
        "qwen3.5-plus",
        "qwen-plus",
        "qwen-plus-latest",
        "qwen-turbo",
        "qwen-turbo-latest",
    ]

    models = _INTL_MODELS if is_intl else _CHINA_MODELS

    # ── 用一次极简 completions 请求验证 Key ──
    key_valid: bool | None = None
    key_error: str = ""

    if api_key:
        compat_base = (
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            if is_intl
            else "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{compat_base}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "qwen-turbo",
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                    },
                )
            if resp.status_code in (200, 400):
                # 400 也算 Key 有效（请求格式问题，非认证问题）
                key_valid = True
            elif resp.status_code == 401:
                key_valid = False
                key_error = "API Key 无效，请检查是否填写正确。"
            else:
                key_valid = None
                key_error = f"验证请求返回 {resp.status_code}，无法确认。"
        except Exception as exc:
            key_valid = None
            key_error = f"网络请求失败：{exc}"
    else:
        key_valid = False
        key_error = "API Key 未配置。"

    return JSONResponse({
        "models": models,
        "key_valid": key_valid,
        "key_error": key_error,
        "region": "intl" if is_intl else "china",
    })


# ── 对话 ──

@app.post("/api/conversations")
async def create_conversation() -> JSONResponse:
    conversation_id = str(uuid4())
    conv = conv_store.create(conversation_id)
    return JSONResponse(
        {
            "id": conv["id"],
            "title": conv["title"],
            "updated_at": conv["updated_at"],
            "messages": [],
        }
    )


@app.get("/api/conversations")
async def list_conversations() -> JSONResponse:
    items = conv_store.list_items(limit=MAX_EXPOSED_CONVERSATIONS)
    return JSONResponse({"items": items})


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> JSONResponse:
    found = conv_store.delete(conversation_id)
    if not found:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return JSONResponse({"ok": True})


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> JSONResponse:
    conv = conv_store.get(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return JSONResponse(
        {
            "id": conv["id"],
            "title": conv.get("title", "New chat"),
            "updated_at": conv.get("updated_at", 0),
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in conv.get("messages", [])
            ],
        }
    )


# ── 知识库文件管理 ──

@app.post("/api/upload")
async def upload_documents(files: list[UploadFile] = File(...)) -> JSONResponse:
    saved, errors = await save_uploads(
        files,
        DATA_DIR,
        ALLOWED_UPLOAD_EXTENSIONS,
        MAX_UPLOAD_SIZE_MB,
    )
    if saved:
        semantic_cache.clear()
    training_started = _start_training() if saved else False
    return JSONResponse({"saved": saved, "errors": errors, "training_started": training_started})


@app.get("/api/documents")
async def list_documents() -> JSONResponse:
    return JSONResponse({"documents": list_knowledge_documents(DATA_DIR, ALLOWED_UPLOAD_EXTENSIONS)})


@app.delete("/api/documents/{filename}")
async def delete_document(filename: str) -> JSONResponse:
    try:
        result = delete_knowledge_document(filename, DATA_DIR, ALLOWED_UPLOAD_EXTENSIONS)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    semantic_cache.clear()
    return JSONResponse(result)


@app.get("/api/training/status")
async def training_status() -> JSONResponse:
    with _TRAINING_LOCK:
        return JSONResponse(dict(_TRAINING_STATE))


@app.post("/api/training/start")
async def training_start() -> JSONResponse:
    started = _start_training()
    semantic_cache.clear()
    return JSONResponse(
        {
            "started": started,
            "message": "Training already running — marked as pending" if not started else "Training started",
        }
    )


@app.get("/api/cache/stats")
async def cache_stats() -> JSONResponse:
    return JSONResponse(semantic_cache.stats())


@app.get("/api/knowledge/stats")
async def knowledge_stats() -> JSONResponse:
    """知识库概览：文档数、manifest 记录数、chunk 总数、最近索引时间、缓存条目数。"""
    from rag.ingestion import load_manifest

    manifest = load_manifest()
    docs_in_manifest = manifest.get("documents", {})

    total_chunks = sum(
        len(record.get("chunk_ids", []))
        for record in docs_in_manifest.values()
    )

    last_indexed: str | None = None
    for record in docs_in_manifest.values():
        at = record.get("indexed_at")
        if at and (last_indexed is None or at > last_indexed):
            last_indexed = at

    file_docs = list_knowledge_documents(DATA_DIR, ALLOWED_UPLOAD_EXTENSIONS)

    return JSONResponse({
        "document_count": len(file_docs),
        "manifest_records": len(docs_in_manifest),
        "total_chunks": total_chunks,
        "last_indexed": last_indexed,
        "cache_entries": semantic_cache.stats().get("size", 0),
    })


# ── 聊天 ──

@app.post("/api/chat")
async def chat(payload: ChatRequest) -> StreamingResponse:
    if not _dashscope_configured():
        raise HTTPException(
            status_code=400,
            detail="DASHSCOPE_API_KEY is not configured. Please set it in /settings.",
        )

    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    conversation_id = payload.conversation_id or str(uuid4())

    return StreamingResponse(
        stream_chat_answer(
            message=message,
            conversation_id=conversation_id,
            conversation_store=conv_store,
            semantic_cache=semantic_cache,
            get_agent=_get_agent,
            max_history_turns=MAX_HISTORY_TURNS,
            char_stream_delay_seconds=CHAR_STREAM_DELAY_SECONDS,
        ),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conversation_id,
        },
    )
