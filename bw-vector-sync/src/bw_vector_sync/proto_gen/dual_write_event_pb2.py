"""兼容 protoc 输出的双写事件类型（开发期手写 stub）。

⚠️ 生产部署前请用 protoc 重新生成::

    protoc --python_out=. -I proto proto/dual_write_event.proto

当前实现以 JSON 序列化（bytes），与 protoc 的二进制线格式不互通；
但 dataclass 形状、字段、``ParseFromString`` / ``HasField`` / ``Unpack``
接口与 protoc 生成代码完全一致，便于开发期单测与本地调试。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ---------- 异常 ----------
class DecodeError(Exception):
    pass


# ---------- Any 包装 ----------
class _Any:
    """``google.protobuf.Any`` 的极简兼容实现。"""

    def __init__(self, type_name: str = "", value: Optional[Dict[str, Any]] = None) -> None:
        self._type_name = type_name
        self._value = value or {}

    def TypeName(self) -> str:
        # 取末段短名（与 protoc TypeName() 行为一致：返回去掉包前缀的类名）
        return self._type_name.rsplit(".", 1)[-1]

    def Unpack(self, target: Any) -> bool:
        if not self._value:
            return False
        for k, v in self._value.items():
            if hasattr(target, k):
                setattr(target, k, v)
        return True

    @staticmethod
    def Pack(message: Any, type_url_prefix: str = "bw.dualwrite.v1") -> "_Any":
        if hasattr(message, "__dataclass_fields__"):
            data = asdict(message)
        else:
            data = {k: v for k, v in vars(message).items() if not k.startswith("_")}
        return _Any(
            type_name=f"{type_url_prefix}.{type(message).__name__}",
            value=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"type_name": self._type_name, "value": self._value}


# ---------- 业务消息 ----------
@dataclass
class PostData:
    post_id: str = ""
    user_id: str = ""
    title: str = ""
    content: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: int = 0


@dataclass
class UserData:
    user_id: str = ""
    user_account: str = ""
    user_name: str = ""
    user_avatar: str = ""
    user_profile: str = ""


@dataclass
class Vector:
    model: str = ""
    dim: int = 0
    embedding: List[float] = field(default_factory=list)


@dataclass
class DualWriteEvent:
    biz_type: str = ""
    biz_id: str = ""
    version: int = 0
    occurred_at: int = 0
    operation: str = ""
    data: Optional[_Any] = None
    vector: Optional[Vector] = None
    headers: Dict[str, str] = field(default_factory=dict)

    def ParseFromString(self, data: bytes) -> int:
        obj = json.loads(data.decode("utf-8"))
        self.biz_type = obj.get("biz_type", "")
        self.biz_id = obj.get("biz_id", "")
        self.version = int(obj.get("version", 0))
        self.occurred_at = int(obj.get("occurred_at", 0))
        self.operation = obj.get("operation", "")
        self.headers = dict(obj.get("headers") or {})

        v = obj.get("vector")
        self.vector = Vector(
            model=v.get("model", ""),
            dim=int(v.get("dim", 0)),
            embedding=list(v.get("embedding") or []),
        ) if v else None

        d = obj.get("data")
        self.data = _Any(
            type_name=d.get("type_name", ""),
            value=d.get("value") or {},
        ) if d else None

        return len(data)

    def SerializeToString(self) -> bytes:
        obj: Dict[str, Any] = {
            "biz_type": self.biz_type,
            "biz_id": self.biz_id,
            "version": self.version,
            "occurred_at": self.occurred_at,
            "operation": self.operation,
            "headers": self.headers,
        }
        if self.vector:
            obj["vector"] = asdict(self.vector)
        if self.data:
            obj["data"] = self.data.to_dict()
        return json.dumps(obj, ensure_ascii=False).encode("utf-8")

    def HasField(self, name: str) -> bool:
        if name == "data":
            return self.data is not None
        if name == "vector":
            return self.vector is not None
        return False
