"""Milvus 写入器：把双写事件落库到 Milvus 集合。

特性：
- 启动时确保 collection + 索引（HNSW + COSINE）
- pymilvus 同步 SDK → ``asyncio.to_thread`` 放入线程池，避免阻塞事件循环
- ``upsert`` 语义：同 ``id`` 重复消息幂等（pymilvus 内置）
- 异常分类：网络异常可重试、参数异常不可重试
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import structlog
from pymilvus import DataType, MilvusClient

from ..config import Settings
from ..observability.metrics import milvus_write_latency_seconds

logger = structlog.get_logger(__name__)


# ---------- 异常分类 ----------
class MilvusError(Exception):
    """Milvus 写入基类异常。"""


class MilvusNetworkError(MilvusError):
    """网络/超时类异常（可重试）。"""


class MilvusParamError(MilvusError):
    """参数错误（不可重试 → DLQ）。"""


class MilvusCollectionNotExistError(MilvusError):
    """Collection 不存在（可重试，等待初始化完成）。"""


# ---------- Schema 描述 ----------
POST_SCHEMA_FIELDS = [
    ("id", DataType.INT64, {"is_primary": True}),
    ("user_id", DataType.INT64, {}),
    ("vector", DataType.FLOAT_VECTOR, {"dim": 1024}),
    ("metadata", DataType.JSON, {}),
]

USER_SCHEMA_FIELDS = [
    ("id", DataType.INT64, {"is_primary": True}),
    ("account_vector", DataType.FLOAT_VECTOR, {"dim": 1024}),
    ("metadata", DataType.JSON, {}),
]


def _build_schema(fields):
    """从字段定义构建 Milvus schema。"""
    schema = MilvusClient.create_schema(auto_id=False)
    for name, dtype, extra in fields:
        # pymilvus 的 schema.add_field 接受 kwargs
        schema.add_field(name, dtype, **extra)
    return schema


# ---------- 写入器 ----------
class MilvusWriter:
    """Milvus 写入门面。

    使用方式::

        writer = MilvusWriter(settings)
        await writer.upsert_post(post_id=123, user_id=456,
                                 vector=[0.1, 0.2, ...],
                                 metadata={"title": "...", "tags": [...], ...})
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: MilvusClient | None = None
        # 缓存已初始化的 collection，避免重复 has_collection
        self._initialized_collections: set[str] = set()

    # ---- 生命周期 ----
    def connect(self) -> None:
        if self._client is not None:
            return
        uri = f"http://{self._settings.milvus_host}:{self._settings.milvus_port}"
        # token 仅在有 user/password 时传入
        token: Optional[str] = None
        if self._settings.milvus_user and self._settings.milvus_password:
            token = f"{self._settings.milvus_user}:{self._settings.milvus_password}"
        self._client = MilvusClient(uri=uri, token=token)
        logger.info("milvus_connected", host=self._settings.milvus_host, port=self._settings.milvus_port)

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(self._client.get_server_version())
        except Exception:
            return False

    # ---- 集合初始化 ----
    def ensure_collections(self) -> None:
        """启动时调用，确保 collection 与索引就绪（幂等）。"""
        self._ensure_post_collection()
        self._ensure_user_collection()

    def _ensure_post_collection(self) -> None:
        name = self._settings.milvus_collection_post
        if name in self._initialized_collections:
            return
        assert self._client is not None
        if not self._client.has_collection(name):
            schema = _build_schema(POST_SCHEMA_FIELDS)
            self._client.create_collection(collection_name=name, schema=schema)
            logger.info("milvus_collection_created", name=name)
        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type=self._settings.milvus_index_type,
            metric_type=self._settings.milvus_metric_type,
            params={"M": 16, "efConstruction": 200},
        )
        self._client.create_index(name, index_params)
        # 释放 collection 以加载到内存
        try:
            self._client.load_collection(name)
        except Exception as e:  # pragma: no cover
            logger.warning("milvus_load_collection_failed", name=name, error=str(e))
        self._initialized_collections.add(name)
        logger.info("milvus_collection_ready", name=name)

    def _ensure_user_collection(self) -> None:
        name = self._settings.milvus_collection_user
        if name in self._initialized_collections:
            return
        assert self._client is not None
        if not self._client.has_collection(name):
            schema = _build_schema(USER_SCHEMA_FIELDS)
            self._client.create_collection(collection_name=name, schema=schema)
            logger.info("milvus_collection_created", name=name)
        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="account_vector",
            index_type=self._settings.milvus_index_type,
            metric_type=self._settings.milvus_metric_type,
            params={"M": 16, "efConstruction": 200},
        )
        self._client.create_index(name, index_params)
        try:
            self._client.load_collection(name)
        except Exception as e:  # pragma: no cover
            logger.warning("milvus_load_collection_failed", name=name, error=str(e))
        self._initialized_collections.add(name)
        logger.info("milvus_collection_ready", name=name)

    # ---- 写接口 ----
    async def upsert_post(
        self,
        post_id: int,
        user_id: int,
        vector: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        await self._upsert(
            collection=self._settings.milvus_collection_post,
            data=[{
                "id": int(post_id),
                "user_id": int(user_id),
                "vector": list(vector),
                "metadata": dict(metadata),
            }],
            operation="upsert_post",
        )

    async def delete_post(self, post_id: int) -> None:
        await self._delete(
            collection=self._settings.milvus_collection_post,
            expr=f"id == {int(post_id)}",
            operation="delete_post",
        )

    async def upsert_user(
        self,
        user_id: int,
        vector: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        await self._upsert(
            collection=self._settings.milvus_collection_user,
            data=[{
                "id": int(user_id),
                "account_vector": list(vector),
                "metadata": dict(metadata),
            }],
            operation="upsert_user",
        )

    async def delete_user(self, user_id: int) -> None:
        await self._delete(
            collection=self._settings.milvus_collection_user,
            expr=f"id == {int(user_id)}",
            operation="delete_user",
        )

    # ---- 内部 ----
    async def _upsert(self, collection: str, data: List[Dict[str, Any]], operation: str) -> None:
        if self._client is None:
            raise RuntimeError("MilvusWriter.connect() must be called first")
        start = time.perf_counter()
        try:
            await asyncio.to_thread(
                self._client.upsert, collection_name=collection, data=data
            )
        except Exception as e:
            elapsed = time.perf_counter() - start
            milvus_write_latency_seconds.labels(collection=collection, operation=operation).observe(elapsed)
            self._classify_error(e, collection)
            raise
        elapsed = time.perf_counter() - start
        milvus_write_latency_seconds.labels(collection=collection, operation=operation).observe(elapsed)
        logger.info("milvus_upsert_ok", collection=collection, count=len(data), op=operation)

    async def _delete(self, collection: str, expr: str, operation: str) -> None:
        if self._client is None:
            raise RuntimeError("MilvusWriter.connect() must be called first")
        start = time.perf_counter()
        try:
            await asyncio.to_thread(
                self._client.delete, collection_name=collection, expr=expr
            )
        except Exception as e:
            elapsed = time.perf_counter() - start
            milvus_write_latency_seconds.labels(collection=collection, operation=operation).observe(elapsed)
            self._classify_error(e, collection)
            raise
        elapsed = time.perf_counter() - start
        milvus_write_latency_seconds.labels(collection=collection, operation=operation).observe(elapsed)
        logger.info("milvus_delete_ok", collection=collection, expr=expr, op=operation)

    @staticmethod
    def _classify_error(e: Exception, collection: str) -> None:
        """根据异常类型决定后续是否重试。"""
        name = type(e).__name__
        msg = str(e).lower()
        # 参数类 → DLQ
        if "param" in name.lower() or "invalid" in msg or "value" in msg:
            raise MilvusParamError(f"milvus param error [{collection}]: {e}") from e
        # collection 不存在 → 可重试（等待生产者建表）
        if "collectionnotexist" in name.lower() or "collection not exist" in msg:
            raise MilvusCollectionNotExistError(f"milvus collection missing [{collection}]: {e}") from e
        # 其余视为网络/瞬时错误 → 可重试
        raise MilvusNetworkError(f"milvus network error [{collection}]: {e}") from e
