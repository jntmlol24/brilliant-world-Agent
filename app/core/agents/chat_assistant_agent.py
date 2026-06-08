"""聊天助手 Agent - 核心业务逻辑"""
from typing import Dict, Any, List, Optional
import json
import re

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

from app.config.settings import settings
from app.db.postgres_client import postgres_client
from app.core.services.user_style_service import UserStyleService
from app.utils.logger import logger


class ChatAssistantAgent:
    """聊天助手 Agent

    根据用户聊天习惯和对话语境，生成多个不同方向的建议语句。
    当用户数据不足时使用默认数据生成。
    """

    def __init__(self):
        self.user_style_service = UserStyleService()

        # 初始化 LLM
        self.llm = None
        self.default_prompt = None
        self.style_prompt = None
        self.parser = None

        if LANGCHAIN_AVAILABLE and (settings.OPENAI_API_KEY or settings.QWEN_API_KEY):
            try:
                if settings.OPENAI_API_KEY:
                    self.llm = ChatOpenAI(
                        model=settings.LLM_MODEL,
                        temperature=settings.LLM_TEMPERATURE,
                        openai_api_key=settings.OPENAI_API_KEY,
                        openai_api_base=settings.OPENAI_BASE_URL,
                    )
                else:
                    # 使用 Qwen
                    from langchain_community.chat_models import ChatTongyi
                    self.llm = ChatTongyi(
                        model_name=settings.QWEN_MODEL,
                        temperature=settings.LLM_TEMPERATURE,
                        dashscope_api_key=settings.QWEN_API_KEY,
                    )
                self.parser = JsonOutputParser()
                self._init_prompts()
                logger.info(f"聊天助手 Agent LLM 初始化完成: {settings.LLM_MODEL}")
            except Exception as e:
                logger.error(f"LLM 初始化失败: {e}")
                self.llm = None

    def _init_prompts(self):
        """初始化提示词模板"""
        # 默认风格提示词（无用户风格数据时使用）
        self.default_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个聊天助手，根据用户当前的对话上下文，生成3个不同方向的可能回复。"
                    "回复应该自然、简洁，符合日常聊天习惯。\n"
                    "输出格式为严格的JSON数组，包含3个字符串元素。\n"
                    "例如：[\"好的，没问题\", \"我再考虑一下\", \"那就这样吧\"]",
                ),
                ("human", "对话上下文：\n{context}\n\n用户接下来可能想说的3个不同方向回复："),
            ]
        )

        # 个性化风格提示词（有用户风格数据时使用）
        self.style_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个聊天助手，根据用户的聊天风格和当前对话上下文，生成3个不同方向的可能回复。\n"
                    "用户的历史聊天风格示例：\n{style_examples}\n\n"
                    "要求：\n"
                    "1. 严格模仿用户的语言风格、用词习惯和语气\n"
                    "2. 生成3个不同方向（赞同/反对/中立/提问等）的回复\n"
                    "3. 输出格式为严格的JSON数组，包含3个字符串元素。",
                ),
                (
                    "human",
                    "对话上下文：\n{context}\n\n用户接下来可能想说的3个不同方向回复：",
                ),
            ]
        )

    async def get_user_settings(self, user_id: str) -> Dict[str, Any]:
        """获取用户聊天设置"""
        try:
            record = await postgres_client.fetchrow(
                """
                SELECT chat_assistant_enabled, data_collection_enabled, style_data_count
                FROM user_chat_settings
                WHERE user_id = $1
                """,
                user_id,
            )
            if record:
                return {
                    "chat_assistant_enabled": record["chat_assistant_enabled"],
                    "data_collection_enabled": record["data_collection_enabled"],
                    "style_data_count": record["style_data_count"],
                }
            return {
                "chat_assistant_enabled": False,
                "data_collection_enabled": False,
                "style_data_count": 0,
            }
        except Exception as e:
            logger.error(f"获取用户设置失败: {e}")
            return {
                "chat_assistant_enabled": False,
                "data_collection_enabled": False,
                "style_data_count": 0,
            }

    async def update_user_settings(
        self,
        user_id: str,
        chat_assistant_enabled: bool,
        data_collection_enabled: bool,
    ) -> Dict[str, Any]:
        """更新用户聊天设置"""
        try:
            await postgres_client.execute(
                """
                INSERT INTO user_chat_settings (user_id, chat_assistant_enabled, data_collection_enabled, last_updated)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET chat_assistant_enabled = $2, data_collection_enabled = $3, last_updated = NOW()
                """,
                user_id,
                chat_assistant_enabled,
                data_collection_enabled,
            )
            return await self.get_user_settings(user_id)
        except Exception as e:
            logger.error(f"更新用户设置失败: {e}")
            raise

    async def generate_suggestions(
        self,
        user_id: str,
        context: str,
        suggestion_count: int = 3,
    ) -> Dict[str, Any]:
        """生成聊天建议

        Args:
            user_id: 用户ID
            context: 对话上下文
            suggestion_count: 建议数量

        Returns:
            包含建议的字典
        """
        # 1. 检查用户是否开启了聊天助手
        settings_data = await self.get_user_settings(user_id)
        if not settings_data["chat_assistant_enabled"]:
            return {
                "enabled": False,
                "data_sufficient": False,
                "message": "聊天助手未开启",
                "suggestions": [],
            }

        # 2. 检查用户风格数据是否足够
        similarity = await self.user_style_service.get_user_style_similarity(
            user_id, context
        )
        is_sufficient = await self.user_style_service.is_data_sufficient(user_id)

        # 3. 根据数据情况选择提示词
        if is_sufficient and similarity >= settings.STYLE_SIMILARITY_THRESHOLD:
            # 使用个性化风格
            style_examples = await self.user_style_service.get_user_style_examples(
                user_id, limit=5
            )
            suggestions = await self._invoke_llm(
                prompt=self.style_prompt,
                variables={"style_examples": "\n".join(style_examples) or "无", "context": context},
                count=suggestion_count,
            )
            return {
                "enabled": True,
                "data_sufficient": True,
                "message": "基于您的聊天风格生成建议",
                "suggestions": suggestions,
                "style_similarity": similarity,
            }
        else:
            # 使用默认风格
            suggestions = await self._invoke_llm(
                prompt=self.default_prompt,
                variables={"context": context},
                count=suggestion_count,
            )
            return {
                "enabled": True,
                "data_sufficient": False,
                "message": "数据不足，使用默认数据",
                "suggestions": suggestions,
                "style_similarity": similarity,
            }

    async def _invoke_llm(
        self,
        prompt: Any,
        variables: Dict[str, Any],
        count: int = 3,
    ) -> List[str]:
        """调用 LLM 生成建议"""
        if self.llm is None or prompt is None:
            # 没有 LLM 时的回退方案：使用模板
            return self._fallback_suggestions(variables.get("context", ""), count)

        try:
            chain = prompt | self.llm | self.parser
            result = await chain.ainvoke(variables)

            if isinstance(result, list):
                return [str(s) for s in result[:count]]
            elif isinstance(result, dict):
                # 尝试从字典中提取
                for key in ["suggestions", "replies", "messages"]:
                    if key in result and isinstance(result[key], list):
                        return [str(s) for s in result[key][:count]]
                # 字典转字符串列表
                return [str(v) for v in result.values()][:count]
            else:
                return self._fallback_suggestions(variables.get("context", ""), count)
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return self._fallback_suggestions(variables.get("context", ""), count)

    def _fallback_suggestions(self, context: str, count: int = 3) -> List[str]:
        """LLM 不可用时的回退建议"""
        default = [
            "好的，我明白了",
            "我需要再想想",
            "那就这样吧",
        ]
        return default[:count]

    async def submit_message(
        self,
        user_id: str,
        message: str,
        message_type: int,
        conversation_id: str,
    ) -> Dict[str, Any]:
        """提交聊天消息（用于风格数据采集）

        Args:
            user_id: 用户ID
            message: 消息内容
            message_type: 1=用户发送, 2=用户接收
            conversation_id: 会话ID

        Returns:
            处理结果
        """
        # 检查是否允许数据采集
        settings_data = await self.get_user_settings(user_id)
        if not settings_data["data_collection_enabled"]:
            return {
                "message_id": None,
                "processed": False,
                "chunks_count": 0,
                "message": "未授权数据采集",
            }

        # 只有用户发送的消息（message_type=1）才用于风格学习
        if message_type == 1:
            return await self.user_style_service.add_user_message(
                user_id=user_id,
                message=message,
                message_type=message_type,
                conversation_id=conversation_id,
            )
        else:
            return {
                "message_id": None,
                "processed": False,
                "chunks_count": 0,
                "message": "仅采集用户发送的消息",
            }

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        """获取聊天助手状态"""
        settings_data = await self.get_user_settings(user_id)
        count = settings_data["style_data_count"]
        threshold = settings.USER_STYLE_MIN_COUNT

        if count >= threshold * 2:
            accuracy = "high"
        elif count >= threshold:
            accuracy = "medium"
        elif count >= threshold * 0.5:
            accuracy = "low"
        else:
            accuracy = "insufficient"

        return {
            "enabled": settings_data["chat_assistant_enabled"],
            "data_collection_enabled": settings_data["data_collection_enabled"],
            "data_collected": count > 0,
            "style_data_count": count,
            "style_accuracy": accuracy,
        }

    async def upload_chat_data(
        self,
        user_id: str,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """批量上传聊天数据"""
        # 检查授权
        settings_data = await self.get_user_settings(user_id)
        if not settings_data["data_collection_enabled"]:
            return {
                "chunks_created": 0,
                "total_messages": len(messages),
                "message": "未授权数据采集",
            }

        total_chunks = 0
        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue
            message_type = msg.get("message_type", 1)
            conversation_id = msg.get("conversation_id", "default")
            result = await self.user_style_service.add_user_message(
                user_id=user_id,
                message=content,
                message_type=message_type,
                conversation_id=conversation_id,
            )
            total_chunks += result.get("chunks_count", 0)

        return {
            "chunks_created": total_chunks,
            "total_messages": len(messages),
            "message": "数据上传成功",
        }
