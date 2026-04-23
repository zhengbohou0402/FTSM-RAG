"""
RAG 摘要服务：为用户问题检索参考文档，并将问题与上下文一并发送给模型生成最终回答。
RAG summarization service: retrieve reference documents for a user query and
send both the query and context to the model for a final answer.

增强：集成中文预处理（繁转简 + 同义词扩展），对扩展后的多个查询分别检索并去重合并。
"""

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from model.factory import get_chat_model
from rag.vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompts
from utils.query_preprocessor import preprocessor


class RagSummarizeService(object):
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.retriever = self.vector_store.get_retriever()
        self.prompt_text = load_rag_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = get_chat_model()
        self.chain = self._init_chain()

    def _init_chain(self):
        chain = self.prompt_template | self.model | StrOutputParser()
        return chain

    def retriever_docs(self, query: str) -> list[Document]:
        """
        多查询检索：先做中文预处理，对原始查询 + 扩展查询分别检索，
        按 page_content 去重后合并，保证不超过 k*2 条。
        """
        queries = preprocessor.process(query)
        seen: set[str] = set()
        merged: list[Document] = []

        for q in queries:
            for doc in self.retriever.invoke(q):
                key = doc.page_content[:100]   # 用前 100 字符作去重键
                if key not in seen:
                    seen.add(key)
                    merged.append(doc)

        return merged

    def rag_summarize(self, query: str) -> str:
        context_docs = self.retriever_docs(query)

        context = ""
        counter = 0
        for doc in context_docs:
            counter += 1
            context += (
                f"[Reference {counter}] Content: {doc.page_content} | "
                f"Metadata: {doc.metadata}\n"
            )

        return self.chain.invoke(
            {
                "input": query,
                "context": context,
            }
        )


if __name__ == "__main__":
    rag = RagSummarizeService()
    print(rag.rag_summarize("Which robot vacuum is suitable for a small apartment?"))
