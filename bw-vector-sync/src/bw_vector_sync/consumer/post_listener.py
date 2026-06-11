"""Post 监听器：处理帖子双写事件（bw.dw.q.post）。

流程：
1. 解析 message header 中的 traceparent（跨语言 trace 串联）
2. Redis SETNX 去重
3. Protobuf 解码
4. 业务校验：biz_type == POST、operation in (UPSERT, DELETE)
5. 调用 MilvusWriter 落库（带 tenacity 重试）
"""
from __future__ import annotations

import time
from typing import Optional

import aio_pika
import structlog
from opentelemetry import trace
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
from ..proto_decoder import DecodeError, PostData, ProtoDecoder, Vector
from ..writer.idempotency_guard import IdempotencyGuard
from ..writer.milvus_writer import (
    MilvusCollectionNotExistError,
    MilvusNetworkError,
    MilvusParamError,
    MilvusWriter,
)

logger = structlog.get_logger(__name__)
_tracer = get_tracer()

QUEUE_NAME = "bw.dw.q.post"


class PostListener:
    """POST 队列消息处理器。"""

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
            "consume.post",
            context=ctx,
            attributes={
                "messaging.system": "rabbitmq",
                "messaging.destination": self.queue,
                "messaging.message_id": str(message.message_id or ""),
            },
        ):
            await self._handle_inner(message)

    async def _handle_inner(self, message: aio_pika.IncomingMessage) -> None:
        # ---- 1. 去重 ----
        dedup_key = f"{self.queue}:{message.message_id or 'no-id'}"
        if not await self.guard.try_acquire(dedup_key):
            dedup_hits_total.labels(queue=self.queue).inc()
            logger.info("post_dedup_skip", message_id=str(message.message_id))
            return

        # ---- 2. 解码 ----
        try:
            event = self.decoder.decode(message.body)
        except DecodeError as e:
            # 不可重试 → 释放去重锁后抛出，触发 DLX
            await self.guard.release(dedup_key)
            messages_failed_total.labels(
                queue=self.queue, biz_type="POST", error_type="DecodeError"
            ).inc()
            logger.error("post_decode_failed", error=str(e))
            raise

        # ---- 3. 业务校验 ----
        if event.biz_type != "POST":
            await self.guard.release(dedup_key)
            messages_failed_total.labels(
                queue=self.queue, biz_type="POST", error_type="BizTypeMismatch"
            ).inc()
            raise DecodeError(f"unexpected biz_type on post queue: {event.biz_type!r}")

        # ---- 4. lag 指标 ----
        if event.occurred_at:
            lag = max(0.0, time.time() * 1000 - event.occurred_at) / 1000.0
            consumer_lag_seconds.labels(queue=self.queue).set(lag)

        # ---- 5. 落库（带重试） ----
        try:
            await self._do_write(event)
        except (MilvusParamError, DecodeError):
            # 不可重试 → DLQ
            messages_failed_total.labels(
                queue=self.queue, biz_type="POST", error_type="ParamError"
            ).inc()
            raise
        except (MilvusNetworkError, MilvusCollectionNotExistError):
            # 可重试 → 释放去重锁（重投时不阻塞），重抛
            await self.guard.release(dedup_key)
            messages_failed_total.labels(
                queue=self.queue, biz_type="POST", error_type="NetworkError"
            ).inc()
            raise

        messages_consumed_total.labels(
            queue=self.queue, biz_type="POST", operation=event.operation
        ).inc()
        logger.info(
            "post_consume_ok",
            biz_id=event.biz_id,
            operation=event.operation,
            version=event.version,
        )

    async def _do_write(self, event) -> None:
        """带 tenacity 重试的写库流程。"""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_not_exception_type((MilvusParamError, DecodeError)),
            reraise=True,
        ):
            with attempt:
                if event.is_upsert:
                    if not isinstance(event.data, PostData):
                        raise DecodeError("post event missing PostData payload")
                    if not event.vector or not event.vector.embedding:
                        raise MilvusParamError("post event missing vector embedding")
                    self._validate_vector_dim(event.vector)
                    await self.milvus.upsert_post(
                        post_id=int(event.biz_id),
                        user_id=int(event.data.user_id),
                        vector=event.vector.embedding,
                        metadata=event.data.to_metadata(),
                    )
                elif event.is_delete:
                    await self.milvus.delete_post(int(event.biz_id))
                else:
                    raise DecodeError(f"unknown operation: {event.operation!r}")

    @staticmethod
    def _validate_vector_dim(v: Vector) -> None:
        if v.dim and v.dim != 1024 and len(v.embedding) != v.dim:
            raise MilvusParamError(
                f"vector dim mismatch: declared={v.dim}, actual={len(v.embedding)}"
            )
