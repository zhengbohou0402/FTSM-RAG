"""
RAG 摘要服务：检索参考文档，并将问题与上下文一并发送给模型生成最终回答。

检索流程：
  1. Qdrant 原生混合检索（多查询并发）
  2. DashScope gte-rerank-v2 精排（可选，配置 rerank_top_n > 0 时启用）
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from model.factory import get_chat_model
from rag.vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompts
from utils.query_preprocessor import preprocessor
from utils.config_handler import qdrant_conf

MAX_SOURCES = 5
MAX_SOURCE_EXCERPT_CHARS = 220

# Reranker 最终保留 top-N 给 LLM（0 = 禁用 reranker）
_RERANK_TOP_N = 6

NO_ANSWER_MESSAGE = (
    "The available UKM FTSM knowledge base does not contain enough confirmed "
    "information to answer this question. Please verify through the official "
    "FTSM or UKM channels."
)

OFFICIAL_SOURCE_PATTERNS = (
    "ftsm_official_website",
    "academic_calendar",
    "semester2_exam_schedule",
    "master_coursemode_timetable",
    "programmes_and_admissions",
    "facilities_and_services",
    "industrial_training_and_contacts",
    "advisors_and_academic_staff",
    "advisors_expertise_index",
    "ukm_campus_bus_routes_guide",
)

COMMUNITY_SOURCE_PATTERNS = (
    "student_portal",
    "community",
)

STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "can",
    "check",
    "does",
    "for",
    "from",
    "give",
    "how",
    "information",
    "into",
    "list",
    "me",
    "need",
    "please",
    "show",
    "student",
    "tell",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
}


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


def _doc_source_name(doc: Document) -> str:
    metadata = doc.metadata or {}
    file_path = str(metadata.get("file_path") or metadata.get("source") or "")
    file_name = Path(file_path).name if file_path else ""
    return (
        str(metadata.get("filename") or "")
        or str(metadata.get("title") or "")
        or file_name
        or "unknown"
    ).lower()


def _source_priority(doc: Document) -> int:
    metadata = doc.metadata or {}
    raw_priority = metadata.get("source_priority")
    try:
        if raw_priority not in (None, ""):
            return int(raw_priority)
    except (TypeError, ValueError):
        pass

    source_type = str(metadata.get("source_type") or "").lower()
    if source_type == "official":
        return 1
    if source_type == "scraped_website":
        return 2
    if source_type == "community_guide":
        return 3
    if source_type == "generated_summary":
        return 4

    name = _doc_source_name(doc)
    if "ftsm_official_website" in name:
        return 2
    if any(pattern in name for pattern in OFFICIAL_SOURCE_PATTERNS):
        return 1
    if any(pattern in name for pattern in COMMUNITY_SOURCE_PATTERNS):
        return 3
    return 2


def _apply_source_weight(docs: list[Document]) -> list[Document]:
    """
    Add a small authority adjustment after semantic reranking.
    The original rank remains dominant; this prevents an official but less relevant
    chunk from jumping ahead of a clearly better community/student-guide chunk.
    """
    def adjusted_rank(item: tuple[int, Document]) -> float:
        rank, doc = item
        priority = _source_priority(doc)
        if priority == 1:
            return rank - 0.25
        if priority >= 3:
            return rank + 0.15
        return float(rank)

    weighted = sorted(
        enumerate(docs),
        key=adjusted_rank,
    )
    return [doc for _, doc in weighted]


def _query_identifiers(query: str) -> dict[str, set[str]]:
    lowered = query.lower()
    return {
        "course_codes": {m.group(0).upper() for m in re.finditer(r"\b[A-Z]{2}\d{4}\b", query.upper())},
        "rooms": {m.group(0).upper().replace(" ", "") for m in re.finditer(r"\bBK\s*\d+\b", query.upper())},
        "blocks": {m.group(0).upper() for m in re.finditer(r"\bBLOCK\s+[A-H]\b", query.upper())},
        "years": {m.group(0) for m in re.finditer(r"\b20\d{2}(?:\s*/\s*20\d{2})?\b", query)},
        "map_terms": {
            term
            for term in ("map", "地图", "room", "rooms", "facility", "facilities", "lecture room", "tutorial")
            if term in lowered or term in query
        },
        "calendar_terms": {
            term
            for term in ("calendar", "kalendar", "校历", "academic", "semester", "sem")
            if term in lowered or term in query
        },
        "registration_terms": {
            term
            for term in ("joinukm", "registration", "register", "renewal", "emgs", "visa", "体检", "注册", "续签")
            if term in lowered or term in query
        },
    }


def _phrase_terms(query: str) -> set[str]:
    phrases: set[str] = set()
    for phrase in re.findall(r"[A-Za-z][A-Za-z0-9&/() -]{4,}", query):
        cleaned = " ".join(phrase.lower().split())
        if cleaned and cleaned not in STOP_WORDS:
            phrases.add(cleaned)
            words = [
                word
                for word in re.findall(r"[a-zA-Z0-9]+", cleaned)
                if len(word) > 2 and word not in STOP_WORDS
            ]
            phrases.update(words)
            phrases.update(" ".join(words[i : i + 2]) for i in range(max(0, len(words) - 1)))
            phrases.update(" ".join(words[i : i + 3]) for i in range(max(0, len(words) - 2)))
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        phrases.add(phrase)
    return phrases


def _query_boost(query: str, doc: Document) -> float:
    text = (doc.page_content or "").lower()
    compact_text = text.replace(" ", "")
    name = _doc_source_name(doc)
    identifiers = _query_identifiers(query)
    boost = 0.0

    for code in identifiers["course_codes"]:
        if code.lower() in text:
            boost += 5.0
    for room in identifiers["rooms"]:
        if room.lower() in compact_text:
            boost += 3.0
    for block in identifiers["blocks"]:
        if block.lower() in text:
            boost += 2.0
    for year in identifiers["years"]:
        if year.replace(" ", "") in text.replace(" ", ""):
            boost += 1.25

    for phrase in _phrase_terms(query):
        if len(phrase) >= 5 and phrase.lower() in text:
            boost += 4.0 if " " in phrase else 0.75

    if identifiers["map_terms"] and any(
        marker in text or marker in name
        for marker in ("faculty map", "ftsm map", "学院地图", "rooms & facilities", "faculty_map")
    ):
        boost += 3.0
    if identifiers["calendar_terms"] and any(
        marker in text or marker in name
        for marker in ("academic calendar", "kalendar akademik", "校历", "academic_calendar")
    ):
        boost += 3.0
    if identifiers["registration_terms"] and any(
        marker in text or marker in name
        for marker in ("joinukm", "registration", "renewal", "emgs", "visa", "体检", "注册", "续签")
    ):
        boost += 3.0

    if ("coursework_timetable" in name or "timetable" in name) and (
        identifiers["course_codes"] or identifiers["rooms"]
    ):
        boost += 1.0
    if "student_portal_ftsm_faculty_map_rooms" in name and (
        identifiers["map_terms"] or identifiers["rooms"] or identifiers["blocks"]
    ):
        boost += 1.0

    return boost


def _apply_query_boost(query: str, docs: list[Document]) -> list[Document]:
    if not docs:
        return docs

    def adjusted(item: tuple[int, Document]) -> float:
        rank, doc = item
        return rank - _query_boost(query, doc)

    return [doc for _, doc in sorted(enumerate(docs), key=adjusted)]


def _query_terms(query: str) -> set[str]:
    terms = {
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9]+", query)
        if len(token) > 2 and token.lower() not in STOP_WORDS
    }
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        if len(phrase) <= 4:
            terms.add(phrase)
        else:
            terms.update(phrase[i : i + 2] for i in range(len(phrase) - 1))
    return terms


def _has_retrieval_signal(query: str, docs: list[Document]) -> bool:
    if not docs:
        return False

    terms = _query_terms(query)
    if not terms:
        return True

    top_text = "\n".join(
        (doc.page_content or "").lower()
        for doc in docs[: min(3, len(docs))]
    )
    overlap = sum(1 for term in terms if term.lower() in top_text)
    required_overlap = 1 if len(terms) <= 2 else 2
    if overlap >= required_overlap:
        return True

    return len(terms) <= 2 and _source_priority(docs[0]) <= 2


class RagSummarizeService(object):
    def __init__(self):
        self.vector_store = VectorStoreService()
        self._retriever = self.vector_store.get_retriever(k=qdrant_conf.get("hybrid_search_limit", 20))
        self.prompt_text = load_rag_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.chain = None

    # ── Chain ────────────────────────────────────────────────────────────────

    def _get_chain(self):
        if self.chain is None:
            model = get_chat_model()
            self.chain = self.prompt_template | model | StrOutputParser()
        return self.chain

    # ── 主检索入口 ────────────────────────────────────────────────────────────

    def _hybrid_retrieve_all(self, queries: list[str]) -> list[Document]:
        """对所有扩展查询并发地执行混合检索，去重后合并。"""
        def _single(q: str) -> list[Document]:
            return self._retriever.invoke(q)

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
        两阶段检索：
          1. Qdrant 混合检索（Dense向量 + Sparse向量并行，底层自含 RRF，支持多查询并发）
          2. Reranker 精排（_RERANK_TOP_N > 0 时）
        """
        queries = preprocessor.process(query)

        # ① Qdrant 原生混合检索（多查询并发，并合并结果）
        hybrid_ranked = self._hybrid_retrieve_all(queries)

        # ② Reranker 精排
        if _RERANK_TOP_N > 0 and hybrid_ranked:
            reranked = _rerank(query, hybrid_ranked, _RERANK_TOP_N)
            return _apply_source_weight(_apply_query_boost(query, reranked))

        return _apply_source_weight(_apply_query_boost(query, hybrid_ranked[:max(_RERANK_TOP_N, 6)]))

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
    def _source_trust_label(doc: Document) -> str:
        metadata = doc.metadata or {}
        label = str(metadata.get("source_trust_label") or "").strip()
        if label:
            return label

        source_type = str(metadata.get("source_type") or "").lower()
        if source_type == "official":
            return "Official material"
        if source_type == "scraped_website":
            return "Scraped official website"
        if source_type == "community_guide":
            return "Student guide"
        if source_type == "generated_summary":
            return "Generated summary"

        name = RagSummarizeService._source_name(doc).lower()
        if "ftsm_official_website" in name:
            return "Scraped official website"
        if "student_portal" in name:
            return "Student guide"
        if "index" in name:
            return "Generated summary"
        return "Official material"

    def format_source_reliability(self, docs: list[Document], limit: int = MAX_SOURCES) -> str:
        counts: dict[str, int] = {}
        seen: set[tuple[str, str]] = set()
        for doc in docs:
            metadata = doc.metadata or {}
            doc_id = str(metadata.get("doc_id") or self._source_name(doc))
            chunk_index = str(metadata.get("chunk_index", ""))
            key = (doc_id, chunk_index)
            if key in seen:
                continue
            seen.add(key)
            label = self._source_trust_label(doc)
            counts[label] = counts.get(label, 0) + 1
            if len(seen) >= limit:
                break
        if not counts:
            return ""
        parts = [f"{label}: {count}" for label, count in sorted(counts.items())]
        return "Source reliability: " + "; ".join(parts) + "."

    @staticmethod
    def _source_excerpt(text: str) -> str:
        """单行摘录：去掉纯分隔线行，避免 UI 里出现大段 ===。"""
        parts: list[str] = []
        for line in (text or "").splitlines():
            s = line.strip()
            if not s:
                continue
            if len(s) >= 8 and set(s) <= {"=", "-", "_", "*", "#"}:
                continue
            parts.append(s)
        excerpt = " ".join(parts)
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
            trust_label = self._source_trust_label(doc)
            chunk_label = f", chunk {chunk_index}" if chunk_index != "" else ""
            excerpt = self._source_excerpt(doc.page_content)
            lines.append(
                f"- [{len(lines) + 1}] {name} [{trust_label}]{chunk_label}: {excerpt}"
            )
            if len(lines) >= limit:
                break
        return "\n".join(lines)

    def rag_summarize(self, query: str) -> str:
        context_docs = self.retriever_docs(query)
        if not _has_retrieval_signal(query, context_docs):
            return NO_ANSWER_MESSAGE
        context = self._build_context(context_docs)
        answer = self._get_chain().invoke({"input": query, "context": context}).strip()
        reliability = self.format_source_reliability(context_docs)
        sources = self.format_sources(context_docs)
        if sources:
            reliability_block = f"\n\n{reliability}" if reliability else ""
            return f"{answer}{reliability_block}\n\nSources:\n{sources}"
        return answer


if __name__ == "__main__":
    rag = RagSummarizeService()
    print(rag.rag_summarize("What are the admission requirements for FTSM postgraduate programmes?"))
