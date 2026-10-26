"""Client for the Java ftsm-conversation service (per-student storage).

The gateway verifies the ftsm_student_session cookie, strips any client-supplied
X-Student-Id, and injects the verified one before forwarding to ftsm-rag. When a
chat request carries that header we mirror every turn into the Java service so
the history sidebar (routed to ftsm-conversation by the gateway) stays in sync
with the locally-persisted copy. All calls are best-effort: on failure we log
and fall back to the in-process ConversationStore only.
"""
from __future__ import annotations

import os
from typing import Any

import requests
from utils.logger_handler import logger

_CONVERSATION_URI = os.environ.get("FTSM_CONVERSATION_URI", "http://127.0.0.1:8102").rstrip("/")
_TIMEOUT = 5


def append_turn(
    conversation_id: str,
    student_id: str,
    user_content: str,
    assistant_content: str,
    title: str | None = None,
) -> bool:
    """Mirror one chat turn into ftsm-conversation. Auto-creates the conversation."""
    if not student_id:
        return False
    try:
        res = requests.post(
            f"{_CONVERSATION_URI}/internal/conversations/{conversation_id}/turn",
            json={
                "studentId": student_id,
                "userContent": user_content,
                "assistantContent": assistant_content,
                "title": title or "New chat",
            },
            timeout=_TIMEOUT,
        )
        if res.status_code != 200:
            logger.warning(
                "[conversation_client] append_turn failed: %s %s",
                res.status_code,
                res.text[:200],
            )
            return False
        return True
    except Exception as exc:
        logger.warning("[conversation_client] append_turn error: %s", exc)
        return False


def recent_messages(conversation_id: str, student_id: str, max_turns: int) -> list[dict[str, str]] | None:
    """Fetch recent turns for LLM context. Returns None when the remote service is unavailable."""
    if not student_id:
        return None
    try:
        res = requests.get(
            f"{_CONVERSATION_URI}/internal/conversations/{conversation_id}/recent",
            params={"studentId": student_id, "maxTurns": max_turns},
            timeout=_TIMEOUT,
        )
        if res.status_code != 200:
            return None
        data = res.json()
        return [
            {"role": m["role"], "content": m["content"]}
            for m in data
            if isinstance(m, dict) and m.get("role") and "content" in m
        ]
    except Exception as exc:
        logger.warning("[conversation_client] recent_messages error: %s", exc)
        return None
