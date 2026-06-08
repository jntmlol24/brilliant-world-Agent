"""用户行为分析相关异步任务"""
from app.tasks.worker import celery_app
from app.utils.logger import logger
import asyncio
from datetime import datetime, timedelta


@celery_app.task(name="behavior.analyze_user_interest", bind=True, max_retries=2)
def analyze_user_interest_task(self, user_id: str):
    """异步分析用户兴趣，更新兴趣向量"""
    try:
        from app.core.services.user_behavior_service import UserBehaviorService

        service = UserBehaviorService()
        # 生成并缓存兴趣向量
        interest_vector = asyncio.run(service.get_user_interest_vector(user_id))
        interests = asyncio.run(service.get_user_interest_topics(user_id))

        logger.info(f"用户兴趣分析完成: {user_id}")
        return {
            "user_id": user_id,
            "interest_vector_length": len(interest_vector),
            "interests_count": len(interests),
            "analyzed_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"用户兴趣分析失败: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name="behavior.cleanup_expired_data", bind=True)
def cleanup_expired_data_task(self):
    """清理过期数据"""
    try:
        from app.db.postgres_client import postgres_client

        async def cleanup():
            # 删除 90 天前的行为数据
            result = await postgres_client.execute(
                "DELETE FROM user_behavior WHERE created_at < NOW() - INTERVAL '90 days'"
            )
            return result

        result = asyncio.run(cleanup())
        logger.info(f"过期数据清理完成: {result}")
        return {"status": "success", "result": str(result)}
    except Exception as e:
        logger.error(f"过期数据清理失败: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="behavior.refresh_recommendations", bind=True, max_retries=2)
def refresh_user_recommendations_task(self, user_id: str):
    """刷新用户推荐缓存"""
    try:
        from app.core.agents.post_recommend_agent import PostRecommendAgent

        agent = PostRecommendAgent()
        asyncio.run(agent.refresh_recommendation_cache(user_id))
        # 预热推荐缓存
        result = asyncio.run(agent.get_recommendations(user_id, limit=10, use_cache=False))
        logger.info(f"用户推荐刷新完成: {user_id}")
        return {"status": "success", "recommendation_type": result.get("recommendation_type")}
    except Exception as e:
        logger.error(f"用户推荐刷新失败: {e}")
        raise self.retry(exc=e, countdown=60)


# 定时任务配置（需在 Celery beat 中启动）
celery_app.conf.beat_schedule = {
    "cleanup-expired-data-daily": {
        "task": "behavior.cleanup_expired_data",
        "schedule": 86400.0,  # 每天执行
    },
}
