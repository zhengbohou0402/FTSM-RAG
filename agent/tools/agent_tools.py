from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService

_rag: RagSummarizeService | None = None


def get_rag_service() -> RagSummarizeService:
    global _rag
    if _rag is None:
        _rag = RagSummarizeService()
    return _rag


def reset_rag_service() -> None:
    global _rag
    _rag = None


@tool(
    description=(
        "Retrieve relevant public information about UKM FTSM from the vector store. / "
        "从向量库检索 UKM FTSM 的公开资料。"
    )
)
def rag_summarize(query: str) -> str:
    return get_rag_service().rag_summarize(query)
