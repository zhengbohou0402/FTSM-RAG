import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymysql
import pymysql.cursors

from dotenv import load_dotenv
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

load_dotenv(BASE_DIR / ".env")

WEB_DIR = BASE_DIR / "web"

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ftsm_rag")

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

# ── MySQL 连接 ──

def _new_mysql_conn() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


_DB_LOCAL = threading.local()


@contextmanager
def get_db():
    """每个线程维护一个 MySQL 连接，自动重连断线连接。"""
    conn = getattr(_DB_LOCAL, "conn", None)
    if conn is None:
        conn = _new_mysql_conn()
        _DB_LOCAL.conn = conn
    else:
        try:
            conn.ping(reconnect=True)
        except Exception:
            conn = _new_mysql_conn()
            _DB_LOCAL.conn = conn

    conn.begin()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _init_db() -> None:
    """启动时确保四张表存在。"""
    conn = _new_mysql_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    student_id    VARCHAR(80)  NOT NULL PRIMARY KEY,
                    display_name  VARCHAR(80)  NOT NULL,
                    password_hash VARCHAR(200) NOT NULL,
                    created_at    INT UNSIGNED NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token      VARCHAR(64)  NOT NULL PRIMARY KEY,
                    student_id VARCHAR(80)  NOT NULL,
                    expires_at INT UNSIGNED NOT NULL,
                    INDEX idx_sessions_student (student_id),
                    INDEX idx_sessions_expires (expires_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id         VARCHAR(36)  NOT NULL PRIMARY KEY,
                    student_id VARCHAR(80)  NOT NULL,
                    title      VARCHAR(200) NOT NULL DEFAULT 'New chat',
                    updated_at INT UNSIGNED NOT NULL,
                    INDEX idx_conv_student (student_id, updated_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    conversation_id VARCHAR(36)     NOT NULL,
                    role            ENUM('user','assistant') NOT NULL,
                    content         MEDIUMTEXT      NOT NULL,
                    created_at      INT UNSIGNED    NOT NULL,
                    INDEX idx_msg_conv (conversation_id, id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
    finally:
        conn.close()


# ── Training worker ──

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


app = FastAPI(title="FTSM-RAG")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

agent = ReactAgent()
semantic_cache = SemanticCache(threshold=0.92)

CHAR_STREAM_DELAY_SECONDS = 0.006
MAX_CONVERSATION_ITEMS = 200
MAX_EXPOSED_CONVERSATIONS = 50
MAX_HISTORY_TURNS = 5


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = Field(default=None)
    new_chat: bool = Field(default=False)


class StudentAuthRequest(BaseModel):
    student_id: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=6, max_length=200)
    display_name: str | None = Field(default=None, max_length=80)


# ── 工具函数 ──

def _normalize_student_id(student_id: str) -> str:
    normalized = student_id.strip().lower()
    if not re.fullmatch(r"[a-z0-9@._-]{3,80}", normalized):
        raise HTTPException(
            status_code=400,
            detail="Student ID can only contain letters, numbers, @, dot, underscore, or hyphen.",
        )
    return normalized


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


# ── Session ──

def _create_student_session(response: Response, student_id: str) -> None:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + AUTH_SESSION_TTL_SECONDS
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO auth_sessions (token, student_id, expires_at) VALUES (%s,%s,%s)",
                (token, student_id, expires_at),
            )
    response.set_cookie(
        AUTH_COOKIE_NAME, token,
        max_age=AUTH_SESSION_TTL_SECONDS,
        httponly=True, samesite="lax",
    )


def _clear_student_session(request: Request, response: Response) -> None:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM auth_sessions WHERE token=%s", (token,))
    response.delete_cookie(AUTH_COOKIE_NAME)


def _cleanup_expired_sessions() -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_sessions WHERE expires_at<%s", (int(time.time()),))


def require_student(request: Request) -> dict[str, str]:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT student_id, expires_at FROM auth_sessions WHERE token=%s", (token,)
            )
            row = cur.fetchone()
    if not row or row["expires_at"] < int(time.time()):
        if row:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM auth_sessions WHERE token=%s", (token,))
        raise HTTPException(status_code=401, detail="Login required")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT student_id, display_name FROM students WHERE student_id=%s",
                (row["student_id"],),
            )
            student = cur.fetchone()
    if not student:
        raise HTTPException(status_code=401, detail="Login required")
    return {"student_id": student["student_id"], "display_name": student["display_name"]}


def require_admin_api_key(x_admin_api_key: str | None = Header(default=None)) -> None:
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_API_KEY is not configured on the server.")
    if not x_admin_api_key or x_admin_api_key.strip() != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── 对话 / 消息 ──

