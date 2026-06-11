"""配置层：Pydantic Settings 管理环境变量与配置文件。

约定：
- 所有键提供默认值以便本地开发
- 生产环境通过 K8s ConfigMap / Secret 注入
- 支持 .env 文件加载
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """消费者侧全局配置。

    字段按域分组：RabbitMQ / Milvus / Redis / Observability / 业务阈值。
    所有字段同时支持环境变量（同名大写）与 .env 文件。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- RabbitMQ ----
    rabbitmq_url: str = Field(
        default="amqp://bw_app:change-me@localhost:5672/%2Fbw",
        description="RabbitMQ AMQP 连接串（生产侧使用 Quorum Queue）",
    )
    rabbitmq_exchange: str = Field(default="bw.dw.exchange", description="业务交换机名")
    rabbitmq_queues: List[str] = Field(
        default_factory=lambda: ["bw.dw.q.post", "bw.dw.q.user"],
        description="消费者订阅的队列列表",
    )
    rabbitmq_dlq: str = Field(default="bw.dw.q.dlq", description="死信队列名")
    consumer_prefetch: int = Field(default=50, ge=1, le=1000, description="单消费者预取数（QoS）")
    consumer_concurrency: int = Field(default=50, ge=1, description="Pod 内协程并发数")

    # ---- Milvus ----
    milvus_host: str = Field(default="localhost", description="Milvus 主机")
    milvus_port: int = Field(default=19530, description="Milvus gRPC 端口")
    milvus_user: Optional[str] = Field(default=None, description="Milvus 鉴权用户（可选）")
    milvus_password: Optional[str] = Field(default=None, description="Milvus 鉴权密码（可选）")
    milvus_collection_post: str = Field(default="bw_post", description="帖子集合名")
    milvus_collection_user: str = Field(default="bw_user", description="用户集合名")
    milvus_vector_dim: int = Field(default=1024, description="向量维度（与 text-embedding-v3 对齐）")
    milvus_metric_type: str = Field(default="COSINE", description="距离度量")
    milvus_index_type: str = Field(default="HNSW", description="索引类型")

    # ---- Redis（幂等去重 + 速率限制） ----
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis 连接 URL")
    redis_dedup_prefix: str = Field(default="dw:dedup:", description="去重键前缀")
    dedup_ttl_seconds: int = Field(default=7 * 86400, description="去重记录 TTL（默认 7 天）")

    # ---- Observability ----
    otlp_endpoint: str = Field(default="http://localhost:4317", description="OTLP Collector gRPC 端点")
    otlp_enabled: bool = Field(default=False, description="是否上报到 OTLP（开发可关闭）")
    service_name: str = Field(default="bw-vector-sync", description="服务名（用于 trace resource）")
    metrics_port: int = Field(default=9100, description="Prometheus 暴露端口")

    # ---- 运行时 ----
    log_level: str = Field(default="INFO", description="日志级别")
    log_json: bool = Field(default=True, description="是否 JSON 格式输出（K8s 推荐）")
    health_port: int = Field(default=8080, description="健康检查 HTTP 端口")
    batch_size: int = Field(default=100, ge=1, description="批量写入大小")
    batch_timeout_ms: int = Field(default=50, ge=0, description="批量等待超时")

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid log level: {v}")
        return v

    @field_validator("rabbitmq_queues", mode="before")
    @classmethod
    def _split_queue_env(cls, v):
        """支持 `BW_VECTOR_SYNC_RABBITMQ_QUEUES=a,b,c` 形式的环境变量。"""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例获取配置。

    使用 lru_cache 避免重复读取 .env 与系统环境。
    """
    return Settings()
