"""
RAG 摘要服务：检索参考文档，并将问题与上下文一并发送给模型生成最终回答。

检索流程（三阶段）：
  1. 多查询向量检索 + BM25 关键词检索（扩大召回）
  2. 证据门限判定（稠密余弦 / 词面重叠 / BM25 覆盖率，任一过线才继续）
  3. RRF（Reciprocal Rank Fusion）融合排序 → 交叉编码器精排

精排（reranking）由 config/rag.yml 的 rerank.provider 决定：
  none / dashscope(gte-rerank-v2) / local(sentence-transformers CrossEncoder) / auto。
**精排与对话后端解耦**——此前它被 resolve_backend() == "vertex" 直接短路，
导致 vertex 部署下声称为"交叉编码器重排"的实际只是原序截断。现在只依赖
provider 配置；不可用时降级为融合序并在日志中留痕（不再静默 pass）。

门限阈值同样来自 config/rag.yml，标定脚本 scripts/calibrate_dense_threshold.py。
"""

import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from rank_bm25 import BM25Okapi

from model.factory import get_chat_model
from rag.gates import evaluate
from rag.vector_store import VectorStoreService
from utils.config_handler import rag_conf
from utils.logger_handler import logger
from utils.prompt_loader import load_rag_prompts
from utils.query_preprocessor import preprocessor

MAX_SOURCES = 5
MAX_SOURCE_EXCERPT_CHARS = 220

# 兜底默认值；实际取值来自 config/rag.yml 的 retrieval / rerank 段
_VECTOR_K = 12
_BM25_K = 12
_RRF_K = 60
_RERANK_TOP_N = 6
_RERANK_MAX_CANDIDATES = 12
_RRF_DEDUPE_CHARS = 100


def _retrieval_conf() -> dict[str, Any]:
    try:
        return rag_conf.get("retrieval") or {}
    except Exception:
        return {}


