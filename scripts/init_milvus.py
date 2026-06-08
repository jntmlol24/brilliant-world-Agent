"""
初始化 Milvus 集合和 PostgreSQL 表
用于首次部署或重置时使用
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.milvus_client import milvus_client
from app.db.postgres_client import postgres_client
from app.config.model_config import model_config
from app.utils.logger import logger


async def init_milvus_collections():
    """初始化 Milvus 集合"""
    logger.info("=" * 60)
    logger.info("初始化 Milvus 集合")
    logger.info("=" * 60)

    milvus_client.connect()

    # 创建用户风格集合
    config = model_config.user_chat_styles_collection
    logger.info(f"创建集合: {config.name}")
    milvus_client.create_collection(config.name)

    # 创建帖子内容集合
    config = model_config.post_contents_collection
    logger.info(f"创建集合: {config.name}")
    milvus_client.create_collection(config.name)

    logger.info("Milvus 集合初始化完成")


async def init_postgres_tables():
    """初始化 PostgreSQL 表"""
    logger.info("=" * 60)
    logger.info("初始化 PostgreSQL 表")
    logger.info("=" * 60)

    await postgres_client.connect()
    # _init_tables 会在 connect 时自动调用
    logger.info("PostgreSQL 表初始化完成")


async def drop_all():
    """删除所有集合和表（危险操作）"""
    confirm = input("确认删除所有 Milvus 集合和 PostgreSQL 表吗？(yes/no): ")
    if confirm.lower() != "yes":
        logger.info("操作已取消")
        return

    milvus_client.connect()
    await postgres_client.drop_all_tables() if hasattr(postgres_client, "drop_all_tables") else None

    for config in [model_config.user_chat_styles_collection, model_config.post_contents_collection]:
        logger.info(f"删除集合: {config.name}")
        await milvus_client.drop_collection(config.name)

    logger.info("删除完成")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="初始化 Milvus 和 PostgreSQL")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="删除所有集合和表（危险）",
    )
    args = parser.parse_args()

    if args.drop:
        await drop_all()
    else:
        try:
            await init_milvus_collections()
            await init_postgres_tables()
            logger.info("=" * 60)
            logger.info("所有初始化完成！")
            logger.info("=" * 60)
        except Exception as e:
            logger.error(f"初始化失败: {e}", exc_info=True)
            sys.exit(1)
        finally:
            await postgres_client.close()


if __name__ == "__main__":
    asyncio.run(main())
