"""
Chat / embedding 模型工厂（双后端：Vertex AI / DashScope）。

- 后端选择：LLM_BACKEND=vertex|dashscope；未设置时，有 VERTEX_PROJECT_ID
  则默认 vertex，否则 dashscope。
- 懒加载：模块 import 时不创建客户端，避免无凭据时启动崩溃。
- DashScope 后端通过 DASHSCOPE_BASE_URL 切换国内/国际 endpoint。
- 通过 reset_models() 在用户更新 .env 后重建客户端。
"""

import os
import threading
from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from utils.config_handler import rag_conf


_ALLOWED_DASHSCOPE_BASE_URLS = {
    "https://dashscope.aliyuncs.com/api/v1",
    "https://dashscope-intl.aliyuncs.com/api/v1",
}


def resolve_backend() -> str:
    """vertex | dashscope。显式 LLM_BACKEND 优先，其次看 VERTEX_PROJECT_ID。"""
    explicit = os.getenv("LLM_BACKEND", "").strip().lower()
    if explicit in ("vertex", "dashscope"):
        return explicit
    if os.getenv("VERTEX_PROJECT_ID", "").strip():
        return "vertex"
    return "dashscope"


def resolve_chat_model_name() -> str:
    if resolve_backend() == "vertex":
        return (
            os.getenv("VERTEX_MODEL_NAME", "").strip()
            or os.getenv("CHAT_MODEL_NAME", "").strip()
            or rag_conf.get("chat_model_name", "gemini-2.5-flash")
        )
    override = os.getenv("CHAT_MODEL_NAME", "").strip()
    return override or rag_conf.get("chat_model_name", "qwen3-max")


def resolve_embedding_model_name() -> str:
    """当前后端实际使用的 embedding 模型名（进索引指纹，换模型即触发全量重嵌）。"""
    if resolve_backend() == "vertex":
        return (
            os.getenv("VERTEX_EMBEDDING_MODEL", "").strip()
            or "gemini-embedding-001"
        )
    return rag_conf.get("embedding_model_name", "text-embedding-v3")


def _apply_endpoint() -> None:
    """DashScope 后端：每次创建客户端前同步当前环境里的 base url。

    注意：若 DASHSCOPE_BASE_URL 为空字符串，必须从 os.environ 中删除，
    否则 DashScope SDK 会直接读取空字符串拼出无效 URL，导致 400 url error。
    """
    import dashscope

    base_url = os.getenv("DASHSCOPE_BASE_URL", "").strip()
    if base_url:
        base_url = base_url.rstrip("/")
        if base_url not in _ALLOWED_DASHSCOPE_BASE_URLS:
            raise ValueError("DASHSCOPE_BASE_URL must use an official DashScope endpoint")
        dashscope.base_http_api_url = base_url
        os.environ["DASHSCOPE_BASE_URL"] = base_url
    else:
        # 删除空值，让 DashScope SDK 用自己的硬编码默认值
        os.environ.pop("DASHSCOPE_BASE_URL", None)
        dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"


def _ensure_vertex_adc_path() -> None:
    """兼容容器内路径 `/ftsm/.gcp/...` 与宿主机本地运行。"""
    adc = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if adc and not os.path.exists(adc) and adc.startswith("/ftsm/"):
        from utils.path_tool import get_abs_path

        local_candidate = get_abs_path(adc[len("/ftsm/") :])
        if os.path.exists(local_candidate):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_candidate


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


class ChatModelFactory(BaseModelFactory):
    def __init__(self, streaming: bool = False):
        self.streaming = streaming

    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        if resolve_backend() == "vertex":
            _ensure_vertex_adc_path()
            from langchain_google_vertexai import ChatVertexAI

            return ChatVertexAI(
                model=resolve_chat_model_name(),
                project=os.getenv("VERTEX_PROJECT_ID", "").strip(),
                location=os.getenv("VERTEX_LOCATION", "global").strip() or "global",
                streaming=self.streaming,
            )
        from langchain_community.chat_models.tongyi import ChatTongyi

        _apply_endpoint()
        return ChatTongyi(model=resolve_chat_model_name(), streaming=self.streaming)


class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        if resolve_backend() == "vertex":
            _ensure_vertex_adc_path()
            from langchain_google_vertexai import VertexAIEmbeddings

            return VertexAIEmbeddings(
                model=resolve_embedding_model_name(),
                project=os.getenv("VERTEX_PROJECT_ID", "").strip(),
                location=os.getenv("VERTEX_LOCATION", "global").strip() or "global",
            )
        from langchain_community.embeddings import DashScopeEmbeddings

        _apply_endpoint()
        return DashScopeEmbeddings(model=resolve_embedding_model_name())


def create_chat_model(*, streaming: bool = False) -> BaseChatModel:
    return ChatModelFactory(streaming=streaming).generator()


# DashScope SDK 的 endpoint 是进程级全局变量。reranker 走的是 DashScope API
# 但独立于对话后端（vertex 对话 + dashscope 重排是允许的组合），因此在
# rag_service 侧调用精排前需要显式同步一次 endpoint。放宽为公开别名。
apply_dashscope_endpoint = _apply_endpoint


# ── 单例懒加载 ────────────────────────────────────────────
_chat_model: Optional[BaseChatModel] = None
_embed_model: Optional[Embeddings] = None
_model_lock = threading.Lock()


def get_chat_model() -> BaseChatModel:
    global _chat_model
    if _chat_model is None:
        with _model_lock:
            if _chat_model is None:
                _chat_model = create_chat_model()
    return _chat_model


def get_embed_model() -> Embeddings:
    global _embed_model
    if _embed_model is None:
        with _model_lock:
            if _embed_model is None:
                _embed_model = EmbeddingsFactory().generator()
    return _embed_model


def reset_models() -> None:
    """Settings 保存后调用，下次取用时会用最新配置重建。"""
    global _chat_model, _embed_model
    with _model_lock:
        _chat_model = None
        _embed_model = None
