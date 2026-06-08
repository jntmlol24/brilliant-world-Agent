"""FastAPI 主应用入口"""
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.api.deps import init_db_connections, close_db_connections
from app.api.v1 import chat_agent, recommend_agent
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info(f"启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    try:
        await init_db_connections()
        logger.info("数据库连接初始化完成")
    except Exception as e:
        logger.error(f"数据库连接初始化失败: {e}")

    # 初始化 Milvus 集合
    try:
        from app.core.services.user_style_service import UserStyleService
        from app.core.services.post_content_service import PostContentService

        style_service = UserStyleService()
        await style_service.init_collection()

        post_service = PostContentService()
        await post_service.init_collection()
        logger.info("Milvus 集合初始化完成")
    except Exception as e:
        logger.error(f"Milvus 集合初始化失败: {e}")

    yield

    # 关闭时
    logger.info("关闭应用...")
    try:
        await close_db_connections()
    except Exception as e:
        logger.error(f"关闭数据库连接失败: {e}")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## 帖子交流网站 LangChain Agent 服务

提供两个核心 Agent 功能：

### 1. 智能聊天助手
- 根据用户聊天风格生成建议
- 支持用户授权开关
- 数据不足时使用默认数据

### 2. 生成式帖子推荐引擎
- 基于用户兴趣向量的个性化推荐
- 支持精确/发散两种搜索模式
- 主页和搜索页主动推送
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录请求日志"""
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {process_time:.2f}ms"
        )
        response.headers["X-Process-Time"] = f"{process_time:.2f}"
        return response
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        logger.error(
            f"{request.method} {request.url.path} - ERROR - {process_time:.2f}ms - {str(e)}"
        )
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "Internal Server Error", "detail": str(e)},
        )


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.error(f"未处理异常 {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "Internal Server Error", "detail": str(exc)},
    )


# 注册路由
app.include_router(chat_agent.router, prefix=settings.API_PREFIX)
app.include_router(recommend_agent.router, prefix=settings.API_PREFIX)


# 根路由
@app.get("/", tags=["根"])
async def root():
    """根路由"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


# 健康检查
@app.get("/health", tags=["健康检查"])
async def health():
    """健康检查"""
    from app.db.milvus_client import milvus_client
    from app.db.postgres_client import postgres_client
    from app.db.redis_client import redis_client

    milvus_ok = False
    postgres_ok = False
    redis_ok = False

    try:
        milvus_client._ensure_connected()
        milvus_ok = True
    except Exception:
        pass

    try:
        if postgres_client._pool or postgres_client._mock_mode:
            postgres_ok = True
    except Exception:
        pass

    try:
        if redis_client._client or redis_client._mock_mode:
            redis_ok = True
    except Exception:
        pass

    status = "healthy" if (milvus_ok and postgres_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "services": {
            "milvus": "connected" if milvus_ok else "disconnected",
            "postgres": "connected" if postgres_ok else "disconnected",
            "redis": "connected" if redis_ok else "disconnected",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
