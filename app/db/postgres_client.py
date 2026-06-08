"""PostgreSQL 客户端"""
from typing import List, Dict, Any, Optional
import asyncio
from contextlib import asynccontextmanager
import asyncpg
from app.config.settings import settings
from app.utils.logger import logger


class PostgresClient:
    """PostgreSQL 异步客户端（单例）"""

    _instance: Optional["PostgresClient"] = None
    _pool: Optional[asyncpg.Pool] = None
    _mock_mode: bool = False
    _mock_data: Dict[str, List[Dict[str, Any]]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.host = settings.POSTGRES_HOST
        self.port = settings.POSTGRES_PORT
        self.user = settings.POSTGRES_USER
        self.password = settings.POSTGRES_PASSWORD
        self.database = settings.POSTGRES_DB

    async def connect(self):
        """创建连接池"""
        if self._pool is not None or self._mock_mode:
            return

        try:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            logger.info(f"PostgreSQL 连接池创建成功: {self.host}:{self.port}")
            await self._init_tables()
        except Exception as e:
            logger.error(f"PostgreSQL 连接失败: {e}")
            self._mock_mode = True
            logger.warning("PostgreSQL 进入 mock 模式（用于本地开发测试）")
            self._init_mock_tables()

    async def _init_tables(self):
        """初始化表结构"""
        if not self._pool:
            return

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_chat_settings (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(64) UNIQUE NOT NULL,
                    chat_assistant_enabled BOOLEAN DEFAULT FALSE,
                    data_collection_enabled BOOLEAN DEFAULT FALSE,
                    style_data_count INT DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    post_id VARCHAR(64) UNIQUE NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    content TEXT,
                    category VARCHAR(64),
                    tags VARCHAR(500),
                    author_id VARCHAR(64),
                    view_count INT DEFAULT 0,
                    like_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_behavior (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    post_id VARCHAR(64) NOT NULL,
                    behavior_type VARCHAR(20) NOT NULL,
                    duration INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_behavior_user_id ON user_behavior(user_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_behavior_post_id ON user_behavior(post_id);"
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    conversation_id VARCHAR(64) NOT NULL,
                    message_id VARCHAR(128) UNIQUE,
                    content TEXT,
                    message_type INT DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);"
            )

            logger.info("PostgreSQL 表结构初始化完成")

    def _init_mock_tables(self):
        """初始化 Mock 表"""
        self._mock_data = {
            "user_chat_settings": [],
            "posts": [],
            "user_behavior": [],
            "chat_messages": [],
        }

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL 连接池已关闭")

    async def execute(self, query: str, *args) -> str:
        """执行 SQL"""
        if self._mock_mode:
            return await self._mock_execute(query, *args)

        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """查询多条"""
        if self._mock_mode:
            return await self._mock_fetch(query, *args)

        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """查询单条"""
        if self._mock_mode:
            results = await self._mock_fetch(query, *args)
            return results[0] if results else None

        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> Any:
        """查询单值"""
        if self._mock_mode:
            results = await self._mock_fetch(query, *args)
            if results:
                record = results[0]
                return record[list(record.keys())[0]] if hasattr(record, "keys") else record[0]
            return None

        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def _mock_execute(self, query: str, *args) -> str:
        """Mock 模式执行"""
        logger.debug(f"[MOCK PG] {query[:100]} | args={args}")
        return "MOCK"

    async def _mock_fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """Mock 模式查询"""
        logger.debug(f"[MOCK PG] {query[:100]} | args={args}")
        q = query.lower().strip()
        if q.startswith("select count"):
            return [{"count": 0}]
        if "from user_chat_settings" in q and "user_id" in q:
            return []
        return []


# 全局实例
postgres_client = PostgresClient()
