import asyncio
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
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

# Tauri `cargo run` 调试时启动的是 dist 下的 PyInstaller exe，默认同级 .env 在 dist/FTSM-RAG/；
# 通过 FTSM_PROJECT_ROOT 让后端改用仓库根目录的 .env，与源码开发一致。
_env_override = os.environ.get("FTSM_PROJECT_ROOT", "").strip()
if _env_override:
    _env_root = Path(_env_override)
    _env_path = (_env_root / ".env") if _env_root.is_dir() else BASE_DIR / ".env"
else:
    _env_path = BASE_DIR / ".env"

# 首次启动：若本地没有 .env，从 bundle 里的 .env.example 复制一份
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
from utils.indexing_lock import indexing_lock  # noqa: E402
from utils.logger_handler import logger  # noqa: E402
from utils.path_tool import get_abs_path  # noqa: E402
from utils.scheduler import get_status as scheduler_status  # noqa: E402
from utils.scheduler import start_scheduler, stop_scheduler  # noqa: E402
from utils.scheduler import trigger_manual_crawl  # noqa: E402
from utils.semantic_cache import SemanticCache  # noqa: E402

WEB_DIR = _BUNDLE_DIR / "web"
REACT_DIST_DIR = _BUNDLE_DIR / "desktop" / "dist"
REACT_INDEX = REACT_DIST_DIR / "index.html"

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
    """索引 worker。

    注意：`running` 标志由 `_start_training()` 在**持锁期间**置位，本函数不再置位。
    历史实现是「先释放锁 → 再 Thread.start() → 由 worker 置 running=True」，
    中间存在一个 running 仍为 False 的窗口；前端刚 POST 完立刻轮询会读到
    running=False / last_result=None，从而误报「训练已停止」。现在 POST 返回时
    running 必然已为 True。
    """
    while True:
        should_continue = False
        try:
            from rag.vector_store import VectorStoreService
            with indexing_lock:
                vs = VectorStoreService()
                result = vs.load_document()
            if not result["success"]:
                raise RuntimeError(result["error_summary"] or "Indexing failed")
            # 知识库更新后重置 RAG 单例，确保 BM25 索引随新文档重建
            _reset_agent()
            # 回写权威状态：本地训练路径不发 MQ 事件，若不回写则 ftsm-knowledge
            # 的 doc 行会永远停在 INDEXING（降级场景下的状态背离）
            _sync_training_result_to_knowledge()
            with _TRAINING_LOCK:
                _TRAINING_STATE["running"] = False
                _TRAINING_STATE["last_result"] = "success"
                should_continue = _TRAINING_STATE["pending"]
        except Exception as exc:
            with _TRAINING_LOCK:
                _TRAINING_STATE["running"] = False
                _TRAINING_STATE["pending"] = False
                _TRAINING_STATE["last_error"] = str(exc)
            break

        if not should_continue:
            break


def _start_training() -> bool:
    """启动一次索引；已在运行则标记 pending 并返回 False。"""
    with _TRAINING_LOCK:
        if _TRAINING_STATE["running"]:
            _TRAINING_STATE["pending"] = True
            return False
        # 持锁占位，消除 POST 返回后 /api/training/status 仍显示未运行的竞态窗口
        _TRAINING_STATE["running"] = True
        _TRAINING_STATE["pending"] = False
        _TRAINING_STATE["last_result"] = None
        _TRAINING_STATE["last_error"] = None
    t = threading.Thread(target=_training_worker, daemon=True)
    t.start()
    return True


# ── FastAPI app ──
app = FastAPI(title="FTSM-RAG")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
    allow_origin_regex=r"^https?://(?:127\.0\.0\.1|localhost)(?::\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_trusted_browser_origin(origin: str) -> bool:
    if origin in {"http://tauri.localhost", "https://tauri.localhost", "tauri://localhost"}:
        return True
    try:
        from urllib.parse import urlparse

        parsed = urlparse(origin)
        return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}
    except ValueError:
        return False


@app.middleware("http")
async def reject_untrusted_api_origins(request: Request, call_next):
    origin = request.headers.get("origin", "").strip()
    if request.url.path.startswith("/api/") and origin and not _is_trusted_browser_origin(origin):
        return JSONResponse(status_code=403, content={"detail": "Untrusted request origin."})
    return await call_next(request)


app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
if (REACT_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=REACT_DIST_DIR / "assets"), name="react_assets")
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


