"""死信监听器：处理进入 DLQ 的消息，记录日志并发送告警。

约定：
- DLQ 队列由 RabbitMQ DLX 投递（消息带 x-death header）
- 我们只记录 + 推送告警通道，不做自动重投
- 运维通过 RabbitMQ Management UI 查询后用 ``rabbitmqadmin`` 手动重投
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import aio_pika
import structlog

logger = structlog.get_logger(__name__)

QUEUE_NAME = "bw.dw.q.dlq"


class DlqListener:
    """DLQ 消息处理器（仅记录 + 告警）。"""

    def __init__(
        self,
        alerter: Optional[Any] = None,
        queue: str = QUEUE_NAME,
    ) -> None:
        self.alerter = alerter
        self.queue = queue

    async def handle(self, message: aio_pika.IncomingMessage) -> None:
        x_death = message.headers.get("x-death") if message.headers else None
        first_death = x_death[0] if isinstance(x_death, list) and x_death else {}
        original_queue = first_death.get("queue", "<unknown>")
        reason = first_death.get("reason", "<unknown>")

        # 限制 body 长度防止日志爆炸
        body_preview = message.body[:200].decode("utf-8", errors="replace")
        logger.error(
            "dlq_message_received",
            queue=self.queue,
            original_queue=original_queue,
            reason=reason,
            message_id=str(message.message_id),
            body_preview=body_preview,
        )
        # 告警（可对接 AlertManager / 企业微信 / 钉钉）
        if self.alerter is not None:
            try:
                await self.alerter.send(
                    f"DLQ 消息需人工处理: original={original_queue}, "
                    f"reason={reason}, msg_id={message.message_id}"
                )
            except Exception as e:  # pragma: no cover
                logger.error("dlq_alerter_send_failed", error=str(e))
