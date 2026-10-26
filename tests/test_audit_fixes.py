import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from model import factory as model_factory
from rag.ingestion import save_manifest
from services.chat_service import _is_cacheable_answer
from utils.semantic_cache import SemanticCache
from web_app import _validate_dashscope_base_url, app, _env_path as _import_time_env_path


class AuditFixesTests(unittest.TestCase):
    def test_empty_dashscope_base_url_resets_cleanly(self) -> None:
        self.assertEqual(_validate_dashscope_base_url(""), "")
        self.assertEqual(_validate_dashscope_base_url("   "), "")

    def test_vertex_model_name_resolution_respects_chat_model_name(self) -> None:
        with patch.dict(os.environ, {"LLM_BACKEND": "vertex", "CHAT_MODEL_NAME": "gemini-3.6-flash"}, clear=False):
            os.environ.pop("VERTEX_MODEL_NAME", None)
            self.assertEqual(model_factory.resolve_chat_model_name(), "gemini-3.6-flash")

    def test_cacheable_answer_rejects_refusals_and_errors(self) -> None:
        self.assertFalse(_is_cacheable_answer(""))
        self.assertFalse(_is_cacheable_answer("Short answer"))
        self.assertFalse(
            _is_cacheable_answer(
                "The available UKM FTSM knowledge base does not contain enough confirmed information to answer this question."
            )
        )
        self.assertFalse(_is_cacheable_answer("I apologize, but I cannot answer that."))
        self.assertFalse(_is_cacheable_answer("\n\n[Error] Connection to model timed out."))
        self.assertTrue(
            _is_cacheable_answer(
                "The academic calendar for semester 1 begins on 6 October 2025.\n\nSources:\n- [1] academic_calendar.txt [Official material]"
            )
        )

    def test_admin_api_key_required_for_settings_and_crawler(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            # 隔离 .env：不 patch 的话 POST /api/settings 会篡改真实 .env
            temp_env_path = Path(temp_dir) / ".env"
            temp_env_path.write_text("ADMIN_API_KEY=supersecretkey\n", encoding="utf-8")
            with (
                patch("web_app._env_path", temp_env_path),
                patch("web_app.semantic_cache") as mock_cache,
                patch("web_app.trigger_manual_crawl", return_value={"started": True}),
                patch.dict(os.environ, {"ADMIN_API_KEY": "supersecretkey"}, clear=False),
            ):
                mock_cache.clear.return_value = None
                with TestClient(app) as client:
                    res1 = client.post("/api/settings", json={"dashscope_api_key": "", "dashscope_base_url": "", "chat_model_name": ""})
                    self.assertEqual(res1.status_code, 401)

                    res2 = client.post(
                        "/api/settings",
                        headers={"X-Admin-Api-Key": "supersecretkey"},
                        json={"dashscope_api_key": "", "dashscope_base_url": "", "chat_model_name": "qwen3-max"},
                    )
                    self.assertEqual(res2.status_code, 200)

                    res3 = client.post("/api/knowledge/update")
                    self.assertEqual(res3.status_code, 401)

            # 测试退出后确认真实 .env 未被写入（纵深防御；_import_time_env_path
            # 是 import 时捕获的真实路径，patch 不会影响它）
            if _import_time_env_path.exists():
                content = _import_time_env_path.read_text(encoding="utf-8")
                self.assertNotIn("CHAT_MODEL_NAME=qwen3-max\n", content)

    def test_max_dense_cosine_accepts_str_and_list_query(self) -> None:
        """回归测试：_max_dense_cosine 必须同时支持 str 与 list[str]，不得抛异常退化。"""
        from langchain_core.documents import Document
        from rag.rag_service import RagSummarizeService

        class _FakeChroma:
            def get(self, ids=None, include=None):
                return {"embeddings": [[1.0, 0.0, 0.0, 0.0] for _ in ids]}

        class _FakeVectorStoreService:
            # _max_dense_cosine 访问 self.vector_store.vector_store.get(...)（外层为包装服务）
            vector_store = _FakeChroma()

        docs = [
            Document(page_content="a", metadata={"chunk_id": "c1"}),
            Document(page_content="b", metadata={"chunk_id": "c2"}),
        ]
        service = RagSummarizeService.__new__(RagSummarizeService)
        service.vector_store = _FakeVectorStoreService()

        def _fake_vectors(texts):
            return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

        with patch("rag.rag_service._query_vectors", side_effect=_fake_vectors):
            single = service._max_dense_cosine("hello", docs)
            multi = service._max_dense_cosine(["hello", "world"], docs)
            # 过滤空串后仍可用
            mixed = service._max_dense_cosine(["hello", "", "world"], docs)

        self.assertIsInstance(single, float)
        self.assertIsInstance(multi, float)
        self.assertAlmostEqual(single, multi)
        self.assertAlmostEqual(mixed, single)

    def test_semantic_cache_atomic_save_and_stats_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "test_cache.json"
            with patch("utils.semantic_cache.CACHE_FILE", cache_file):
                cache = SemanticCache()
                cache._entries = [{"question": "test", "answer": "ans", "vector": [0.1, 0.2], "created_at": 1000}]
                cache._hit_count = 5
                cache._miss_count = 3
                cache._save()

                self.assertTrue(cache_file.exists())
                # Verify atomic save does not leave .tmp behind
                self.assertFalse(cache_file.with_suffix(".tmp").exists())

                # Verify reload restores hit_count and miss_count
                cache2 = SemanticCache()
                self.assertEqual(cache2._hit_count, 5)
                self.assertEqual(cache2._miss_count, 3)
                self.assertEqual(len(cache2._entries), 1)

    def test_atomic_save_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_file = Path(temp_dir) / "test_manifest.json"
            with patch("rag.ingestion.MANIFEST_PATH", manifest_file):
                save_manifest({"documents": {}})
                self.assertTrue(manifest_file.exists())
                self.assertFalse(manifest_file.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