def _cfg_int(section: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(section.get(key, default))
    except (TypeError, ValueError):
        return default


def _vector_k() -> int:
    return max(1, _cfg_int(_retrieval_conf(), "vector_k", _VECTOR_K))


def _bm25_k() -> int:
    return max(1, _cfg_int(_retrieval_conf(), "bm25_k", _BM25_K))


def _rrf_k() -> int:
    return max(1, _cfg_int(_retrieval_conf(), "rrf_k", _RRF_K))


def _rrf_dedupe_chars() -> int:
    return max(16, _cfg_int(_retrieval_conf(), "rrf_dedupe_chars", _RRF_DEDUPE_CHARS))


def _rerank_conf() -> tuple[str, str, int]:
    """返回 (provider, model, top_n)。"""
    try:
        cfg = rag_conf.get("rerank") or {}
    except Exception:
        cfg = {}
    provider = str(cfg.get("provider", "auto")).strip().lower() or "auto"
    model = str(cfg.get("model", "") or "").strip()
    return provider, model, _cfg_int(cfg, "top_n", _RERANK_TOP_N)


def _rerank_max_candidates() -> int:
    """喂给重排器的候选上限；<=0 表示不限制。"""
    try:
        cfg = rag_conf.get("rerank") or {}
    except Exception:
        cfg = {}
    return _cfg_int(cfg, "max_candidates", _RERANK_MAX_CANDIDATES)


def _max_context_docs() -> int:
    return max(1, _cfg_int(_retrieval_conf(), "max_context_docs", _RERANK_TOP_N))


# ── 重排器状态与降级留痕 ────────────────────────────────────────────────────
# 命中"非重试类"故障（欠费/配额/API 未开通/依赖缺失）后，本进程内不再重试，
# 避免每次检索都白付一次失败请求的延迟。
_RERANK_DISABLED_REASON: str | None = None
_RERANK_WARNED: set[str] = set()
_RERANK_DISABLE_LOCK = threading.Lock()
_LOCAL_RERANKER: Any = None
_LOCAL_RERANKER_LOCK = threading.Lock()

_NON_RETRYABLE_MARKERS = (
    "arrearage",
    "quota",
    "denied",
    "insufficient",
    "billing",
    "overdue",
    "not enabled",
    "permission",
    "unauthorized",
)

# 查询向量备忘（避免为算余弦重复调用 embedding API）
_QUERY_VEC_CACHE: dict[str, list[float]] = {}
_QUERY_VEC_LOCK = threading.Lock()
_QUERY_VEC_MAX = 256


def _warn_once(key: str, message: str) -> None:
    if key in _RERANK_WARNED:
        return
    _RERANK_WARNED.add(key)
    logger.warning(message)


def _is_non_retryable(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _NON_RETRYABLE_MARKERS)


def _disable_rerank(reason: str) -> None:
    global _RERANK_DISABLED_REASON
    with _RERANK_DISABLE_LOCK:
        if _RERANK_DISABLED_REASON is not None:
            return
        _RERANK_DISABLED_REASON = reason
    logger.warning(f"[rerank] 本进程内关闭精排：{reason}")


def rerank_status() -> dict[str, Any]:
    """供 /api/kb/stats 等接口暴露“精排到底有没有在跑”。"""
    provider, model, top_n = _rerank_conf()
    resolved = "none" if _RERANK_DISABLED_REASON else _resolve_rerank_provider()
    return {
        "configured_provider": provider,
        "resolved_provider": resolved,
        "model": model,
        "top_n": top_n,
        "active": resolved != "none",
        "disabled_reason": _RERANK_DISABLED_REASON,
    }


def _resolve_rerank_provider() -> str:
    if _RERANK_DISABLED_REASON is not None:
        return "none"
    provider, _, _ = _rerank_conf()
    if provider == "auto":
        # auto 的语义是"挑一个当下真的能用的"。
        # 注意不能只看 DASHSCOPE_API_KEY 是否存在：本项目 .env 里长期留着这个
        # **legacy** key（对话与向量早已迁到 Vertex），照它判断会把 vertex 部署
        # 也导到 dashscope，而后者可能正因账号欠费直接 400 —— 表现为"精排悄悄没跑"。
        # 故改为跟随当前对话后端。
        from model.factory import resolve_backend

        if resolve_backend() == "dashscope":
            return "dashscope" if os.getenv("DASHSCOPE_API_KEY", "").strip() else "none"
        # vertex：Ranking API（Discovery Engine）是独立付费产品，本项目实测 403 未开通；
        # LLM listwise 可用但约 8s/次，不适合当默认。两条都不做 auto。
        _warn_once(
            "rerank-auto-vertex",
            "[rerank] auto 在 vertex 后端下回退为 none（Vertex Ranking API 未开通、"
            "LLM listwise 约 8s/次不适合做默认）。如需重排请显式设置 config/rag.yml 的 "
            "rerank.provider: vertex | local | dashscope。",
        )
        return "none"
    if provider not in {"none", "dashscope", "local", "vertex"}:
        _warn_once(
            "rerank-provider",
            f"[rerank] config/rag.yml 里 provider={provider!r} 不是合法值，按 none 处理。",
        )
        return "none"
    return provider


def _query_vector(text: str) -> list[float]:
    """查询向量（带备忘，避免为算余弦重复调用 embedding API）。"""
    return _query_vectors([text])[0]


def _query_vectors(texts: list[str]) -> list[list[float]]:
    """批量获取查询向量（命中缓存的直接复用，未命中的合并为单次 embed_documents RPC）。"""
    if not texts:
        return []
    keys = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]
    results: list[list[float] | None] = [None] * len(texts)
    missing_indices: list[int] = []
    missing_texts: list[str] = []

    with _QUERY_VEC_LOCK:
        for idx, k in enumerate(keys):
            cached = _QUERY_VEC_CACHE.get(k)
            if cached is not None:
                results[idx] = cached
            else:
                missing_indices.append(idx)
                missing_texts.append(texts[idx])

    if missing_texts:
        from model.factory import get_embed_model

        embed_model = get_embed_model()
        if len(missing_texts) == 1:
            fetched = [embed_model.embed_query(missing_texts[0])]
        else:
            fetched = embed_model.embed_documents(missing_texts)
        with _QUERY_VEC_LOCK:
            if len(_QUERY_VEC_CACHE) + len(fetched) > _QUERY_VEC_MAX:
                _QUERY_VEC_CACHE.clear()
            for idx, vec in zip(missing_indices, fetched):
                _QUERY_VEC_CACHE[keys[idx]] = vec
                results[idx] = vec

    return [r or [] for r in results]


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