def _cache_namespace() -> str:
    from model.factory import resolve_chat_model_name
    from rag.ingestion import load_manifest

    env = _parse_env_file(_env_path)
    base_url = env.get("DASHSCOPE_BASE_URL", "").strip() or os.getenv("DASHSCOPE_BASE_URL", "").strip()
    region = "intl" if "intl" in base_url else "china"
    index_version = (load_manifest().get("index") or {}).get("version", 0)
    return f"v2|region={region}|chat={resolve_chat_model_name()}|index={index_version}"


def _dashscope_configured() -> bool:
    """LLM 是否已配置（DashScope key 或 Vertex 项目）。

    历史名 dashscope_configured 保留给前端消费，Vertex 后端也算已配置。
    不能只用 os.getenv：load_dotenv 默认不覆盖已有环境变量，若系统在用户/终端里
    已导出变量，会导致误以为「应用内已配置」，桌面端首次引导弹窗不出现。
    """
    env = parse_env_file(_env_path)
    if bool(env.get("DASHSCOPE_API_KEY", "").strip()):
        return True
    # Vertex 后端：应用 .env 或环境里有项目 ID 且存在 ADC 凭据
    if (env.get("VERTEX_PROJECT_ID", "").strip() or os.getenv("VERTEX_PROJECT_ID", "").strip()):
        from model.factory import _ensure_vertex_adc_path

        _ensure_vertex_adc_path()
        adc = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        return bool(adc and Path(adc).exists())
    return False


def _react_web_available() -> bool:
    return REACT_INDEX.exists()


def _react_web_response() -> FileResponse:
    return FileResponse(REACT_INDEX)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = Field(default=None)


# ── 生命周期 ──

def _sync_training_result_to_knowledge() -> None:
    """本地训练成功后把索引结果回写到 ftsm-knowledge（best-effort）。

    没有这一步，降级训练会让 doc 行永远停在 INDEXING（见 services/knowledge_client.py）。
    """
    try:
        from services.knowledge_client import sync_training_result

        sync_training_result()
    except Exception as exc:
        logger.warning("[training] knowledge write-back skipped: %s", exc)


# ── MQ 索引消费者（带自愈重连）──

_MQ_RETRY_BASE_DELAY = 5
_MQ_RETRY_MAX_DELAY = 120


async def _run_index_consumer() -> None:
    """常驻 MQ 索引消费者。

    历史实现只在启动时尝试一次（内部 10 次快速重试），耗尽后任务直接结束，
    **整个进程生命周期内不再重连**——RabbitMQ 晚于网关启动或中途重启，
    索引链路就永久退化为「必须手动点开始训练」，且只有一条不进日志文件的告警。
    现在改为外层无限重连，退避上限 120s。
    """
    delay = _MQ_RETRY_BASE_DELAY
    while True:
        try:
            logger.info("[mq] starting index consumer…")
            from rag.index_consumer import start_consumer

            await start_consumer()
            # start_consumer 正常返回只发生在消费循环异常结束时，重置退避后再试
            logger.warning("[mq] index consumer returned unexpectedly; reconnecting…")
            delay = _MQ_RETRY_BASE_DELAY
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "[mq] index consumer unavailable (degraded to local training), "
                "retrying in %ss: %s",
                delay,
                exc,
            )
        await asyncio.sleep(delay)
        delay = min(delay * 2, _MQ_RETRY_MAX_DELAY)


_consumer_task: asyncio.Task | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _consumer_task
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    start_scheduler(on_index_updated=_reset_agent)
    if os.getenv("FTSM_MQ_ENABLED", "1").strip() != "0":
        _consumer_task = asyncio.create_task(_run_index_consumer())
    try:
        from services.knowledge_client import sync_training_result

        asyncio.get_event_loop().run_in_executor(None, sync_training_result)
    except Exception as exc:
        logger.warning(f"[startup] knowledge sync failed: {exc}")


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _consumer_task
    stop_scheduler()
    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass


# ── 路由 ──

@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api/config/status")
def config_status() -> JSONResponse:
    """前端用来判断是否需要引导用户去设置 API Key。"""
    return JSONResponse({"dashscope_configured": _dashscope_configured()})


@app.get("/api/scheduler/status")
def scheduler_status_api() -> JSONResponse:
    return JSONResponse(scheduler_status())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if _react_web_available():
        return _react_web_response()

    # 若未配置 API Key，自动跳转到设置页
    return templates.TemplateResponse(request, "legacy.html", {})


