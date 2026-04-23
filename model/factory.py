"""
DashScope chat / embedding 模型工厂。

- 懒加载：模块 import 时不创建客户端，避免无 API key 时启动崩溃。
- 通过 DASHSCOPE_BASE_URL 环境变量切换国内/国际 endpoint。
- 通过 reset_models() 在用户更新 .env 后重建客户端。
"""
import os
from abc import ABC, abstractmethod
from typing import Optional

import dashscope
from langchain_core.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel, ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings

from utils.config_handler import rag_conf


def _apply_endpoint() -> None:
    """每次创建客户端前同步当前环境里的 base url。"""
    base_url = os.getenv("DASHSCOPE_BASE_URL", "").strip()
    dashscope.base_http_api_url = (
        base_url or "https://dashscope.aliyuncs.com/api/v1"
    )


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


def resolve_chat_model_name() -> str:
    """优先读 .env 的 CHAT_MODEL_NAME；无则回退到 rag.yml 的默认值。"""
    override = os.getenv("CHAT_MODEL_NAME", "").strip()
    return override or rag_conf.get("chat_model_name", "qwen3-max")


class ChatModelFactory(BaseModelFactory):
    def __init__(self, streaming: bool = False):
        self.streaming = streaming

    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        _apply_endpoint()
        return ChatTongyi(model=resolve_chat_model_name(), streaming=self.streaming)


class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
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
