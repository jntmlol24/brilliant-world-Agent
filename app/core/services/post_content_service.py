"""帖子内容服务 - 帖子内容向量化、存储、检索"""
from typing import List, Dict, Any, Optional
import time
from app.db.milvus_client import milvus_client
from app.db.postgres_client import postgres_client
from app.core.services.vector_service import VectorService
from app.utils.text_splitter import split_post_content
from app.config.settings import settings
from app.config.model_config import model_config
from app.utils.logger import logger


class PostContentService:
    """帖子内容服务"""

    def __init__(self):
        self.vector_service = VectorService()
        self.collection_name = model_config.post_contents_collection.name
        self.precise_threshold = settings.PRECISE_SEARCH_SIMILARITY
        self.divergent_threshold = settings.DIVERGENT_SEARCH_SIMILARITY

    async def init_collection(self):
        """初始化集合"""
        milvus_client.create_collection(self.collection_name)

    async def add_post(
        self,
        post_id: str,
        title: str,
        content: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        author_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """添加帖子到内容库

        Args:
            post_id: 帖子ID
            title: 标题
            content: 内容
            category: 分类
            tags: 标签列表
            author_id: 作者ID

        Returns:
            处理结果
        """
        tags = tags or []
        # 文本分片
        chunks = split_post_content(title, content)
        if not chunks:
            return {"post_id": post_id, "chunks_processed": 0, "success": False}

        # 向量化
        vectors = await self.vector_service.embed_texts(chunks)

        # 批量插入 Milvus
        timestamp = int(time.time() * 1000)
        data_list = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            data_list.append(
                {
                    "post_id": post_id,
                    "chunk_id": i,
                    "content_vector": vector,
                    "content_text": chunk[:2000],
                    "category": category or "",
                    "tags": ",".join(tags)[:500],
                    "title": title[:200],
                    "created_at": timestamp,
                }
            )

        await milvus_client.insert(
            collection_name=self.collection_name,
            data=data_list,
        )

        # 保存到 PostgreSQL
        try:
            await postgres_client.execute(
                """
                INSERT INTO posts (post_id, title, content, category, tags, author_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
                ON CONFLICT (post_id) DO UPDATE
                SET title = $2, content = $3, category = $4, tags = $5, updated_at = NOW()
                """,
                post_id,
                title,
                content,
                category or "",
                ",".join(tags),
                author_id or "",
            )
        except Exception as e:
            logger.warning(f"保存帖子元数据失败: {e}")

        logger.info(f"帖子 {post_id} 添加成功，分片数: {len(chunks)}")
        return {
            "post_id": post_id,
            "chunks_processed": len(chunks),
            "success": True,
        }

    async def batch_add_posts(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量添加帖子"""
        total = len(posts)
        success = 0
        failed_ids = []

        for post in posts:
            try:
                result = await self.add_post(
                    post_id=post.get("post_id"),
                    title=post.get("title", ""),
                    content=post.get("content", ""),
                    category=post.get("category"),
                    tags=post.get("tags", []),
                    author_id=post.get("author_id"),
                )
                if result.get("success"):
                    success += 1
                else:
                    failed_ids.append(post.get("post_id"))
            except Exception as e:
                logger.error(f"批量添加帖子失败 {post.get('post_id')}: {e}")
                failed_ids.append(post.get("post_id"))

        return {
            "total": total,
            "success": success,
            "failed": total - success,
            "failed_ids": failed_ids,
        }

    async def search_posts(
        self,
        query: str,
        search_mode: str = "precise",
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """搜索帖子

        Args:
            query: 搜索关键词
            search_mode: precise/divergent
            limit: 返回数量
            filters: 过滤条件

        Returns:
            帖子ID列表
        """
        # 构建过滤表达式
        filter_parts = []
        if filters:
            if "category" in filters and filters["category"]:
                filter_parts.append(f'category == "{filters["category"]}"')

        filter_expr = " && ".join(filter_parts) if filter_parts else None

        # 选择阈值和参数
        if search_mode == "precise":
            threshold = self.precise_threshold
            search_limit = limit
        else:
            threshold = self.divergent_threshold
            search_limit = limit * 2  # 发散搜索获取更多结果

        # 向量检索
        results = await self.vector_service.search_similar(
            collection_name=self.collection_name,
            query_text=query,
            filter_expr=filter_expr,
            limit=search_limit,
            output_fields=["post_id", "content_text", "category", "tags", "title"],
            threshold=threshold,
        )

        # 去重并返回帖子ID列表
        post_ids = []
        seen = set()
        for r in results:
            pid = r.get("post_id")
            if pid and pid not in seen:
                seen.add(pid)
                post_ids.append(pid)
                if len(post_ids) >= limit:
                    break
        return post_ids

    async def search_posts_with_details(
        self,
        query: str,
        search_mode: str = "precise",
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """搜索帖子并返回详细信息"""
        # 构建过滤表达式
        filter_parts = []
        if filters:
            if "category" in filters and filters["category"]:
                filter_parts.append(f'category == "{filters["category"]}"')

        filter_expr = " && ".join(filter_parts) if filter_parts else None

        if search_mode == "precise":
            threshold = self.precise_threshold
            search_limit = limit
        else:
            threshold = self.divergent_threshold
            search_limit = limit * 2

        results = await self.vector_service.search_similar(
            collection_name=self.collection_name,
            query_text=query,
            filter_expr=filter_expr,
            limit=search_limit,
            output_fields=["post_id", "content_text", "category", "tags", "title"],
            threshold=threshold,
        )

        # 去重
        seen = set()
        unique_results = []
        for r in results:
            pid = r.get("post_id")
            if pid and pid not in seen:
                seen.add(pid)
                unique_results.append(
                    {
                        "post_id": pid,
                        "title": r.get("title", ""),
                        "snippet": r.get("content_text", "")[:200],
                        "similarity_score": r.get("score", 0),
                        "category": r.get("category", ""),
                        "tags": r.get("tags", "").split(",") if r.get("tags") else [],
                    }
                )
                if len(unique_results) >= limit:
                    break
        return unique_results

    async def get_post_vectors(self, post_id: str) -> List[List[float]]:
        """获取帖子的所有分片向量"""
        try:
            # 使用一个空查询获取该 post_id 的所有分片
            query_vector = await self.vector_service.embed_query(" ")
            results = await milvus_client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                filter_expr=f'post_id == "{post_id}"',
                limit=100,
                output_fields=["post_id"],
            )
            return [r.get("score", 0) for r in results]  # 实际应返回向量，这里返回score仅占位
        except Exception as e:
            logger.error(f"获取帖子向量失败: {e}")
            return []

    async def get_posts_by_ids(self, post_ids: List[str]) -> List[Dict[str, Any]]:
        """根据ID列表获取帖子信息"""
        if not post_ids:
            return []

        try:
            # 从 PostgreSQL 获取
            query = """
                SELECT post_id, title, content, category, tags, author_id, view_count, like_count, created_at
                FROM posts
                WHERE post_id = ANY($1)
            """
            records = await postgres_client.fetch(query, post_ids)

            result_map = {}
            for r in records:
                pid = r["post_id"]
                tags = r["tags"].split(",") if r["tags"] else []
                result_map[pid] = {
                    "post_id": pid,
                    "title": r["title"],
                    "content": r["content"],
                    "category": r["category"],
                    "tags": tags,
                    "author_id": r["author_id"],
                    "view_count": r["view_count"],
                    "like_count": r["like_count"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }

            # 保持输入顺序
            return [result_map.get(pid, {"post_id": pid}) for pid in post_ids if pid in result_map]
        except Exception as e:
            logger.error(f"获取帖子信息失败: {e}")
            return [{"post_id": pid} for pid in post_ids]

    async def get_hot_posts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取热门帖子"""
        try:
            records = await postgres_client.fetch(
                """
                SELECT post_id, title, content, category, tags, view_count, like_count, created_at
                FROM posts
                ORDER BY (view_count + like_count * 5) DESC, created_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [
                {
                    "post_id": r["post_id"],
                    "title": r["title"],
                    "content": r["content"],
                    "category": r["category"],
                    "tags": r["tags"].split(",") if r["tags"] else [],
                    "view_count": r["view_count"],
                    "like_count": r["like_count"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in records
            ]
        except Exception as e:
            logger.error(f"获取热门帖子失败: {e}")
            return []

    async def delete_post(self, post_id: str) -> int:
        """删除帖子"""
        try:
            count = await milvus_client.delete(
                collection_name=self.collection_name,
                filter_expr=f'post_id == "{post_id}"',
            )
            await postgres_client.execute(
                "DELETE FROM posts WHERE post_id = $1",
                post_id,
            )
            return count
        except Exception as e:
            logger.error(f"删除帖子失败: {e}")
            return 0
