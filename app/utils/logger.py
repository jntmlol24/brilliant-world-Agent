"""日志工具"""
import sys
import os
from loguru import logger as _logger
from app.config.settings import settings


# 移除默认的 handler
_logger.remove()

# 添加控制台输出
_logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.DEBUG else "INFO",
    colorize=True,
)

# 添加文件输出
log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(log_path, exist_ok=True)

_logger.add(
    os.path.join(log_path, "app_{time:YYYY-MM-DD}.log"),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="00:00",
    retention="30 days",
    encoding="utf-8",
    enqueue=True,
)


logger = _logger
