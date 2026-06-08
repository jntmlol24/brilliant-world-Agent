"""阿里云百炼 text-embedding-v3 嵌入模型封装（通过 DashScope OpenAI 兼容接口 / httpx）"""
from typing import List, Optional
import asyncio
import numpy as np
import httpx
from langchain_core.embeddings import Embeddings
from app.config.settings import settings
from app.config.model_config import model_config
from app.utils.logger import logger


class BGEEmbedding(Embeddings):
    """阿里云百炼 text-embedding-v3 嵌入模型封装类

    通过 DashScope OpenAI 兼容接口（httpx）调用 text-embedding-v3。
    类名沿用 BGEEmbedding 以保持对历史调用方（app.utils.__init__、vector_service 等）的兼容。
    """

    _instance: Optional["BGEEmbedding"] = None
    _lock = asyncio.Lock()

    # DashScope OpenAI 兼容 embeddings 端点
    _ENDPOINT_SUFFIX = "/embeddings"
    # 单次请求最大文本数（DashScope 限制）
    _MAX_BATCH_SIZE = 25

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        logger.info(
            f"初始化 text-embedding-v3 嵌入模型: {model_config.embedding_model_name} "
            f"(endpoint={settings.EMBEDDING_BASE_URL})"
        )

        self.model_name = model_config.embedding_model_name
        self.api_key = settings.EMBEDDING_API_KEY
        self.base_url = (settings.EMBEDDING_BASE_URL or "").rstrip("/")
        self._initialized = True
        logger.info("text-embedding-v3 嵌入模型初始化完成")

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用 DashScope OpenAI 兼容 embeddings 接口"""
        url = self.base_url + self._ENDPOINT_SUFFIX
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model_name,
            "input": texts,
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        # OpenAI 兼容格式：{"data": [{"embedding": [...], "index": 0}, ...]}
        embeddings = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        return embeddings

    def _embed_with_batching(self, texts: List[str]) -> List[List[float]]:
        """分批调用 API 嵌入文本"""
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), self._MAX_BATCH_SIZE):
            batch = texts[i : i + self._MAX_BATCH_SIZE]
            all_embeddings.extend(self._call_api(batch))
        return all_embeddings

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文档"""
        try:
            return self._embed_with_batching(texts)
        except Exception as e:
            logger.error(f"文档嵌入失败: {e}")
            return [_random_vector() for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        """嵌入查询文本"""
        try:
            return self._call_api([text])[0]
        except Exception as e:
            logger.error(f"查询嵌入失败: {e}")
            return _random_vector()

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """异步批量嵌入文档"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)

    async def aembed_query(self, text: str) -> List[float]:
        """异步嵌入查询"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)


class _RandomEmbedding(Embeddings):
    """随机向量占位符（仅用于无嵌入模型时的测试）"""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [_random_vector() for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        return _random_vector()


def _random_vector(dim: int = None) -> List[float]:
    """生成随机向量"""
    if dim is None:
        dim = model_config.embedding_dim
    vector = np.random.randn(dim).astype(np.float32).tolist()
    return vector


# 全局单例
_embedding_instance: Optional[BGEEmbedding] = None


def get_embedding() -> BGEEmbedding:
    """获取全局嵌入实例"""
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = BGEEmbedding()
    return _embedding_instance
