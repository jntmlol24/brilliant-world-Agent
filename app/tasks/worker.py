"""Celery Worker 入口"""
from celery import Celery
from app.config.settings import settings

# 创建 Celery 应用
celery_app = Celery(
    "post_agent",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.vector_tasks",
        "app.tasks.behavior_tasks",
    ],
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_max_tasks_per_child=1000,
    worker_prefetch_multiplier=1,
)

if __name__ == "__main__":
    celery_app.start()
