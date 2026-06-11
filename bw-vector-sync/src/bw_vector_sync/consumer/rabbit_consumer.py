"""aio-pika 消费基类：负责连接、QoS、ACK 语义与 DLX 路由。

设计原则：
- RobustConnection：网络抖动自动重连
- 手动 ACK（``message.process(requeue=False, ignore_processed=True)``）
  - 业务异常 → nack(requeue=False) → DLX → DLQ
  - 不在业务侧手动 ack/nack，交给 aio-pika context manager
- prefetch_count 控制并发，避免单 Pod 饥饿
"""
from __future__ import annotations

from typing import Awaitable, Callable, Iterable, Optional

import aio_pika
import structlog

from ..config import Settings
from ..observability.metrics import connection_status

logger = structlog.get_logger(__name__)


MessageHandler = Callable[[aio_pika.IncomingMessage], Awaitable[None]]


class RabbitConsumer:
    """aio-pika 消费基类。

    使用方式::

        consumer = RabbitConsumer(settings)
        await consumer.start()
        await consumer.consume("bw.dw.q.post", post_listener.handle)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.RobustChannel] = None

    # ---- 生命周期 ----
    async def start(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            return
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        self._channel = await self._connection.channel(publisher_confirms=True)
        await self._channel.set_qos(prefetch_count=self._settings.consumer_prefetch)
        connection_status.labels(component="rabbitmq").set(1)
        logger.info(
            "rabbit_consumer_started",
            prefetch=self._settings.consumer_prefetch,
            queues=self._settings.rabbitmq_queues,
        )

    async def close(self) -> None:
        if self._channel is not None and not self._channel.is_closed:
            await self._channel.close()
            self._channel = None
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
            self._connection = None
        connection_status.labels(component="rabbitmq").set(0)
        logger.info("rabbit_consumer_closed")

    def is_connected(self) -> bool:
        return (
            self._connection is not None
            and not self._connection.is_closed
            and self._channel is not None
            and not self._channel.is_closed
        )

    # ---- 消费 ----
    async def consume(self, queue_name: str, handler: MessageHandler) -> None:
        """持续消费指定队列。

        aio-pika 的 ``queue.iterator()`` + ``message.process(...)`` 负责
        ACK/nack + DLX 路由；业务侧只关心 handler 抛不抛异常：
            - 正常返回 → 自动 ack
            - 异常抛出 → nack(requeue=False) → DLX
        """
        if self._channel is None:
            raise RuntimeError("RabbitConsumer.start() must be called first")
        # passive=True：队列已存在（由生产者侧声明为 Quorum Queue）
        queue = await self._channel.declare_queue(
            queue_name, durable=True, passive=True
        )
        logger.info("rabbit_consumer_listening", queue=queue_name)
        async with queue.iterator() as it:
            async for message in it:
                # ignore_processed=True 避免在 handler 内部手 ack 触发状态异常
                async with message.process(requeue=False, ignore_processed=True):
                    await handler(message)

    async def consume_many(
        self, queue_handler_pairs: Iterable[tuple[str, MessageHandler]]
    ) -> None:
        """并发订阅多个队列（每个队列独立任务）。"""
        import asyncio
        tasks = [
            asyncio.create_task(self.consume(q, h), name=f"consumer:{q}")
            for q, h in queue_handler_pairs
        ]
        if not tasks:
            return
        await asyncio.gather(*tasks)
