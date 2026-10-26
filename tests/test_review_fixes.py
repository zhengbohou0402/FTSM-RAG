import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

import rag.vector_store as vector_store_module
from model import factory as model_factory
from rag.vector_store import VectorStoreService
import web_app
from web_app import _validate_dashscope_base_url, app


class ApiBoundaryTests(unittest.TestCase):
    def test_untrusted_browser_origin_is_rejected(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/api/health",
                headers={"Origin": "https://example.test"},
            )
        self.assertEqual(response.status_code, 403)

    def test_local_browser_origin_is_allowed(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/api/health",
                headers={"Origin": "http://127.0.0.1:5173"},
            )
        self.assertEqual(response.status_code, 200)

    def test_only_official_dashscope_endpoints_are_allowed(self) -> None:
        self.assertEqual(
            _validate_dashscope_base_url(
                "https://dashscope-intl.aliyuncs.com/api/v1/"
            ),
            "https://dashscope-intl.aliyuncs.com/api/v1",
        )
        with self.assertRaises(HTTPException):
            _validate_dashscope_base_url("https://attacker.example/api/v1")

    def test_runtime_model_factory_rejects_unofficial_endpoint(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"DASHSCOPE_BASE_URL": "https://attacker.example/api/v1"},
                clear=False,
            ),
            self.assertRaises(ValueError),
        ):
            model_factory._apply_endpoint()


class VectorStoreStateTests(unittest.TestCase):
    def test_delete_failure_preserves_manifest_record(self) -> None:
        doc_id = "file:data/example.txt"
        manifest = {
            "documents": {
                doc_id: {
                    "chunk_ids": ["chunk-1"],
                }
            }
        }
        service = VectorStoreService.__new__(VectorStoreService)
        service._delete_chunk_ids = lambda chunk_ids, current_doc_id: False

        with (
            patch.object(vector_store_module, "load_manifest", return_value=manifest),
            patch.object(vector_store_module, "stable_file_doc_id", return_value=doc_id),
            patch.object(vector_store_module, "save_manifest") as save_manifest,
        ):
            result = service.delete_document_by_path("example.txt")

        self.assertFalse(result["vector_delete_ok"])
        self.assertIn(doc_id, manifest["documents"])
        save_manifest.assert_not_called()

    def test_unreadable_document_is_reported_as_index_failure(self) -> None:
        service = VectorStoreService.__new__(VectorStoreService)
        service.index_fingerprint = "test"
        service.index_config = {}
        service._get_file_documents = lambda path: []

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "empty.txt"
            source_path.write_text("", encoding="utf-8")
            manifest = {"documents": {}, "index": {}}
            with (
                patch.object(vector_store_module, "load_manifest", return_value=manifest),
                patch.object(vector_store_module, "save_manifest"),
                patch.object(vector_store_module, "update_manifest_index_state"),
            ):
                result = service.load_document(target_paths=[source_path])

        self.assertFalse(result["success"])
        self.assertIn("no valid text found", result["error_summary"])

    def test_training_worker_exposes_index_failure(self) -> None:
        class FailingVectorStore:
            def load_document(self) -> dict:
                return {
                    "success": False,
                    "errors": ["example.txt: failed"],
                    "error_summary": "example.txt: failed",
                    "modified": False,
                }

        with web_app._TRAINING_LOCK:
            web_app._TRAINING_STATE.update(
                running=False,
                pending=False,
                last_result=None,
                last_error=None,
            )

        with (
            patch.object(vector_store_module, "VectorStoreService", FailingVectorStore),
            patch.object(web_app, "_reset_agent"),
        ):
            web_app._training_worker()

        with web_app._TRAINING_LOCK:
            state = dict(web_app._TRAINING_STATE)
        self.assertFalse(state["running"])
        self.assertIsNone(state["last_result"])
        self.assertEqual(state["last_error"], "example.txt: failed")


if __name__ == "__main__":
    unittest.main()
