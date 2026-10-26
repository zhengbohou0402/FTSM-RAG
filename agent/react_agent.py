import re

from langchain.agents import create_agent

from agent.tools.agent_tools import rag_summarize
from agent.tools.middleware import log_before_model, monitor_tool
from model.factory import create_chat_model
from utils.prompt_loader import load_system_prompts

_SOURCES_HEADING_RE = re.compile(
    r"(?m)^\s*(?:#{1,6}\s*)?\*{0,2}\s*sources:?\s*\*{0,2}\s*$",
    re.IGNORECASE,
)
_REFUSAL_MARKERS = (
    "does not contain enough confirmed information",
    "does not confirm the answer",
    "does not contain the answer",
    "not mentioned in the available",
    "没有足够确认的信息",
    "未包含",
    "没有提及",
    "无法确认",
    "tiada maklumat",
)


def _extract_sources_trailer(tool_output: str) -> str:
    """从 rag_summarize 工具返回中提取尾部的 Source reliability + Sources 块。"""
    if not tool_output or "\nSources:\n" not in tool_output:
        return ""
    idx = tool_output.find("\nSource reliability:")
    if idx != -1:
        return tool_output[idx + 1 :].strip()
    src_idx = tool_output.find("\nSources:\n")
    return tool_output[src_idx + 1 :].strip() if src_idx != -1 else ""


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=create_chat_model(streaming=True),
            system_prompt=load_system_prompts(),
            tools=[rag_summarize],
            middleware=[monitor_tool, log_before_model],
        )

    def execute_stream(self, query: str, history: list[dict] | None = None):
        """
        Args:
            query:   当前用户消息
            history: 历史消息列表，格式 [{"role": "user"/"assistant", "content": "..."}]
                     最多传最近 N 轮，由调用方控制长度
        """
        messages = list(history) if history else []
        messages.append({"role": "user", "content": query})
        input_dict = {"messages": messages}

        tool_search_emitted = False
        sources_trailer = ""
        emitted_parts: list[str] = []

        for message_chunk, metadata in self.agent.stream(
            input_dict,
            stream_mode="messages",
            context={"report": False},
        ):
            node = metadata.get("langgraph_node")
            if node == "tools":
                tool_text = str(getattr(message_chunk, "content", "") or "")
                extracted = _extract_sources_trailer(tool_text)
                if extracted:
                    sources_trailer = extracted
                continue

            if node == "model":
                content = getattr(message_chunk, "content", "") or ""
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    )
                tool_calls = getattr(message_chunk, "tool_calls", None)
                tool_call_chunks = getattr(message_chunk, "tool_call_chunks", None)

                if tool_calls and not tool_search_emitted:
                    tool_search_emitted = True
                    yield "__THINK__Searching knowledge base...__ENDTHINK__"

                if tool_call_chunks:
                    continue

                if content and not tool_calls:
                    emitted_parts.append(content)
                    yield content

        # P1-4：工具不再跑内层 LLM，也不让外层 LLM 逐 token 复述 Sources 尾块；
        # 流式正文结束后，若工具返回了 Sources 且回答不是拒答、也未自带 Sources，
        # 由系统确定性追加，保证前端（guide.js / desktop useChat.ts）100% 稳定解析。
        full_answer = "".join(emitted_parts).strip()
        if (
            sources_trailer
            and full_answer
            and not _SOURCES_HEADING_RE.search(full_answer)
            and not any(marker in full_answer.lower() for marker in _REFUSAL_MARKERS)
        ):
            yield f"\n\n{sources_trailer}"


if __name__ == "__main__":
    agent = ReactAgent()
    for chunk in agent.execute_stream("What facilities are available at UKM FTSM?"):
        print(chunk, end="", flush=True)

