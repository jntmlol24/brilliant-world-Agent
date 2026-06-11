"""bw-vector-sync：Python 消费者（RabbitMQ → Milvus）

将 Java 侧 Outbox 投递的双写事件落库到 Milvus，提供：
- 跨语言 Protobuf 契约
- 幂等去重（Redis SETNX）
- 失败重试与 DLQ 路由
- 可观测性（OpenTelemetry + Prometheus）
"""

__version__ = "3.0.0"
