"""依赖注入"""
from typing import Optional
from fastapi import Depends, HTTPException, Header
from app.core.agents.chat_assistant_agent import ChatAssistantAgent
from app.core.agents.post_recommend_agent import PostRecommendAgent
from app.db.milvus_client import milvus_client
from app.db.postgres_client import postgres_client
from app.db.redis_client import redis_client


# 全局 Agent 实例（单例）
_chat_agent: Optional[ChatAssistantAgent] = None
_recommend_agent: Optional[PostRecommendAgent] = None


def get_chat_agent() -> ChatAssistantAgent:
    """获取聊天助手 Agent"""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAssistantAgent()
    return _chat_agent


def get_recommend_agent() -> PostRecommendAgent:
    """获取推荐 Agent"""
    global _recommend_agent
    if _recommend_agent is None:
        _recommend_agent = PostRecommendAgent()
    return _recommend_agent


async def verify_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    """从 Header 验证用户ID（示例）"""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="缺少用户标识")
    return x_user_id


async def init_db_connections():
    """初始化数据库连接"""
    milvus_client.connect()
    await postgres_client.connect()
    await redis_client.connect()


async def close_db_connections():
    """关闭数据库连接"""
    await postgres_client.close()
    await redis_client.close()