def _get_conversation_owner(conversation_id: str) -> str | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT student_id FROM conversations WHERE id=%s", (conversation_id,)
            )
            row = cur.fetchone()
    return row["student_id"] if row else None


def _ensure_conversation(conversation_id: str, title: str = "New chat", student_id: str = "") -> None:
    now = int(time.time())
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM conversations WHERE id=%s", (conversation_id,))
            exists = cur.fetchone()
            if not exists:
                cur.execute(
                    "INSERT INTO conversations (id, student_id, title, updated_at) VALUES (%s,%s,%s,%s)",
                    (conversation_id, student_id, title, now),
                )


def _update_conversation_title(conversation_id: str, title: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET title=%s, updated_at=%s WHERE id=%s",
                (title, int(time.time()), conversation_id),
            )


def _save_messages(conversation_id: str, user_msg: str, assistant_msg: str) -> None:
    now = int(time.time())
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (%s,%s,%s,%s)",
                (conversation_id, "user", user_msg, now),
            )
            cur.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (%s,%s,%s,%s)",
                (conversation_id, "assistant", assistant_msg, now),
            )
            # 只保留最近 40 条
            cur.execute(
                """
                DELETE FROM messages WHERE conversation_id=%s
                AND id NOT IN (
                    SELECT id FROM (
                        SELECT id FROM messages WHERE conversation_id=%s
                        ORDER BY id DESC LIMIT 40
                    ) AS t
                )
                """,
                (conversation_id, conversation_id),
            )


def _get_recent_messages(conversation_id: str, max_turns: int = 5) -> list[dict[str, str]]:
    limit = max_turns * 2
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content FROM messages
                    WHERE conversation_id=%s ORDER BY id DESC LIMIT %s
                ) AS t ORDER BY id ASC
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def _prune_conversations(student_id: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM conversations WHERE student_id=%s", (student_id,)
            )
            cnt = cur.fetchone()["cnt"]
            if cnt > MAX_CONVERSATION_ITEMS:
                cur.execute(
                    """
                    DELETE FROM conversations WHERE student_id=%s
                    AND id NOT IN (
                        SELECT id FROM (
                            SELECT id FROM conversations WHERE student_id=%s
                            ORDER BY updated_at DESC LIMIT %s
                        ) AS t
                    )
                    """,
                    (student_id, student_id, MAX_CONVERSATION_ITEMS),
                )


# ── FastAPI 生命周期 ──

@app.on_event("startup")
async def _startup():
    _init_db()
    _cleanup_expired_sessions()
    start_scheduler()


@app.on_event("shutdown")
async def _shutdown():
    stop_scheduler()


# ── 路由 ──

@app.get("/api/scheduler/status")
async def scheduler_status_api() -> JSONResponse:
    return JSONResponse(scheduler_status())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/manage", response_class=HTMLResponse)
async def manage(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin.html", {})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings.html", {})


# ── Settings API（Admin Key 保护） ──

def _parse_env_file(env_path: Path) -> dict[str, str]:
    """读取 .env 文件，返回 key-value 字典（跳过注释行）。"""
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env_file(env_path: Path, updates: dict[str, str]) -> None:
    """把 updates 写入 .env，已有 key 原地更新，新 key 追加到末尾。"""
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
    admin_api_key: str = Field(default="")


@app.get("/api/settings")
async def get_settings(x_admin_api_key: str = Header(default="")) -> JSONResponse:
    if ADMIN_API_KEY and x_admin_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key.")
    env = _parse_env_file(BASE_DIR / ".env")
    return JSONResponse({
        "dashscope_api_key": env.get("DASHSCOPE_API_KEY", ""),
        "admin_api_key":     env.get("ADMIN_API_KEY", ""),
    })


@app.post("/api/settings")
async def save_settings(
    payload: SettingsPayload,
    x_admin_api_key: str = Header(default=""),
) -> JSONResponse:
    if ADMIN_API_KEY and x_admin_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key.")
    updates: dict[str, str] = {}
    if payload.dashscope_api_key:
        updates["DASHSCOPE_API_KEY"] = payload.dashscope_api_key
    if payload.admin_api_key:
        updates["ADMIN_API_KEY"] = payload.admin_api_key
    if updates:
        _write_env_file(BASE_DIR / ".env", updates)
        # 立即生效到当前进程环境变量
        for k, v in updates.items():
            os.environ[k] = v
    return JSONResponse({"ok": True, "updated": list(updates.keys())})


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api/auth/me")
async def auth_me(student: dict[str, str] = Depends(require_student)) -> JSONResponse:
    return JSONResponse({"authenticated": True, "student": student})


