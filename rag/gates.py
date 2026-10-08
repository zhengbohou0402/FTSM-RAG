"""
双门限拒答（候选准入）：稠密语义信号与 BM25 覆盖率任一过线才放行，两路都低于门限即拒答。
对齐 tjxt 的 RagKnowledgeService 设计：similarity 门限 + BM25 coverage 门限。

说明：稠密门限当前用查询词-文档的语义重叠信号（_has_retrieval_signal）实现，
因为 Chroma 集合默认 L2 距离无法直接换算 cosine 相似度；迁移到 Qdrant（cosine 空间）后，
DENSE_MIN_COSINE 可直接作用于检索分数。
"""

from __future__ import annotations

from langchain_core.documents import Document

BM25_MIN_COVERAGE = 0.30
DENSE_MIN_COSINE = 0.60  # reserved for the Qdrant/cosine migration

# 站名等 boilerplate 不算有效信号（防"FTSM"一词让域外问题误命中）
_BOILERPLATE = {"ftsm", "ukm", "faculty", "university", "malaysia", "kembangan", "bangi"}


def _content_terms(text: str) -> set[str]:
    import re

    return {t.lower() for t in re.findall(r"[a-zA-Z0-9]+", text) if len(t) > 2}


def bm25_coverage(query: str, doc: Document) -> float:
    """查询有效词在文档中的覆盖率：0.0-1.0。"""
    terms = _content_terms(query) - _BOILERPLATE
    if not terms:
        return 1.0  # 全部是 boilerplate 的查询没有可考核的词，交给稠密路
    text_terms = _content_terms(doc.page_content or "")
    matched = sum(1 for term in terms if term in text_terms)
    return matched / len(terms)


def dense_signal_ok(query: str, vector_docs: list[Document]) -> bool:
    from rag.rag_service import _has_retrieval_signal

    return _has_retrieval_signal(query, vector_docs)


def should_reject(query: str, vector_docs: list[Document], bm25_docs: list[Document]) -> bool:
    """稠密语义信号与 BM25 覆盖率双门限准入：任一路过线即放行。"""
    if dense_signal_ok(query, vector_docs):
        return False
    for doc in (bm25_docs or [])[:3]:
        if bm25_coverage(query, doc) >= BM25_MIN_COVERAGE:
            return False
    return True
