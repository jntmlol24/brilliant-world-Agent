"""帖子相关 Pydantic 模型"""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class PostCreateRequest(BaseModel):
    """创建帖子请求"""
    post_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    category: Optional[str] = Field(default=None, max_length=64)
    tags: List[str] = Field(default_factory=list)
    author_id: Optional[str] = Field(default=None, max_length=64)


class PostCreateResponse(BaseModel):
    """创建帖子响应"""
    post_id: str
    chunks_processed: int
    success: bool
    message: Optional[str] = None


class PostBatchCreateRequest(BaseModel):
    """批量创建帖子请求"""
    posts: List[PostCreateRequest]


class PostBatchCreateResponse(BaseModel):
    """批量创建帖子响应"""
    total: int
    success: int
    failed: int
    failed_ids: List[str] = Field(default_factory=list)


class PostInfo(BaseModel):
    """帖子信息"""
    post_id: str
    title: str
    content: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    author_id: Optional[str] = None
    view_count: int = 0
    like_count: int = 0
    created_at: Optional[datetime] = None


class PostSearchRequest(BaseModel):
    """帖子搜索请求"""
    user_id: Optional[str] = None
    query: str = Field(..., min_length=1, max_length=500)
    search_mode: str = Field(default="precise", description="precise:精确, divergent:发散")
    limit: int = Field(default=20, ge=1, le=100)
    filters: Optional[dict] = None


class PostSearchResultItem(BaseModel):
    """搜索结果项"""
    post_id: str
    title: str
    snippet: str
    similarity_score: float
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class PostSearchResponse(BaseModel):
    """搜索响应"""
    query: str
    search_mode: str
    total_found: int
    results: List[PostSearchResultItem] = []
    summary: Optional[str] = None
    suggestion: Optional[str] = None


class PostRecommendationItem(BaseModel):
    """推荐项"""
    post_id: str
    title: str
    snippet: Optional[str] = None
    thumbnail: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    score: float
    similarity: Optional[float] = None
    reason: Optional[str] = None


class PostRecommendationResponse(BaseModel):
    """推荐响应"""
    recommendation_type: str  # personalized / hot / new
    posts: List[PostRecommendationItem] = []
    refresh_timestamp: Optional[str] = None


class SearchSuggestionItem(BaseModel):
    """搜索建议项"""
    name: str
    relevance: float


class SearchSuggestionsResponse(BaseModel):
    """搜索建议响应"""
    suggested_topics: List[SearchSuggestionItem] = []
    hot_keywords: List[str] = []
