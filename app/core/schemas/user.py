"""用户行为相关 Pydantic 模型"""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class BehaviorTrackViewRequest(BaseModel):
    """追踪浏览请求"""
    user_id: str = Field(..., min_length=1, max_length=64)
    post_id: str = Field(..., min_length=1, max_length=64)
    dwell_time_seconds: int = Field(default=0, ge=0, description="停留时长（秒）")
    scroll_depth: float = Field(default=0.0, ge=0.0, le=1.0, description="滚动深度")
    timestamp: Optional[datetime] = None


class BehaviorTrackInteractionRequest(BaseModel):
    """追踪交互请求"""
    user_id: str = Field(..., min_length=1, max_length=64)
    post_id: str = Field(..., min_length=1, max_length=64)
    interaction_type: str = Field(..., description="like / comment / share / bookmark")
    timestamp: Optional[datetime] = None


class BehaviorTrackResponse(BaseModel):
    """行为追踪响应"""
    success: bool
    message: str
    recorded_id: Optional[int] = None


class UserInterestItem(BaseModel):
    """用户兴趣项"""
    topic: str
    weight: float


class UserProfileResponse(BaseModel):
    """用户画像响应"""
    user_id: str
    interests: List[UserInterestItem] = []
    activity_level: str  # high / medium / low
    engagement_score: float
    total_behaviors: int
    interest_vector_ready: bool
    last_updated: Optional[datetime] = None


# 通用响应
class APIResponse(BaseModel):
    """统一 API 响应"""
    code: int = 200
    message: str = "success"
    data: Optional[dict] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    code: int
    message: str
    detail: Optional[str] = None
