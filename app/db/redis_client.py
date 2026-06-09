"""Redis 客户端"""
import json
from typing import Any, Optional, Union
import redis.asyncio as aioredis
from app.config.settings import settings
from app.utils.logger import logger


class RedisClient:
    """Redis 异步客户端（单例）"""

    _instance: Optional["RedisClient"] = None
    _client: Optional[aioredis.Redis] = None
    _mock_mode: bool = False
    _mock_store: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.host = settings.REDIS_HOST
        self.port = settings.REDIS_PORT
        self.db = settings.REDIS_DB
        self.password = settings.REDIS_PASSWORD

    async def connect(self):
        """连接 Redis"""
        if self._client is not None or self._mock_mode:
            return

        try:
            self._client = aioredis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password if self.password else None,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                # 强制 RESP2 协议，避免服务端不支持 HELLO 命令（如 Redis < 6、KeyDB 旧版等）
                protocol=2,
            )
            await self._client.ping()
            logger.info(f"Redis 连接成功: {self.host}:{self.port}/{self.db}")
        except Exception as e:
            logger.error(f"Redis 连接失败: {e}")
            self._mock_mode = True
            self._client = None
            logger.warning("Redis 进入 mock 模式（用于本地开发测试）")

    async def close(self):
        """关闭连接"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis 连接已关闭")

    @property
    def client(self) -> aioredis.Redis:
        """获取客户端"""
        if self._mock_mode:
            return None
        return self._client

    async def get(self, key: str) -> Optional[str]:
        """获取值"""
        if self._mock_mode:
            return self._mock_store.get(key)
        if not self._client:
            await self.connect()
        try:
            return await self._client.get(key)
        except Exception as e:
            logger.error(f"Redis GET 失败: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Union[str, int, float, dict, list],
        ex: Optional[int] = None,
    ) -> bool:
        """设置值"""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        elif not isinstance(value, str):
            value = str(value)

        if self._mock_mode:
            self._mock_store[key] = value
            return True

        if not self._client:
            await self.connect()
        try:
            return await self._client.set(key, value, ex=ex)
        except Exception as e:
            logger.error(f"Redis SET 失败: {e}")
            return False

    async def delete(self, *keys: str) -> int:
        """删除键"""
        if not keys:
            return 0

        if self._mock_mode:
            count = 0
            for key in keys:
                if key in self._mock_store:
                    del self._mock_store[key]
                    count += 1
            return count

        if not self._client:
            await self.connect()
        try:
            return await self._client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis DELETE 失败: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if self._mock_mode:
            return key in self._mock_store
        if not self._client:
            await self.connect()
        try:
            return await self._client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS 失败: {e}")
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        if self._mock_mode:
            return True
        if not self._client:
            await self.connect()
        try:
            return await self._client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis EXPIRE 失败: {e}")
            return False

    async def incr(self, key: str, amount: int = 1) -> int:
        """自增"""
        if self._mock_mode:
            self._mock_store[key] = int(self._mock_store.get(key, 0)) + amount
            return self._mock_store[key]
        if not self._client:
            await self.connect()
        try:
            return await self._client.incr(key, amount)
        except Exception as e:
            logger.error(f"Redis INCR 失败: {e}")
            return 0

    async def get_json(self, key: str) -> Any:
        """获取 JSON 值"""
        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def set_json(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
    ) -> bool:
        """设置 JSON 值"""
        return await self.set(key, value, ex=ex)

    async def keys(self, pattern: str) -> list:
        """查找键"""
        if self._mock_mode:
            return [k for k in self._mock_store.keys() if pattern.replace("*", "") in k]
        if not self._client:
            await self.connect()
        try:
            return await self._client.keys(pattern)
        except Exception as e:
            logger.error(f"Redis KEYS 失败: {e}")
            return []


# 全局实例
redis_client = RedisClient()
