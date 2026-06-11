"""OpenTelemetry trace 初始化与上下文传播。

跨语言 trace 串联：
- Java 侧将 `traceparent` 写入 RabbitMQ message header
- Python 端在 consumer 入口 extract 出父 span context
- 子 span (consume.post / consume.user) 在 writer 调用时延续
"""
from __future__ import annotations

from typing import Optional

import structlog
from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    OTLP_AVAILABLE = True
except Exception:  # pragma: no cover - 可选依赖
    OTLP_AVAILABLE = False

from ..config import Settings

logger = structlog.get_logger(__name__)


_initialized = False


def setup_tracing(settings: Settings) -> trace.Tracer:
    """初始化全局 TracerProvider（幂等）。"""
    global _initialized
    if _initialized:
        return trace.get_tracer(settings.service_name)

    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)

    if settings.otlp_enabled and OTLP_AVAILABLE:
        exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("otel_exporter_enabled", endpoint=settings.otlp_endpoint)
    else:
        logger.info("otel_exporter_disabled", reason="otlp_disabled or exporter unavailable")

    trace.set_tracer_provider(provider)
    _initialized = True
    return trace.get_tracer(settings.service_name)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer("bw-vector-sync")


def extract_context(headers: Optional[dict]) -> Optional[trace.Context]:
    """从 RabbitMQ message header 提取 W3C traceparent。

    RabbitMQ header 值是 bytes，这里统一转 str 以匹配 W3C 规范。
    """
    if not headers:
        return None
    norm = {}
    for k, v in headers.items():
        if isinstance(v, bytes):
            try:
                norm[k] = v.decode("utf-8")
            except UnicodeDecodeError:
                continue
        elif isinstance(v, str):
            norm[k] = v
    if not norm:
        return None
    try:
        return extract(norm)
    except Exception:  # pragma: no cover
        return None
