"""bw-vector-sync 服务入口。

启动流程：
1. 加载配置（Settings）
2. 初始化 OpenTelemetry trace
3. 启动健康检查 HTTP 服务
4. 启动 Prometheus 暴露端口
5. 初始化 Milvus writer + collection + 索引
6. 启动 RabbitMQ 消费基类
7. 启动 IdempotencyGuard（Redis）
8. 构造 Post/User/DLQ 监听器
9. 订阅三个队列
10. 等待 SIGTERM / SIGINT 优雅关闭
"""
from __future__ import annotations

import asyncio
import signal
import sys
from typing import List

import structlog

from .config import Settings, get_settings
from .consumer.dlq_listener import DlqListener
from .consumer.post_listener import PostListener
from .consumer.rabbit_consumer import RabbitConsumer
from .consumer.user_listener import UserListener
from .observability.metrics import start_metrics_server
from .observability.tracing import setup_tracing
from .proto_decoder import ProtoDecoder
from .service.health_server import HealthServer
from .writer.idempotency_guard import IdempotencyGuard
from .writer.milvus_writer import MilvusWriter


def _configure_logging(settings: Settings) -> None:
    processors: List = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if settings.log_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, settings.log_level)
        ),
        cache_logger_on_first_use=True,
    )


async def run(settings: Settings) -> None:
    log = structlog.get_logger("main")
    log.info("starting", service=settings.service_name, version="3.0.0")

    # ---- 可观测性 ----
    setup_tracing(settings)
    start_metrics_server(settings.metrics_port)

    # ---- 健康检查 ----
    health = HealthServer()
    await health.start(settings.health_port)

    # ---- Milvus ----
    milvus = MilvusWriter(settings)
    milvus.connect()
    milvus.ensure_collections()
    log.info("milvus_ready")

    # ---- Redis 幂等 ----
    guard = IdempotencyGuard(settings)
    await guard.connect()
    log.info("idempotency_ready")

    # ---- RabbitMQ ----
    consumer = RabbitConsumer(settings)
    await consumer.start()

    # 更新 health server 的依赖
    health._consumer = consumer
    health._milvus = milvus
    health._guard = guard

    # ---- 监听器 ----
    decoder = ProtoDecoder()
    post_listener = PostListener(milvus, guard, decoder)
    user_listener = UserListener(milvus, guard, decoder)
    dlq_listener = DlqListener()

    queue_handlers = [
        (post_listener.queue, post_listener.handle),
        (user_listener.queue, user_listener.handle),
        (dlq_listener.queue, dlq_listener.handle),
    ]

    # ---- 优雅关闭 ----
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # Windows
            pass

    consumer_task = asyncio.create_task(
        consumer.consume_many(queue_handlers), name="consume_all"
    )

    log.info("service_ready", queues=[q for q, _ in queue_handlers])
    await stop_event.wait()
    log.info("shutdown_initiated")

    # 关闭顺序：消费 → 连接 → 健康
    consumer_task.cancel()
    try:
        await consumer_task
    except (asyncio.CancelledError, Exception):
        pass
    await consumer.close()
    await guard.close()
    milvus.close()
    await health.stop()
    log.info("shutdown_complete")


def main() -> int:
    settings = get_settings()
    _configure_logging(settings)
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
