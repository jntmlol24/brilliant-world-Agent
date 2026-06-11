"""User 监听器：处理用户双写事件（bw.dw.q.user）。

与 PostListener 结构相同，业务侧写入 bw_user collection。
"""
from __future__ import annotations

import time

import aio_pika
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..observability.metrics import (
    consumer_lag_seconds,
    dedup_hits_total,
    messages_consumed_total,
    messages_failed_total,
)
from ..observability.tracing import extract_context, get_tracer
from ..proto_decoder import DecodeError, ProtoDecoder, UserData, Vector
from ..writer.idempotency_guard import IdempotencyGuard
from ..writer.milvus_writer import (
    MilvusCollectionNotExistError,
    MilvusNetworkError,
    MilvusParamError,
    MilvusWriter,
)

logger = structlog.get_logger(__name__)
_tracer = get_tracer()

QUEUE_NAME = "bw.dw.q.user"


class UserListener:
    """USER 队列消息处理器。"""

    def __init__(
        self,
        milvus: MilvusWriter,
        guard: IdempotencyGuard,
        decoder: ProtoDecoder,
        queue: str = QUEUE_NAME,
    ) -> None:
        self.milvus = milvus
        self.guard = guard
        self.decoder = decoder
        self.queue = queue

    async def handle(self, message: aio_pika.IncomingMessage) -> None:
        ctx = extract_context(message.headers)
        with _tracer.start_as_current_span(
            "consume.user",
            context=ctx,
            attributes={
                "messaging.system": "rabbitmq",
                "messaging.destination": self.queue,
                "messaging.message_id": str(message.message_id or ""),
            },
        ):
            dedup_key = f"{self.queue}:{message.message_id or 'no-id'}"

            if not await self.guard.try_acquire(dedup_key):
                dedup_hits_total.labels(queue=self.queue).inc()
                logger.info("user_dedup_skip", message_id=str(message.message_id))
                return

            try:
                event = self.decoder.decode(message.body)
            except DecodeError as e:
                await self.guard.release(dedup_key)
                messages_failed_total.labels(
                    queue=self.queue, biz_type="USER", error_type="DecodeError"
                ).inc()
                logger.error("user_decode_failed", error=str(e))
                raise

            if event.biz_type != "USER":
                await self.guard.release(dedup_key)
                messages_failed_total.labels(
                    queue=self.queue, biz_type="USER", error_type="BizTypeMismatch"
                ).inc()
                raise DecodeError(f"unexpected biz_type on user queue: {event.biz_type!r}")

            if event.occurred_at:
                lag = max(0.0, time.time() * 1000 - event.occurred_at) / 1000.0
                consumer_lag_seconds.labels(queue=self.queue).set(lag)

            try:
                await self._do_write(event)
            except (MilvusParamError, DecodeError):
                messages_failed_total.labels(
                    queue=self.queue, biz_type="USER", error_type="ParamError"
                ).inc()
                raise
            except (MilvusNetworkError, MilvusCollectionNotExistError):
                await self.guard.release(dedup_key)
                messages_failed_total.labels(
                    queue=self.queue, biz_type="USER", error_type="NetworkError"
                ).inc()
                raise

            messages_consumed_total.labels(
                queue=self.queue, biz_type="USER", operation=event.operation
            ).inc()
            logger.info(
                "user_consume_ok",
                biz_id=event.biz_id,
                operation=event.operation,
                version=event.version,
            )

    async def _do_write(self, event) -> None:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_not_exception_type((MilvusParamError, DecodeError)),
            reraise=True,
        ):
            with attempt:
                if event.is_upsert:
                    if not isinstance(event.data, UserData):
                        raise DecodeError("user event missing UserData payload")
                    if not event.vector or not event.vector.embedding:
                        raise MilvusParamError("user event missing vector embedding")
                    await self.milvus.upsert_user(
                        user_id=int(event.biz_id),
                        vector=event.vector.embedding,
                        metadata=event.data.to_metadata(),
                    )
                elif event.is_delete:
                    await self.milvus.delete_user(int(event.biz_id))
                else:
                    raise DecodeError(f"unknown operation: {event.operation!r}")