def _rrf_fuse(
    ranked_lists: list[list[Document]],
    k: int = 60,
) -> list[Document]:
    """
    Reciprocal Rank Fusion：把多个已排序列表融合为单一排序。

    去重键优先用 metadata["chunk_id"]（vector_store 写入的稳定 id），
    缺失时才退化为正文前缀——此前一律用 page_content[:100]，两份文档若开头
    相同会被误判为同一条而丢失候选。
    """
    dedupe_chars = _rrf_dedupe_chars()
    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}

    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked, start=1):
            key = str((doc.metadata or {}).get("chunk_id") or "") or doc.page_content[:dedupe_chars]
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            doc_map[key] = doc

    sorted_keys = sorted(scores, key=lambda k_: scores[k_], reverse=True)
    return [doc_map[k] for k in sorted_keys]


def _rerank_dashscope(query: str, docs: list[Document], top_n: int) -> list[Document] | None:
    """DashScope gte-rerank-v2（交叉编码器）。返回 None 表示本次降级。"""
    from model.factory import apply_dashscope_endpoint

    apply_dashscope_endpoint()
    import dashscope  # type: ignore

    resp = dashscope.TextReRank.call(
        model="gte-rerank-v2",
        query=query,
        documents=[d.page_content for d in docs],
        top_n=min(top_n, len(docs)),
        return_documents=False,
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
    )
    if resp.status_code != 200:
        message = f"HTTP {resp.status_code} {getattr(resp, 'code', '')} {getattr(resp, 'message', '')}"
        if _is_non_retryable(message):
            _disable_rerank(f"dashscope gte-rerank-v2 不可用：{message.strip()[:200]}")
        else:
            _warn_once("rerank-dashscope-http", f"[rerank] dashscope 调用失败，本次降级：{message.strip()[:200]}")
        return None
    indices = [r.index for r in resp.output.results]
    return [docs[i] for i in indices if 0 <= i < len(docs)]


def _rerank_local(query: str, docs: list[Document], top_n: int, model_name: str) -> list[Document] | None:
    """本地交叉编码器（sentence-transformers CrossEncoder）。返回 None 表示降级。

    注意：本路径需要额外安装 sentence-transformers，首次调用会下载模型权重；
    未安装时会一次性关闭精排并写日志，不会每次检索重复尝试。
    """
    global _LOCAL_RERANKER
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except ImportError as exc:
        _disable_rerank(
            "provider=local 需要 sentence-transformers（pip install sentence-transformers）："
            f"{exc}"
        )
        return None
    if not model_name:
        _disable_rerank("provider=local 但 config/rag.yml 的 rerank.model 为空")
        return None

    with _LOCAL_RERANKER_LOCK:
        if _LOCAL_RERANKER is None:
            _LOCAL_RERANKER = CrossEncoder(model_name)
        reranker = _LOCAL_RERANKER
    scores = reranker.predict([(query, d.page_content) for d in docs])
    order = sorted(range(len(docs)), key=lambda i: -float(scores[i]))
    return [docs[i] for i in order[:top_n]]


# listwise 重排提示词：只要索引排列，避免模型回写正文（省 token 也便于解析）
_RERANK_LISTWISE_PROMPT = """You are re-ranking retrieved passages for a question about the \
Faculty of Information Science and Technology (FTSM), Universiti Kebangsaan Malaysia.

Question: {query}

Candidate passages:
{passages}

Order the passages by how likely each one contains the answer, most relevant first.
Judge topical relevance only; ignore writing style and length.

Reply with ONLY a JSON array of the index numbers, most relevant first, listing every
index exactly once. Example: [2, 0, 1]"""


