import hashlib
import json
import time
from pathlib import Path
import threading

import urllib3
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from model.factory import get_embed_model
from rag.ingestion import (
    build_file_source_document,
    load_manifest,
    save_manifest,
    source_to_manifest_record,
    stable_file_doc_id,
    update_manifest_index_state,
)
from utils.config_handler import qdrant_conf, rag_conf
from utils.file_handler import (
    image_loader,
    listdir_with_allowed_type,
    pdf_loader,
    txt_loader,
)
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

urllib3.util.connection.HAS_IPV6 = False

BATCH_SIZE = 20


_qdrant_client_instance = None
_qdrant_client_lock = threading.Lock()

def get_shared_qdrant_client() -> QdrantClient:
    global _qdrant_client_instance
    with _qdrant_client_lock:
        if _qdrant_client_instance is None:
            db_path = get_abs_path(qdrant_conf["persist_directory"])
            _qdrant_client_instance = QdrantClient(path=db_path)
            
            # Auto-create collection if it doesn't exist
            collection_name = qdrant_conf["collection_name"]
            if not _qdrant_client_instance.collection_exists(collection_name):
                logger.info(f"Collection {collection_name} does not exist. Creating it.")
                from qdrant_client.http import models as qdrant_models
                embed_model = get_embed_model()
                try:
                    sample_vector = embed_model.embed_query("test")
                    vector_size = len(sample_vector)
                except Exception as e:
                    logger.error(f"Failed to determine embedding dimension. Qdrant collection cannot be initialized: {e}")
                    raise RuntimeError("Failed to determine embedding dimension. Please check embedding model configuration or API keys.") from e
                _qdrant_client_instance.create_collection(
                    collection_name=collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=vector_size,
                        distance=qdrant_models.Distance.COSINE
                    ),
                    sparse_vectors_config={
                        "fast-sparse": qdrant_models.SparseVectorParams()
                    }
                )
                logger.info(f"Collection {collection_name} created successfully.")
        return _qdrant_client_instance


