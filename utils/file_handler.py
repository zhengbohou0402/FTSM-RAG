import base64
import hashlib
import os

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from utils.config_handler import rag_conf
from utils.logger_handler import logger
from utils.text_encoding import read_text_safely


def get_file_md5_hex(filepath: str):
    if not os.path.exists(filepath):
        logger.error(f"[md5] File does not exist: {filepath}")
        return None

    if not os.path.isfile(filepath):
        logger.error(f"[md5] Path is not a file: {filepath}")
        return None

    md5_obj = hashlib.md5()
    chunk_size = 4096

    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                md5_obj.update(chunk)

        return md5_obj.hexdigest()
    except Exception as e:
        logger.error(f"[md5] Failed to calculate md5 for {filepath}: {str(e)}")
        return None


def listdir_with_allowed_type(path: str, allowed_types: tuple[str]):
    """递归扫描目录下所有匹配后缀的文件（含子目录如 uploads/）。

    第二轮复审 P0：旧实现用 os.listdir 只扫顶层，导致全量索引重建时
    current_doc_ids 漏掉 uploads/ 子目录中已入库的文件，
    missing-source 清理逻辑会把它们的向量误删。
    """
    files = []

    if not os.path.isdir(path):
        logger.error(f"[listdir_with_allowed_type] Not a directory: {path}")
        return []

    allowed = tuple(t.lower() if t.startswith(".") else f".{t.lower()}" for t in allowed_types)

    for root, dirnames, filenames in os.walk(path):
        # 跳过隐藏文件/目录（以 . 开头）
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in sorted(filenames):
            if f.startswith("."):
                continue
            if f.lower().endswith(allowed):
                files.append(os.path.join(root, f))

    return tuple(sorted(files))


def pdf_loader(filepath: str, passwd=None) -> list[Document]:
    docs = PyPDFLoader(filepath, passwd).load()
    text_chars = sum(len((doc.page_content or "").strip()) for doc in docs)
    if text_chars < 80:
        logger.warning(
            "[pdf_loader] %s appears to be image-only or scanned (%s text chars). "
            "Create a text transcript before indexing.",
            filepath,
            text_chars,
        )
        return []
    return docs


def txt_loader(filepath: str) -> list[Document]:
    decoded = read_text_safely(filepath)
    if decoded.mojibake_score:
        logger.warning(
            "[txt_loader] Possible mojibake in %s after decoding as %s (score=%s).",
            filepath,
            decoded.encoding,
            decoded.mojibake_score,
        )
    return [
        Document(
            page_content=decoded.text,
            metadata={
                "source": filepath,
                "filename": os.path.basename(filepath),
                "encoding": decoded.encoding,
                "mojibake_score": decoded.mojibake_score,
            },
        )
    ]


def _image_mime_type(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")


def _extract_image_text_vertex(
    image_base64: str, mime_type: str, prompt_text: str
) -> str:
    """Gemini vision (Vertex 后端)：走与 chat 相同的多模态模型。"""
    from langchain_core.messages import HumanMessage

    from model.factory import get_chat_model

    message = HumanMessage(
        content=[
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
            {"type": "text", "text": prompt_text},
        ]
    )
    response = get_chat_model().invoke([message])
    content = response.content
    if isinstance(content, list):
        # Vertex/Gemini 返回 content blocks（如 [{'type':'text','text':...}]）
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(content).strip()


def _extract_image_text_dashscope(
    image_base64: str, prompt_text: str, image_model_name: str
) -> str:
    """DashScope Qwen-VL（dashscope 回滚后端）。"""
    from dashscope import MultiModalConversation

    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"data:image/jpeg;base64,{image_base64}"},
                {"text": prompt_text},
            ],
        }
    ]
    response = MultiModalConversation.call(model=image_model_name, messages=messages)
    if response.status_code != 200:
        raise RuntimeError(f"DashScope vision API error: {response.message}")
    return response.output.choices[0].message.content[0]["text"]


def image_loader(filepath: str) -> list[Document]:
    """
    Extract text from images using the configured vision-capable chat model
    (Gemini via Vertex AI, or Qwen-VL when running the dashscope backend).

    Args:
        filepath: Path to image file (png, jpg, jpeg, webp, gif)

    Returns:
        List of Document objects containing extracted text
    """
    from langchain_core.documents import Document

    try:
        # Read image and convert to base64
        with open(filepath, "rb") as image_file:
            image_base64 = base64.b64encode(image_file.read()).decode("utf-8")

        # Get image filename for context
        filename = os.path.basename(filepath)

        # Get image dimensions for proper formatting
        from PIL import Image

        with Image.open(filepath) as img:
            width, height = img.size

        # Construct prompt for text extraction
        prompt_text = """请仔细分析这张图片，并提取其中所有可读的文字内容。图片文件名: FILENAME。图片尺寸: WIDTHxHEIGHT像素。请按以下格式输出: 1 如果图片包含表格请用表格格式呈现 2 如果图片包含步骤说明请列出所有步骤 3 如果图片包含表单字段请列出字段名和示例值 4 保留原文的所有细节包括数字日期网址等 5 如果图片是截图请标注关键UI元素的位置如右上角高亮显示等。请直接输出提取的文字，不要有其他解释。"""
        prompt_text = prompt_text.replace("FILENAME", filename).replace("WIDTH", str(width)).replace("HEIGHT", str(height))

        from model.factory import resolve_backend

        if resolve_backend() == "vertex":
            extracted_text = _extract_image_text_vertex(
                image_base64, _image_mime_type(filepath), prompt_text
            )
        else:
            extracted_text = _extract_image_text_dashscope(
                image_base64,
                prompt_text,
                rag_conf.get("image_model_name", "qwen-vl-plus"),
            )

        if not extracted_text:
            logger.warning(f"[image_loader] Vision model returned no text for {filepath}")
            return []

        # Create document with metadata
        doc = Document(
            page_content=extracted_text,
            metadata={
                "source": filepath,
                "filename": filename,
                "type": "image",
                "image_extracted": True,
                "image_width": width,
                "image_height": height
            }
        )

        logger.info(f"[image_loader] Successfully extracted text from: {filepath}")
        return [doc]

    except FileNotFoundError:
        logger.error(f"[image_loader] Image file not found: {filepath}")
        return []
    except ImportError as e:
        logger.error(f"[image_loader] Missing dependency: {str(e)}")
        logger.error("[image_loader] Vertex backend requires: pip install langchain-google-vertexai pillow")
        return []
    except Exception as e:
        logger.error(f"[image_loader] Failed to extract text from {filepath}: {str(e)}")
        return []