def _message_text(response: Any) -> str:
    """把模型回复统一成纯文本。

    **后端差异**：Vertex(Gemini) 经 LangChain 返回的 `content` 是**内容块列表**
    （`[{'type':'text','text':...}, ...]`，还夹带 `thought_signature`），
    而 DashScope / OpenAI 兼容后端返回纯字符串。若直接 `str(content)`，
    Vertex 下拿到的是 Python repr（`"[{'type': 'text', ...}]"`），
    解析器会永远失败 —— 表现为「vertex 重排静默不可用」。
    """
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def _parse_rerank_order(raw: str, count: int) -> list[int] | None:
    """从模型回复里抽出索引排列；去重、丢弃越界项，并把漏掉的索引按原序补回尾部。

    补尾是刻意的：模型偶尔少给一两个索引，若直接截断会**丢候选**，
    比"排错序"更糟。
    """
    match = re.search(r"\[[\s\S]*?\]", raw or "")
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return None
    if not isinstance(parsed, list):
        return None
    order: list[int] = []
    for item in parsed:
        try:
            idx = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < count and idx not in order:
            order.append(idx)
    if not order:
        return None
    order.extend(i for i in range(count) if i not in order)
    return order


def _rerank_vertex(query: str, docs: list[Document], top_n: int) -> list[Document] | None:
    """用当前对话后端（Vertex Gemini）做 listwise 重排。

    为什么需要这条路径：Vertex 的 Ranking API（Discovery Engine）是独立付费产品，
    本项目 rag-fist 实测返回 403 not enabled；dashscope 的 gte-rerank-v2 又可能因
    账号欠费不可用。这条路径复用**已经可用**的 Gemini 对话模型，是 vertex 部署下
    唯一开箱可用的重排方式。

    代价是慢：实测约 7.9s/次（对比 gte-rerank-v2 的百毫秒级），因此只做显式
    opt-in（rerank.provider: vertex），不放进 auto。
    """
    from model.factory import get_chat_model

    passages = "\n".join(
        f"[{i}] {(d.page_content or '').strip()[:600]}" for i, d in enumerate(docs)
    )
    prompt = _RERANK_LISTWISE_PROMPT.format(query=query, passages=passages)
    raw = _message_text(get_chat_model().invoke(prompt))
    order = _parse_rerank_order(raw, len(docs))
    if order is None:
        _warn_once(
            "rerank-vertex-parse",
            f"[rerank] vertex listwise 返回无法解析，本次降级为融合序：{raw[:200]}",
        )
        return None
    return [docs[i] for i in order[:top_n]]


def _rerank(
    query: str,
    docs: list[Document],
    top_n: int,
    *,
    trace: dict[str, Any] | None = None,
) -> list[Document]:
    """交叉编码器精排；provider 由 config/rag.yml 决定，失败降级为融合序（有日志）。"""
    if not docs or top_n <= 0:
        return docs[:top_n] if top_n > 0 else docs

    provider = _resolve_rerank_provider()
    if trace is not None:
        trace["rerankProvider"] = provider
    if provider == "none":
        return docs[:top_n]

    # 候选上限：RRF 之后 fused 最多有 vector_k + bm25_k 条，全量喂给重排器既贵又慢——
    # vertex listwise 实测在 6 条候选时约 3.2s、24 条时约 10.5s。而重排的意义只是
    # 在头部候选里重新排序，尾部候选本来也进不了 top_n，故按 rrf 序先截断。
    cap = _rerank_max_candidates()
    if cap > 0:
        docs = docs[:cap]
    if trace is not None:
        trace["rerankCandidates"] = len(docs)

    _, model_name, _ = _rerank_conf()
    started = time.perf_counter()
    try:
        if provider == "dashscope":
            ranked = _rerank_dashscope(query, docs, top_n)
        elif provider == "vertex":
            ranked = _rerank_vertex(query, docs, top_n)
        else:
            ranked = _rerank_local(query, docs, top_n, model_name)
    except Exception as exc:
        message = str(exc)
        if _is_non_retryable(message):
            _disable_rerank(f"{provider} 精排报错：{message[:200]}")
        else:
            _warn_once(f"rerank-{provider}-exc", f"[rerank] {provider} 异常，本次降级：{message[:200]}")
        ranked = None

    if ranked is None:
        if trace is not None:
            trace["rerankDegraded"] = True
        return docs[:top_n]

    if trace is not None:
        trace["rerankApplied"] = True
        trace["rerankMs"] = round((time.perf_counter() - started) * 1000)
    return ranked


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


