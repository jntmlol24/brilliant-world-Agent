"""Protobuf 解码器：将 AMQP 消息体解析为强类型事件对象。

设计要点：
- 使用 .proto 自动生成 Python 类（protoc --python_out）
- 解码失败抛 DecodeError，被消费者识别为不可重试
- 提供便捷的字段取值方法，屏蔽 Protobuf API 复杂度
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

from .proto_gen import dual_write_event_pb2 as pb

logger = structlog.get_logger(__name__)


# ---------- 异常 ----------
class DecodeError(Exception):
    """Protobuf 解码失败（不可重试 → 走 DLQ）。"""


# ---------- 数据类 ----------
@dataclass(frozen=True)
class Vector:
    """统一向量表示（业务侧只看 dataclass，不接触 Protobuf）。"""

    model: str
    dim: int
    embedding: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return {"model": self.model, "dim": self.dim, "embedding": list(self.embedding)}


@dataclass(frozen=True)
class PostData:
    post_id: str
    user_id: str
    title: str
    content: str
    tags: List[str]
    created_at: int = 0

    def to_metadata(self) -> Dict[str, Any]:
        return {"title": self.title, "tags": list(self.tags), "content_length": len(self.content)}


@dataclass(frozen=True)
class UserData:
    user_id: str
    user_account: str
    user_name: str
    user_avatar: str
    user_profile: str = ""

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "user_account": self.user_account,
            "user_name": self.user_name,
            "user_avatar": self.user_avatar,
        }


@dataclass(frozen=True)
class DualWriteEvent:
    """统一事件表示。"""

    biz_type: str           # "POST" | "USER"
    biz_id: str
    version: int
    occurred_at: int        # 毫秒
    operation: str          # "UPSERT" | "DELETE"
    data: Any               # PostData | UserData | None
    vector: Optional[Vector]
    headers: Dict[str, str]

    @property
    def is_upsert(self) -> bool:
        return self.operation == "UPSERT"

    @property
    def is_delete(self) -> bool:
        return self.operation == "DELETE"


# ---------- 解码器 ----------
class ProtoDecoder:
    """Protobuf 解码器门面。

    使用方式::

        decoder = ProtoDecoder()
        event = decoder.decode(message.body)
    """

    SUPPORTED_BIZ_TYPES = {"POST", "USER"}
    SUPPORTED_OPERATIONS = {"UPSERT", "DELETE"}

    def decode(self, body: bytes) -> DualWriteEvent:
        """解码消息体。失败抛 DecodeError。"""
        if not body:
            raise DecodeError("empty message body")
        try:
            raw = pb.DualWriteEvent()
            raw.ParseFromString(body)
        except Exception as e:
            logger.error("protobuf_decode_failed", error=str(e), body_size=len(body))
            raise DecodeError(f"invalid protobuf payload: {e}") from e

        if raw.biz_type not in self.SUPPORTED_BIZ_TYPES:
            raise DecodeError(f"unsupported biz_type: {raw.biz_type!r}")
        if raw.operation not in self.SUPPORTED_OPERATIONS:
            raise DecodeError(f"unsupported operation: {raw.operation!r}")
        if not raw.biz_id:
            raise DecodeError("missing biz_id")

        data = self._decode_data(raw)
        vector = self._decode_vector(raw) if raw.HasField("vector") else None

        return DualWriteEvent(
            biz_type=raw.biz_type,
            biz_id=raw.biz_id,
            version=raw.version,
            occurred_at=raw.occurred_at,
            operation=raw.operation,
            data=data,
            vector=vector,
            headers=dict(raw.headers),
        )

    # ---- 内部辅助 ----
    def _decode_data(self, raw: pb.DualWriteEvent):
        if not raw.HasField("data"):
            return None
        type_name = raw.data.TypeName()
        # 严格校验 Any 内嵌类型与 biz_type 的对应关系
        expected = "PostData" if raw.biz_type == "POST" else "UserData"
        if type_name != expected:
            raise DecodeError(
                f"biz_type {raw.biz_type!r} expects {expected} but got {type_name!r}"
            )
        try:
            if raw.biz_type == "POST":
                inner = pb.PostData()
                raw.data.Unpack(inner)
                return PostData(
                    post_id=inner.post_id,
                    user_id=inner.user_id,
                    title=inner.title,
                    content=inner.content,
                    tags=list(inner.tags),
                    created_at=inner.created_at,
                )
            if raw.biz_type == "USER":
                inner = pb.UserData()
                raw.data.Unpack(inner)
                return UserData(
                    user_id=inner.user_id,
                    user_account=inner.user_account,
                    user_name=inner.user_name,
                    user_avatar=inner.user_avatar,
                    user_profile=inner.user_profile,
                )
        except DecodeError:
            raise
        except Exception as e:
            raise DecodeError(f"failed to unpack Any payload for {type_name}: {e}") from e
        return None

    @staticmethod
    def _decode_vector(raw: pb.DualWriteEvent) -> Optional[Vector]:
        v = raw.vector
        if v.dim and len(v.embedding) != v.dim:
            raise DecodeError(
                f"vector dim mismatch: declared={v.dim}, actual={len(v.embedding)}"
            )
        return Vector(model=v.model, dim=v.dim or len(v.embedding), embedding=list(v.embedding))
