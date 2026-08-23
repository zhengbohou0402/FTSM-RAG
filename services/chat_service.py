from typing import Any, Callable, Iterator


def stream_chat_answer(
    *,
    message: str,
    conversation_id: str,
    conversation_store: Any,
    semantic_cache: Any,
    get_agent: Callable[[], Any],
    cache_namespace: Callable[[], str],
    max_history_turns: int,
) -> Iterator[str]:
    def save_history(answer: str) -> None:
        title = message if len(message) <= 40 else f"{message[:40]}..."
        conversation_store.append_turn(
            conversation_id,
            user_content=message,
            assistant_content=answer,
            title=title or "New chat",
        )

    recent_history = conversation_store.recent_messages(conversation_id, max_history_turns)
    namespace = cache_namespace()
    if not recent_history:
        hit, cached_answer = semantic_cache.get(message, namespace=namespace)
        if hit and cached_answer and "__THINK" not in cached_answer:
            yield "__THINK__Answering from cache...__ENDTHINK__"
            save_history(cached_answer)
            yield cached_answer
            return

    result_chunks: list[str] = []
    had_error = False
    try:
        for chunk in get_agent().execute_stream(message, history=recent_history):
            if not chunk:
                continue
            if isinstance(chunk, list):
                text_parts = []
                for part in chunk:
                    if isinstance(part, dict) and 'text' in part:
                        text_parts.append(part['text'])
                    elif isinstance(part, str):
                        text_parts.append(part)
                chunk_str = "".join(text_parts)
            else:
                chunk_str = str(chunk) if not isinstance(chunk, str) else chunk

            if chunk_str.startswith("__THINK__"):
                yield chunk_str
                continue

            result_chunks.append(chunk_str)
            yield chunk_str
    except Exception as exc:
        had_error = True
        err_msg = f"\n\n[Error] {exc}"
        result_chunks.append(err_msg)
        yield err_msg

    final_answer = "".join(result_chunks).strip()
    if final_answer:
        if not had_error and not recent_history:
            semantic_cache.set(message, final_answer, namespace=namespace)
        save_history(final_answer)