@app.get("/manage", response_class=HTMLResponse)
async def manage(request: Request) -> HTMLResponse:
    if _react_web_available():
        return _react_web_response()
    return templates.TemplateResponse(request, "legacy.html", {})


@app.get("/guide", response_class=HTMLResponse)
async def guide_page(request: Request) -> HTMLResponse:
    """Student life guide portal (English): quick topics with sample questions + bus maps."""
    response = templates.TemplateResponse(request, "guide.html", {})
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    if _react_web_available():
        return _react_web_response()
    return templates.TemplateResponse(request, "legacy.html", {})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    if _react_web_available():
        return _react_web_response()
    return templates.TemplateResponse(request, "legacy.html", {})


@app.get("/legacy", response_class=HTMLResponse)
async def legacy_index(request: Request):
    return templates.TemplateResponse(request, "legacy.html", {})


@app.get("/legacy/{legacy_path:path}", response_class=HTMLResponse)
async def legacy_fallback(request: Request, legacy_path: str) -> HTMLResponse:
    return templates.TemplateResponse(request, "legacy.html", {})


# ── 设置（单机版，无保护） ──

def _parse_env_file(env_path: Path) -> dict[str, str]:
    return parse_env_file(env_path)


def _write_env_file(env_path: Path, updates: dict[str, str]) -> None:
    write_env_file(env_path, updates)


class SettingsPayload(BaseModel):
    dashscope_api_key: str = Field(default="")
    dashscope_base_url: str = Field(default="")
    chat_model_name: str = Field(default="")


_ALLOWED_DASHSCOPE_BASE_URLS = {
    "",
    "https://dashscope.aliyuncs.com/api/v1",
    "https://dashscope-intl.aliyuncs.com/api/v1",
}


def _validate_dashscope_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized:
        return ""
    if normalized not in _ALLOWED_DASHSCOPE_BASE_URLS:
        raise HTTPException(
            status_code=400,
            detail="Only official DashScope China or international endpoints are allowed.",
        )
    return normalized


def _mask_api_key(key: str) -> str:
    """返回掩码形式，仅保留末 4 位，如 sk-****abcd"""
    if not key:
        return ""
    visible = key[-4:] if len(key) >= 4 else key
    return f"sk-****{visible}"


@app.get("/api/settings")
def get_settings() -> JSONResponse:
    env = _parse_env_file(_env_path)
    from model.factory import resolve_backend, resolve_chat_model_name
    raw_key = env.get("DASHSCOPE_API_KEY", "")
    return JSONResponse({
        "backend":            resolve_backend(),
        "dashscope_api_key":  _mask_api_key(raw_key),
        "dashscope_base_url": env.get("DASHSCOPE_BASE_URL", ""),
        "chat_model_name":    env.get("CHAT_MODEL_NAME", "") or resolve_chat_model_name(),
    })


