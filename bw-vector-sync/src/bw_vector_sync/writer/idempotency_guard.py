"""幂等去重：基于 Redis SETNX 的消息级去重。

设计：
- 同一 ``(routing_key, message_id)`` 在 TTL 窗口内只会被处理一次
- TTL 默认 7 天，足够覆盖业务回放窗口与对账任务
- 使用 ``SET key val NX EX ttl`` 原子操作（redis-py async）
- 失败抛 RedisError，被消费者识别为可重试
"""
from __future__ import annotations

import redis.asyncio as aioredis
import structlog

from ..config import Settings

logger = structlog.get_logger(__name__)


class IdempotencyGuard:
    """幂等去重器（Redis SETNX）。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        if self._redis is not None:
            return
        self._redis = aioredis.from_url(
            self._settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        # 使用 protocol=2 兼容老版本 Redis（KeyDB / Redis < 6）
        try:
            await self._redis.ping()
        except Exception as e:
            logger.error("idempotency_redis_ping_failed", error=str(e))
            raise
        logger.info("idempotency_redis_connected", url=self._settings.redis_url)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def try_acquire(self, key: str, ttl: int | None = None) -> bool:
        """尝试获取去重锁。

        :param key: 业务键（如 ``bw.dw.q.post:msg-123``）
        :param ttl: 过期秒数，默认使用 settings.dedup_ttl_seconds
        :return: True 表示首次处理，False 表示重复消息
        """
        if self._redis is None:
            raise RuntimeError("IdempotencyGuard.connect() must be called first")
        ttl = ttl if ttl is not None else self._settings.dedup_ttl_seconds
        full_key = f"{self._settings.redis_dedup_prefix}{key}"
        ok = await self._redis.set(full_key, "1", ex=ttl, nx=True)
        return bool(ok)

    async def release(self, key: str) -> None:
        """释放去重锁（用于消费失败重置状态，重投时不阻塞）。"""
        if self._redis is None:
            return
        full_key = f"{self._settings.redis_dedup_prefix}{key}"
        await self._redis.delete(full_key)

    async def ping(self) -> bool:
        """健康检查。"""
        if self._redis is None:
            return False
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False