def _bm25_tokens(text: str) -> list[str]:
    """P1-6：BM25 语料/查询统一分词 —— 拉丁词（小写）+ 中文二元组。

    旧实现 .lower().split() 依赖空格分词：中文整句被切成单个超长 token，
    BM25Okapi 得分恒为 0（中文查询在 BM25 路完全失效）；带标点的英文词
    （如 "EMGS?"、"registration,"）也无法匹配。与 _query_terms 的提取逻辑同源。
    注意这里不过滤停用词/短词 —— BM25 的 IDF 会自行压低常见词权重，
    过滤反而破坏了"短查询词也能命中"的能力。"""
    tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", text)]
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(phrase) == 2:
            tokens.append(phrase)
        else:
            tokens.extend(phrase[i : i + 2] for i in range(len(phrase) - 1))
    return tokens


def _has_retrieval_signal(
    query: str,
    docs: list[Document],
    *,
    dense_cosine: float | None = None,
) -> bool:
    """词面重叠复核（第二道闸）。

    当稠密余弦已算出且过线时直接放行——多语言/同义表达下词面重叠会误判为"无信号"，
    而余弦已经证明了语义相关性。

    注意：这里**故意移除了**历史上的一条兜底规则
    （`len(terms) <= 2 and _source_priority(docs[0]) <= 2` → 直接判 True）。
    它让任意 1~2 词的域外查询只要首位命中 official/scraped 文档就无条件放行，
    是"拒答能力被高估"的主因。
    """
    if not docs:
        return False

    if dense_cosine is not None:
        try:
            from rag.gates import _thresholds

            dense_min, _ = _thresholds()
            if dense_min > 0 and float(dense_cosine) >= dense_min:
                return True
        except Exception:
            pass

    terms = _query_terms(query)
    if not terms:
        return True

    top_text = "\n".join(
        (doc.page_content or "").lower()
        for doc in docs[: min(3, len(docs))]
    )
    overlap = sum(1 for term in terms if term.lower() in top_text)
    required_overlap = 1 if len(terms) <= 2 else 2
    return overlap >= required_overlap