def _require_admin_api_key(request: Request) -> None:
    expected = (os.getenv("ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_API_KEY is not configured on the server.",
        )
    provided = (request.headers.get("X-Admin-Api-Key") or "").strip()
    if provided != expected:
        raise HTTPException(status_code=401, detail="Admin API key required")


@app.post("/api/settings")
def save_settings(payload: SettingsPayload, request: Request) -> JSONResponse:
    # P0-3 纵深防御：除网关 ADMIN_PATHS 外，服务本身也校验管理员密钥
    #（直连 8104 端口绕过网关的场景也被挡住）。
    _require_admin_api_key(request)
    updates: dict[str, str] = {}
    raw_key = payload.dashscope_api_key.strip()
    # 如果前端回传的仍是掩码（sk-****xxxx），说明用户未修改，跳过覆盖
    is_masked = raw_key.startswith("sk-****") and len(raw_key) <= 12
    if raw_key and not is_masked:
        updates["DASHSCOPE_API_KEY"] = raw_key
    # 空字符串表示恢复默认（base_url 不设 = 国内版；模型名不设 = rag.yml 默认值）
    updates["DASHSCOPE_BASE_URL"] = _validate_dashscope_base_url(payload.dashscope_base_url)
    model_name = payload.chat_model_name.strip()
    updates["CHAT_MODEL_NAME"] = model_name
    from model.factory import resolve_backend
    # vertex 后端下无论 model_name 是否为空都同步 VERTEX_MODEL_NAME：
    # 空串表示"恢复默认"，若不同步清空，旧值会一直残留在 .env 中
    if resolve_backend() == "vertex":
        updates["VERTEX_MODEL_NAME"] = model_name

    _write_env_file(_env_path, updates)
    apply_runtime_env(updates)

    _reset_agent()
    return JSONResponse({"ok": True})


@app.get("/api/models")
async def list_models(list_region: str | None = Query(default=None)) -> JSONResponse:
    """
    返回当前后端可用的对话模型列表并验证凭据。
    - vertex 后端：Gemini 模型列表 + 一次轻量 embed 调用验证 ADC 凭据。
    - dashscope 后端：Qwen 模型列表 + 一次轻量 completions 调用验证 API Key
      （compatible-mode 不支持 /v1/models 端点，用官方文档整理的静态列表）。

    list_region 仅对 dashscope 后端有意义（china | intl）。
    """
    from model.factory import resolve_backend

    if resolve_backend() == "vertex":
        # P1-7：_list_models_vertex 内含一次同步 embed 调用，丢线程池执行避免卡事件循环
        return await asyncio.to_thread(_list_models_vertex)

    import httpx

    env = _parse_env_file(_env_path)
    api_key = env.get("DASHSCOPE_API_KEY", "").strip() or os.getenv("DASHSCOPE_API_KEY", "").strip()
    base_url = env.get("DASHSCOPE_BASE_URL", "").strip() or os.getenv("DASHSCOPE_BASE_URL", "").strip()

    env_is_intl = bool(base_url and "intl" in base_url)
    if list_region == "intl":
        list_is_intl = True
    elif list_region == "china":
        list_is_intl = False
    else:
        list_is_intl = env_is_intl

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

    models = _INTL_MODELS if list_is_intl else _CHINA_MODELS

    # ── 用一次极简 completions 请求验证 Key（始终按已保存地域的 endpoint）──
    key_valid: bool | None = None
    key_error: str = ""

    if api_key:
        compat_base = (
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            if env_is_intl
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
        "region": "intl" if list_is_intl else "china",
    })


def _list_models_vertex() -> JSONResponse:
    """Vertex/Gemini 后端的模型列表 + ADC 凭据验证（轻量 embed 调用）。"""
    from model.factory import resolve_chat_model_name

    current = resolve_chat_model_name()
    _GEMINI_MODELS = [
        current,
        # Gemini 3.x 系列
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        # Gemini 2.5 系列
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
    ]
    # 去重保序
    models = list(dict.fromkeys(_GEMINI_MODELS))

    key_valid: bool | None = None
    key_error: str = ""

    from model.factory import _ensure_vertex_adc_path

    _ensure_vertex_adc_path()
    project = os.getenv("VERTEX_PROJECT_ID", "").strip()
    adc = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not project:
        key_valid = False
        key_error = "VERTEX_PROJECT_ID 未配置。"
    elif not adc or not Path(adc).exists():
        key_valid = False
        key_error = "ADC 凭据文件不存在（GOOGLE_APPLICATION_CREDENTIALS）。"
    else:
        try:
            from model.factory import get_embed_model

            get_embed_model().embed_query("health check")
            key_valid = True
        except Exception as exc:
            key_valid = None
            key_error = f"Vertex 凭据验证失败：{str(exc)[:180]}"

    return JSONResponse({
        "models": models,
        "key_valid": key_valid,
        "key_error": key_error,
        "region": "vertex",
    })


# ── 语音（TTS 朗读 / STT 语音输入）──

@app.post("/api/voice/tts")
async def voice_tts(payload: dict) -> StreamingResponse:
    """Text -> Cloud TTS (Chirp 3 HD) -> 24 kHz WAV for browser playback."""
    from services.voice_service import strip_markdown_for_speech, synthesize_speech

    text = (payload or {}).get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")
    speech = strip_markdown_for_speech(text)
    if not speech:
        raise HTTPException(status_code=400, detail="Nothing to speak after cleanup.")
    try:
        wav = await asyncio.to_thread(synthesize_speech, speech)
    except Exception as exc:
        logger.warning("[voice_tts] synthesize failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"TTS failed: {exc}") from exc
    return StreamingResponse(
        iter([wav]),
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/voice/stt")
async def voice_stt(audio: UploadFile = File(...)) -> JSONResponse:
    """Audio clip (WAV/MP3/OGG) -> Gemini transcription -> text."""
    from services.voice_service import transcribe_audio

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Audio file is empty.")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio too large (max 15 MB).")
    mime = audio.content_type or "audio/wav"
    if mime not in ("audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/ogg"):
        mime = "audio/wav"
    try:
        text = await asyncio.to_thread(transcribe_audio, data, mime)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"STT failed: {exc}") from exc
    return JSONResponse({"text": text})


