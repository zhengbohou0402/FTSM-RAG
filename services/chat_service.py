from typing import Any, Callable, Iterator

import time

from services import conversation_client

# Simulated typing cadence for cache hits: small chunks + short sleeps so a
# cached answer still feels like a live streamed response instead of a dump.
_CACHE_CHUNK_CHARS = 6
_CACHE_CHUNK_DELAY_S = 0.012


_EXTRA_REFUSAL_MARKERS = (
    "does not contain enough confirmed information",
    "not contain enough confirmed information",
    "please verify through the official",
    "verify through the official",
    "apologize",
    "i cannot answer",
)


def _is_cacheable_answer(answer: str) -> bool:
    if not answer or len(answer.strip()) < 15:
        return False
    lower = answer.lower()
    try:
        from agent.react_agent import _REFUSAL_MARKERS
        if any(marker in lower for marker in _REFUSAL_MARKERS):
            return False
    except Exception:
        pass
    if any(marker in lower for marker in _EXTRA_REFUSAL_MARKERS):
        return False
    if "[error]" in lower:
        return False
    return True


def _stream_cached(text: str) -> Iterator[str]:
    for i in range(0, len(text), _CACHE_CHUNK_CHARS):
        yield text[i : i + _CACHE_CHUNK_CHARS]
        time.sleep(_CACHE_CHUNK_DELAY_S)


def stream_chat_answer(
    *,
    message: str,
    conversation_id: str,
    conversation_store: Any,
    semantic_cache: Any,
    get_agent: Callable[[], Any],
    cache_namespace: Callable[[], str],
    max_history_turns: int,
    student_id: str | None = None,
) -> Iterator[str]:
    def save_history(answer: str) -> None:
        title = message if len(message) <= 40 else f"{message[:40]}..."
        conversation_store.append_turn(
            conversation_id,
            user_content=message,
            assistant_content=answer,
            title=title or "New chat",
        )
        if student_id:
            conversation_client.append_turn(
                conversation_id,
                student_id,
                message,
                answer,
                title=title or "New chat",
            )

    # When the request comes through the gateway we have a verified student id:
    # ftsm-conversation is the source of truth for history (the local store may
    # not know conversations created there). Fall back to the local store ONLY
    # when ftsm-conversation is unavailable (returned None) or no student_id.
    remote_history = (
        conversation_client.recent_messages(conversation_id, student_id, max_history_turns)
        if student_id
        else None
    )
    if remote_history is not None:
        recent_history = remote_history
    else:
        recent_history = conversation_store.recent_messages(conversation_id, max_history_turns)

    namespace = cache_namespace()
    if not recent_history:
        hit, cached_answer = semantic_cache.get(message, namespace=namespace)
        if hit and cached_answer and "__THINK" not in cached_answer:
            yield "__THINK__Answering from cache...__ENDTHINK__"
            save_history(cached_answer)
            # Re-stream the cached answer in small chunks so the UI keeps the
            # same flowing/typing effect as a live LLM response.
            yield from _stream_cached(cached_answer)
            return

    result_chunks: list[str] = []
    had_error = False
    try:
        for chunk in get_agent().execute_stream(message, history=recent_history):
            if not chunk:
                continue
            if chunk.startswith("__THINK__"):
                yield chunk
                continue
            result_chunks.append(chunk)
            yield chunk
    except Exception as exc:
        had_error = True
        err_msg = f"\n\n[Error] {exc}"
        result_chunks.append(err_msg)
        yield err_msg

    final_answer = "".join(result_chunks).strip()
    if final_answer:
        if not had_error and not recent_history and _is_cacheable_answer(final_answer):
            semantic_cache.set(message, final_answer, namespace=namespace)
        save_history(final_answer)
