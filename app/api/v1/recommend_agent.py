"""帖子推荐引擎 API"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.agents.post_recommend_agent import PostRecommendAgent
from app.core.services.post_content_service import PostContentService
from app.core.services.user_behavior_service import UserBehaviorService
from app.core.schemas.post import (
    PostCreateRequest,
    PostCreateResponse,
    PostBatchCreateRequest,
    PostBatchCreateResponse,
    PostSearchRequest,
    PostSearchResponse,
    PostSearchResultItem,
    PostRecommendationResponse,
    PostRecommendationItem,
    SearchSuggestionsResponse,
)
from app.core.schemas.user import (
    BehaviorTrackViewRequest,
    BehaviorTrackInteractionRequest,
    BehaviorTrackResponse,
    UserProfileResponse,
    UserInterestItem,
)
from app.api.deps import get_recommend_agent
from app.utils.logger import logger

router = APIRouter(prefix="", tags=["帖子推荐"])


# ============ 帖子管理接口 ============
@router.post("/posts", response_model=PostCreateResponse, summary="添加帖子")
async def create_post(
    request: PostCreateRequest,
):
    """添加帖子到内容库（自动分片向量化）"""
    try:
        service = PostContentService()
        await service.init_collection()
        result = await service.add_post(
            post_id=request.post_id,
            title=request.title,
            content=request.content,
            category=request.category,
            tags=request.tags,
            author_id=request.author_id,
        )
        return PostCreateResponse(
            post_id=result["post_id"],
            chunks_processed=result["chunks_processed"],
            success=result["success"],
        )
    except Exception as e:
        logger.error(f"添加帖子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/posts/batch", response_model=PostBatchCreateResponse, summary="批量添加帖子")
async def batch_create_posts(
    request: PostBatchCreateRequest,
):
    """批量添加帖子"""
    try:
        service = PostContentService()
        await service.init_collection()
        posts_data = [p.dict() for p in request.posts]
        result = await service.batch_add_posts(posts_data)
        return PostBatchCreateResponse(
            total=result["total"],
            success=result["success"],
            failed=result["failed"],
            failed_ids=result["failed_ids"],
        )
    except Exception as e:
        logger.error(f"批量添加帖子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/posts/{post_id}", summary="删除帖子")
async def delete_post(post_id: str):
    """删除指定帖子"""
    try:
        service = PostContentService()
        count = await service.delete_post(post_id)
        return {"success": True, "deleted_chunks": count}
    except Exception as e:
        logger.error(f"删除帖子失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ 搜索接口 ============
@router.post("/search", response_model=PostSearchResponse, summary="智能搜索帖子")
async def search_posts(
    request: PostSearchRequest,
    agent: PostRecommendAgent = Depends(get_recommend_agent),
):
    """Agent 智能搜索，支持精确/发散两种模式"""
    try:
        if request.search_mode not in ("precise", "divergent"):
            raise HTTPException(
                status_code=400,
                detail="search_mode 必须为 precise 或 divergent",
            )

        result = await agent.search_with_agent(
            user_id=request.user_id,
            query=request.query,
            search_mode=request.search_mode,
            limit=request.limit,
            filters=request.filters,
        )

        return PostSearchResponse(
            query=result["query"],
            search_mode=result["search_mode"],
            total_found=result["total_found"],
            results=[PostSearchResultItem(**r) for r in result.get("results", [])],
            summary=result.get("summary"),
            suggestion=result.get("suggestion"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ 推荐接口 ============
@router.get(
    "/recommendations",
    response_model=PostRecommendationResponse,
    summary="获取首页推荐",
)
async def get_recommendations(
    user_id: str = Query(..., description="用户ID"),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
    refresh: bool = Query(False, description="是否强制刷新"),
    agent: PostRecommendAgent = Depends(get_recommend_agent),
):
    """获取首页/搜索页个性化推荐"""
    try:
        if refresh:
            await agent.refresh_recommendation_cache(user_id)
        result = await agent.get_recommendations(
            user_id=user_id,
            limit=limit,
            use_cache=not refresh,
        )
        return PostRecommendationResponse(
            recommendation_type=result.get("recommendation_type", "hot"),
            posts=[PostRecommendationItem(**p) for p in result.get("posts", [])],
            refresh_timestamp=result.get("refresh_timestamp"),
        )
    except Exception as e:
        logger.error(f"获取推荐失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/search-suggestions/{user_id}",
    response_model=SearchSuggestionsResponse,
    summary="获取搜索建议",
)
async def get_search_suggestions(
    user_id: str,
    agent: PostRecommendAgent = Depends(get_recommend_agent),
):
    """获取主页/搜索页推送的兴趣主题与热门关键词"""
    try:
        result = await agent.get_search_suggestions(user_id)
        return SearchSuggestionsResponse(**result)
    except Exception as e:
        logger.error(f"获取搜索建议失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ 用户行为接口 ============
@router.post(
    "/behavior/view",
    response_model=BehaviorTrackResponse,
    summary="上报浏览行为",
)
async def track_view(request: BehaviorTrackViewRequest):
    """上报帖子浏览行为（包含停留时长）"""
    try:
        service = UserBehaviorService()
        result = await service.record_behavior(
            user_id=request.user_id,
            post_id=request.post_id,
            behavior_type="view",
            duration=request.dwell_time_seconds,
        )
        return BehaviorTrackResponse(**result)
    except Exception as e:
        logger.error(f"上报浏览行为失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/behavior/interaction",
    response_model=BehaviorTrackResponse,
    summary="上报交互行为",
)
async def track_interaction(request: BehaviorTrackInteractionRequest):
    """上报点赞/评论/分享/收藏等交互行为"""
    try:
        if request.interaction_type not in ("like", "comment", "share", "bookmark"):
            raise HTTPException(
                status_code=400,
                detail="interaction_type 必须为 like/comment/share/bookmark",
            )
        service = UserBehaviorService()
        result = await service.record_behavior(
            user_id=request.user_id,
            post_id=request.post_id,
            behavior_type=request.interaction_type,
        )
        return BehaviorTrackResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上报交互行为失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/behavior/profile/{user_id}",
    response_model=UserProfileResponse,
    summary="获取用户画像",
)
async def get_user_profile(user_id: str):
    """获取用户兴趣画像"""
    try:
        service = UserBehaviorService()
        profile = await service.get_user_profile(user_id)
        return UserProfileResponse(
            user_id=profile["user_id"],
            interests=[UserInterestItem(**i) for i in profile.get("interests", [])],
            activity_level=profile.get("activity_level", "low"),
            engagement_score=profile.get("engagement_score", 0.0),
            total_behaviors=profile.get("total_behaviors", 0),
            interest_vector_ready=profile.get("interest_vector_ready", False),
            last_updated=profile.get("last_updated"),
        )
    except Exception as e:
        logger.error(f"获取用户画像失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