@app.post("/api/auth/register")
async def auth_register(payload: StudentAuthRequest, response: Response) -> JSONResponse:
    student_id = _normalize_student_id(payload.student_id)
    display_name = (payload.display_name or student_id).strip() or student_id
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT student_id FROM students WHERE student_id=%s", (student_id,))
            exists = cur.fetchone()
            if exists:
                raise HTTPException(status_code=409, detail="Student account already exists.")
            cur.execute(
                "INSERT INTO students (student_id, display_name, password_hash, created_at) VALUES (%s,%s,%s,%s)",
                (student_id, display_name, _hash_password(payload.password), int(time.time())),
            )
    res = JSONResponse(
        {"authenticated": True, "student": {"student_id": student_id, "display_name": display_name}}
    )
    _create_student_session(res, student_id)
    return res


@app.post("/api/auth/login")
async def auth_login(payload: StudentAuthRequest) -> JSONResponse:
    student_id = _normalize_student_id(payload.student_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT student_id, display_name, password_hash FROM students WHERE student_id=%s",
                (student_id,),
            )
            record = cur.fetchone()
    if not record or not _verify_password(payload.password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid student ID or password.")
    res = JSONResponse(
        {"authenticated": True, "student": {"student_id": record["student_id"], "display_name": record["display_name"]}}
    )
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

    training_started = False
    if saved:
        training_started = _start_training()
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
async def delete_document(
    filename: str,
    _: None = Depends(require_admin_api_key),
) -> JSONResponse:
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
    started = _start_training()
    return JSONResponse(
        {
            "started": started,
            "message": "Training already running — marked as pending" if not started else "Training started",
        }
    )


@app.post("/api/conversations")
async def create_conversation(student: dict[str, str] = Depends(require_student)) -> JSONResponse:
    conversation_id = str(uuid4())
    _ensure_conversation(conversation_id, student_id=student["student_id"])
    return JSONResponse(
        {"id": conversation_id, "title": "New chat", "updated_at": int(time.time()), "messages": []}
    )


@app.get("/api/conversations")
async def list_conversations(student: dict[str, str] = Depends(require_student)) -> JSONResponse:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, updated_at FROM conversations
                WHERE student_id=%s ORDER BY updated_at DESC LIMIT %s
                """,
                (student["student_id"], MAX_EXPOSED_CONVERSATIONS),
            )
            rows = cur.fetchall()
    return JSONResponse({"items": [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"]} for r in rows]})


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    student: dict[str, str] = Depends(require_student),
) -> JSONResponse:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, student_id, title, updated_at FROM conversations WHERE id=%s",
                (conversation_id,),
            )
            conv = cur.fetchone()
    if not conv or conv["student_id"] != student["student_id"]:
        raise HTTPException(status_code=404, detail="Conversation not found")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM messages WHERE conversation_id=%s ORDER BY id ASC",
                (conversation_id,),
            )
            msgs = cur.fetchall()
    return JSONResponse(
        {
            "id": conv["id"],
            "title": conv["title"],
            "updated_at": conv["updated_at"],
            "messages": [{"role": m["role"], "content": m["content"]} for m in msgs],
        }
    )


@app.get("/api/cache/stats")
async def cache_stats() -> JSONResponse:
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

    owner = _get_conversation_owner(conversation_id)
    if owner and owner != student["student_id"]:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if payload.new_chat or not owner:
        _ensure_conversation(conversation_id, student_id=student["student_id"])

    def save_history(answer: str) -> None:
        title = message.strip()
        if len(title) > 40:
            title = f"{title[:40]}..."
        _save_messages(conversation_id, message, answer)
        _update_conversation_title(conversation_id, title or "New chat")
        _prune_conversations(student["student_id"])

    def stream_response():
        hit, cached_answer = semantic_cache.get(message)
        # 若缓存内容包含控制标记（历史脏数据），跳过缓存重新走 agent
        if hit and cached_answer and "__THINK" not in cached_answer:
            yield "__THINK__Answering from cache...__ENDTHINK__"
            save_history(cached_answer)
            for char in cached_answer:
                yield char
                time.sleep(CHAR_STREAM_DELAY_SECONDS)
            return

        recent_history = _get_recent_messages(conversation_id, MAX_HISTORY_TURNS)

        result_chunks: list[str] = []
        for chunk in agent.execute_stream(message, history=recent_history):
            if not chunk:
                continue
            # 工具调用提示标记直接转发，不逐字符、不计入最终答案
            if chunk.startswith("__THINK__"):
                yield chunk
                continue
            result_chunks.append(chunk)
            for char in chunk:
                yield char
                time.sleep(CHAR_STREAM_DELAY_SECONDS)

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
