"""聊天相关 Pydantic 模型"""
from typing import List, Optional
from pydantic import BaseModel, Field


# 聊天设置
class ChatSettingsRequest(BaseModel):
    """聊天设置请求"""
    user_id: str = Field(..., description="用户ID", min_length=1, max_length=64)
    chat_assistant_enabled: bool = Field(default=False, description="是否开启聊天助手")
    data_collection_enabled: bool = Field(default=False, description="是否允许数据采集")


class ChatSettingsResponse(BaseModel):
    """聊天设置响应"""
    user_id: str
    chat_assistant_enabled: bool
    data_collection_enabled: bool
    style_data_count: int
    last_updated: Optional[str] = None


# 聊天消息
class ChatMessageRequest(BaseModel):
    """聊天消息请求"""
    user_id: str = Field(..., min_length=1, max_length=64)
    conversation_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=4000)
    message_type: int = Field(default=1, description="1:用户发送, 2:用户接收")


class ChatMessageResponse(BaseModel):
    """聊天消息响应"""
    message_id: str
    processed: bool
    chunks_count: int = 0


# 聊天建议
class ChatSuggestionRequest(BaseModel):
    """聊天建议请求"""
    user_id: str = Field(..., min_length=1, max_length=64)
    context: str = Field(..., min_length=1, max_length=4000, description="对话上下文")
    suggestion_count: int = Field(default=3, ge=1, le=10)


class ChatSuggestionItem(BaseModel):
    """单条聊天建议"""
    text: str
    type: Optional[str] = None
    confidence: Optional[float] = None


class ChatSuggestionResponse(BaseModel):
    """聊天建议响应"""
    enabled: bool
    data_sufficient: bool
    message: Optional[str] = None
    suggestions: List[str] = []


# 聊天授权
class ChatAuthorizeRequest(BaseModel):
    """聊天助手授权请求"""
    user_id: str
    authorize: bool
    data_types: List[str] = Field(default_factory=lambda: ["chat_history", "writing_style"])


class ChatAuthorizeResponse(BaseModel):
    """聊天助手授权响应"""
    user_id: str
    chat_assistant_enabled: bool
    data_collection_enabled: bool


# 上传聊天数据
class ChatDataUploadRequest(BaseModel):
    """聊天数据上传请求"""
    user_id: str
    messages: List[dict] = Field(..., description="消息列表，每条包含 content 和 timestamp")


class ChatDataUploadResponse(BaseModel):
    """聊天数据上传响应"""
    chunks_created: int
    total_messages: int


# 状态查询
class ChatAssistantStatus(BaseModel):
    """聊天助手状态"""
    enabled: bool
    data_collection_enabled: bool
    data_collected: bool
    style_data_count: int
    style_accuracy: str  # high / medium / low / insufficient
