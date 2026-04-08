from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService

rag = RagSummarizeService()


@tool(
    description=(
        "Retrieve relevant public information about UKM FTSM from the vector store. / "
        "从向量库检索 UKM FTSM 的公开资料。"
    )
)
def rag_summarize(query: str) -> str:
    return rag.rag_summarize(query)
