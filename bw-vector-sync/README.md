# bw-vector-sync · Python 消费者（RabbitMQ → Milvus）

> 版本 v3.0 · 依据 `req-docs/RabbitMQ-mysql-milvus-dual-write-plan.md` 下篇（消费者侧）实现
> 跨语言栈：Java（生产侧 Outbox）→ **Python（本服务）** → Milvus

## 🎯 角色

消费 RabbitMQ Quorum Queue 中的双写事件，幂等地落库到 Milvus。

```
Java Outbox ──publish──▶ RabbitMQ Quorum Queue
                              │
                              ▼
                    ┌──────────────────────┐
                    │  bw-vector-sync (3+) │
                    │  - aio-pika consumer │
                    │  - Protobuf decode   │
                    │  - Redis SETNX dedup │
                    │  - pymilvus writer   │
                    └──────────┬───────────┘
                               │
                               ▼
                          Milvus Cluster
                          (bw_post / bw_user)
```

## 📦 目录结构

```
bw-vector-sync/
├── pyproject.toml             # Poetry 依赖
├── Dockerfile                 # 多阶段构建（builder + slim runtime）
├── proto/
│   └── dual_write_event.proto # 跨语言 Protobuf 契约
├── src/bw_vector_sync/
│   ├── main.py                # 启动入口
│   ├── config.py              # Pydantic Settings
│   ├── proto_decoder.py       # Protobuf → dataclass 适配
│   ├── proto_gen/             # proto 生成代码（开发期手写 stub）
│   ├── consumer/
│   │   ├── rabbit_consumer.py # aio-pika 基类
│   │   ├── post_listener.py   # 帖子监听器
│   │   ├── user_listener.py   # 用户监听器
│   │   └── dlq_listener.py    # 死信监听器
│   ├── writer/
│   │   ├── milvus_writer.py   # pymilvus 封装 + 异常分类
│   │   └── idempotency_guard.py # Redis SETNX 去重
│   ├── observability/
│   │   ├── tracing.py         # OpenTelemetry
│   │   └── metrics.py         # Prometheus
│   └── service/
│       └── health_server.py   # K8s 探针
├── tests/
│   ├── unit/                  # 单元测试
│   └── integration/           # 集成测试
├── deploy/
│   ├── k8s-deployment.yaml
│   └── k8s-service.yaml
└── README.md
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd bw-vector-sync
poetry install
# 或：pip install -e .
```

### 2. 配置环境变量

`.env` 示例：

```ini
# RabbitMQ
RABBITMQ_URL=amqp://bw_app:secret@rabbitmq-cluster:5672/%2Fbw
RABBITMQ_QUEUES=bw.dw.q.post,bw.dw.q.user
RABBITMQ_DLQ=bw.dw.q.dlq
CONSUMER_PREFETCH=50

# Milvus
MILVUS_HOST=milvus-cluster
MILVUS_PORT=19530
MILVUS_USER=bw_user
MILVUS_PASSWORD=bw_pw
MILVUS_COLLECTION_POST=bw_post
MILVUS_COLLECTION_USER=bw_user

# Redis（幂等去重）
REDIS_URL=redis://redis-cluster:6379/0
REDIS_DEDUP_PREFIX=dw:dedup:
DEDUP_TTL_SECONDS=604800

# Observability
OTLP_ENABLED=true
OTLP_ENDPOINT=http://otel-collector:4317
METRICS_PORT=9100
HEALTH_PORT=8080

# Logging
LOG_LEVEL=INFO
LOG_JSON=true
```

### 3. 启动服务

```bash
poetry run python -m bw_vector_sync.main
```

或 Docker：

```bash
docker build -t bw-vector-sync:3.0.0 -f Dockerfile .
docker run -p 8080:8080 -p 9100:9100 --env-file .env bw-vector-sync:3.0.0
```

或 K8s：

```bash
kubectl apply -f deploy/k8s-deployment.yaml
kubectl apply -f deploy/k8s-service.yaml
```

## 🧪 测试

```bash
# 全部测试 + HTML 报告
poetry run pytest --html=reports/report.html --self-contained-html

# 单元测试
poetry run pytest tests/unit/

# 集成测试
poetry run pytest tests/integration/

# 覆盖率
poetry run pytest --cov=bw_vector_sync --cov-report=html
```

