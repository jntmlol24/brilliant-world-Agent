"""模型配置"""
from dataclasses import dataclass, field
from typing import Dict, Any
from app.config.settings import settings


@dataclass
class MilvusCollectionConfig:
    """Milvus 集合配置"""
    name: str
    description: str
    fields: list
    index_params: Dict[str, Any]
    search_params: Dict[str, Any]


@dataclass
class ModelConfig:
    """模型配置"""

    # 嵌入模型配置
    embedding_model_name: str = settings.EMBEDDING_MODEL_NAME
    embedding_dim: int = settings.EMBEDDING_DIM
    embedding_device: str = settings.EMBEDDING_DEVICE
    embedding_batch_size: int = settings.EMBEDDING_BATCH_SIZE
    embedding_max_length: int = settings.EMBEDDING_MAX_LENGTH

    # LLM 配置
    llm_model: str = settings.LLM_MODEL
    llm_temperature: float = settings.LLM_TEMPERATURE
    openai_api_key: str = settings.OPENAI_API_KEY
    openai_base_url: str = settings.OPENAI_BASE_URL or "https://api.openai.com/v1"

    # Milvus 集合配置
    user_chat_styles_collection = MilvusCollectionConfig(
        name="user_chat_styles",
        description="用户聊天风格向量库",
        fields=[
            {"name": "id", "dtype": "INT64", "is_primary": True, "auto_id": True},
            {"name": "user_id", "dtype": "VARCHAR", "max_length": 64},
            {"name": "message_id", "dtype": "VARCHAR", "max_length": 128},
            {"name": "content_vector", "dtype": "FLOAT_VECTOR", "dim": settings.EMBEDDING_DIM},
            {"name": "content_text", "dtype": "VARCHAR", "max_length": 2000},
            {"name": "message_type", "dtype": "INT64"},
            {"name": "conversation_id", "dtype": "VARCHAR", "max_length": 64},
            {"name": "created_at", "dtype": "INT64"},
        ],
        index_params={
            "metric_type": "COSINE",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128},
        },
        search_params={
            "metric_type": "COSINE",
            "params": {"nprobe": 10},
        },
    )

    post_contents_collection = MilvusCollectionConfig(
        name="post_contents",
        description="帖子内容向量库",
        fields=[
            {"name": "id", "dtype": "INT64", "is_primary": True, "auto_id": True},
            {"name": "post_id", "dtype": "VARCHAR", "max_length": 64},
            {"name": "chunk_id", "dtype": "INT64"},
            {"name": "content_vector", "dtype": "FLOAT_VECTOR", "dim": settings.EMBEDDING_DIM},
            {"name": "content_text", "dtype": "VARCHAR", "max_length": 2000},
            {"name": "category", "dtype": "VARCHAR", "max_length": 64},
            {"name": "tags", "dtype": "VARCHAR", "max_length": 500},
            {"name": "title", "dtype": "VARCHAR", "max_length": 200},
            {"name": "created_at", "dtype": "INT64"},
        ],
        index_params={
            "metric_type": "COSINE",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128},
        },
        search_params={
            "metric_type": "COSINE",
            "params": {"nprobe": 10},
        },
    )


model_config = ModelConfig()
