"""
语义缓存模块
-----------
对相同或相似的问题直接返回缓存结果，避免重复调用 LLM，节省 API 费用。

原理：
    1. 每次回答成功后，将问题向量化并存入缓存
    2. 新问题进来时，与缓存中所有问题计算余弦相似度
    3. 相似度 >= threshold（默认 0.92）时命中缓存，直接返回答案
    4. 缓存持久化到本地 JSON 文件，重启后不丢失

使用：
    cache = SemanticCache()
    hit, answer = cache.get("What is FTSM?")
    if not hit:
        answer = call_llm(...)
        cache.set("What is FTSM?", answer)
"""

import hashlib
import json
import time
import urllib3
from pathlib import Path
from threading import Lock

import numpy as np

# 强制 IPv4，与 vector_store.py 保持一致
urllib3.util.connection.HAS_IPV6 = False

from model.factory import get_embed_model
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

CACHE_FILE = Path(get_abs_path("data/ukm_ftsm")) / "semantic_cache.json"
MAX_CACHE_ENTRIES = 500       # 最多缓存条目数
DEFAULT_THRESHOLD = 0.92      # 余弦相似度阈值，越高越严格
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 缓存有效期：7 天
MAX_QVEC_CACHE = 256          # 查询向量备忘缓存上限（按文本哈希去重，省一次 embedding API）


def _normalize(m: np.ndarray) -> np.ndarray:
    """按行归一化，零向量保持原样（避免除零）"""
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


class SemanticCache:
    """
    语义缓存：用向量相似度匹配相似问题，全局共享（跨 conversation）
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold
        self._lock = Lock()
        # entries: list of {"question": str, "answer": str, "vector": list[float], "created_at": int}
        self._entries: list[dict] = []
        self._hit_count: int = 0
        self._miss_count: int = 0
        self._qvec_cache: dict[str, list[float]] = {}  # sha256(text) -> 向量
        self._load()

    # ------------------------------------------------------------------ #
    #  公开接口                                                             #
    # ------------------------------------------------------------------ #

    def get(self, question: str, *, namespace: str = "") -> tuple[bool, str | None]:
        """
        查询缓存。
        Returns:
            (True, answer)  命中缓存
            (False, None)   未命中
        """
        try:
            q_vec = self._embed_cached(question)
        except Exception as e:
            logger.warning(f"[SemanticCache] embed failed on get: {e}")
            return False, None

        now = int(time.time())
        with self._lock:
            best_score = 0.0
            best_answer = None
            vecs: list[list[float]] = []
            answers: list[str] = []
            for entry in self._entries:
                if str(entry.get("namespace") or "") != namespace:
                    continue
                # 跳过过期条目
                if now - entry.get("created_at", 0) > CACHE_TTL_SECONDS:
                    continue
                vecs.append(entry["vector"])
                answers.append(entry["answer"])

            if vecs:
                # numpy 批量余弦：一次矩阵乘替代逐条纯 Python 循环
                scores = _normalize(np.asarray(vecs, dtype=np.float32)) @ _normalize(
                    np.asarray(q_vec, dtype=np.float32)
                )
                idx = int(np.argmax(scores))
                best_score = float(scores[idx])
                best_answer = answers[idx]

        if best_score >= self.threshold and best_answer:
            logger.info(f"[SemanticCache] HIT  similarity={best_score:.4f}  q={question[:60]}")
            with self._lock:
                self._hit_count += 1
            return True, best_answer

        logger.info(f"[SemanticCache] MISS similarity={best_score:.4f}  q={question[:60]}")
        with self._lock:
            self._miss_count += 1
        return False, None

    def set(self, question: str, answer: str, *, namespace: str = "") -> None:
        """将问答对写入缓存"""
        try:
            q_vec = self._embed_cached(question)
        except Exception as e:
            logger.warning(f"[SemanticCache] embed failed on set: {e}")
            return

        entry = {
            "namespace": namespace,
            "question": question,
            "answer": answer,
            "vector": q_vec,
            "created_at": int(time.time()),
        }

        with self._lock:
            self._entries.append(entry)
            # 超出上限时，删除最旧的条目
            if len(self._entries) > MAX_CACHE_ENTRIES:
                self._entries = self._entries[-MAX_CACHE_ENTRIES:]
            self._save()

        logger.info(f"[SemanticCache] SET  q={question[:60]}")

    def stats(self) -> dict:
        """返回缓存统计信息"""
        with self._lock:
            total = len(self._entries)
            now = int(time.time())
            valid = sum(
                1 for e in self._entries
                if now - e.get("created_at", 0) <= CACHE_TTL_SECONDS
            )
            namespaces: dict[str, int] = {}
            for entry in self._entries:
                name = str(entry.get("namespace") or "legacy")
                namespaces[name] = namespaces.get(name, 0) + 1
            hit = self._hit_count
            miss = self._miss_count
        total_queries = hit + miss
        hit_rate = round(hit / total_queries, 4) if total_queries else 0.0
        return {
            "size": total,
            "valid": valid,
            "threshold": self.threshold,
            "hit_count": hit,
            "miss_count": miss,
            "hit_rate": hit_rate,
            "namespaces": namespaces,
        }

    def clear(self) -> None:
        """Clear cached answers after knowledge-base or model changes."""
        with self._lock:
            self._entries = []
            self._hit_count = 0
            self._miss_count = 0
            self._save()
        logger.info("[SemanticCache] CLEARED")

    # ------------------------------------------------------------------ #
    #  内部方法                                                             #
    # ------------------------------------------------------------------ #

    def _embed(self, text: str) -> list[float]:
        """将文本向量化（当前后端：Vertex gemini-embedding-001 或 DashScope）"""
        return get_embed_model().embed_query(text)

    def _embed_cached(self, text: str) -> list[float]:
        """带备忘录的向量化：同一文本（按 sha256 判等）只调一次 embedding API"""
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            cached = self._qvec_cache.get(key)
        if cached is not None:
            return cached
        vec = self._embed(text)
        with self._lock:
            if len(self._qvec_cache) >= MAX_QVEC_CACHE:
                self._qvec_cache.clear()  # 简单粗暴防止无限增长
            self._qvec_cache[key] = vec
        return vec

    def _load(self) -> None:
        """从本地文件加载缓存"""
        if not CACHE_FILE.exists():
            return
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            self._entries = data.get("entries", [])
            self._hit_count = int(data.get("hit_count", 0) or 0)
            self._miss_count = int(data.get("miss_count", 0) or 0)
            logger.info(f"[SemanticCache] Loaded {len(self._entries)} entries from disk")
        except Exception as e:
            logger.warning(f"[SemanticCache] Failed to load cache: {e}")
            self._entries = []

    def _save(self) -> None:
        """持久化缓存到本地文件（已在锁内调用，原子写入）"""
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = CACHE_FILE.with_suffix(".tmp")
        try:
            content = json.dumps(
                {
                    "entries": self._entries,
                    "hit_count": self._hit_count,
                    "miss_count": self._miss_count,
                },
                ensure_ascii=False,
            )
            tmp_file.write_text(content, encoding="utf-8")
            tmp_file.replace(CACHE_FILE)
        except Exception as e:
            logger.warning(f"[SemanticCache] Failed to save cache: {e}")
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass
