"""
DashScope / Google Vertex AI chat / embedding 模型工厂。

- 懒加载：模块 import 时不创建客户端，避免无 API key 时启动崩溃。
- 支持 LLM_PROVIDER="dashscope" 或 "vertexai" 切换。
- 通过 reset_models() 在用户更新 .env 后重建客户端。
"""

import os
from abc import ABC, abstractmethod
from typing import Optional

import dashscope
from langchain_community.chat_models.tongyi import BaseChatModel, ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.embeddings import Embeddings

from utils.config_handler import rag_conf


_ALLOWED_DASHSCOPE_BASE_URLS = {
    "https://dashscope.aliyuncs.com/api/v1",
    "https://dashscope-intl.aliyuncs.com/api/v1",
}


def _apply_endpoint() -> None:
    """每次创建客户端前同步当前环境里的 base url。

    注意：若 DASHSCOPE_BASE_URL 为空字符串，必须从 os.environ 中删除，
    否则 DashScope SDK 会直接读取空字符串拼出无效 URL，导致 400 url error。
    """
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


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


def resolve_chat_model_name(provider: str = "dashscope") -> str:
    """优先读 .env 的 CHAT_MODEL_NAME；无则回退到 rag.yml 的默认值。"""
    override = os.getenv("CHAT_MODEL_NAME", "").strip()
    
    if provider == "vertexai":
        # Vertex AI 支持的模型列表（截至 2026-06）
        _VERTEX_MODELS = {
            "gemini-3.5-flash",
            "gemini-3.5-pro",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        }
        if override.lower() in _VERTEX_MODELS:
            return override
        return os.getenv("VERTEX_MODEL_NAME", "gemini-3.5-flash")
    else:
        # dashscope fallback
        if override and override.lower().startswith("gemini"):
            return "qwen-turbo"
        return override or rag_conf.get("chat_model_name", "qwen3-max")


class ChatModelFactory(BaseModelFactory):
    def __init__(self, streaming: bool = False):
        self.streaming = streaming

    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        provider = os.getenv("LLM_PROVIDER", "dashscope").strip().lower()
        if provider == "vertexai":
            from langchain_google_vertexai import ChatVertexAI
            return ChatVertexAI(
                model_name=resolve_chat_model_name(provider),
                project=os.getenv("VERTEX_PROJECT_ID", "rag-fist"),
                location=os.getenv("VERTEX_LOCATION", "global"),
                streaming=self.streaming,
            )
            
        _apply_endpoint()
        return ChatTongyi(model=resolve_chat_model_name(provider), streaming=self.streaming)


class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        provider = os.getenv("LLM_PROVIDER", "dashscope").strip().lower()
        if provider == "vertexai":
            from langchain_google_vertexai import VertexAIEmbeddings
            embed_model = os.getenv("VERTEX_EMBEDDING_MODEL", "gemini-embedding-001")
            # gemini-embedding-001 支持 Matryoshka 可变维度（256 / 768 / 1536 / 3072）
            # 3072 维精度最高；若需节省存储可改为 768
            if embed_model == "gemini-embedding-001":
                return VertexAIEmbeddings(
                    model_name=embed_model,
                    project=os.getenv("VERTEX_PROJECT_ID", "rag-fist"),
                    location=os.getenv("VERTEX_LOCATION", "global"),
                )
            return VertexAIEmbeddings(
                model_name=embed_model,
                project=os.getenv("VERTEX_PROJECT_ID", "rag-fist"),
                location=os.getenv("VERTEX_LOCATION", "global"),
            )
            
        _apply_endpoint()
        return DashScopeEmbeddings(model=rag_conf["embedding_model_name"])


def create_chat_model(*, streaming: bool = False) -> BaseChatModel:
    return ChatModelFactory(streaming=streaming).generator()


# ── 单例懒加载 ────────────────────────────────────────────
_chat_model: Optional[BaseChatModel] = None
_embed_model: Optional[Embeddings] = None


def get_chat_model() -> BaseChatModel:
    global _chat_model
    if _chat_model is None:
        _chat_model = create_chat_model()
    return _chat_model


def get_embed_model() -> Embeddings:
    global _embed_model
    if _embed_model is None:
        _embed_model = EmbeddingsFactory().generator()
    return _embed_model


def reset_models() -> None:
    """Settings 保存后调用，下次取用时会用最新配置重建。"""
    global _chat_model, _embed_model
    _chat_model = None
    _embed_model = None
