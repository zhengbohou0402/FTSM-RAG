import hashlib
import json
import time
from pathlib import Path

import urllib3
from langchain_chroma import Chroma
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
from utils.config_handler import chroma_conf, rag_conf
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


class VectorStoreService:
    def __init__(self):
        self.vector_store = Chroma(
            collection_name=chroma_conf["collection_name"],
            embedding_function=get_embed_model(),
            persist_directory=get_abs_path(chroma_conf["persist_directory"]),
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

        self.index_config = self._build_index_config()
        self.index_fingerprint = self._build_index_fingerprint(self.index_config)

    @staticmethod
    def _build_index_config() -> dict:
        return {
            "schema_version": 2,
            "embedding_model_name": rag_conf["embedding_model_name"],
            "collection_name": chroma_conf["collection_name"],
            "chunk_size": chroma_conf["chunk_size"],
            "chunk_overlap": chroma_conf["chunk_overlap"],
            "separators": chroma_conf["separators"],
            "allowed_file_types": chroma_conf["allow_knowledge_file_type"],
        }

    @staticmethod
    def _build_index_fingerprint(index_config: dict) -> str:
        payload = json.dumps(index_config, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def get_retriever(self, k: int | None = None):
        return self.vector_store.as_retriever(
            search_kwargs={"k": k or chroma_conf["k"]}
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
        chunk_id = f"{source.doc_id}:chunk:{chunk_index}:{source.hash[:12]}"
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

    def load_document(self, target_paths: list[str | Path] | None = None):
        manifest = load_manifest()
        manifest.setdefault("documents", {})
        modified = False
        errors: list[str] = []

        if target_paths is None:
            allowed_files_path: list[str] = listdir_with_allowed_type(
                get_abs_path(chroma_conf["data_path"]),
                tuple(chroma_conf["allow_knowledge_file_type"]),
            )
            current_doc_ids = {stable_file_doc_id(path) for path in allowed_files_path}

            for doc_id, record in list(manifest["documents"].items()):
                if not doc_id.startswith("file:") or doc_id in current_doc_ids:
                    continue
                self._delete_chunk_ids(record.get("chunk_ids", []), doc_id)
                del manifest["documents"][doc_id]
                modified = True
                save_manifest(manifest)
                logger.info(f"[knowledge load] Removed missing source document {doc_id}.")
        else:
            allowed_extensions = tuple(
                f".{ext.lower().lstrip('.')}" for ext in chroma_conf["allow_knowledge_file_type"]
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
                    logger.warning(
                        f"[knowledge load] No valid text found in {path}. Skipping."
                    )
                    continue

                split_document: list[Document] = self.spliter.split_documents(documents)
                if not split_document:
                    logger.warning(
                        f"[knowledge load] No valid chunks produced from {path}. Skipping."
                    )
                    continue

                chunk_ids: list[str] = []
                for index, doc in enumerate(split_document):
                    chunk_id = f"{source.doc_id}:chunk:{index}:{source.hash[:12]}"
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
                    self._delete_chunk_ids(stale_ids, source.doc_id)

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


if __name__ == "__main__":
    vs = VectorStoreService()
    vs.load_document()

    retriever = vs.get_retriever()
    res = retriever.invoke("stuck")
    for r in res:
        print(r.page_content)
        print("-" * 20)
