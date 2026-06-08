# Post Agent Service - 帖子交流网站 LangChain Agent 服务

基于 LangChain + FastAPI 开发的智能 Agent 服务，为帖子交流网站提供：
1. **智能聊天助手** - 根据用户聊天风格生成建议语句
2. **生成式帖子推荐引擎** - 基于用户兴趣的个性化推荐

## 技术栈

- **语言**: Python 3.10+
- **Web框架**: FastAPI
- **Agent框架**: LangChain 0.2+
- **嵌入模型**: BGE-M3 (多语言，1024维)
- **向量数据库**: Milvus 2.3+
- **关系数据库**: PostgreSQL 15+
- **缓存**: Redis 7.0+
- **异步任务**: Celery 5.3+
- **LLM**: OpenAI GPT-3.5-turbo / Qwen-14B-Chat

## 项目结构

```
post_agent_service/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── config/                 # 配置
│   │   ├── settings.py
│   │   └── model_config.py
│   ├── api/                    # API 层
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── chat_agent.py
│   │       └── recommend_agent.py
│   ├── core/                   # 核心业务
│   │   ├── agents/
│   │   │   ├── chat_assistant_agent.py
│   │   │   └── post_recommend_agent.py
│   │   ├── services/
│   │   │   ├── vector_service.py
│   │   │   ├── user_style_service.py
│   │   │   ├── post_content_service.py
│   │   │   └── user_behavior_service.py
│   │   └── schemas/
│   │       ├── chat.py
│   │       ├── post.py
│   │       └── user.py
│   ├── db/                     # 数据库
│   │   ├── milvus_client.py
│   │   ├── postgres_client.py
│   │   └── redis_client.py
│   ├── tasks/                  # Celery 任务
│   │   ├── worker.py
│   │   ├── vector_tasks.py
│   │   └── behavior_tasks.py
│   └── utils/
│       ├── embedding.py
│       ├── text_splitter.py
│       └── logger.py
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .env.example
├── requirements.txt
└── README.md
```

## 快速开始

### 本地开发

1. **克隆项目并安装依赖**
```bash
cd brillian-world-Agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **配置环境变量**
```bash
cp docker/.env.example .env
# 编辑 .env 文件，填入 OPENAI_API_KEY 等配置
```

3. **启动依赖服务（可选）**
```bash
cd docker
docker-compose up -d postgres milvus-standalone redis
```

> 注意：未启动依赖服务时，应用会自动进入 mock 模式，可用于本地开发测试。

4. **启动应用**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. **访问 API 文档**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Docker 部署

```bash
cd docker
docker-compose up -d
```

## HTTP API 接口

服务基础地址：`http://<host>:8000/api/v1`

### 聊天助手接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat/settings` | 更新聊天助手设置 |
| GET  | `/chat/settings/{user_id}` | 获取聊天助手设置 |
| POST | `/chat/authorize` | 授权开启/关闭聊天助手 |
| POST | `/chat/messages` | 提交聊天消息（采集风格） |
| POST | `/chat/upload` | 批量上传聊天数据 |
| POST | `/chat/suggestions` | 获取聊天建议 |
| GET  | `/chat/status/{user_id}` | 获取助手状态 |

### 帖子推荐接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/posts` | 添加帖子 |
| POST | `/posts/batch` | 批量添加帖子 |
| DELETE | `/posts/{post_id}` | 删除帖子 |
| POST | `/search` | 智能搜索（精确/发散） |
| GET  | `/recommendations` | 首页个性化推荐 |
| GET  | `/search-suggestions/{user_id}` | 搜索建议 |

### 用户行为接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/behavior/view` | 上报浏览行为 |
| POST | `/behavior/interaction` | 上报交互行为 |
| GET  | `/behavior/profile/{user_id}` | 获取用户画像 |

## 接口调用示例

### 1. 授权开启聊天助手

```bash
curl -X POST http://localhost:8000/api/v1/chat/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "authorize": true,
    "data_types": ["chat_history", "writing_style"]
  }'
```

