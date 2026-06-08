"""用户风格服务 - 聊天风格向量库管理"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
from app.db.milvus_client import milvus_client
from app.db.postgres_client import postgres_client
from app.core.services.vector_service import VectorService
from app.utils.text_splitter import split_chat_message
from app.config.settings import settings
from app.config.model_config import model_config
from app.utils.logger import logger


class UserStyleService:
    """用户聊天风格服务"""

    def __init__(self):
        self.vector_service = VectorService()
        self.collection_name = model_config.user_chat_styles_collection.name
        self.min_count = settings.USER_STYLE_MIN_COUNT
        self.similarity_threshold = settings.STYLE_SIMILARITY_THRESHOLD

    async def init_collection(self):
        """初始化集合"""
        milvus_client.create_collection(self.collection_name)

    async def add_user_message(
        self,
        user_id: str,
        message: str,
        message_type: int = 1,
        conversation_id: str = "default",
    ) -> Dict[str, Any]:
        """添加用户消息到风格库

        Args:
            user_id: 用户ID
            message: 消息内容
            message_type: 1=用户发送, 2=用户接收
            conversation_id: 会话ID

        Returns:
            处理结果
        """
        # 文本分片
        chunks = split_chat_message(message)
        if not chunks:
            return {"message_id": None, "chunks_count": 0, "processed": False}

        # 向量化
        vectors = await self.vector_service.embed_texts(chunks)

        # 批量插入
        timestamp = int(time.time() * 1000)
        data_list = []
        message_ids = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            message_id = f"{conversation_id}_{timestamp}_{i}"
            message_ids.append(message_id)
            data_list.append(
                {
                    "user_id": user_id,
                    "message_id": message_id,
                    "content_vector": vector,
                    "content_text": chunk[:2000],
                    "message_type": message_type,
                    "conversation_id": conversation_id,
                    "created_at": timestamp,
                }
            )

        await milvus_client.insert(
            collection_name=self.collection_name,
            data=data_list,
        )

        # 保存到 PostgreSQL 备份
        for i, chunk in enumerate(chunks):
            try:
                await postgres_client.execute(
                    """
                    INSERT INTO chat_messages (user_id, conversation_id, message_id, content, message_type, created_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    ON CONFLICT (message_id) DO NOTHING
                    """,
                    user_id,
                    conversation_id,
                    message_ids[i],
                    chunk,
                    message_type,
                )
            except Exception as e:
                logger.warning(f"保存消息备份失败: {e}")

        # 更新用户风格计数
        await self.update_user_style_count(user_id)

        return {
            "message_id": message_ids[0] if message_ids else None,
            "chunks_count": len(chunks),
            "processed": True,
        }

    async def get_user_style_count(self, user_id: str) -> int:
        """获取用户风格数据条数"""
        try:
            count = await postgres_client.fetchval(
                "SELECT style_data_count FROM user_chat_settings WHERE user_id = $1",
                user_id,
            )
            return count or 0
        except Exception as e:
            logger.error(f"获取用户风格数量失败: {e}")
            return 0

    async def update_user_style_count(self, user_id: str, increment: int = 1):
        """更新用户风格数据计数"""
        try:
            await postgres_client.execute(
                """
                INSERT INTO user_chat_settings (user_id, style_data_count, last_updated)
                VALUES ($1, $2, NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET style_data_count = user_chat_settings.style_data_count + $2, last_updated = NOW()
                """,
                user_id,
                increment,
            )
        except Exception as e:
            logger.error(f"更新用户风格计数失败: {e}")

    async def get_user_style_similarity(
        self, user_id: str, current_context: str
    ) -> float:
        """计算用户当前风格匹配度

        Args:
            user_id: 用户ID
            current_context: 当前对话上下文

        Returns:
            平均相似度（0-1）
        """
        # 检查数据量是否足够
        count = await self.get_user_style_count(user_id)
        if count < self.min_count:
            logger.debug(f"用户 {user_id} 风格数据不足：{count} < {self.min_count}")
            return 0.0

        # 检索相似风格
        try:
            results = await self.vector_service.search_similar(
                collection_name=self.collection_name,
                query_text=current_context,
                filter_expr=f'user_id == "{user_id}"',
                limit=10,
                output_fields=["content_text"],
            )

            if not results:
                return 0.0

            # 计算平均相似度
            scores = [r.get("score", 0) for r in results]
            avg_similarity = sum(scores) / len(scores) if scores else 0.0
            logger.debug(f"用户 {user_id} 风格匹配度: {avg_similarity:.3f}")
            return avg_similarity
        except Exception as e:
            logger.error(f"计算风格相似度失败: {e}")
            return 0.0

    async def get_user_style_examples(
        self, user_id: str, limit: int = 5
    ) -> List[str]:
        """获取用户风格示例"""
        try:
            # 优先获取用户最近发送的消息（message_type=1）
            results = await milvus_client.search(
                collection_name=self.collection_name,
                query_vector=await self.vector_service.embed_query("日常聊天"),
                filter_expr=f'user_id == "{user_id}" && message_type == 1',
                limit=limit,
                output_fields=["content_text"],
            )
            return [r.get("content_text", "") for r in results]
        except Exception as e:
            logger.error(f"获取用户风格示例失败: {e}")
            return []

    async def delete_user_style(self, user_id: str) -> int:
        """删除用户所有风格数据"""
        try:
            # 删除 Milvus 数据
            count = await milvus_client.delete(
                collection_name=self.collection_name,
                filter_expr=f'user_id == "{user_id}"',
            )

            # 重置计数
            await postgres_client.execute(
                """
                UPDATE user_chat_settings
                SET style_data_count = 0, last_updated = NOW()
                WHERE user_id = $1
                """,
                user_id,
            )

            # 删除消息备份
            await postgres_client.execute(
                "DELETE FROM chat_messages WHERE user_id = $1",
                user_id,
            )

            return count
        except Exception as e:
            logger.error(f"删除用户风格数据失败: {e}")
            return 0

    async def is_data_sufficient(self, user_id: str) -> bool:
        """判断用户数据是否充足"""
        count = await self.get_user_style_count(user_id)
        return count >= self.min_count
