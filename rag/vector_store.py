import time

import urllib3
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from model.factory import embed_model
from rag.ingestion import (
    build_file_source_document,
    stable_file_doc_id,
    load_manifest,
    save_manifest,
    source_to_manifest_record,
)
from utils.config_handler import chroma_conf
from utils.file_handler import image_loader, listdir_with_allowed_type, pdf_loader, txt_loader
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

urllib3.util.connection.HAS_IPV6 = False

BATCH_SIZE = 20


class VectorStoreService:
    def __init__(self):
        self.vector_store = Chroma(
            collection_name=chroma_conf["collection_name"],
            embedding_function=embed_model,
            persist_directory=chroma_conf["persist_directory"],
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": chroma_conf["k"]})

    def _get_file_documents(self, read_path: str) -> list[Document]:
        lower_path = read_path.lower()
        if lower_path.endswith(".txt"):
            return txt_loader(read_path)
        if lower_path.endswith(".pdf"):
            return pdf_loader(read_path)
        if any(lower_path.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
            return image_loader(read_path)
        return []

    def _delete_chunk_ids(self, chunk_ids: list[str], doc_id: str) -> None:
        if not chunk_ids:
            return
        try:
            self.vector_store.delete(ids=chunk_ids)
            logger.info(f"[knowledge load] Deleted {len(chunk_ids)} old chunks for {doc_id}.")
        except Exception as exc:
            logger.warning(f"[knowledge load] Failed to delete old chunks for {doc_id}: {exc}")

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

    def load_document(self):
        manifest = load_manifest()
        manifest.setdefault("documents", {})

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
            save_manifest(manifest)
            logger.info(f"[knowledge load] Removed missing source document {doc_id}.")

        for path in allowed_files_path:
            try:
                source = build_file_source_document(path)
                previous = manifest["documents"].get(source.doc_id)

                if previous and previous.get("hash") == source.hash:
                    logger.info(f"[knowledge load] {path} unchanged. Skipping.")
                    continue

                if previous:
                    self._delete_chunk_ids(previous.get("chunk_ids", []), source.doc_id)

                documents: list[Document] = self._get_file_documents(path)
                if not documents:
                    logger.warning(f"[knowledge load] No valid text found in {path}. Skipping.")
                    continue

                split_document: list[Document] = self.spliter.split_documents(documents)
                if not split_document:
                    logger.warning(f"[knowledge load] No valid chunks produced from {path}. Skipping.")
                    continue

                chunk_ids: list[str] = []
                for index, doc in enumerate(split_document):
                    chunk_id = f"{source.doc_id}:chunk:{index}:{source.hash[:12]}"
                    chunk_ids.append(chunk_id)
                    doc.metadata = self._metadata_for_chunk(source, index, doc.metadata)

                total_batches = (len(split_document) - 1) // BATCH_SIZE + 1
                for i in range(0, len(split_document), BATCH_SIZE):
                    batch = split_document[i:i + BATCH_SIZE]
                    batch_ids = chunk_ids[i:i + BATCH_SIZE]
                    batch_no = i // BATCH_SIZE + 1

                    for attempt in range(3):
                        try:
                            self.vector_store.add_documents(batch, ids=batch_ids)
                            logger.info(f"[knowledge load] batch {batch_no}/{total_batches} OK ({source.title})")
                            break
                        except Exception as batch_err:
                            if attempt < 2:
                                logger.warning(f"[knowledge load] batch {batch_no} retry {attempt + 1}: {batch_err}")
                                time.sleep(5)
                            else:
                                raise
                    time.sleep(1)

                manifest["documents"][source.doc_id] = source_to_manifest_record(source, chunk_ids)
                save_manifest(manifest)
                logger.info(
                    f"[knowledge load] Loaded {len(chunk_ids)} chunks from {path} "
                    f"(doc_id={source.doc_id})."
                )
            except Exception as e:
                logger.error(f"[knowledge load] Failed to load {path}: {str(e)}", exc_info=True)
                continue


if __name__ == "__main__":
    vs = VectorStoreService()
    vs.load_document()

    retriever = vs.get_retriever()
    res = retriever.invoke("stuck")
    for r in res:
        print(r.page_content)
        print("-" * 20)
