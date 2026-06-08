"""帖子推荐 Agent"""
from typing import Dict, Any, List, Optional
import time

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

from app.config.settings import settings
from app.core.services.post_content_service import PostContentService
from app.core.services.user_behavior_service import UserBehaviorService
from app.db.redis_client import redis_client
from app.utils.logger import logger


class PostRecommendAgent:
    """帖子推荐 Agent

    1. 个性化推荐：基于用户兴趣向量
    2. 智能搜索：支持精确/发散两种模式
    """

    def __init__(self):
        self.post_content_service = PostContentService()
        self.user_behavior_service = UserBehaviorService()

        # 初始化 LLM
        self.llm = None
        self.recommend_prompt = None
        self.search_summary_prompt = None
        self.parser = None

        if LANGCHAIN_AVAILABLE and (settings.OPENAI_API_KEY or settings.QWEN_API_KEY):
            try:
                if settings.OPENAI_API_KEY:
                    self.llm = ChatOpenAI(
                        model=settings.LLM_MODEL,
                        temperature=0.3,
                        openai_api_key=settings.OPENAI_API_KEY,
                        openai_api_base=settings.OPENAI_BASE_URL,
                    )
                else:
                    from langchain_community.chat_models import ChatTongyi
                    self.llm = ChatTongyi(
                        model_name=settings.QWEN_MODEL,
                        temperature=0.3,
                        dashscope_api_key=settings.QWEN_API_KEY,
                    )
                self.parser = JsonOutputParser()
                self._init_prompts()
            except Exception as e:
                logger.error(f"推荐 Agent LLM 初始化失败: {e}")
                self.llm = None

    def _init_prompts(self):
        """初始化提示词"""
        self.recommend_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个帖子推荐助手，根据用户的兴趣和搜索查询，为每个帖子生成个性化推荐理由。\n"
                    "推荐理由应该：\n"
                    "1. 简洁有吸引力（20字以内）\n"
                    "2. 突出帖子的核心价值\n"
                    "3. 与用户兴趣相关\n"
                    "4. 输出格式为严格的JSON对象，键是帖子ID，值是推荐理由字符串",
                ),
                (
                    "human",
                    "用户兴趣：{user_interests}\n搜索查询：{query}\n帖子列表：\n{posts}\n\n推荐理由：",
                ),
            ]
        )

        self.search_summary_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个搜索助手，根据用户的搜索查询和返回的帖子，生成一个简短的搜索结果说明。\n"
                    "说明应该：\n"
                    "1. 总结搜索结果的主要内容\n"
                    "2. 帮助用户快速了解搜索结果\n"
                    "3. 不超过80字",
                ),
                (
                    "human",
                    "搜索查询：{query}\n搜索结果：\n{posts}\n\n结果说明：",
                ),
            ]
        )

    async def get_recommendations(
        self,
        user_id: str,
        limit: int = 10,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """获取个性化推荐帖子

        Args:
            user_id: 用户ID
            limit: 返回数量
            use_cache: 是否使用缓存

        Returns:
            推荐结果
        """
        cache_key = f"recommendation:{user_id}:{limit}"
        if use_cache:
            cached = await redis_client.get_json(cache_key)
            if cached:
                return cached

        # 判断是否需要个性化推荐
        should_recommend = await self.user_behavior_service.should_recommend(user_id)
        if not should_recommend:
            # 新用户：返回热门帖子
            result = await self._get_hot_recommendations(limit)
        else:
            # 老用户：基于兴趣向量推荐
            result = await self._get_personalized_recommendations(user_id, limit)

        # 缓存结果
        await redis_client.set_json(
            cache_key, result, ex=settings.CACHE_TTL_RECOMMENDATION
        )
        return result

    async def _get_personalized_recommendations(
        self, user_id: str, limit: int
    ) -> Dict[str, Any]:
        """基于兴趣向量的个性化推荐"""
        interest_vector = await self.user_behavior_service.get_user_interest_vector(user_id)
        if not interest_vector:
            return await self._get_hot_recommendations(limit)

        # 获取用户已浏览的帖子
        viewed_posts = await self.user_behavior_service.get_viewed_posts(user_id)

        # 检索相似帖子
        from app.db.milvus_client import milvus_client

        from app.config.model_config import model_config
        config = model_config.post_contents_collection

        results = await milvus_client.search(
            collection_name=config.name,
            query_vector=interest_vector,
            limit=limit * 3,
            output_fields=["post_id", "content_text", "category", "tags", "title"],
            search_params=config.search_params,
        )

        # 去重并过滤
        recommended_posts = []
        seen_post_ids = set()
        for res in results:
            post_id = res.get("post_id")
            if not post_id or post_id in seen_post_ids:
                continue
            if post_id in viewed_posts:
                continue
            seen_post_ids.add(post_id)
            recommended_posts.append(
                {
                    "post_id": post_id,
                    "title": res.get("title", ""),
                    "snippet": res.get("content_text", "")[:200],
                    "similarity": res.get("score", 0),
                    "category": res.get("category", ""),
                    "tags": res.get("tags", "").split(",") if res.get("tags") else [],
                    "score": res.get("score", 0),
                }
            )
            if len(recommended_posts) >= limit:
                break

        # 获取帖子完整信息
        if recommended_posts:
            post_ids = [p["post_id"] for p in recommended_posts]
            post_infos = await self.post_content_service.get_posts_by_ids(post_ids)
            info_map = {p["post_id"]: p for p in post_infos}
            for p in recommended_posts:
                info = info_map.get(p["post_id"], {})
                p["title"] = info.get("title", p.get("title", ""))
                p["category"] = info.get("category", p.get("category", ""))
                p["tags"] = info.get("tags", p.get("tags", []))

        # 生成推荐理由
        await self._generate_recommendation_reasons(user_id, recommended_posts)

        return {
            "recommendation_type": "personalized",
            "posts": recommended_posts,
            "refresh_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    async def _get_hot_recommendations(self, limit: int) -> Dict[str, Any]:
        """获取热门帖子推荐"""
        hot_posts = await self.post_content_service.get_hot_posts(limit)
        posts = [
            {
                "post_id": p["post_id"],
                "title": p.get("title", ""),
                "snippet": (p.get("content", "") or "")[:200],
                "category": p.get("category", ""),
                "tags": p.get("tags", []),
                "score": 0.5,
                "reason": "热门帖子",
            }
            for p in hot_posts
        ]
        return {
            "recommendation_type": "hot",
            "posts": posts,
            "refresh_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    async def _generate_recommendation_reasons(
        self, user_id: str, posts: List[Dict[str, Any]]
    ):
        """为推荐帖子生成推荐理由"""
        if not posts or self.llm is None:
            for p in posts:
                p["reason"] = "根据你的兴趣推荐"
            return

        try:
            # 获取用户兴趣主题
            interests = await self.user_behavior_service.get_user_interest_topics(
                user_id, limit=3
            )
            interest_text = (
                ", ".join([f"{i['topic']}(权重{i['weight']:.2f})" for i in interests])
                or "未分析出明确兴趣"
            )

            posts_info = "\n".join(
                [
                    f"帖子ID: {p['post_id']}, 标题: {p.get('title','')[:50]}, 分类: {p.get('category','')}, 标签: {','.join(p.get('tags', []))}"
                    for p in posts[:10]
                ]
            )

            chain = self.recommend_prompt | self.llm | self.parser
            reasons = await chain.ainvoke(
                {
                    "user_interests": interest_text,
                    "query": "",
                    "posts": posts_info,
                }
            )

            if isinstance(reasons, dict):
                for p in posts:
                    pid = p["post_id"]
                    p["reason"] = reasons.get(
                        pid, reasons.get(str(pid), "根据你的兴趣推荐")
                    )
            else:
                for p in posts:
                    p["reason"] = "根据你的兴趣推荐"
        except Exception as e:
            logger.error(f"生成推荐理由失败: {e}")
            for p in posts:
                p["reason"] = "根据你的兴趣推荐"

    async def search_with_agent(
        self,
        user_id: Optional[str],
        query: str,
        search_mode: str = "precise",
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Agent 智能搜索

        Args:
            user_id: 用户ID（可选，用于个性化）
            query: 搜索关键词
            search_mode: precise/divergent
            limit: 返回数量
            filters: 过滤条件

        Returns:
            搜索结果
        """
        # 1. 基础搜索
        results = await self.post_content_service.search_posts_with_details(
            query=query,
            search_mode=search_mode,
            limit=limit,
            filters=filters,
        )

        if not results:
            return {
                "query": query,
                "search_mode": search_mode,
                "total_found": 0,
                "results": [],
                "summary": "未找到相关帖子",
                "suggestion": "没有找到相关帖子，试试其他关键词或切换为发散搜索",
            }

        # 2. 生成搜索结果说明
        summary = await self._generate_search_summary(query, results)

        return {
            "query": query,
            "search_mode": search_mode,
            "total_found": len(results),
            "results": results,
            "summary": summary,
        }

    async def _generate_search_summary(
        self, query: str, results: List[Dict[str, Any]]
    ) -> str:
        """生成搜索结果说明"""
        if self.llm is None or not results:
            return f"找到 {len(results)} 篇相关帖子"

        try:
            posts_info = "\n".join(
                [
                    f"标题: {r.get('title','')[:50]}, 分类: {r.get('category','')}, 摘要: {r.get('snippet','')[:100]}"
                    for r in results[:5]
                ]
            )

            chain = self.search_summary_prompt | self.llm
            response = await chain.ainvoke({"query": query, "posts": posts_info})
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"生成搜索说明失败: {e}")
            return f"找到 {len(results)} 篇相关帖子"

    async def get_search_suggestions(self, user_id: str) -> Dict[str, Any]:
        """获取搜索建议（主页/搜索页推送用）"""
        try:
            # 获取用户兴趣主题
            interests = await self.user_behavior_service.get_user_interest_topics(
                user_id, limit=8
            )
            suggested_topics = [
                {"name": i["topic"], "relevance": i["weight"]} for i in interests
            ]

            # 热门关键词（取热门帖子分类作为参考）
            hot_posts = await self.post_content_service.get_hot_posts(limit=20)
            categories_count: Dict[str, int] = {}
            for p in hot_posts:
                cat = p.get("category", "")
                if cat:
                    categories_count[cat] = categories_count.get(cat, 0) + 1
            hot_keywords = [
                cat for cat, _ in sorted(categories_count.items(), key=lambda x: x[1], reverse=True)[:10]
            ]

            return {
                "suggested_topics": suggested_topics,
                "hot_keywords": hot_keywords,
            }
        except Exception as e:
            logger.error(f"获取搜索建议失败: {e}")
            return {"suggested_topics": [], "hot_keywords": []}

    async def refresh_recommendation_cache(self, user_id: str):
        """刷新推荐缓存"""
        keys = await redis_client.keys(f"recommendation:{user_id}:*")
        for key in keys:
            await redis_client.delete(key)
