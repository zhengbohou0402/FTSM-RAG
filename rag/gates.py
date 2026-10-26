"""
证据门限（grounding gate）：三路信号任一过线即放行，全不过线则拒答（OR 关系）。

三路信号：
  1. 稠密路：查询向量与候选片段的**最大余弦相似度** ≥ dense_cosine_min。
     这一路此前是缺失的——Chroma 集合默认 L2 空间，检索分数不能直接当余弦用，
     因此改为对候选片段显式取回向量并重算余弦（见 rag_service._max_dense_cosine）。
  2. 词面重叠路：查询有效词在 top-3 片段正文中的覆盖率（余弦不可得时的兜底）。
  3. BM25 路：查询有效词在 BM25 top-3 片段中的**命中词数** ≥ bm25_min_matches
     且**覆盖率** ≥ bm25_coverage_min（比例 + 绝对下限双重判据）。

阈值集中在 config/rag.yml，标定脚本 scripts/calibrate_dense_threshold.py。
对齐 tjxt 的 RagKnowledgeService 设计（similarity 门限 + BM25 coverage 门限）。
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.documents import Document

# 兜底默认值：与 config/rag.yml 保持一致，仅在配置缺失时生效
BM25_MIN_COVERAGE = 0.30
BM25_MIN_MATCHES = 2
DENSE_MIN_COSINE = 0.66

# 站名等 boilerplate 不算有效信号（防"FTSM"一词让域外问题误命中）
_BOILERPLATE = {"ftsm", "ukm", "faculty", "university", "malaysia", "kembangan", "bangi"}

# 纯数字（年份、序号等）不计入 BM25 路的证据，见 _is_evidence_term
_NUMERIC_ONLY = re.compile(r"^[0-9]+$")


def _thresholds() -> tuple[float, float]:
    """从 config/rag.yml 读取门限；读取失败时回落到模块默认值。"""
    try:
        from utils.config_handler import rag_conf

        dense = float(rag_conf.get("dense_cosine_min", DENSE_MIN_COSINE) or 0.0)
        bm25 = float(rag_conf.get("bm25_coverage_min", BM25_MIN_COVERAGE) or 0.0)
        return dense, bm25
    except Exception:
        return DENSE_MIN_COSINE, BM25_MIN_COVERAGE


def _bm25_min_matches() -> int:
    """BM25 路的最小命中有效词数（绝对下限，防短问句靠一个虚词刷比例）。"""
    try:
        from utils.config_handler import rag_conf

        return int(rag_conf.get("bm25_min_matches", BM25_MIN_MATCHES) or 0)
    except Exception:
        return BM25_MIN_MATCHES


def _content_terms(text: str) -> set[str]:
    """有效词抽取：复用 rag_service._query_terms（拉丁词去停用词 + 中文二元组）。

    此前这里是 `re.findall(r"[a-zA-Z0-9]+", ...)` 的独立实现，与 rag_service 里的
    分词器**各写一份且不一致**，造成两个方向的错误：
      ① 只认拉丁字母——中文查询抽不出任何有效词，BM25 路对中文实际失效；
      ② 不过滤停用词——`What is the weather forecast ...` 的 what/the 成了"有效词"，
         域外问句靠虚词刷出 0.30~0.43 的假覆盖率而被放行（实测 10 条域外有 3 条如此）。
    复用同一分词器后，两处口径一致，且上述两类误判同时消失。
    """
    from rag.rag_service import _query_terms

    return set(_query_terms(text)) - _BOILERPLATE


def _is_evidence_term(term: str) -> bool:
    """判断某有效词是否具备"主题区分度"。

    纯数字不算证据：年份（2024/2025）这类词几乎遍布全库，命中它并不能说明
    "用户问的是本知识库范围内的事"。实测 `Who won the 2024 Formula 1 world
    championship?` 正是靠 2024 + world 两个泛词凑到 0.333 过线，是本轮标定里
    最后一条被误放行的域外样本。注意：这里只收窄**门限的判定口径**，不影响
    检索本身——数字仍会参与 BM25/向量召回。
    """
    return not _NUMERIC_ONLY.match(term)


def bm25_matches(query: str, doc: Document) -> int:
    """查询有效词在文档中命中的**个数**（只数"有主题区分度"的词，见 _is_evidence_term）。"""
    terms = {term for term in _content_terms(query) if _is_evidence_term(term)}
    if not terms:
        return 0
    text_terms = _content_terms(doc.page_content or "")
    return sum(1 for term in terms if term in text_terms)


def bm25_coverage(query: str, doc: Document) -> float:
    """查询有效词在文档中的覆盖率：0.0-1.0。"""
    terms = _content_terms(query)
    if not terms:
        return 1.0  # 全部是 boilerplate 的查询没有可考核的词，交给稠密路
    return bm25_matches(query, doc) / len(terms)


def dense_signal_ok(query: str, vector_docs: list[Document]) -> bool:
    """词面重叠兜底路（仅在余弦不可得时使用）。"""
    from rag.rag_service import _has_retrieval_signal

    return _has_retrieval_signal(query, vector_docs)


def evaluate(
    query: str,
    vector_docs: list[Document],
    bm25_docs: list[Document],
    *,
    dense_cosine: float | None = None,
    candidate_queries: list[str] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """返回 (是否需要拒答, 判定明细)。

    判定明细会进检索日志，便于事后核对「这一问为什么被拒 / 被放行」。
    """
    dense_min, bm25_min = _thresholds()
    min_matches = _bm25_min_matches()
    detail: dict[str, Any] = {
        "denseCosine": None if dense_cosine is None else round(float(dense_cosine), 4),
        "denseMin": dense_min,
        "densePass": False,
        "lexicalPass": False,
        "bm25Pass": False,
        "bm25MinCoverage": bm25_min,
        "bm25MinMatches": min_matches,
        "bm25BestCoverage": None,
        "bm25BestMatches": 0,
        "admittedBy": None,
    }

    # ① 稠密路（主路）：显式余弦
    if dense_cosine is not None and dense_min > 0:
        if float(dense_cosine) >= dense_min:
            detail["densePass"] = True
            detail["admittedBy"] = "dense_cosine"
            return False, detail

    c_queries = candidate_queries or [query]

    # ② 词面重叠兜底路：仅当稠密路不可用时才启用
    #    （若余弦已算出但没过线，说明语义上确实不相关，不应再由词面兜底放行）
    if dense_cosine is None or dense_min <= 0:
        if any(dense_signal_ok(q, vector_docs) for q in c_queries):
            detail["lexicalPass"] = True
            detail["admittedBy"] = "lexical_overlap"
            return False, detail

    # ③ BM25 路：覆盖率 + 最小命中词数
    #    只有比例是不够的——`What is the price of Bitcoin today` 只要今天/today 之一
    #    命中就得到 0.33 过线，故再加绝对下限；两者同时满足才放行。
    best_cov = 0.0
    best_hits = 0
    for doc in (bm25_docs or [])[:3]:
        for q in c_queries:
            hits = bm25_matches(q, doc)
            cov = bm25_coverage(q, doc)
            best_hits = max(best_hits, hits)
            best_cov = max(best_cov, cov)
            if hits >= min_matches and cov >= bm25_min:
                detail["bm25Pass"] = True
                detail["bm25BestCoverage"] = round(cov, 4)
                detail["bm25BestMatches"] = hits
                detail["admittedBy"] = "bm25_coverage"
                return False, detail

    detail["bm25BestCoverage"] = round(best_cov, 4)
    detail["bm25BestMatches"] = best_hits
    return True, detail


def should_reject(
    query: str,
    vector_docs: list[Document],
    bm25_docs: list[Document],
    *,
    dense_cosine: float | None = None,
) -> bool:
    """兼容旧调用点的薄封装（只关心是否拒答时用它）。"""
    reject, _ = evaluate(query, vector_docs, bm25_docs, dense_cosine=dense_cosine)
    return reject
