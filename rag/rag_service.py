"""
RAG 摘要服务：检索参考文档，并将问题与上下文一并发送给模型生成最终回答。

检索流程（三阶段）：
  1. 多查询向量检索 + BM25 关键词检索（扩大召回）
  2. RRF（Reciprocal Rank Fusion）融合排序
  3. DashScope gte-rerank-v2 精排（可选，配置 rerank_top_n > 0 时启用）
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from rank_bm25 import BM25Okapi

from model.factory import get_chat_model
from rag.vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompts
from utils.query_preprocessor import preprocessor

MAX_SOURCES = 5
MAX_SOURCE_EXCERPT_CHARS = 220

# 向量检索和 BM25 各自最多召回条数（RRF 前）
_VECTOR_K = 12
_BM25_K = 12
# Reranker 最终保留 top-N 给 LLM（0 = 禁用 reranker）
_RERANK_TOP_N = 6


def _rrf_fuse(
    ranked_lists: list[list[Document]],
    k: int = 60,
) -> list[Document]:
    """
    Reciprocal Rank Fusion：把多个已排序列表融合为单一排序。
    用 page_content[:100] 作为文档唯一键去重。
    """
    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}

    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked, start=1):
            key = doc.page_content[:100]
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            doc_map[key] = doc

    sorted_keys = sorted(scores, key=lambda k_: scores[k_], reverse=True)
    return [doc_map[k] for k in sorted_keys]


def _rerank(query: str, docs: list[Document], top_n: int) -> list[Document]:
    """
    调用 DashScope gte-rerank-v2 对候选文档精排，返回 top_n 条。
    若 API 不可用则静默降级，原序返回 top_n 条。
    """
    if not docs or top_n <= 0:
        return docs[:top_n] if top_n > 0 else docs
    try:
        import dashscope  # type: ignore
        resp = dashscope.TextReRank.call(
            model="gte-rerank-v2",
            query=query,
            documents=[d.page_content for d in docs],
            top_n=min(top_n, len(docs)),
            return_documents=False,
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        )
        if resp.status_code == 200:
            indices = [r.index for r in resp.output.results]
            return [docs[i] for i in indices]
    except Exception:
        pass
    return docs[:top_n]


class RagSummarizeService(object):
    def __init__(self):
        self.vector_store = VectorStoreService()
        self._vector_retriever = self.vector_store.get_retriever(k=_VECTOR_K)
        self.prompt_text = load_rag_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.chain = None
        # BM25 索引在首次调用时懒加载；用锁保护并发初始化
        self._bm25: BM25Okapi | None = None
        self._bm25_docs: list[Document] = []
        self._bm25_lock = threading.Lock()

    # ── Chain ────────────────────────────────────────────────────────────────

    def _get_chain(self):
        if self.chain is None:
            model = get_chat_model()
            self.chain = self.prompt_template | model | StrOutputParser()
        return self.chain

    # ── BM25 ─────────────────────────────────────────────────────────────────

    def _ensure_bm25(self) -> None:
        """懒加载 BM25 索引（从向量库拉全量文档）。线程安全。"""
        if self._bm25 is not None:
            return
        with self._bm25_lock:
            # 双重检查：加锁后再确认未被其他线程初始化
            if self._bm25 is not None:
                return
            try:
                all_docs_raw = self.vector_store.vector_store.get(include=["documents", "metadatas"])
                texts = all_docs_raw.get("documents") or []
                metas = all_docs_raw.get("metadatas") or []
                self._bm25_docs = [
                    Document(page_content=t, metadata=m)
                    for t, m in zip(texts, metas)
                    if t
                ]
                tokenized = [doc.page_content.lower().split() for doc in self._bm25_docs]
                self._bm25 = BM25Okapi(tokenized) if tokenized else None
            except Exception:
                self._bm25_docs = []
                self._bm25 = None

    def _bm25_retrieve(self, query: str, top_k: int) -> list[Document]:
        """BM25 关键词检索，返回 top_k 条。"""
        self._ensure_bm25()
        if self._bm25 is None or not self._bm25_docs:
            return []
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [self._bm25_docs[i] for i in top_indices if scores[i] > 0]

    # ── 主检索入口 ────────────────────────────────────────────────────────────

    def _vector_retrieve_all(self, queries: list[str]) -> list[Document]:
        """对所有扩展查询并发地执行向量检索，去重后合并。"""
        def _single(q: str) -> list[Document]:
            return self._vector_retriever.invoke(q)

        docs: list[Document] = []
        seen: set[str] = set()
        with ThreadPoolExecutor(max_workers=min(len(queries), 4)) as pool:
            futures = {pool.submit(_single, q): q for q in queries}
            for fut in as_completed(futures):
                try:
                    for doc in fut.result():
                        key = doc.page_content[:100]
                        if key not in seen:
                            seen.add(key)
                            docs.append(doc)
                except Exception:
                    pass
        return docs

    def retriever_docs(self, query: str) -> list[Document]:
        """
        三阶段并行检索：
          1. 向量检索（多查询并发）与 BM25 检索同步并行执行
          2. RRF 融合
          3. Reranker 精排（_RERANK_TOP_N > 0 时）
        """
        queries = preprocessor.process(query)

        # ① 向量检索 与 BM25 检索 并行执行（ThreadPoolExecutor）
        with ThreadPoolExecutor(max_workers=2) as pool:
            vec_future = pool.submit(self._vector_retrieve_all, queries)
            bm25_future = pool.submit(self._bm25_retrieve, query, _BM25_K)
            vector_ranked = vec_future.result()
            bm25_ranked = bm25_future.result()

        # ② RRF 融合
        fused = _rrf_fuse([vector_ranked, bm25_ranked])

        # ③ Reranker 精排
        if _RERANK_TOP_N > 0 and fused:
            return _rerank(query, fused, _RERANK_TOP_N)

        return fused[:max(_RERANK_TOP_N, 6)]

    # ── 格式化 ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_context(context_docs: list[Document]) -> str:
        context = ""
        for counter, doc in enumerate(context_docs, start=1):
            context += (
                f"[Reference {counter}] Content: {doc.page_content} | "
                f"Metadata: {doc.metadata}\n"
            )
        return context

    @staticmethod
    def _source_name(doc: Document) -> str:
        metadata = doc.metadata or {}
        file_path = str(metadata.get("file_path") or metadata.get("source") or "")
        file_name = Path(file_path).name if file_path else ""
        return (
            str(metadata.get("filename") or "")
            or str(metadata.get("title") or "")
            or file_name
            or "Unknown source"
        )

    @staticmethod
    def _source_excerpt(text: str) -> str:
        excerpt = " ".join((text or "").split())
        if len(excerpt) > MAX_SOURCE_EXCERPT_CHARS:
            excerpt = excerpt[:MAX_SOURCE_EXCERPT_CHARS].rstrip() + "..."
        return excerpt

    def format_sources(self, docs: list[Document], limit: int = MAX_SOURCES) -> str:
        lines: list[str] = []
        seen: set[tuple[str, str]] = set()
        for doc in docs:
            metadata = doc.metadata or {}
            doc_id = str(metadata.get("doc_id") or self._source_name(doc))
            chunk_index = str(metadata.get("chunk_index", ""))
            key = (doc_id, chunk_index)
            if key in seen:
                continue
            seen.add(key)
            name = self._source_name(doc)
            chunk_label = f", chunk {chunk_index}" if chunk_index != "" else ""
            excerpt = self._source_excerpt(doc.page_content)
            lines.append(f"- [{len(lines) + 1}] {name}{chunk_label}: {excerpt}")
            if len(lines) >= limit:
                break
        return "\n".join(lines)

    def rag_summarize(self, query: str) -> str:
        context_docs = self.retriever_docs(query)
        context = self._build_context(context_docs)
        answer = self._get_chain().invoke({"input": query, "context": context}).strip()
        sources = self.format_sources(context_docs)
        if sources:
            return f"{answer}\n\nSources:\n{sources}"
        return answer


if __name__ == "__main__":
    rag = RagSummarizeService()
    print(rag.rag_summarize("What are the admission requirements for FTSM postgraduate programmes?"))
