"""用户行为服务 - 记录和分析用户行为"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import time
from app.db.postgres_client import postgres_client
from app.db.redis_client import redis_client
from app.core.services.post_content_service import PostContentService
from app.core.services.vector_service import VectorService
from app.config.settings import settings
from app.utils.logger import logger


class UserBehaviorService:
    """用户行为服务"""

    def __init__(self):
        self.post_content_service = PostContentService()
        self.vector_service = VectorService()
        self.view_threshold = settings.BEHAVIOR_VIEW_THRESHOLD
        self.duration_threshold = settings.BEHAVIOR_DURATION_THRESHOLD

    async def record_behavior(
        self,
        user_id: str,
        post_id: str,
        behavior_type: str,
        duration: Optional[int] = None,
    ) -> Dict[str, Any]:
        """记录用户行为

        Args:
            user_id: 用户ID
            post_id: 帖子ID
            behavior_type: view / click / like / comment / share / bookmark
            duration: 浏览时长（秒，仅 view 行为有效）

        Returns:
            记录结果
        """
        try:
            record_id = await postgres_client.fetchval(
                """
                INSERT INTO user_behavior (user_id, post_id, behavior_type, duration, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                RETURNING id
                """,
                user_id,
                post_id,
                behavior_type,
                duration,
            )

            # 更新帖子的统计信息
            if behavior_type == "view":
                await postgres_client.execute(
                    "UPDATE posts SET view_count = view_count + 1 WHERE post_id = $1",
                    post_id,
                )
                # 缓存浏览行为
                await self._track_view_cache(user_id, post_id, duration or 0)
            elif behavior_type == "like":
                await postgres_client.execute(
                    "UPDATE posts SET like_count = like_count + 1 WHERE post_id = $1",
                    post_id,
                )

            # 失效用户兴趣缓存
            await redis_client.delete(f"user_interest:{user_id}")

            return {"success": True, "message": "行为已记录", "recorded_id": record_id}
        except Exception as e:
            logger.error(f"记录用户行为失败: {e}")
            return {"success": False, "message": str(e), "recorded_id": None}

    async def _track_view_cache(self, user_id: str, post_id: str, duration: int):
        """跟踪浏览缓存（用于判断是否达到阈值）"""
        try:
            key = f"view_count:{user_id}:{post_id}"
            await redis_client.incr(key, 1)
            await redis_client.expire(key, 86400 * 7)  # 7天过期

            # 累计停留时长
            duration_key = f"view_duration:{user_id}:{post_id}"
            await redis_client.incr(duration_key, duration)
            await redis_client.expire(duration_key, 86400 * 7)
        except Exception as e:
            logger.warning(f"缓存浏览记录失败: {e}")

    async def check_recommend_threshold(self, user_id: str, post_id: str) -> bool:
        """检查是否达到推荐触发阈值"""
        try:
            view_count = await redis_client.get(f"view_count:{user_id}:{post_id}")
            view_count = int(view_count) if view_count else 0

            duration = await redis_client.get(f"view_duration:{user_id}:{post_id}")
            duration = int(duration) if duration else 0

            return view_count >= self.view_threshold or duration >= self.duration_threshold
        except Exception:
            return False

    async def get_user_interest_vector(self, user_id: str) -> List[float]:
        """生成用户兴趣向量（加权平均帖子向量）"""
        # 先从缓存读取
        cached = await redis_client.get(f"user_interest:{user_id}")
        if cached:
            try:
                import json

                return json.loads(cached)
            except Exception:
                pass

        try:
            # 获取用户最近30天的行为数据
            behaviors = await postgres_client.fetch(
                """
                SELECT post_id, behavior_type, duration, created_at
                FROM user_behavior
                WHERE user_id = $1 AND created_at > NOW() - INTERVAL '30 days'
                ORDER BY created_at DESC
                LIMIT 100
                """,
                user_id,
            )

            if not behaviors:
                return []

            # 计算每个帖子的权重
            post_weights: Dict[str, float] = {}
            for behavior in behaviors:
                weight = 0
                behavior_type = behavior["behavior_type"]
                if behavior_type == "view":
                    # 浏览时长权重：最多10分
                    duration = behavior["duration"] or 0
                    weight = min(duration / 60, 10)
                elif behavior_type == "click":
                    weight = 5
                elif behavior_type == "like":
                    weight = 15
                elif behavior_type == "comment":
                    weight = 20
                elif behavior_type == "share":
                    weight = 25
                elif behavior_type == "bookmark":
                    weight = 18

                # 时间衰减：越新的行为权重越高
                created_at = behavior["created_at"]
                if isinstance(created_at, datetime):
                    days_ago = (datetime.now() - created_at).days
                else:
                    days_ago = 0
                time_decay = 1 / (1 + days_ago * 0.1)
                weight *= time_decay

                post_id = behavior["post_id"]
                post_weights[post_id] = post_weights.get(post_id, 0) + weight

            # 获取权重最高的10个帖子
            top_posts = sorted(post_weights.items(), key=lambda x: x[1], reverse=True)[:10]
            if not top_posts:
                return []

            # 生成用户兴趣向量：通过对帖子向量加权平均
            # 注：实际生产中应获取帖子向量数据，这里采用简化策略
            # 通过对帖子内容文本的嵌入向量加权平均
            interest_vector = None
            total_weight = 0.0

            for pid, weight in top_posts:
                # 获取帖子信息
                post_info = await self.post_content_service.get_posts_by_ids([pid])
                if not post_info:
                    continue
                title = post_info[0].get("title", "")
                content = post_info[0].get("content", "")
                text = f"{title} {content[:200]}"

                post_vector = await self.vector_service.embed_query(text)
                if not post_vector:
                    continue

                if interest_vector is None:
                    interest_vector = [x * weight for x in post_vector]
                else:
                    # 确保维度一致
                    min_dim = min(len(interest_vector), len(post_vector))
                    interest_vector = [
                        interest_vector[i] + post_vector[i] * weight
                        for i in range(min_dim)
                    ]
                total_weight += weight

            if total_weight == 0 or interest_vector is None:
                return []

            # 归一化
            interest_vector = [x / total_weight for x in interest_vector]

            # 缓存
            try:
                import json

                await redis_client.set(
                    f"user_interest:{user_id}",
                    json.dumps(interest_vector),
                    ex=settings.CACHE_TTL_INTEREST_VECTOR,
                )
            except Exception:
                pass

            return interest_vector
        except Exception as e:
            logger.error(f"生成用户兴趣向量失败: {e}")
            return []

    async def get_user_interest_topics(
        self, user_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取用户兴趣主题列表（从行为数据中提取）"""
        try:
            records = await postgres_client.fetch(
                """
                SELECT p.category, p.tags, ub.behavior_type, ub.duration, ub.created_at
                FROM user_behavior ub
                JOIN posts p ON ub.post_id = p.post_id
                WHERE ub.user_id = $1 AND ub.created_at > NOW() - INTERVAL '30 days'
                ORDER BY ub.created_at DESC
                LIMIT 200
                """,
                user_id,
            )

            topic_weights: Dict[str, float] = {}
            for r in records:
                weight = 0
                bt = r["behavior_type"]
                if bt == "view":
                    weight = min((r["duration"] or 0) / 60, 10)
                elif bt == "click":
                    weight = 5
                elif bt == "like":
                    weight = 15
                elif bt == "comment":
                    weight = 20
                elif bt == "share":
                    weight = 25
                else:
                    weight = 8

                category = r["category"] or ""
                if category:
                    topic_weights[category] = topic_weights.get(category, 0) + weight

                tags = (r["tags"] or "").split(",")
                for tag in tags:
                    tag = tag.strip()
                    if tag:
                        topic_weights[tag] = topic_weights.get(tag, 0) + weight * 0.5

            # 归一化
            total = sum(topic_weights.values()) or 1
            topics = [
                {"topic": t, "weight": w / total}
                for t, w in sorted(topic_weights.items(), key=lambda x: x[1], reverse=True)
            ]
            return topics[:limit]
        except Exception as e:
            logger.error(f"获取用户兴趣主题失败: {e}")
            return []

    async def get_viewed_posts(self, user_id: str) -> set:
        """获取用户已浏览过的帖子ID集合"""
        try:
            records = await postgres_client.fetch(
                """
                SELECT DISTINCT post_id FROM user_behavior
                WHERE user_id = $1 AND behavior_type = 'view'
                """,
                user_id,
            )
            return {r["post_id"] for r in records}
        except Exception as e:
            logger.error(f"获取已浏览帖子失败: {e}")
            return set()

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """获取用户画像"""
        try:
            # 行为总数
            total_behaviors = await postgres_client.fetchval(
                "SELECT COUNT(*) FROM user_behavior WHERE user_id = $1",
                user_id,
            ) or 0

            # 兴趣主题
            interests = await self.get_user_interest_topics(user_id)

            # 活跃度
            if total_behaviors > 100:
                activity_level = "high"
            elif total_behaviors > 30:
                activity_level = "medium"
            else:
                activity_level = "low"

            # 互动分数
            engagement_score = min(total_behaviors / 200, 1.0)

            # 兴趣向量是否准备好
            interest_vector = await self.get_user_interest_vector(user_id)

            return {
                "user_id": user_id,
                "interests": interests,
                "activity_level": activity_level,
                "engagement_score": engagement_score,
                "total_behaviors": total_behaviors,
                "interest_vector_ready": len(interest_vector) > 0,
                "last_updated": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"获取用户画像失败: {e}")
            return {
                "user_id": user_id,
                "interests": [],
                "activity_level": "low",
                "engagement_score": 0.0,
                "total_behaviors": 0,
                "interest_vector_ready": False,
            }

    async def should_recommend(self, user_id: str) -> bool:
        """判断是否应该为该用户生成推荐"""
        try:
            # 检查累计浏览数
            total_views = await postgres_client.fetchval(
                """
                SELECT COUNT(*) FROM user_behavior
                WHERE user_id = $1 AND behavior_type = 'view'
                """,
                user_id,
            ) or 0
            return total_views >= self.view_threshold
        except Exception:
            return False
