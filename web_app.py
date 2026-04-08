import json
import threading
import time
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from agent.react_agent import ReactAgent
from utils.config_handler import chroma_conf
from utils.path_tool import get_abs_path
from utils.scheduler import get_status as scheduler_status
from utils.scheduler import start_scheduler, stop_scheduler
from utils.semantic_cache import SemanticCache

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
SESSION_STORE_PATH = BASE_DIR / "data" / "ukm_ftsm" / "chat_sessions.json"

# ── Knowledge Base ──
DATA_DIR = Path(get_abs_path(chroma_conf["data_path"]))
ALLOWED_UPLOAD_EXTENSIONS: set[str] = set(
    chroma_conf.get(
        "allow_knowledge_file_type", ["txt", "pdf", "png", "jpg", "jpeg", "webp", "gif"]
    )
)
MAX_UPLOAD_SIZE_MB = 50

_TRAINING_LOCK = threading.Lock()
_TRAINING_STATE: dict[str, Any] = {
    "running": False,
    "pending": False,
    "last_result": None,  # "success" | None
    "last_error": None,  # error message string | None
}

# ── Training worker ──


def _training_worker() -> None:
    """Background worker: runs VectorStoreService.load_document(), re-runs if pending."""
    while True:
        with _TRAINING_LOCK:
            if _TRAINING_STATE["running"]:
                return  # another worker is active
            _TRAINING_STATE["running"] = True
            _TRAINING_STATE["pending"] = False
            _TRAINING_STATE["last_result"] = None
            _TRAINING_STATE["last_error"] = None

        should_continue = False
        try:
            from rag.vector_store import (
                VectorStoreService,  # lazy import avoids circular deps
            )

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
    """Start training thread; if already running mark as pending. Returns True when a new thread is spawned."""
    with _TRAINING_LOCK:
        if _TRAINING_STATE["running"]:
            _TRAINING_STATE["pending"] = True
            return False
    t = threading.Thread(target=_training_worker, daemon=True)
    t.start()
    return True


app = FastAPI(title="FTSM-RAG")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

agent = ReactAgent()
semantic_cache = SemanticCache(threshold=0.92)

CHAR_STREAM_DELAY_SECONDS = 0.006
MAX_CONVERSATION_ITEMS = 200
MAX_EXPOSED_CONVERSATIONS = 50
MAX_HISTORY_TURNS = 5

CONVERSATIONS: dict[str, list[dict[str, str]]] = {}
CONVERSATION_META: dict[str, dict[str, str | int]] = {}
SESSION_LOCK = Lock()


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = Field(default=None)
    new_chat: bool = Field(default=False)


