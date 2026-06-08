"""全局配置"""
from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """应用全局配置"""

    # 应用基础配置
    APP_NAME: str = "Post Agent Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    API_PREFIX: str = "/api/v1"

    # 服务地址
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Milvus 配置
    MILVUS_HOST: str = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT: int = int(os.getenv("MILVUS_PORT", "19530"))
    MILVUS_USER: Optional[str] = os.getenv("MILVUS_USER", "bw-user")
    MILVUS_PASSWORD: Optional[str] = os.getenv("MILVUS_PASSWORD", "bw-pw")
    MILVUS_DB_NAME: str = os.getenv("MILVUS_DB_NAME", "bw_Agent_db")

    # PostgreSQL 配置
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "brillian_world_agent")

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis 配置
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", "aa123123")

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # LLM 配置
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))

    # 兼容 .env 中的别名（映射到标准变量）
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY", None)
    LLM_MODEL_ID: Optional[str] = os.getenv("LLM_MODEL_ID", None)
    LLM_BASE_URL: Optional[str] = os.getenv("LLM_BASE_URL", None)

    def model_post_init(self, __context):
        """Pydantic v2 后处理钩子：处理环境变量别名"""
        # 如果设置了别名但没有设置标准变量，使用别名
        if not self.OPENAI_API_KEY and self.LLM_API_KEY:
            object.__setattr__(self, "OPENAI_API_KEY", self.LLM_API_KEY)
        # 仅当 OPENAI_BASE_URL 为默认值或空时才使用别名的 BASE_URL
        if self.LLM_BASE_URL and not os.getenv("OPENAI_BASE_URL"):
            object.__setattr__(self, "OPENAI_BASE_URL", self.LLM_BASE_URL)
        if self.LLM_MODEL_ID and not os.getenv("LLM_MODEL"):
            object.__setattr__(self, "LLM_MODEL", self.LLM_MODEL_ID)
        # 嵌入模型：未显式配置时复用 LLM 的 API Key 与 BaseURL
        if not self.EMBEDDING_API_KEY:
            object.__setattr__(self, "EMBEDDING_API_KEY", self.OPENAI_API_KEY)
        if not self.EMBEDDING_BASE_URL:
            object.__setattr__(self, "EMBEDDING_BASE_URL", self.OPENAI_BASE_URL)

    # Qwen 配置（备选）
    QWEN_API_KEY: Optional[str] = os.getenv("QWEN_API_KEY", "sk-cd61d429134847ba8e5987595a35e05e")
    QWEN_BASE_URL: Optional[str] = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    QWEN_MODEL: str = os.getenv("QWEN_MODEL", "qwen-plus-2025-07-28")

    # 嵌入模型配置（阿里云百炼 text-embedding-v3 / DashScope OpenAI 兼容接口）
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v3")
    EMBEDDING_API_KEY: Optional[str] = os.getenv("EMBEDDING_API_KEY", None)
    EMBEDDING_BASE_URL: Optional[str] = os.getenv("EMBEDDING_BASE_URL", None)
    EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    EMBEDDING_BATCH_SIZE: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
    EMBEDDING_MAX_LENGTH: int = int(os.getenv("EMBEDDING_MAX_LENGTH", "512"))

    # 文本分片配置
    CHAT_CHUNK_SIZE: int = int(os.getenv("CHAT_CHUNK_SIZE", "200"))
    CHAT_CHUNK_OVERLAP: int = int(os.getenv("CHAT_CHUNK_OVERLAP", "20"))
    POST_CHUNK_SIZE: int = int(os.getenv("POST_CHUNK_SIZE", "500"))
    POST_CHUNK_OVERLAP: int = int(os.getenv("POST_CHUNK_OVERLAP", "50"))

    # 推荐阈值配置
    USER_STYLE_MIN_COUNT: int = int(os.getenv("USER_STYLE_MIN_COUNT", "50"))  # 触发个性化推荐的最少消息数
    STYLE_SIMILARITY_THRESHOLD: float = float(os.getenv("STYLE_SIMILARITY_THRESHOLD", "0.6"))  # 风格相似度阈值
    BEHAVIOR_VIEW_THRESHOLD: int = int(os.getenv("BEHAVIOR_VIEW_THRESHOLD", "10"))  # 浏览次数触发推荐
    BEHAVIOR_DURATION_THRESHOLD: int = int(os.getenv("BEHAVIOR_DURATION_THRESHOLD", "60"))  # 停留时长触发推荐
    PRECISE_SEARCH_SIMILARITY: float = float(os.getenv("PRECISE_SEARCH_SIMILARITY", "0.7"))  # 精确搜索相似度
    DIVERGENT_SEARCH_SIMILARITY: float = float(os.getenv("DIVERGENT_SEARCH_SIMILARITY", "0.5"))  # 发散搜索相似度

    # Celery 配置
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

    # 缓存配置
    CACHE_TTL_RECOMMENDATION: int = int(os.getenv("CACHE_TTL_RECOMMENDATION", "600"))  # 推荐结果缓存10分钟
    CACHE_TTL_INTEREST_VECTOR: int = int(os.getenv("CACHE_TTL_INTEREST_VECTOR", "3600"))  # 兴趣向量缓存1小时
    CACHE_TTL_HOT_POSTS: int = int(os.getenv("CACHE_TTL_HOT_POSTS", "1800"))  # 热门帖子缓存30分钟

    # 限流配置
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # 允许 .env 中存在未定义的额外变量


settings = Settings()
