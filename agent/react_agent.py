from langgraph.prebuilt import create_react_agent

from agent.tools.agent_tools import rag_summarize
from model.factory import create_chat_model
from utils.prompt_loader import load_system_prompts

class ReactAgent:
    def __init__(self):
        self.agent = create_react_agent(
            model=create_chat_model(streaming=True),
            prompt=load_system_prompts(),
            tools=[rag_summarize],
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

        for message_chunk, metadata in self.agent.stream(
            input_dict,
            stream_mode="messages",
            context={"report": False},
        ):
            node = metadata.get("langgraph_node")
            if node == "tools":
                continue

            if node == "agent":
                content = getattr(message_chunk, "content", "") or ""
                tool_calls = getattr(message_chunk, "tool_calls", None)
                tool_call_chunks = getattr(message_chunk, "tool_call_chunks", None)

                if tool_calls and not tool_search_emitted:
                    tool_search_emitted = True
                    yield "__THINK__Searching knowledge base...__ENDTHINK__"

                if tool_call_chunks:
                    continue

                if content and not tool_calls:
                    yield content


if __name__ == "__main__":
    agent = ReactAgent()
    for chunk in agent.execute_stream("What facilities are available at UKM FTSM?"):
        print(chunk, end="", flush=True)
