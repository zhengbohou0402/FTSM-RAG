import base64
import hashlib
import os

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

from utils.config_handler import rag_conf
from utils.logger_handler import logger


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
    files = []

    if not os.path.isdir(path):
        logger.error(f"[listdir_with_allowed_type] Not a directory: {path}")
        return []

    for f in os.listdir(path):
        if f.endswith(allowed_types):
            files.append(os.path.join(path, f))

    return tuple(files)


def pdf_loader(filepath: str, passwd=None) -> list[Document]:
    return PyPDFLoader(filepath, passwd).load()


def txt_loader(filepath: str) -> list[Document]:
    return TextLoader(filepath, encoding="utf-8").load()


def image_loader(filepath: str) -> list[Document]:
    """
    Extract text from images using vision model (DashScope Qwen-VL).
    
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
        
        from dashscope import MultiModalConversation
        
        # Get image dimensions for proper formatting
        from PIL import Image
        img = Image.open(filepath)
        width, height = img.size
        
        # Construct prompt for text extraction
        prompt_text = """请仔细分析这张图片，并提取其中所有可读的文字内容。图片文件名: FILENAME。图片尺寸: WIDTHxHEIGHT像素。请按以下格式输出: 1 如果图片包含表格请用表格格式呈现 2 如果图片包含步骤说明请列出所有步骤 3 如果图片包含表单字段请列出字段名和示例值 4 保留原文的所有细节包括数字日期网址等 5 如果图片是截图请标注关键UI元素的位置如右上角高亮显示等。请直接输出提取的文字，不要有其他解释。"""
        prompt_text = prompt_text.replace("FILENAME", filename).replace("WIDTH", str(width)).replace("HEIGHT", str(height))
        
        # Call Qwen-VL model directly using DashScope SDK
        messages = [
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/jpeg;base64,{image_base64}"},
                    {"text": prompt_text}
                ]
            }
        ]
        
        image_model_name = rag_conf.get("image_model_name", "qwen-vl-plus")
        response = MultiModalConversation.call(model=image_model_name, messages=messages)
        
        if response.status_code == 200:
            extracted_text = response.output.choices[0].message.content[0]["text"]
        else:
            logger.error(f"[image_loader] API error: {response.message}")
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
        logger.error(f"[image_loader] Please install: pip install dashscope pillow")
        return []
    except Exception as e:
        logger.error(f"[image_loader] Failed to extract text from {filepath}: {str(e)}")
        return []
