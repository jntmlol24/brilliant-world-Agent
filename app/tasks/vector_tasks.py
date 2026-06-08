"""向量生成相关异步任务"""
from app.tasks.worker import celery_app
from app.utils.logger import logger
import asyncio


@celery_app.task(name="vector.process_post", bind=True, max_retries=3)
def process_post_task(self, post_id: str, title: str, content: str, category: str, tags: list, author_id: str = None):
    """异步处理帖子向量化"""
    try:
        from app.core.services.post_content_service import PostContentService

        service = PostContentService()
        result = asyncio.run(
            service.add_post(
                post_id=post_id,
                title=title,
                content=content,
                category=category,
                tags=tags,
                author_id=author_id,
            )
        )
        logger.info(f"异步处理帖子完成: {post_id}")
        return result
    except Exception as e:
        logger.error(f"异步处理帖子失败: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name="vector.process_chat_message", bind=True, max_retries=3)
def process_chat_message_task(self, user_id: str, message: str, message_type: int, conversation_id: str):
    """异步处理聊天消息向量化"""
    try:
        from app.core.services.user_style_service import UserStyleService

        service = UserStyleService()
        result = asyncio.run(
            service.add_user_message(
                user_id=user_id,
                message=message,
                message_type=message_type,
                conversation_id=conversation_id,
            )
        )
        logger.info(f"异步处理聊天消息完成: {user_id}")
        return result
    except Exception as e:
        logger.error(f"异步处理聊天消息失败: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name="vector.batch_process_posts", bind=True, max_retries=2)
def batch_process_posts_task(self, posts: list):
    """批量处理帖子"""
    try:
        from app.core.services.post_content_service import PostContentService

        service = PostContentService()
        result = asyncio.run(service.batch_add_posts(posts))
        logger.info(f"批量处理帖子完成: success={result['success']}")
        return result
    except Exception as e:
        logger.error(f"批量处理帖子失败: {e}")
        raise self.retry(exc=e, countdown=120)
