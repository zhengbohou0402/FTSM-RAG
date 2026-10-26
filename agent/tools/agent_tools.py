import threading

from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService

_rag: RagSummarizeService | None = None
_rag_lock = threading.Lock()


def get_rag_service() -> RagSummarizeService:
    global _rag
    if _rag is None:
        with _rag_lock:
            if _rag is None:
                _rag = RagSummarizeService()
    return _rag


def reset_rag_service() -> None:
    """重置 RAG 服务单例，下次调用时重新构建（含 BM25 索引）。"""
    global _rag
    with _rag_lock:
        _rag = None


@tool(
    description=(
        "Retrieve relevant public reference chunks about UKM FTSM from the knowledge base. / "
        "从知识库检索 UKM FTSM 的相关参考片段与来源元数据。"
    )
)
def rag_summarize(query: str) -> str:
    return get_rag_service().retrieve_for_agent(query)

