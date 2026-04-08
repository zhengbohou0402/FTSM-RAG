import os
import time

# 强制使用 IPv4，避免 IPv6 不稳定导致 DashScope API 超时
import urllib3
urllib3.util.connection.HAS_IPV6 = False

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from model.factory import embed_model
from utils.config_handler import chroma_conf
from utils.file_handler import get_file_md5_hex, listdir_with_allowed_type, pdf_loader, txt_loader, image_loader
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

BATCH_SIZE = 20  # 每批最多提交的 chunk 数，避免 API 超时


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

    def load_document(self):
        def check_md5_hex(md5_for_check: str):
            md5_store_path = get_abs_path(chroma_conf["md5_hex_store"])
            if not os.path.exists(md5_store_path):
                open(md5_store_path, "w", encoding="utf-8").close()
                return False

            with open(md5_store_path, "r", encoding="utf-8") as f:
                for line in f.readlines():
                    if line.strip() == md5_for_check:
                        return True
                return False

        def save_md5_hex(md5_for_check: str):
            with open(get_abs_path(chroma_conf["md5_hex_store"]), "a", encoding="utf-8") as f:
                f.write(md5_for_check + "\n")

        def get_file_documents(read_path: str):
            if read_path.endswith("txt"):
                return txt_loader(read_path)
            if read_path.endswith("pdf"):
                return pdf_loader(read_path)
            # Support for image files (png, jpg, jpeg, webp, gif)
            if any(read_path.lower().endswith(ext) for ext in ["png", "jpg", "jpeg", "webp", "gif"]):
                return image_loader(read_path)
            return []

        allowed_files_path: list[str] = listdir_with_allowed_type(
            get_abs_path(chroma_conf["data_path"]),
            tuple(chroma_conf["allow_knowledge_file_type"]),
        )

        for path in allowed_files_path:
            md5_hex = get_file_md5_hex(path)

            if check_md5_hex(md5_hex):
                logger.info(f"[knowledge load] {path} already exists in the vector store. Skipping.")
                continue

            try:
                documents: list[Document] = get_file_documents(path)

                if not documents:
                    logger.warning(f"[knowledge load] No valid text found in {path}. Skipping.")
                    continue

                split_document: list[Document] = self.spliter.split_documents(documents)

                if not split_document:
                    logger.warning(f"[knowledge load] No valid chunks produced from {path}. Skipping.")
                    continue

                # 分批提交，每批最多 BATCH_SIZE 个 chunk，失败自动重试 3 次
                total_batches = (len(split_document) - 1) // BATCH_SIZE + 1
                for i in range(0, len(split_document), BATCH_SIZE):
                    batch = split_document[i:i + BATCH_SIZE]
                    batch_no = i // BATCH_SIZE + 1
                    for attempt in range(3):
                        try:
                            self.vector_store.add_documents(batch)
                            logger.info(f"[knowledge load] batch {batch_no}/{total_batches} OK  ({path.split('/')[-1]})")
                            break
                        except Exception as batch_err:
                            if attempt < 2:
                                logger.warning(f"[knowledge load] batch {batch_no} retry {attempt+1}: {batch_err}")
                                time.sleep(5)
                            else:
                                raise
                    time.sleep(1)

                save_md5_hex(md5_hex)
                logger.info(f"[knowledge load] Loaded content from {path} successfully.")
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