### 2. 提交聊天消息

```bash
curl -X POST http://localhost:8000/api/v1/chat/messages \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "conversation_id": "conv_001",
    "message": "今天天气真不错，适合出去走走",
    "message_type": 1
  }'
```

### 3. 获取聊天建议

```bash
curl -X POST http://localhost:8000/api/v1/chat/suggestions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "context": "用户A: 周末一起去看电影吗？\n用户B: 好啊，你想看什么电影？",
    "suggestion_count": 3
  }'
```

### 4. 添加帖子

```bash
curl -X POST http://localhost:8000/api/v1/posts \
  -H "Content-Type: application/json" \
  -d '{
    "post_id": "post_001",
    "title": "Python LangChain 入门教程",
    "content": "LangChain 是一个强大的大语言模型应用开发框架...",
    "category": "技术",
    "tags": ["Python", "LangChain", "AI"],
    "author_id": "user456"
  }'
```

### 5. 智能搜索（精确模式）

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "query": "如何使用 LangChain 开发 Agent",
    "search_mode": "precise",
    "limit": 20
  }'
```

### 6. 首页推荐

```bash
curl -X GET "http://localhost:8000/api/v1/recommendations?user_id=user123&limit=10"
```

### 7. 上报浏览行为

```bash
curl -X POST http://localhost:8000/api/v1/behavior/view \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "post_id": "post_001",
    "dwell_time_seconds": 120,
    "scroll_depth": 0.8
  }'
```

## 核心实现逻辑

### 1. 聊天助手

```
用户开启聊天助手
       ↓
同意数据采集 → 采集对话消息 → 文本分片 → BGE-M3 向量化
       ↓
存入 Milvus user_chat_styles 集合
       ↓
用户请求聊天建议
       ↓
检查风格数据量 ≥ 50 条？
   ├─ 是 → 计算风格相似度 ≥ 0.6？
   │         ├─ 是 → 使用用户风格生成建议
   │         └─ 否 → 使用默认数据生成
   └─ 否 → 使用默认数据生成
```

### 2. 帖子推荐

```
帖子发布
   ↓
文本分片（500字/片，50字重叠）→ BGE-M3 向量化
   ↓
存入 Milvus post_contents 集合
   ↓
用户浏览 → 记录行为（浏览、点赞、评论、分享）
   ↓
计算用户兴趣向量（加权平均 + 时间衰减）
   ↓
判断是否达到推荐阈值
   ├─ 达到 → 基于兴趣向量检索相似帖子 → LLM 生成推荐理由
   └─ 未达到 → 返回热门帖子
```

## 关键配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `USER_STYLE_MIN_COUNT` | 50 | 触发个性化推荐的最少消息数 |
| `STYLE_SIMILARITY_THRESHOLD` | 0.6 | 风格匹配度阈值 |
| `BEHAVIOR_VIEW_THRESHOLD` | 10 | 触发推荐的最少浏览次数 |
| `BEHAVIOR_DURATION_THRESHOLD` | 60 | 触发推荐的最少停留时长（秒） |
| `PRECISE_SEARCH_SIMILARITY` | 0.7 | 精确搜索相似度阈值 |
| `DIVERGENT_SEARCH_SIMILARITY` | 0.5 | 发散搜索相似度阈值 |

## 监控与运维

### 健康检查
```bash
curl http://localhost:8000/health
```

### Celery 监控
```bash
# 启动 Flower
celery -A app.tasks.worker flower --port=5555
# 访问 http://localhost:5555
```

## 注意事项

1. **未配置 OPENAI_API_KEY 时**，聊天助手/推荐引擎会使用降级方案（基于规则），仍可正常运行。
2. **未启动 Milvus/PostgreSQL/Redis 时**，应用自动进入 mock 模式，适合本地开发。
3. **生产环境建议**：启用真实依赖服务，并配置好 BGE-M3 模型（推荐使用 GPU）。
4. **数据隐私**：所有聊天数据采集需用户明确授权，用户可随时关闭/删除。

## License

MIT
