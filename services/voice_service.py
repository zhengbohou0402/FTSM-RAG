"""Voice services for FTSM-RAG: TTS (Cloud TTS Chirp 3 HD) + STT (Gemini multimodal).

- TTS: texttospeech.googleapis.com authenticated with the project ADC
  (authorized_user credentials, same file the Vertex chat backend uses).
  Voice is picked automatically: CJK-dominant text -> cmn-CN, otherwise en-US.
  Returns a 24 kHz mono 16-bit WAV so the browser can play it directly.
- STT: reuses the chat multimodal model (Gemini via Vertex) with an inline
  audio data URI — same content-block pattern as image OCR in file_handler.
"""
from __future__ import annotations

import base64
import io
import os
import re
import struct
import threading

import requests
from utils.logger_handler import logger

_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
_TTS_TIMEOUT = 30
_MAX_SPEECH_CHARS = 2500

_auth_lock = threading.Lock()
_auth_cache: tuple[object, str] | None = None  # (credentials, project_id)


def _get_credentials() -> tuple[object, str]:
    """Load ADC credentials + project id (cached; refreshed on expiry)."""
    global _auth_cache
    with _auth_lock:
        if _auth_cache is not None:
            return _auth_cache
        import google.auth
        import google.auth.transport.requests

        explicit = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if explicit and os.path.exists(explicit):
            import google.oauth2.credentials

            creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
                explicit,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            if not creds.valid:
                creds.refresh(google.auth.transport.requests.Request())
            project = (
                os.environ.get("VERTEX_PROJECT_ID")
                or getattr(creds, "quota_project_id", "")
                or ""
            )
        else:
            creds, project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not project:
            project = os.environ.get("VERTEX_PROJECT_ID", "")
        _auth_cache = (creds, project)
        return _auth_cache


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk / max(1, len(text))


def _split_long_sentences(text: str, max_len: int = 180) -> str:
    """Cloud TTS rejects sentences without ending punctuation that are too long.

    Key facts learned the hard way:
    - TTS does NOT treat newlines as sentence ends — every segment must carry
      its own terminal punctuation or TTS joins it with the following text,
      producing a mega-sentence and a 400 error.
    - A trailing colon is also not a sentence end (convert to a period).
    """
    out: list[str] = []
    for para in text.split("\n"):
        for sent in re.split(r"(?<=[.!?。！？])\s+", para):
            sent = sent.strip()
            if not sent:
                continue
            if sent.endswith(":"):
                sent = sent[:-1] + "."
            elif not sent.endswith((".", "!", "?", "。", "！", "？")):
                sent += "."
            if len(sent) <= max_len:
                out.append(sent)
                continue
            cur = ""
            for word in sent.split(" "):
                if cur and len(cur) + 1 + len(word) > max_len:
                    # A period is required: TTS counts sentences by punctuation,
                    # newlines do not terminate a sentence.
                    out.append(cur.rstrip(",;:、 ") + ".")
                    cur = word
                else:
                    cur = f"{cur} {word}".strip()
            if cur:
                out.append(cur if sent.endswith((".", "!", "?", "。", "！", "？")) else cur + ".")
    return "\n".join(out)


def strip_markdown_for_speech(text: str) -> str:
    """Strip markdown decorations + trailing Sources block so TTS reads cleanly."""
    # Drop the trailing Sources block entirely
    lines = text.split("\n")
    cut = len(lines)
    for i, line in enumerate(lines):
        if re.match(r"^\s*(?:#{1,6}\s*)?\*{0,2}\s*sources:?\s*\*{0,2}\s*$", line, re.I):
            cut = i
            break
    cleaned = "\n".join(lines[:cut])
    # Inline decorations
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)          # inline code
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)     # bold
    cleaned = re.sub(r"(^|[\s(])\*([^*\n]+)\*", r"\1\2", cleaned)  # italic
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.M)  # headings
    cleaned = re.sub(r"^\s*[-*]\s+", "• ", cleaned, flags=re.M)  # bullets -> spoken pause
    cleaned = re.sub(r"^\s*\d+[.)]\s+", "", cleaned, flags=re.M)  # ordered markers
    cleaned = re.sub(r"\[\s*References?\b[^\]]*\]", "", cleaned)  # citation badges
    cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cleaned)  # [label](url) -> label
    # Remove exotic unicode (emoji, symbols, musical glyphs, stray surrogates) that
    # makes Cloud TTS return 400 — keep ASCII, latin accents, CJK and CJK punct.
    cleaned = re.sub(
        r"[^\x09\x0a\x0d\x20-\x7e\u00a0-\u024f\u2010-\u205e\u3000-\u303f"
        r"\u4e00-\u9fff\uff00-\uffef]",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # Drop horizontal rules / decoration-only lines (e.g. "---") — TTS would
    # read them as stray punctuation and they serve no spoken purpose.
    cleaned = re.sub(r"(?m)^\s*[-=*_~—–]{3,}\s*$", "", cleaned)
    cleaned = _split_long_sentences(cleaned.strip())
    return cleaned.strip()[:_MAX_SPEECH_CHARS]


def _wrap_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap raw mono 16-bit PCM into a 44-byte-header WAV."""
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(pcm)))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(pcm)))
    buf.write(pcm)
    return buf.getvalue()


def synthesize_speech(text: str) -> bytes:
    """Cloud TTS (Chirp 3 HD) -> 24 kHz mono WAV. Raises on failure."""
    creds, project = _get_credentials()
    if not creds.valid:
        import google.auth.transport.requests

        creds.refresh(google.auth.transport.requests.Request())
    language = "cmn-CN" if _cjk_ratio(text) > 0.3 else "en-US"
    body = {
        "input": {"text": text},
        "voice": {"languageCode": language, "name": f"{language}-Chirp3-HD-Aoede"},
        "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000},
    }
    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
    if project:
        headers["x-goog-user-project"] = project
    res = requests.post(_TTS_URL, json=body, headers=headers, timeout=_TTS_TIMEOUT)
    if res.status_code != 200:
        raise RuntimeError(f"TTS HTTP {res.status_code}: {res.text[:800]}")
    audio = res.json().get("audioContent", "")
    if not audio:
        raise RuntimeError("TTS returned empty audioContent")
    return _wrap_wav(base64.b64decode(audio))


def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    """Gemini multimodal transcription of a short audio clip (WAV/MP3/OGG)."""
    from langchain_core.messages import HumanMessage

    from model.factory import get_chat_model

    message = HumanMessage(
        content=[
            # langchain-google-vertexai "media" block: raw bytes, not base64
            {"type": "media", "mime_type": mime_type, "data": audio_bytes},
            {
                "type": "text",
                "text": "请把这段语音转写为文字，只输出转写结果本身，不要任何解释、标点修饰或额外内容。",  # noqa: E501
            },
        ]
    )
    response = get_chat_model().invoke([message])
    content = response.content
    if isinstance(content, list):  # content blocks -> join text parts
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return (content or "").strip()


def reset_credentials_cache() -> None:
    global _auth_cache
    with _auth_lock:
        _auth_cache = None