# ── 对话 ──

@app.post("/api/conversations")
def create_conversation() -> JSONResponse:
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
def list_conversations() -> JSONResponse:
    items = conv_store.list_items(limit=MAX_EXPOSED_CONVERSATIONS)
    return JSONResponse({"items": items})


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> JSONResponse:
    found = conv_store.delete(conversation_id)
    if not found:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return JSONResponse({"ok": True})


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> JSONResponse:
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
    # 微服务路径：注册到 ftsm-knowledge（建 INDEXING 记录并发 doc.index.requested）。
    # 但「注册成功」不等于「事件发得出去」——MQ 掉线时事件会静默丢弃、文档永远停在
    # INDEXING。因此这里额外确认消费者是否真的在监听，否则退回本地训练兜底，
    # 保证「上传 → 可检索」无论如何都能走完。
    registered = await _register_with_knowledge(saved) if saved else False
    mq_live = _mq_consumer_live() if registered else False
    training_started = _start_training() if (saved and not mq_live) else False
    return JSONResponse(
        {
            "saved": saved,
            "errors": errors,
            "registered": registered,
            "index_via": "mq" if mq_live else ("local" if saved else "none"),
            "training_started": training_started,
        }
    )


def _mq_consumer_live() -> bool:
    """索引消费者是否已连上 RabbitMQ 并在监听。"""
    try:
        from rag.index_consumer import consumer_ready

        return consumer_ready()
    except Exception:
        return False


async def _register_with_knowledge(saved: list[str]) -> bool:
    """把上传文件注册到 ftsm-knowledge；返回 False 表示回退到本地训练。"""
    import httpx

    from rag.ingestion import file_sha256, stable_file_doc_id

    base = os.getenv("FTSM_KNOWLEDGE_URL", "http://127.0.0.1:8103").rstrip("/")
    registrations = []
    for name in saved:
        path = DATA_DIR / name
        if not path.exists():
            continue
        registrations.append({
            "docId": stable_file_doc_id(path),
            "name": name,
            "title": name,
            "sourceType": "file",
            "size": path.stat().st_size,
            "fileHash": file_sha256(path),
        })
    if not registrations:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(f"{base}/internal/docs", json={"docs": registrations})
        return resp.status_code == 200
    except Exception as exc:
        import logging

        logging.getLogger("ftsm.web").warning(
            f"[knowledge] registration failed, falling back to local training: {exc}"
        )
        return False


@app.get("/api/documents")
def list_documents() -> JSONResponse:
    # P1-7：同步重 I/O（递归扫描 + 全量哈希）不放事件循环，FastAPI 自动进线程池
    return JSONResponse({"documents": list_knowledge_documents(DATA_DIR, ALLOWED_UPLOAD_EXTENSIONS)})


@app.delete("/api/documents/{filename:path}")
def delete_document(filename: str) -> JSONResponse:
    try:
        result = delete_knowledge_document(filename, DATA_DIR, ALLOWED_UPLOAD_EXTENSIONS)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    semantic_cache.clear()
    # P1-5：删除后使本进程 RAG 单例（含 BM25 快照）失效，防止已删文档仍被召回。
    # （_ensure_bm25 的 manifest 签名检查是双保险，这里主动重置立即生效。）
    try:
        from agent.tools.agent_tools import reset_rag_service

        reset_rag_service()
    except Exception as reset_exc:
        logger.warning(f"[delete] reset_rag_service failed: {reset_exc}")
    # 状态变更走事件：ftsm-knowledge 消费 doc.deleted 后删除权威记录
    doc_id = (result or {}).get("doc_id")
    if doc_id:
        from rag.mq_events import KEY_DOC_DELETED, publish_soon

        publish_soon(KEY_DOC_DELETED, {"kind": "deleted", "docId": doc_id})
    return JSONResponse(result)


@app.get("/api/training/status")
def training_status() -> JSONResponse:
    with _TRAINING_LOCK:
        return JSONResponse(dict(_TRAINING_STATE))


@app.post("/api/training/start")
def training_start() -> JSONResponse:
    started = _start_training()
    semantic_cache.clear()
    return JSONResponse(
        {
            "started": started,
            "message": "Training already running — marked as pending" if not started else "Training started",
        }
    )


