from langchain.agents import create_agent

from agent.tools.agent_tools import rag_summarize
from agent.tools.middleware import log_before_model, monitor_tool
from model.factory import create_chat_model
from utils.prompt_loader import load_system_prompts


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=create_chat_model(streaming=True),
            system_prompt=load_system_prompts(),
            tools=[rag_summarize],
            middleware=[monitor_tool, log_before_model],
        )

    def _analyze_query_intent(self, query: str) -> str:
        """Analyze the user's query and return a brief intent description."""
        query_lower = query.lower()
        
        # Holiday related
        if any(kw in query_lower for kw in ['holiday', '假期', 'public holiday', '节假日', 'deepavali', 'hari raya', 'christmas', 'new year', 'chinese new year']):
            return 'Searching Malaysian public holidays'
        # Academic calendar
        if any(kw in query_lower for kw in ['calendar', '日历', 'semester', '学期', 'schedule', '安排']):
            return 'Searching academic calendar'
        # Timetable
        if any(kw in query_lower for kw in ['timetable', '时间表', 'course', '课程', 'class', '课程表']):
            return 'Searching course timetables'
        # Advisor/Supervisor
        if any(kw in query_lower for kw in ['advisor', '导师', 'supervisor', 'professor', '教授', 'staff', '教师']):
            return 'Searching advisor information'
        # Admission
        if any(kw in query_lower for kw in ['admission', '入学', 'apply', '申请', 'requirement', '要求', 'program', '专业']):
            return 'Searching admission requirements'
        # Visa
        if any(kw in query_lower for kw in ['visa', '签证', 'renew', '续签', 'pass', '准证']):
            return 'Searching visa information'
        # Facilities
        if any(kw in query_lower for kw in ['facility', '设施', 'library', '图书馆', 'lab', '实验室', 'service', '服务']):
            return 'Searching campus facilities'
        # Contact
        if any(kw in query_lower for kw in ['contact', '联系', 'phone', '电话', 'email', '邮箱', 'office', '办公室']):
            return 'Searching contact information'
        # Registration
        if any(kw in query_lower for kw in ['register', '注册', 'enroll', 'enrolment', '报名']):
            return 'Searching registration info'
        # Default
        return 'Analyzing question'

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

        # Step 1: Analyze user intent
        intent = self._analyze_query_intent(query)
        yield f"__THINK__{intent}...__ENDTHINK__"

        thinking_emitted = False
        generating_answer = False

        for message_chunk, metadata in self.agent.stream(
            input_dict,
            stream_mode="messages",
            context={"report": False},
        ):
            node = metadata.get("langgraph_node")

            if node == "model":
                tool_calls = getattr(message_chunk, "tool_calls", None)
                
                # Step 2: Searching knowledge base
                if tool_calls and not thinking_emitted:
                    thinking_emitted = True
                    for tc in tool_calls:
                        q = tc.get("args", {}).get("query", "")
                        if q:
                            yield f"__THINK__Searching: {q}__ENDTHINK__"

                # Skip tool call chunks
                if getattr(message_chunk, "tool_call_chunks", None):
                    continue

                # Step 3: Generating answer
                content = getattr(message_chunk, "content", "")
                if isinstance(content, str) and content:
                    if not generating_answer and not tool_calls:
                        generating_answer = True
                        yield f"__THINK__Generating answer...__ENDTHINK__"
                    if not tool_calls:
                        yield content


if __name__ == "__main__":
    agent = ReactAgent()

    for chunk in agent.execute_stream("What facilities are available at UKM FTSM?"):
        print(chunk, end="", flush=True)
