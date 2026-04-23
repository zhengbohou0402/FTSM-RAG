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

import json
import math
import time
import urllib3
from pathlib import Path
from threading import Lock

# 强制 IPv4，与 vector_store.py 保持一致
urllib3.util.connection.HAS_IPV6 = False

from model.factory import get_embed_model
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

CACHE_FILE = Path(get_abs_path("data/ukm_ftsm")) / "semantic_cache.json"
MAX_CACHE_ENTRIES = 500       # 最多缓存条目数
DEFAULT_THRESHOLD = 0.92      # 余弦相似度阈值，越高越严格
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 缓存有效期：7 天


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticCache:
    """
    语义缓存：用向量相似度匹配相似问题，全局共享（跨 conversation）
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold
        self._lock = Lock()
        # entries: list of {"question": str, "answer": str, "vector": list[float], "created_at": int}
        self._entries: list[dict] = []
        self._load()

    # ------------------------------------------------------------------ #
    #  公开接口                                                             #
    # ------------------------------------------------------------------ #

    def get(self, question: str) -> tuple[bool, str | None]:
        """
        查询缓存。
        Returns:
            (True, answer)  命中缓存
            (False, None)   未命中
        """
        try:
            q_vec = self._embed(question)
        except Exception as e:
            logger.warning(f"[SemanticCache] embed failed on get: {e}")
            return False, None

        now = int(time.time())
        with self._lock:
            best_score = 0.0
            best_answer = None
            for entry in self._entries:
                # 跳过过期条目
                if now - entry.get("created_at", 0) > CACHE_TTL_SECONDS:
                    continue
                score = _cosine_similarity(q_vec, entry["vector"])
                if score > best_score:
                    best_score = score
                    best_answer = entry["answer"]

        if best_score >= self.threshold and best_answer:
            logger.info(f"[SemanticCache] HIT  similarity={best_score:.4f}  q={question[:60]}")
            return True, best_answer

        logger.info(f"[SemanticCache] MISS similarity={best_score:.4f}  q={question[:60]}")
        return False, None

    def set(self, question: str, answer: str) -> None:
        """将问答对写入缓存"""
        try:
            q_vec = self._embed(question)
        except Exception as e:
            logger.warning(f"[SemanticCache] embed failed on set: {e}")
            return

        entry = {
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
        return {"total": total, "valid": valid, "threshold": self.threshold}

    # ------------------------------------------------------------------ #
    #  内部方法                                                             #
    # ------------------------------------------------------------------ #

    def _embed(self, text: str) -> list[float]:
        """将文本向量化（调用 DashScope embedding）"""
        return get_embed_model().embed_query(text)

    def _load(self) -> None:
        """从本地文件加载缓存"""
        if not CACHE_FILE.exists():
            return
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            self._entries = data.get("entries", [])
            logger.info(f"[SemanticCache] Loaded {len(self._entries)} entries from disk")
        except Exception as e:
            logger.warning(f"[SemanticCache] Failed to load cache: {e}")
            self._entries = []

    def _save(self) -> None:
        """持久化缓存到本地文件（已在锁内调用，无需再加锁）"""
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            CACHE_FILE.write_text(
                json.dumps({"entries": self._entries}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[SemanticCache] Failed to save cache: {e}")