@app.get("/api/cache/stats")
def cache_stats() -> JSONResponse:
    return JSONResponse(semantic_cache.stats())


@app.get("/api/kb/stats")
def kb_stats() -> JSONResponse:
    """RAG 索引的真实规模（manifest 口径），供 Guide 页统计条展示。

    注意与 /api/knowledge/stats（ftsm-knowledge Java 服务、MySQL 口径）区分：
    网关把 /api/knowledge/** 路由给 Java，因此这里用独立路径避免被其遮蔽。
    """
    from rag.ingestion import compute_index_state, load_manifest, save_manifest

    manifest = load_manifest()
    docs_in_manifest = manifest.get("documents", {})
    index_state = manifest.get("index") or compute_index_state(manifest)
    if not index_state.get("source_type_counts"):
        index_state = compute_index_state(manifest, previous_state=index_state)
        manifest["index"] = index_state
        save_manifest(manifest)

    # 精排是否真的在跑：dashscope 账号欠费 / 本地模型未装时 _rerank 会静默降级成
    # RRF 序，README 与 Guide 页却仍宣称"交叉编码器精排"。把真实状态暴露出来，
    # 演示前一眼就能看出这个卖点当前是否生效（active=false 时 disabled_reason 给出原因）。
    try:
        from rag.rag_service import rerank_status

        rerank = rerank_status()
    except Exception as exc:  # 精排状态不可得不应拖垮统计接口
        rerank = {"active": False, "disabled_reason": f"status unavailable: {exc}"}

    return JSONResponse({
        "document_count": len(docs_in_manifest),
        "total_chunks": index_state.get("total_chunks", 0),
        "cache_entries": semantic_cache.stats().get("size", 0),
        "index_version": index_state.get("version", 0),
        "source_type_counts": index_state.get("source_type_counts", {}),
        "rerank": rerank,
    })


@app.get("/api/knowledge/stats")
def knowledge_stats() -> JSONResponse:
    """知识库概览：文档数、manifest 记录数、chunk 总数、最近索引时间、缓存条目数。"""
    from rag.ingestion import compute_index_state, load_manifest, save_manifest

    manifest = load_manifest()
    docs_in_manifest = manifest.get("documents", {})
    index_state = manifest.get("index") or compute_index_state(manifest)
    if not index_state.get("source_type_counts"):
        index_state = compute_index_state(manifest, previous_state=index_state)
        manifest["index"] = index_state
        save_manifest(manifest)

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
    source_type_counts = index_state.get("source_type_counts") or {}

    return JSONResponse({
        "document_count": len(file_docs),
        "manifest_records": len(docs_in_manifest),
        "total_chunks": index_state.get("total_chunks", total_chunks),
        "last_indexed": index_state.get("last_indexed") or last_indexed,
        "cache_entries": semantic_cache.stats().get("size", 0),
        "index_version": index_state.get("version", 0),
        "index_updated_at": index_state.get("updated_at"),
        "index_last_error": index_state.get("last_error"),
        "source_type_counts": source_type_counts,
    })


# ── 聊天 ──

@app.post("/api/knowledge/update")
def update_knowledge_from_website(
    request: Request,
    max_pages: int | None = Query(default=None, ge=1, le=300),
    reindex: bool = Query(default=True),
) -> JSONResponse:
    _require_admin_api_key(request)
    result = trigger_manual_crawl(max_pages=max_pages, reindex=reindex)
    if reindex:
        semantic_cache.clear()
    return JSONResponse(result)


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    if not _dashscope_configured():
        raise HTTPException(
            status_code=400,
            detail="LLM backend is not configured. Please set it in /settings.",
        )

    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    conversation_id = payload.conversation_id or str(uuid4())

    # Gateway injects the verified student id after session auth (chat is in
    # STUDENT_EXACT of SessionAuthFilter). Direct access to ftsm-rag skips it.
    student_id = request.headers.get("X-Student-Id") or None

    return StreamingResponse(
        stream_chat_answer(
            message=message,
            conversation_id=conversation_id,
            conversation_store=conv_store,
            semantic_cache=semantic_cache,
            get_agent=_get_agent,
            cache_namespace=_cache_namespace,
            max_history_turns=MAX_HISTORY_TURNS,
            student_id=student_id,
        ),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conversation_id,
        },
    )


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/") or "." in Path(full_path).name or not _react_web_available():
        raise HTTPException(status_code=404, detail="Not found")
    return _react_web_response()
