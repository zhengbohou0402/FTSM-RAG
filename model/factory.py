import os
from abc import ABC, abstractmethod
from typing import Optional

import dashscope
from langchain_core.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models.tongyi import ChatTongyi
from utils.config_handler import rag_conf

# 支持通过环境变量切换国际版/国内版 DashScope endpoint
# 国内版：https://dashscope.aliyuncs.com/api/v1（默认）
# 国际版：https://dashscope-intl.aliyuncs.com/api/v1（qwen3.6-plus 等模型所在地）
_dashscope_base_url = os.getenv("DASHSCOPE_BASE_URL", "").strip()
if _dashscope_base_url:
    dashscope.base_http_api_url = _dashscope_base_url


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


class ChatModelFactory(BaseModelFactory):
    def __init__(self, streaming: bool = False):
        self.streaming = streaming

    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return ChatTongyi(model=rag_conf["chat_model_name"], streaming=self.streaming)


class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return DashScopeEmbeddings(model=rag_conf["embedding_model_name"])


def create_chat_model(*, streaming: bool = False) -> Optional[Embeddings | BaseChatModel]:
    return ChatModelFactory(streaming=streaming).generator()


chat_model = create_chat_model()
embed_model = EmbeddingsFactory().generator()
