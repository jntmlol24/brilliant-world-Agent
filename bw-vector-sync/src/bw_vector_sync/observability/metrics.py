"""Prometheus 指标：消费侧业务 + 运行时指标。"""
from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server

REGISTRY = CollectorRegistry(auto_describe=True)

# 业务指标
messages_consumed_total = Counter(
    "bw_vector_sync_messages_consumed_total",
    "消费成功的消息总数",
    labelnames=("queue", "biz_type", "operation"),
    registry=REGISTRY,
)

messages_failed_total = Counter(
    "bw_vector_sync_messages_failed_total",
    "消费失败的消息总数（最终进 DLQ）",
    labelnames=("queue", "biz_type", "error_type"),
    registry=REGISTRY,
)

dedup_hits_total = Counter(
    "bw_vector_sync_dedup_hits_total",
    "幂等去重拦截次数",
    labelnames=("queue",),
    registry=REGISTRY,
)

# 运行时指标
consumer_lag_seconds = Gauge(
    "bw_vector_sync_consumer_lag_seconds",
    "消息从生产到消费的时间差（秒）",
    labelnames=("queue",),
    registry=REGISTRY,
)

milvus_write_latency_seconds = Histogram(
    "bw_vector_sync_milvus_write_latency_seconds",
    "Milvus 写入耗时（秒）",
    labelnames=("collection", "operation"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)

connection_status = Gauge(
    "bw_vector_sync_connection_status",
    "依赖连接状态（1=connected, 0=disconnected）",
    labelnames=("component",),
    registry=REGISTRY,
)


def start_metrics_server(port: int) -> None:
    """启动独立的 Prometheus 暴露端口（避免占用 health 端口）。"""
    if port <= 0:
        return
    try:
        start_http_server(port, registry=REGISTRY)
    except OSError:
        # 端口已占用（如单测场景）静默忽略
        pass