def _load_session_store() -> None:
    if not SESSION_STORE_PATH.exists():
        return

    try:
        payload = json.loads(SESSION_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return

    conversations = payload.get("conversations", {})
    meta = payload.get("meta", {})

    if isinstance(conversations, dict):
        CONVERSATIONS.update(conversations)
    if isinstance(meta, dict):
        CONVERSATION_META.update(meta)


def _persist_session_store() -> None:
    SESSION_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STORE_PATH.write_text(
        json.dumps(
            {
                "conversations": CONVERSATIONS,
                "meta": CONVERSATION_META,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _prune_conversations() -> None:
    if len(CONVERSATION_META) <= MAX_CONVERSATION_ITEMS:
        return

    ordered_ids = sorted(
        CONVERSATION_META,
        key=lambda cid: int(CONVERSATION_META.get(cid, {}).get("updated_at", 0)),
        reverse=True,
    )
    keep_ids = set(ordered_ids[:MAX_CONVERSATION_ITEMS])
    for cid in list(CONVERSATION_META.keys()):
        if cid in keep_ids:
            continue
        CONVERSATION_META.pop(cid, None)
        CONVERSATIONS.pop(cid, None)


def _ensure_conversation(conversation_id: str, title: str = "New chat") -> None:
    now = int(time.time())
    CONVERSATIONS.setdefault(conversation_id, [])
    existing = CONVERSATION_META.get(conversation_id, {})
    CONVERSATION_META[conversation_id] = {
        "title": str(existing.get("title", title)),
        "updated_at": int(existing.get("updated_at", now)),
    }


_load_session_store()


@app.on_event("startup")
async def _startup():
    start_scheduler()


@app.on_event("shutdown")
async def _shutdown():
    stop_scheduler()


@app.get("/api/scheduler/status")
async def scheduler_status_api() -> JSONResponse:
    """查看定时任务状态"""
    return JSONResponse(scheduler_status())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ── Knowledge Base endpoints ──


@app.post("/api/upload")
async def upload_documents(files: list[UploadFile] = File(...)) -> JSONResponse:
    """Upload one or more documents and kick off background training."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    errors: list[dict[str, str]] = []

    for file in files:
        fname = Path(file.filename or "").name  # strip any path component
        if not fname:
            errors.append(
                {"name": file.filename or "(unknown)", "error": "Invalid filename"}
            )
            continue

        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            errors.append({"name": fname, "error": f"Unsupported file type: .{ext}"})
            continue

        try:
            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                errors.append(
                    {
                        "name": fname,
                        "error": f"File exceeds {MAX_UPLOAD_SIZE_MB} MB limit",
                    }
                )
                continue
            (DATA_DIR / fname).write_bytes(content)
            saved.append(fname)
        except Exception as exc:
            errors.append({"name": fname, "error": str(exc)})
        finally:
            await file.close()

    training_started = False
    if saved:
        training_started = _start_training()

    return JSONResponse(
        {"saved": saved, "errors": errors, "training_started": training_started}
    )


@app.get("/api/documents")
async def list_documents() -> JSONResponse:
    """List all knowledge-base documents in the data directory."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    docs: list[dict[str, Any]] = []
    for f in DATA_DIR.iterdir():
        if not f.is_file():
            continue
        ext = f.suffix.lstrip(".").lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            continue
        stat = f.stat()
        docs.append(
            {"name": f.name, "size": stat.st_size, "modified": int(stat.st_mtime)}
        )
    docs.sort(key=lambda x: x["modified"], reverse=True)
    return JSONResponse({"documents": docs})


@app.delete("/api/documents/{filename}")
async def delete_document(filename: str) -> JSONResponse:
    """Delete a document from the knowledge-base data directory."""
    safe_name = Path(filename).name  # prevent path traversal
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
    """Return the current training state."""
    with _TRAINING_LOCK:
        return JSONResponse(
            {
                "running": _TRAINING_STATE["running"],
                "pending": _TRAINING_STATE["pending"],
                "last_result": _TRAINING_STATE["last_result"],
                "last_error": _TRAINING_STATE["last_error"],
            }
        )


@app.post("/api/training/start")
async def training_start() -> JSONResponse:
    """Manually trigger a training run."""
    started = _start_training()
    return JSONResponse(
        {
            "started": started,
            "message": "Training already running — marked as pending"
            if not started
            else "Training started",
        }
    )


@app.post("/api/conversations")
async def create_conversation() -> JSONResponse:
    conversation_id = str(uuid4())
    with SESSION_LOCK:
        _ensure_conversation(conversation_id)
        _persist_session_store()
    return JSONResponse(
        {
            "id": conversation_id,
            "title": "New chat",
            "updated_at": int(time.time()),
            "messages": [],
        }
    )


@app.get("/api/conversations")
async def list_conversations() -> JSONResponse:
    items: list[dict[str, str | int]] = []
    with SESSION_LOCK:
        for cid, meta in CONVERSATION_META.items():
            items.append(
                {
                    "id": cid,
                    "title": str(meta.get("title", "New chat")),
                    "updated_at": int(meta.get("updated_at", 0)),
                }
            )
    items.sort(key=lambda x: int(x.get("updated_at", 0)), reverse=True)
    return JSONResponse({"items": items[:MAX_EXPOSED_CONVERSATIONS]})


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> JSONResponse:
    with SESSION_LOCK:
        messages = CONVERSATIONS.get(conversation_id, [])
        meta = CONVERSATION_META.get(conversation_id, {})
    return JSONResponse(
        {
            "id": conversation_id,
            "title": str(meta.get("title", "New chat")),
            "updated_at": int(meta.get("updated_at", 0)),
            "messages": messages,
        }
    )


@app.get("/api/cache/stats")
async def cache_stats() -> JSONResponse:
    """查看语义缓存统计"""
    return JSONResponse(semantic_cache.stats())


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> StreamingResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")
    conversation_id = payload.conversation_id or str(uuid4())

    with SESSION_LOCK:
        if payload.new_chat or conversation_id not in CONVERSATIONS:
            _ensure_conversation(conversation_id)
            _persist_session_store()

    def save_history(answer: str) -> None:
        with SESSION_LOCK:
            _ensure_conversation(conversation_id)
            CONVERSATIONS[conversation_id].append({"role": "user", "content": message})
            CONVERSATIONS[conversation_id].append(
                {"role": "assistant", "content": answer}
            )
            if len(CONVERSATIONS[conversation_id]) > 40:
                CONVERSATIONS[conversation_id] = CONVERSATIONS[conversation_id][-40:]
            title = message.strip()
            if len(title) > 40:
                title = f"{title[:40]}..."
            CONVERSATION_META[conversation_id] = {
                "title": title or "New chat",
                "updated_at": int(time.time()),
            }
            _prune_conversations()
            _persist_session_store()

    def stream_response():
        # 1. 语义缓存命中 → 直接流式返回，不调用 LLM
        hit, cached_answer = semantic_cache.get(message)
        if hit and cached_answer:
            yield "__THINK__Answering from cache...__ENDTHINK__"
            save_history(cached_answer)
            for char in cached_answer:
                yield char
                time.sleep(CHAR_STREAM_DELAY_SECONDS)
            return

        # 2. 未命中 → 取历史上下文，调用 Agent
        with SESSION_LOCK:
            all_history = list(CONVERSATIONS.get(conversation_id, []))
        recent_history = all_history[-(MAX_HISTORY_TURNS * 2) :]

        result_chunks: list[str] = []
        for chunk in agent.execute_stream(message, history=recent_history):
            if not chunk:
                continue
            if chunk.startswith("__THINK__"):
                yield chunk
                continue
            result_chunks.append(chunk)
            for char in chunk:
                yield char
                time.sleep(CHAR_STREAM_DELAY_SECONDS)

        # 3. 回答完毕 → 写入语义缓存 + 保存历史
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
