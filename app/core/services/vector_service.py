"""向量服务 - 通用向量操作封装"""
from typing import List, Dict, Any, Optional
import time
from app.db.milvus_client import milvus_client
from app.utils.embedding import get_embedding
from app.config.settings import settings
from app.utils.logger import logger


class VectorService:
    """通用向量服务"""

    def __init__(self):
        self.embedding = get_embedding()

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文本"""
        return await self.embedding.aembed_documents(texts)

    async def embed_query(self, text: str) -> List[float]:
        """嵌入查询"""
        return await self.embedding.aembed_query(text)

    async def search_similar(
        self,
        collection_name: str,
        query_text: str,
        filter_expr: Optional[str] = None,
        limit: int = 10,
        output_fields: Optional[List[str]] = None,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """搜索相似向量

        Args:
            collection_name: 集合名
            query_text: 查询文本
            filter_expr: 过滤表达式
            limit: 返回数量
            output_fields: 输出字段
            threshold: 相似度阈值

        Returns:
            命中结果列表
        """
        query_vector = await self.embed_query(query_text)
        results = await milvus_client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            filter_expr=filter_expr,
            limit=limit,
            output_fields=output_fields,
        )

        if threshold is not None:
            results = [r for r in results if r.get("score", 0) >= threshold]

        return results

    async def search_by_vector(
        self,
        collection_name: str,
        query_vector: List[float],
        filter_expr: Optional[str] = None,
        limit: int = 10,
        output_fields: Optional[List[str]] = None,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """通过向量搜索相似项"""
        results = await milvus_client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            filter_expr=filter_expr,
            limit=limit,
            output_fields=output_fields,
        )

        if threshold is not None:
            results = [r for r in results if r.get("score", 0) >= threshold]

        return results

    @staticmethod
    def current_timestamp() -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.time() * 1000)
