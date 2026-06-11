# 配置说明文档

本文档列出 `bw-vector-sync` 所有可配置参数，按域分组。所有参数同时支持环境变量（同名大写）与 `.env` 文件。

## 1. RabbitMQ

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RABBITMQ_URL` | `amqp://bw_app:change-me@localhost:5672/%2Fbw` | AMQP 连接串，v3 推荐 Quorum Queue |
| `RABBITMQ_EXCHANGE` | `bw.dw.exchange` | 业务交换机（topic） |
| `RABBITMQ_QUEUES` | `bw.dw.q.post,bw.dw.q.user` | 消费者订阅队列列表（逗号分隔） |
| `RABBITMQ_DLQ` | `bw.dw.q.dlq` | 死信队列 |
| `CONSUMER_PREFETCH` | `50` | 单消费者 QoS 预取数（1-1000） |
| `CONSUMER_CONCURRENCY` | `50` | Pod 内协程并发数 |

## 2. Milvus

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MILVUS_HOST` | `localhost` | Milvus gRPC 主机 |
| `MILVUS_PORT` | `19530` | Milvus gRPC 端口 |
| `MILVUS_USER` | `None` | 鉴权用户（可选） |
| `MILVUS_PASSWORD` | `None` | 鉴权密码（可选） |
| `MILVUS_COLLECTION_POST` | `bw_post` | 帖子集合名 |
| `MILVUS_COLLECTION_USER` | `bw_user` | 用户集合名 |
| `MILVUS_VECTOR_DIM` | `1024` | 向量维度（与 text-embedding-v3 对齐） |
| `MILVUS_METRIC_TYPE` | `COSINE` | 距离度量（`COSINE` / `L2` / `IP`） |
| `MILVUS_INDEX_TYPE` | `HNSW` | 索引类型（`HNSW` / `IVF_FLAT` / `ANNOY`） |

## 3. Redis

| 变量 | 默认值 | 说明 |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 URL |
| `REDIS_DEDUP_PREFIX` | `dw:dedup:` | 去重键前缀 |
| `DEDUP_TTL_SECONDS` | `604800` (7d) | 去重记录 TTL（秒） |

## 4. Observability

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OTLP_ENABLED` | `false` | 是否上报到 OTLP Collector |
| `OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC 端点 |
| `SERVICE_NAME` | `bw-vector-sync` | 服务名（trace resource） |
| `METRICS_PORT` | `9100` | Prometheus 暴露端口 |

## 5. 运行时

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `LOG_JSON` | `true` | JSON 格式（K8s 推荐） |
| `HEALTH_PORT` | `8080` | 健康检查 HTTP 端口 |
| `BATCH_SIZE` | `100` | 批量写入大小 |
| `BATCH_TIMEOUT_MS` | `50` | 批量等待超时（毫秒） |

## 6. K8s 探针

| 端点 | 用途 | 默认端口 | 探针类型 |
|---|---|---|---|
| `/health` | 进程存活 | 8080 | `livenessProbe` |
| `/ready` | 依赖就绪 | 8080 | `readinessProbe` |
| `/metrics` | Prometheus | 9100 | `serviceMonitor` |

## 7. 错误处理

| 异常 | 行为 | 重试次数 | 终态 |
|---|---|---|---|
| `DecodeError` | nack(requeue=False) | 0 | DLQ |
| `MilvusParamError` | nack(requeue=False) | 0 | DLQ |
| `MilvusCollectionNotExistError` | tenacity wait_exponential | 3 | DLQ |
| `MilvusNetworkError` | tenacity wait_exponential | 3 | DLQ |
| Redis 不可用 | tenacity | 3 | DLQ |
| 未知异常 | tenacity | 2 | DLQ |

## 8. 跨语言 Protobuf 契约

- `proto/dual_write_event.proto` 由 Java 与 Python 仓库通过 Git submodule 共享
- 字段新增/删除/重命名必须有版本字段（`version`）
- CI 跑契约测试：相同 payload 在两端解析结果一致