class VectorStoreService:
    def __init__(self):
        client = get_shared_qdrant_client()
        collection_name = qdrant_conf["collection_name"]
        self.vector_store = QdrantVectorStore(
            client=client,
            collection_name=collection_name,
            embedding=get_embed_model(),
            sparse_embedding=FastEmbedSparse(model_name=qdrant_conf["sparse_model"]),
            retrieval_mode=RetrievalMode.HYBRID,
            sparse_vector_name="fast-sparse",
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=qdrant_conf["chunk_size"],
            chunk_overlap=qdrant_conf["chunk_overlap"],
            separators=qdrant_conf["separators"],
            length_function=len,
        )

        self.index_config = self._build_index_config()
        self.index_fingerprint = self._build_index_fingerprint(self.index_config)

    @staticmethod
    def _build_index_config() -> dict:
        return {
            "schema_version": 2,
            "embedding_model_name": rag_conf["embedding_model_name"],
            "collection_name": qdrant_conf["collection_name"],
            "chunk_size": qdrant_conf["chunk_size"],
            "chunk_overlap": qdrant_conf["chunk_overlap"],
            "separators": qdrant_conf["separators"],
            "allowed_file_types": qdrant_conf["allow_knowledge_file_type"],
            "sparse_model": qdrant_conf["sparse_model"],
        }

    @staticmethod
    def _build_index_fingerprint(index_config: dict) -> str:
        payload = json.dumps(index_config, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def get_retriever(self, k: int | None = None):
        return self.vector_store.as_retriever(
            search_kwargs={"k": k or qdrant_conf["k"]}
        )

    def _get_file_documents(self, read_path: str) -> list[Document]:
        lower_path = read_path.lower()
        if lower_path.endswith(".txt"):
            return txt_loader(read_path)
        if lower_path.endswith(".pdf"):
            return pdf_loader(read_path)
        if any(
            lower_path.endswith(ext)
            for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]
        ):
            return image_loader(read_path)
        logger.warning(f"[knowledge load] Unsupported file type for {read_path}")
        return []

    def _delete_chunk_ids(self, chunk_ids: list[str], doc_id: str) -> bool:
        if not chunk_ids:
            return True
        try:
            self.vector_store.delete(ids=chunk_ids)
            logger.info(
                f"[knowledge load] Deleted {len(chunk_ids)} old chunks for {doc_id}."
            )
            return True
        except Exception as exc:
            logger.warning(
                f"[knowledge load] Failed to delete old chunks for {doc_id}: {exc}"
            )
            return False

    @staticmethod
    def _is_non_retryable_embedding_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            marker in message
            for marker in (
                "arrearage",
                "free quota",
                "quota",
                "access denied",
                "insufficient",
                "billing",
            )
        )

    def delete_document_by_path(self, file_path: str | Path) -> dict:
        manifest = load_manifest()
        manifest.setdefault("documents", {})

        doc_id = stable_file_doc_id(file_path)
        record = manifest["documents"].get(doc_id)
        if not record:
            logger.info(f"[knowledge delete] No manifest record for {doc_id}.")
            return {
                "doc_id": doc_id,
                "manifest_found": False,
                "vector_delete_ok": None,
                "deleted_chunks": 0,
            }

        chunk_ids = record.get("chunk_ids", [])
        vector_delete_ok = self._delete_chunk_ids(chunk_ids, doc_id)
        if not vector_delete_ok:
            return {
                "doc_id": doc_id,
                "manifest_found": True,
                "vector_delete_ok": False,
                "deleted_chunks": 0,
            }

        del manifest["documents"][doc_id]
        update_manifest_index_state(manifest, bump_version=True)
        save_manifest(manifest)
        logger.info(f"[knowledge delete] Removed {doc_id} from manifest.")

        return {
            "doc_id": doc_id,
            "manifest_found": True,
            "vector_delete_ok": vector_delete_ok,
            "deleted_chunks": len(chunk_ids),
        }

    @staticmethod
    def _metadata_for_chunk(source, chunk_index: int, loader_metadata: dict) -> dict:
        import uuid
        raw_id = f"{source.doc_id}:chunk:{chunk_index}"
        chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_id))
        metadata = {
            "doc_id": source.doc_id,
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "source_type": source.source_type,
            "source_url": source.source_url or "",
            "title": source.title,
            "file_path": source.file_path or "",
            "updated_at": source.updated_at,
            "hash": source.hash,
            "permission_scope": source.permission_scope,
        }

        for key, value in source.extra.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                metadata[key] = "" if value is None else value

        for key, value in loader_metadata.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                metadata[f"loader_{key}"] = "" if value is None else value

        return metadata

    def load_document(self, target_paths: list[str | Path] | None = None) -> dict:
        manifest = load_manifest()
        manifest.setdefault("documents", {})
        modified = False
        errors: list[str] = []

        if target_paths is None:
            allowed_files_path: list[str] = listdir_with_allowed_type(
                get_abs_path(qdrant_conf["data_path"]),
                tuple(qdrant_conf["allow_knowledge_file_type"]),
            )
            current_doc_ids = {stable_file_doc_id(path) for path in allowed_files_path}

            for doc_id, record in list(manifest["documents"].items()):
                if not doc_id.startswith("file:") or doc_id in current_doc_ids:
                    continue
                if not self._delete_chunk_ids(record.get("chunk_ids", []), doc_id):
                    errors.append(f"{doc_id}: failed to remove chunks for missing source")
                    continue
                del manifest["documents"][doc_id]
                modified = True
                save_manifest(manifest)
                logger.info(f"[knowledge load] Removed missing source document {doc_id}.")
        else:
            allowed_extensions = tuple(
                f".{ext.lower().lstrip('.')}" for ext in qdrant_conf["allow_knowledge_file_type"]
            )
            allowed_files_path = [
                str(Path(path).resolve())
                for path in target_paths
                if Path(path).exists() and Path(path).suffix.lower() in allowed_extensions
            ]

        for path in allowed_files_path:
            added_chunk_ids: list[str] = []
            try:
                source = build_file_source_document(path)
                previous = manifest["documents"].get(source.doc_id)

                source_changed = (
                    previous
                    and previous.get("hash") == source.hash
                    and previous.get("source_type") == source.source_type
                    and previous.get("index_fingerprint") == self.index_fingerprint
                    and (previous.get("extra") or {}).get("source_trust_label")
                    == source.extra.get("source_trust_label")
                )

                if source_changed:
                    logger.info(f"[knowledge load] {path} unchanged. Skipping.")
                    continue

                documents: list[Document] = self._get_file_documents(path)
                if not documents:
                    errors.append(f"{Path(path).name}: no valid text found")
                    logger.warning(
                        f"[knowledge load] No valid text found in {path}. Skipping."
                    )
                    continue

                split_document: list[Document] = self.spliter.split_documents(documents)
                if not split_document:
                    errors.append(f"{Path(path).name}: no valid chunks produced")
                    logger.warning(
                        f"[knowledge load] No valid chunks produced from {path}. Skipping."
                    )
                    continue

                import uuid
                chunk_ids: list[str] = []
                for index, doc in enumerate(split_document):
                    raw_id = f"{source.doc_id}:chunk:{index}"
                    chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_id))
                    chunk_ids.append(chunk_id)
                    doc.metadata = self._metadata_for_chunk(source, index, doc.metadata)

                total_batches = (len(split_document) - 1) // BATCH_SIZE + 1
                for i in range(0, len(split_document), BATCH_SIZE):
                    batch = split_document[i : i + BATCH_SIZE]
                    batch_ids = chunk_ids[i : i + BATCH_SIZE]
                    batch_no = i // BATCH_SIZE + 1

                    for attempt in range(3):
                        try:
                            self.vector_store.add_documents(batch, ids=batch_ids)
                            added_chunk_ids.extend(batch_ids)
                            logger.info(
                                f"[knowledge load] batch {batch_no}/{total_batches} OK ({source.title})"
                            )
                            break
                        except Exception as batch_err:
                            if self._is_non_retryable_embedding_error(batch_err):
                                logger.error(
                                    f"[knowledge load] batch {batch_no} failed without retry "
                                    f"({source.title}): {batch_err}"
                                )
                                raise
                            if attempt < 2:
                                logger.warning(
                                    f"[knowledge load] batch {batch_no} retry {attempt + 1}: {batch_err}"
                                )
                                time.sleep(5)
                            else:
                                raise
                    time.sleep(1)

                if previous:
                    previous_ids = previous.get("chunk_ids", [])
                    new_ids = set(chunk_ids)
                    stale_ids = [cid for cid in previous_ids if cid not in new_ids]
                    if stale_ids and not self._delete_chunk_ids(stale_ids, source.doc_id):
                        raise RuntimeError("Failed to remove stale chunks from the previous index")

                manifest["documents"][source.doc_id] = source_to_manifest_record(
                    source,
                    chunk_ids,
                    index_fingerprint=self.index_fingerprint,
                    index_config=self.index_config,
                )
                modified = True
                save_manifest(manifest)
                logger.info(
                    f"[knowledge load] Loaded {len(chunk_ids)} chunks from {path} "
                    f"(doc_id={source.doc_id})."
                )
            except Exception as e:
                if added_chunk_ids:
                    self._delete_chunk_ids(added_chunk_ids, f"{Path(path).name} partial update")
                errors.append(f"{Path(path).name}: {e}")
                logger.error(
                    f"[knowledge load] Failed to load {path}: {str(e)}", exc_info=True
                )
                if self._is_non_retryable_embedding_error(e):
                    logger.error(
                        "[knowledge load] Stopping indexing early because the embedding service "
                        "returned a non-retryable billing/quota error."
                    )
                    break
                continue

        update_manifest_index_state(
            manifest,
            last_error="; ".join(errors) if errors else None,
            bump_version=modified,
            pipeline_fingerprint=self.index_fingerprint,
        )
        save_manifest(manifest)
        return {
            "success": not errors,
            "errors": errors,
            "error_summary": "; ".join(errors),
            "modified": modified,
        }


if __name__ == "__main__":
    vs = VectorStoreService()
    vs.load_document()

    retriever = vs.get_retriever()
    res = retriever.invoke("stuck")
    for r in res:
        print(r.page_content)
        print("-" * 20)
