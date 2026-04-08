import json
import os
import hashlib
import hmac
import re
import secrets
import threading
import time
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
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
STUDENT_STORE_PATH = BASE_DIR / "data" / "ukm_ftsm" / "student_accounts.json"
AUTH_COOKIE_NAME = "ftsm_student_session"
AUTH_SESSION_TTL_SECONDS = 7 * 24 * 3600
PASSWORD_HASH_ITERATIONS = 200_000

# ── Knowledge Base ──
DATA_DIR = Path(get_abs_path(chroma_conf["data_path"]))
ALLOWED_UPLOAD_EXTENSIONS: set[str] = set(
    chroma_conf.get(
        "allow_knowledge_file_type", ["txt", "pdf", "png", "jpg", "jpeg", "webp", "gif"]
    )
)
MAX_UPLOAD_SIZE_MB = 50
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()

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
STUDENT_LOCK = Lock()
AUTH_SESSIONS: dict[str, dict[str, str | int]] = {}


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = Field(default=None)
    new_chat: bool = Field(default=False)


class StudentAuthRequest(BaseModel):
    student_id: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=6, max_length=200)
    display_name: str | None = Field(default=None, max_length=80)


def _normalize_student_id(student_id: str) -> str:
    normalized = student_id.strip().lower()
    if not re.fullmatch(r"[a-z0-9@._-]{3,80}", normalized):
        raise HTTPException(
            status_code=400,
            detail="Student ID can only contain letters, numbers, @, dot, underscore, or hyphen.",
        )
    return normalized


def _load_student_store() -> dict[str, Any]:
    if not STUDENT_STORE_PATH.exists():
        return {"students": {}}
    try:
        return json.loads(STUDENT_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"students": {}}


def _persist_student_store(payload: dict[str, Any]) -> None:
    STUDENT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STUDENT_STORE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations, salt, expected = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def _public_student(student_id: str, record: dict[str, Any]) -> dict[str, str]:
    return {
        "student_id": student_id,
        "display_name": str(record.get("display_name") or student_id),
    }


def _create_student_session(response: Response, student_id: str) -> None:
    token = secrets.token_urlsafe(32)
    AUTH_SESSIONS[token] = {
        "student_id": student_id,
        "expires_at": int(time.time()) + AUTH_SESSION_TTL_SECONDS,
    }
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=AUTH_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )


def _clear_student_session(request: Request, response: Response) -> None:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        AUTH_SESSIONS.pop(token, None)
    response.delete_cookie(AUTH_COOKIE_NAME)


def require_student(request: Request) -> dict[str, str]:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    session = AUTH_SESSIONS.get(token)
    if not session or int(session.get("expires_at", 0)) < int(time.time()):
        AUTH_SESSIONS.pop(token, None)
        raise HTTPException(status_code=401, detail="Login required")
    student_id = str(session["student_id"])
    with STUDENT_LOCK:
        store = _load_student_store()
        record = store.get("students", {}).get(student_id)
    if not record:
        raise HTTPException(status_code=401, detail="Login required")
    return _public_student(student_id, record)


def require_admin_api_key(x_admin_api_key: str | None = Header(default=None)) -> None:
    if not ADMIN_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_API_KEY is not configured on the server.",
        )
    if not x_admin_api_key or x_admin_api_key.strip() != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


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


def _ensure_conversation(
    conversation_id: str,
    title: str = "New chat",
    student_id: str = "",
) -> None:
    now = int(time.time())
    CONVERSATIONS.setdefault(conversation_id, [])
    existing = CONVERSATION_META.get(conversation_id, {})
    CONVERSATION_META[conversation_id] = {
        "title": str(existing.get("title", title)),
        "updated_at": int(existing.get("updated_at", now)),
        "student_id": str(existing.get("student_id") or student_id),
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


@app.get("/manage", response_class=HTMLResponse)
async def manage(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin.html", {})


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api/auth/me")
async def auth_me(student: dict[str, str] = Depends(require_student)) -> JSONResponse:
    return JSONResponse({"authenticated": True, "student": student})


@app.post("/api/auth/register")
async def auth_register(payload: StudentAuthRequest) -> JSONResponse:
    student_id = _normalize_student_id(payload.student_id)
    display_name = (payload.display_name or student_id).strip() or student_id
    with STUDENT_LOCK:
        store = _load_student_store()
        students = store.setdefault("students", {})
        if student_id in students:
            raise HTTPException(status_code=409, detail="Student account already exists.")
        students[student_id] = {
            "student_id": student_id,
            "display_name": display_name,
            "password_hash": _hash_password(payload.password),
            "created_at": int(time.time()),
        }
        _persist_student_store(store)
    res = JSONResponse(
        {"authenticated": True, "student": {"student_id": student_id, "display_name": display_name}}
    )
    _create_student_session(res, student_id)
    return res


@app.post("/api/auth/login")
async def auth_login(payload: StudentAuthRequest) -> JSONResponse:
    student_id = _normalize_student_id(payload.student_id)
    with STUDENT_LOCK:
        store = _load_student_store()
        record = store.get("students", {}).get(student_id)
    if not record or not _verify_password(payload.password, str(record.get("password_hash", ""))):
        raise HTTPException(status_code=401, detail="Invalid student ID or password.")
    res = JSONResponse({"authenticated": True, "student": _public_student(student_id, record)})
    _create_student_session(res, student_id)
    return res


@app.post("/api/auth/logout")
async def auth_logout(request: Request) -> JSONResponse:
    res = JSONResponse({"authenticated": False})
    _clear_student_session(request, res)
    return res


# ── Knowledge Base endpoints ──


@app.post("/api/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    _: None = Depends(require_admin_api_key),
) -> JSONResponse:
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
async def delete_document(
    filename: str,
    _: None = Depends(require_admin_api_key),
) -> JSONResponse:
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
async def training_start(_: None = Depends(require_admin_api_key)) -> JSONResponse:
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
async def create_conversation(student: dict[str, str] = Depends(require_student)) -> JSONResponse:
    conversation_id = str(uuid4())
    with SESSION_LOCK:
        _ensure_conversation(conversation_id, student_id=student["student_id"])
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
async def list_conversations(student: dict[str, str] = Depends(require_student)) -> JSONResponse:
    items: list[dict[str, str | int]] = []
    with SESSION_LOCK:
        for cid, meta in CONVERSATION_META.items():
            if str(meta.get("student_id", "")) != student["student_id"]:
                continue
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
async def get_conversation(
    conversation_id: str,
    student: dict[str, str] = Depends(require_student),
) -> JSONResponse:
    with SESSION_LOCK:
        meta = CONVERSATION_META.get(conversation_id, {})
        if str(meta.get("student_id", "")) != student["student_id"]:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = CONVERSATIONS.get(conversation_id, [])
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
async def chat(
    payload: ChatRequest,
    student: dict[str, str] = Depends(require_student),
) -> StreamingResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")
    conversation_id = payload.conversation_id or str(uuid4())

    with SESSION_LOCK:
        existing_meta = CONVERSATION_META.get(conversation_id)
        if existing_meta and str(existing_meta.get("student_id", "")) != student["student_id"]:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if payload.new_chat or conversation_id not in CONVERSATIONS:
            _ensure_conversation(conversation_id, student_id=student["student_id"])
            _persist_session_store()

    def save_history(answer: str) -> None:
        with SESSION_LOCK:
            _ensure_conversation(conversation_id, student_id=student["student_id"])
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
                "student_id": student["student_id"],
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