def _publish_retrieval_log(
    question: str,
    docs: list[Document],
    started: float,
    *,
    gate: dict[str, Any] | None = None,
) -> None:
    """retrieval.logged 事件（fire-and-forget）：hit/命中数/来源/门限/延迟 → ftsm-knowledge 落库。

    发送失败只记一条限流日志——此前是 `except Exception: pass`，
    导致 MQ 断链时检索日志静默丢失、质量看板恒为空且无人知晓。
    """
    try:
        from rag.mq_events import publish_soon

        sources = sorted({RagSummarizeService._source_name(doc) for doc in docs})
        detail = gate or {}
        dense_cosine = detail.get("denseCosine")
        publish_soon(
            "retrieval.logged",
            {
                "question": (question or "")[:200],
                "hit": bool(docs),
                "hitCount": len(docs),
                "topScore": float(dense_cosine) if dense_cosine is not None else 0.0,
                "sources": "、".join(sources)[:900],
                "latencyMs": round((time.perf_counter() - started) * 1000),
                "gate": {
                    "admittedBy": detail.get("admittedBy"),
                    "denseCosine": dense_cosine,
                    "denseMin": detail.get("denseMin"),
                },
            },
        )
    except Exception as exc:
        # 旁路日志，绝不影响检索主链路；但必须留痕
        _warn_once("retrieval-log", f"[retrieval-log] 发布检索日志失败（本次丢弃）：{exc}")


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
        self._bm25_sig: tuple[int, int] | None = None

    # ── Chain ────────────────────────────────────────────────────────────────

    def _get_chain(self):
        if self.chain is None:
            model = get_chat_model()
            self.chain = self.prompt_template | model | StrOutputParser()
        return self.chain

    # ── BM25 ─────────────────────────────────────────────────────────────────

    def _manifest_signature(self) -> tuple[int, int]:
        """P1-5：manifest 变更信号 = (st_mtime_ns, st_size)。

        第二轮复审：改为对 manifest 文件 stat()，O(1) 且对任何进程
        （MQ 消费者、删除路径、脚本重建）的写入都生效；
        内容级签名需每次解析 JSON，且并发读半写状态可能误判稳定。
        文件不存在视为 (0, 0)；读取异常返回 (-1, -1) 强制重建。"""
        try:
            from rag.ingestion import MANIFEST_PATH

            st = MANIFEST_PATH.stat()
            return (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            return (0, 0)
        except Exception:
            return (-1, -1)

    def _ensure_bm25(self) -> None:
        """懒加载 BM25 索引（从向量库拉全量文档）。线程安全。"""
        sig = self._manifest_signature()
        if self._bm25 is not None and sig == self._bm25_sig:
            return
        with self._bm25_lock:
            # 双重检查：加锁后再确认未被其他线程初始化
            if self._bm25 is not None and sig == self._bm25_sig:
                return
            self._bm25 = None
            self._bm25_docs = []
            try:
                all_docs_raw = self.vector_store.vector_store.get(include=["documents", "metadatas"])
                texts = all_docs_raw.get("documents") or []
                metas = all_docs_raw.get("metadatas") or []
                self._bm25_docs = [
                    Document(page_content=t, metadata=m)
                    for t, m in zip(texts, metas)
                    if t
                ]
                tokenized = [_bm25_tokens(doc.page_content) for doc in self._bm25_docs]
                self._bm25 = BM25Okapi(tokenized) if tokenized else None
                self._bm25_sig = sig
            except Exception:
                self._bm25_docs = []
                self._bm25 = None

    def _bm25_retrieve(self, query: str | list[str], top_k: int) -> list[Document]:
        """BM25 关键词检索，支持单查询或多查询扩展，返回 top_k 条。"""
        self._ensure_bm25()
        if self._bm25 is None or not self._bm25_docs:
            return []
        q_list = [query] if isinstance(query, str) else query
        tokens: list[str] = []
        for q in q_list:
            tokens.extend(_bm25_tokens(q))
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [self._bm25_docs[i] for i in top_indices if scores[i] > 0]

    # ── 检索 ─────────────────────────────────────────────────────────────────

    def _vector_retrieve_all(self, queries: list[str]) -> list[Document]:
        """对所有扩展查询并发地执行向量检索，按「轮转交错」确定性合并。

        为什么必须确定序：此前用 `as_completed` 边完成边 append，合并顺序取决于
        **哪个线程先返回**。同一问题两次运行会得到不同的候选顺序，进而
        ① 改变 RRF 的输入排名（即改变最终答案引用的片段），
        ② 改变 `_max_dense_cosine` 所取的 top-3 前缀（即改变门限的稠密信号）。
        实测同一问题重复 6 次，「Who is the coordinator for the Cybersecurity
        master programme?」的稠密余弦在 0.6368~0.7075 之间摆动（极差 0.0707），
        而域内外样本的整体间距只有约 0.03 —— 噪声大于信号，标定阈值失去意义。

        现在改为：等全部结果就绪 → 按查询顺序取回（pool.map 保序）→ 轮转交错
        （各查询的第 1 名、第 2 名…）。这样既保证可复现，也让每个扩展查询的
        高分片段都排在尾部片段之前；此前"先返回的查询"的全部结果会整体压过
        其他查询的头部结果。
        """
        if not queries:
            return []

        try:
            vectors = _query_vectors(queries)
        except Exception as exc:
            _warn_once("vector-batch-embed", f"[vector] 批量向量化查询失败：{exc}")
            vectors = []

        k = _vector_k()
        ranked_lists: list[list[Document]] = []
        for q, vec in zip(queries, vectors):
            if not vec:
                continue
            try:
                ranked_lists.append(
                    self.vector_store.vector_store.similarity_search_by_vector(vec, k=k)
                )
            except Exception as exc:
                _warn_once("vector-subquery", f"[vector] 扩展查询检索失败，本次跳过：{exc}")
                ranked_lists.append([])

        docs: list[Document] = []
        seen: set[str] = set()
        depth = max((len(items) for items in ranked_lists), default=0)
        for rank in range(depth):
            for items in ranked_lists:
                if rank >= len(items):
                    continue
                doc = items[rank]
                key = str((doc.metadata or {}).get("chunk_id") or "") or doc.page_content[:100]
                if key in seen:
                    continue
                seen.add(key)
                docs.append(doc)
        return docs

    # ── 稠密余弦（证据门限的稠密路）────────────────────────────────────────────

    def _max_dense_cosine(
        self,
        query: str | list[str],
        docs: list[Document],
        top: int = 3,
    ) -> float | None:
        """查询向量与候选片段向量的最大余弦相似度。

        为什么需要单独算：Chroma 集合是默认 L2 空间，`as_retriever` 返回的文档
        不带相似度分数，无法直接当余弦阈值用。这里按 chunk_id 取回向量重算，
        使 config/rag.yml 的 dense_cosine_min 真正作用在一个可比量纲上。

        query 支持 str 与 list[str]（多查询扩展路）；批量走 _query_vectors，
        命中 _QUERY_VEC_CACHE（_vector_retrieve_all 刚批量算过）。
        任何异常都返回 None（视为"余弦不可得"，退化为词面重叠路），不影响主链路。
        """
        if not docs:
            return None
        try:
            ids = [
                str((d.metadata or {}).get("chunk_id") or "")
                for d in docs[: max(1, top)]
            ]
            ids = [i for i in ids if i]
            if not ids:
                return None

            q_list = [query] if isinstance(query, str) else [q for q in query if q]
            if not q_list:
                return None
            # 批量取出所有查询向量（此前 _vector_retrieve_all 已批量算过并缓存，
            # 这里 100% 命中内存缓存，不会再触发 embedding RPC）
            q_vecs = _query_vectors(q_list)
            if not q_vecs:
                return None

            raw = self.vector_store.vector_store.get(ids=ids, include=["embeddings"])
            embeddings = raw.get("embeddings")
            if embeddings is None or len(embeddings) == 0:
                return None

            matrix = np.asarray(embeddings, dtype=np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            norm_matrix = matrix / norms

            max_cos: float = -1.0
            for qv in q_vecs:
                vec = np.asarray(qv, dtype=np.float32)
                q_norm = float(np.linalg.norm(vec))
                if q_norm == 0.0:
                    continue
                vec = vec / q_norm
                cos_val = float(np.max(norm_matrix @ vec))
                if cos_val > max_cos:
                    max_cos = cos_val

            return max_cos if max_cos >= -1.0 else None
        except Exception as exc:
            _warn_once("dense-cosine", f"[dense] 余弦计算失败，本次退化为词面重叠路：{exc}")
            return None

    # ── 主检索入口 ────────────────────────────────────────────────────────────

    def retriever_docs(
        self,
        query: str,
        *,
        trace: dict[str, Any] | None = None,
    ) -> list[Document]:
        """
        三阶段检索 + 证据门限准入 + 查询日志（MQ fire-and-forget）：
          1. 向量检索（多查询并发）与 BM25 检索并行执行
          2. 证据门限：稠密余弦 / 词面重叠 / BM25 覆盖率三路任一过线才继续，否则拒答（返回空）
          3. RRF 融合
          4. 交叉编码器精排（config/rag.yml 的 rerank.provider）
        trace 为可选的输出参数，回填门限判定与精排状态，供调用方与日志消费。
        """
        started = time.perf_counter()
        queries = preprocessor.process(query)

        # ① 向量检索 与 BM25 检索 并行执行（ThreadPoolExecutor）
        with ThreadPoolExecutor(max_workers=2) as pool:
            vec_future = pool.submit(self._vector_retrieve_all, queries)
            bm25_future = pool.submit(self._bm25_retrieve, queries, _bm25_k())
            vector_ranked = vec_future.result()
            bm25_ranked = bm25_future.result()

        # ② 证据门限准入（拒答）
        dense_cosine = self._max_dense_cosine(queries, vector_ranked)
        reject, gate_detail = evaluate(
            query,
            vector_ranked,
            bm25_ranked,
            dense_cosine=dense_cosine,
            candidate_queries=queries,
        )
        if trace is not None:
            trace["gate"] = gate_detail
            trace["denseCosine"] = dense_cosine
        if reject:
            _publish_retrieval_log(query, [], started, gate=gate_detail)
            return []

        # ③ RRF 融合
        fused = _rrf_fuse([vector_ranked, bm25_ranked], k=_rrf_k())

        # ④ 交叉编码器精排
        top_n = _max_context_docs()
        if top_n > 0 and fused:
            final = _apply_source_weight(
                _apply_query_boost(query, _rerank(query, fused, top_n, trace=trace))
            )
        else:
            final = _apply_source_weight(_apply_query_boost(query, fused[: max(top_n, 6)]))
        _publish_retrieval_log(query, final, started, gate=gate_detail)
        return final

    # ── 格式化 ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_context(context_docs: list[Document]) -> str:
        blocks: list[str] = []
        for counter, doc in enumerate(context_docs, start=1):
            name = RagSummarizeService._source_name(doc)
            trust = RagSummarizeService._source_trust_label(doc)
            chunk_idx = (doc.metadata or {}).get("chunk_index", "")
            chunk_tag = f", chunk {chunk_idx}" if chunk_idx != "" else ""
            blocks.append(
                f"[Reference {counter}] ({name} [{trust}]{chunk_tag})\n"
                f"{(doc.page_content or '').strip()}"
            )
        return "\n\n".join(blocks)

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

    def retrieve_for_agent(self, query: str) -> str:
        """P1-4：供 ReAct Agent 工具调用的纯检索入口（不触发内层 LLM 调用）。

        旧路径在工具内部跑一次完整 `self._get_chain().invoke(...)` 生成答案，
        再把答案交回外层 Agent 让第二个 LLM 复述/流式输出，导致首字延迟（TTFT）
        叠加整次非流式生成耗时（3~6s）。
        现在工具只返回结构化参考片段 + 来源可靠性 + 标准 Sources 尾块，
        由外层流式 Agent 直接基于参考片段生成回答。
        """
        trace: dict[str, Any] = {}
        context_docs = self.retriever_docs(query, trace=trace)
        if not _has_retrieval_signal(
            query, context_docs, dense_cosine=trace.get("denseCosine")
        ):
            return NO_ANSWER_MESSAGE
        context = self._build_context(context_docs)
        reliability = self.format_source_reliability(context_docs)
        sources = self.format_sources(context_docs)
        parts = [f"Reference Context:\n{context}"]
        if reliability:
            parts.append(reliability)
        if sources:
            parts.append(f"Sources:\n{sources}")
        return "\n\n".join(parts)

    def rag_summarize(self, query: str) -> str:
        """独立完整 RAG 问答（保留给 scripts/evaluate_rag.py 等非 Agent 离线评测脚本）。"""
        trace: dict[str, Any] = {}
        context_docs = self.retriever_docs(query, trace=trace)
        # 复核用同一份门限判定：若稠密余弦已过线，不再用词面重叠二次否决
        # （否则中文/同义表达会在这一步被误判成「无证据」而拒答）
        if not _has_retrieval_signal(
            query, context_docs, dense_cosine=trace.get("denseCosine")
        ):
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