## 📊 Prometheus 指标

| 指标 | 标签 | 含义 |
|---|---|---|
| `bw_vector_sync_messages_consumed_total` | queue, biz_type, operation | 消费成功数 |
| `bw_vector_sync_messages_failed_total` | queue, biz_type, error_type | 消费失败数（最终进 DLQ） |
| `bw_vector_sync_dedup_hits_total` | queue | 幂等去重拦截数 |
| `bw_vector_sync_consumer_lag_seconds` | queue | 生产到消费时延 |
| `bw_vector_sync_milvus_write_latency_seconds` | collection, operation | Milvus 写入耗时分布 |
| `bw_vector_sync_connection_status` | component | 依赖连接状态（1/0） |

## 🔌 HTTP 端点

| 路径 | 用途 | K8s 探针 |
|---|---|---|
| `GET /health` | liveness（进程存活） | `livenessProbe` |
| `GET /ready` | readiness（依赖就绪） | `readinessProbe` |
| `GET /metrics`（端口 9100） | Prometheus 抓取 | serviceMonitor |

## 🛡️ 错误处理矩阵

| 异常 | 表现 | 处理 |
|---|---|---|
| `DecodeError`（Protobuf 失败） | 业务校验失败 | nack(requeue=False) → DLX |
| `MilvusParamError` | 参数错误 | nack(requeue=False) → DLX |
| `MilvusCollectionNotExistError` | collection 缺失 | tenacity 重试 3 次 → DLX |
| `MilvusNetworkError` | 网络超时 | tenacity 重试 3 次 → DLX |
| Redis 不可用 | 视为可重试 | 重试 3 次 → DLX |

## 🧬 一致性保障

- **MySQL → Milvus** 最终一致，端到端延迟 ≤ 5s
- **幂等**：Redis SETNX + pymilvus upsert 双重幂等
- **DLQ 兜底**：消息处理失败入 `bw.dw.q.dlq`，运维通过 Management UI 修复后 `rabbitmqadmin` 重投
- **回放能力**：依赖 Outbox 归档表（`dual_write_outbox_hist`，30 天 TTL）

## 📐 API 文档

### `ProtoDecoder.decode(body: bytes) -> DualWriteEvent`

解析 Protobuf 字节流为强类型 dataclass 事件。

| 参数 | 类型 | 说明 |
|---|---|---|
| `body` | `bytes` | AMQP 消息体 |

**返回**：`DualWriteEvent` dataclass（不可变），含 `biz_type` / `biz_id` / `version` / `occurred_at` / `operation` / `data` / `vector` / `headers`。

**异常**：`DecodeError`（payload 非法、字段缺失、维度不匹配等）。

### `MilvusWriter.upsert_post(post_id, user_id, vector, metadata)`

写入 / 更新一条 Post 向量到 `bw_post` 集合。

| 参数 | 类型 | 说明 |
|---|---|---|
| `post_id` | `int` | 业务主键（也是 Milvus `id`） |
| `user_id` | `int` | 作者 ID |
| `vector` | `list[float]` | 1024 维向量 |
| `metadata` | `dict` | 写入 JSON 字段（`title` / `tags` / `content_length`） |

**异常**：`MilvusParamError` / `MilvusNetworkError` / `MilvusCollectionNotExistError`。

### `IdempotencyGuard.try_acquire(key: str, ttl: int = 7d) -> bool`

Redis SETNX 原子去重。

| 参数 | 类型 | 说明 |
|---|---|---|
| `key` | `str` | 业务键（监听器已拼为 `{queue}:{message_id}`） |
| `ttl` | `int` | 过期秒数 |

**返回**：`True` 首次处理；`False` 重复消息。

## 🔗 关联项目

| 组件 | 仓库 | 角色 |
|---|---|---|
| `bw-proto-schemas` | Git submodule | Protobuf 共享定义 |
| `bw-common-mq` | Java lib | AMQP Producer 配置 |
| `bw-post` / `bw-user` | Java 微服务 | 业务侧 Outbox 写入 |
| `bw-vector-sync` | **本仓库** | Python 消费者 |
| `bw-vector-outbox` | Java | Outbox 调度器（投递到 RabbitMQ） |

## 📜 License

Proprietary · brillian-world team · 2026
