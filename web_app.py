import os
import shutil
import sys
import threading
import time
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
    from model.factory import reset_models
    reset_models()
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


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings.html", {})


# ── 设置（单机版，无保护） ──

def _parse_env_file(env_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v.strip()
    return result


def _write_env_file(env_path: Path, updates: dict[str, str]) -> None:
    lines: list[str] = []
    written: set[str] = set()
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.partition("=")[0].strip()
                if k in updates:
                    lines.append(f"{k}={updates[k]}")
                    written.add(k)
                    continue
            lines.append(line)
    for k, v in updates.items():
        if k not in written:
            lines.append(f"{k}={v}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class SettingsPayload(BaseModel):
    dashscope_api_key: str = Field(default="")
    dashscope_base_url: str = Field(default="")
    chat_model_name: str = Field(default="")


@app.get("/api/settings")
async def get_settings() -> JSONResponse:
    env = _parse_env_file(_env_path)
    from model.factory import resolve_chat_model_name
    return JSONResponse({
        "dashscope_api_key":  env.get("DASHSCOPE_API_KEY", ""),
        "dashscope_base_url": env.get("DASHSCOPE_BASE_URL", ""),
        "chat_model_name":    env.get("CHAT_MODEL_NAME", "") or resolve_chat_model_name(),
    })


@app.post("/api/settings")
async def save_settings(payload: SettingsPayload) -> JSONResponse:
    updates: dict[str, str] = {}
    if payload.dashscope_api_key:
        updates["DASHSCOPE_API_KEY"] = payload.dashscope_api_key
    # 空字符串表示恢复默认（base_url 不设 = 国内版；模型名不设 = rag.yml 默认值）
    updates["DASHSCOPE_BASE_URL"] = payload.dashscope_base_url.strip()
    updates["CHAT_MODEL_NAME"] = payload.chat_model_name.strip()

    _write_env_file(_env_path, updates)
    for k, v in updates.items():
        if v:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)

    _reset_agent()
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    errors: list[dict[str, str]] = []

    for file in files:
        fname = Path(file.filename or "").name
        if not fname:
            errors.append({"name": file.filename or "(unknown)", "error": "Invalid filename"})
            continue
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            errors.append({"name": fname, "error": f"Unsupported file type: .{ext}"})
            continue
        try:
            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                errors.append({"name": fname, "error": f"File exceeds {MAX_UPLOAD_SIZE_MB} MB limit"})
                continue
            (DATA_DIR / fname).write_bytes(content)
            saved.append(fname)
        except Exception as exc:
            errors.append({"name": fname, "error": str(exc)})
        finally:
            await file.close()

    training_started = _start_training() if saved else False
    return JSONResponse({"saved": saved, "errors": errors, "training_started": training_started})


@app.get("/api/documents")
async def list_documents() -> JSONResponse:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    docs: list[dict[str, Any]] = []
    for f in DATA_DIR.iterdir():
        if not f.is_file():
            continue
        ext = f.suffix.lstrip(".").lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            continue
        stat = f.stat()
        docs.append({"name": f.name, "size": stat.st_size, "modified": int(stat.st_mtime)})
    docs.sort(key=lambda x: x["modified"], reverse=True)
    return JSONResponse({"documents": docs})


@app.delete("/api/documents/{filename}")
async def delete_document(filename: str) -> JSONResponse:
    safe_name = Path(filename).name
    file_path = DATA_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")
    file_path.unlink()
    return JSONResponse({"deleted": safe_name})


@app.get("/api/training/status")
async def training_status() -> JSONResponse:
    with _TRAINING_LOCK:
        return JSONResponse(dict(_TRAINING_STATE))


@app.post("/api/training/start")
async def training_start() -> JSONResponse:
    started = _start_training()
    return JSONResponse(
        {
            "started": started,
            "message": "Training already running — marked as pending" if not started else "Training started",
        }
    )


@app.get("/api/cache/stats")
async def cache_stats() -> JSONResponse:
    return JSONResponse(semantic_cache.stats())


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

    def save_history(answer: str) -> None:
        title = message if len(message) <= 40 else f"{message[:40]}..."
        conv_store.append_turn(
            conversation_id,
            user_content=message,
            assistant_content=answer,
            title=title or "New chat",
        )

    def stream_response():
        hit, cached_answer = semantic_cache.get(message)
        if hit and cached_answer and "__THINK" not in cached_answer:
            yield "__THINK__Answering from cache...__ENDTHINK__"
            save_history(cached_answer)
            for char in cached_answer:
                yield char
                time.sleep(CHAR_STREAM_DELAY_SECONDS)
            return

        recent_history = conv_store.recent_messages(conversation_id, MAX_HISTORY_TURNS)
        result_chunks: list[str] = []
        try:
            for chunk in _get_agent().execute_stream(message, history=recent_history):
                if not chunk:
                    continue
                if chunk.startswith("__THINK__"):
                    yield chunk
                    continue
                result_chunks.append(chunk)
                for char in chunk:
                    yield char
                    time.sleep(CHAR_STREAM_DELAY_SECONDS)
        except Exception as exc:
            err_msg = f"\n\n[Error] {exc}"
            result_chunks.append(err_msg)
            for char in err_msg:
                yield char

        final_answer = "".join(result_chunks).strip()
        if final_answer:
            semantic_cache.set(message, final_answer)
            save_history(final_answer)

    return StreamingResponse(
        stream_response(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conversation_id,
        },
    )
