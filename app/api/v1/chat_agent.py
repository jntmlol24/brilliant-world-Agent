"""聊天助手 API"""
from fastapi import APIRouter, Depends, HTTPException
from app.core.agents.chat_assistant_agent import ChatAssistantAgent
from app.core.schemas.chat import (
    ChatSettingsRequest,
    ChatSettingsResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSuggestionRequest,
    ChatSuggestionResponse,
    ChatAuthorizeRequest,
    ChatAuthorizeResponse,
    ChatDataUploadRequest,
    ChatDataUploadResponse,
    ChatAssistantStatus,
)
from app.api.deps import get_chat_agent
from app.utils.logger import logger

router = APIRouter(prefix="/chat", tags=["聊天助手"])


@router.post("/settings", response_model=ChatSettingsResponse, summary="更新聊天助手设置")
async def update_chat_settings(
    request: ChatSettingsRequest,
    agent: ChatAssistantAgent = Depends(get_chat_agent),
):
    """更新用户的聊天助手设置（开启/关闭、数据采集授权）"""
    try:
        result = await agent.update_user_settings(
            user_id=request.user_id,
            chat_assistant_enabled=request.chat_assistant_enabled,
            data_collection_enabled=request.data_collection_enabled,
        )
        return ChatSettingsResponse(
            user_id=request.user_id,
            chat_assistant_enabled=result["chat_assistant_enabled"],
            data_collection_enabled=result["data_collection_enabled"],
            style_data_count=result["style_data_count"],
            last_updated=None,
        )
    except Exception as e:
        logger.error(f"更新聊天设置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/{user_id}", response_model=ChatSettingsResponse, summary="获取聊天助手设置")
async def get_chat_settings(
    user_id: str,
    agent: ChatAssistantAgent = Depends(get_chat_agent),
):
    """获取用户的聊天助手设置"""
    try:
        result = await agent.get_user_settings(user_id)
        return ChatSettingsResponse(
            user_id=user_id,
            chat_assistant_enabled=result["chat_assistant_enabled"],
            data_collection_enabled=result["data_collection_enabled"],
            style_data_count=result["style_data_count"],
        )
    except Exception as e:
        logger.error(f"获取聊天设置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/authorize", response_model=ChatAuthorizeResponse, summary="授权聊天助手")
async def authorize_chat_assistant(
    request: ChatAuthorizeRequest,
    agent: ChatAssistantAgent = Depends(get_chat_agent),
):
    """用户授权开启/关闭聊天助手及数据采集"""
    try:
        result = await agent.update_user_settings(
            user_id=request.user_id,
            chat_assistant_enabled=request.authorize,
            data_collection_enabled=request.authorize,
        )
        return ChatAuthorizeResponse(
            user_id=request.user_id,
            chat_assistant_enabled=result["chat_assistant_enabled"],
            data_collection_enabled=result["data_collection_enabled"],
        )
    except Exception as e:
        logger.error(f"授权聊天助手失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages", response_model=ChatMessageResponse, summary="提交聊天消息")
async def submit_chat_message(
    request: ChatMessageRequest,
    agent: ChatAssistantAgent = Depends(get_chat_agent),
):
    """提交聊天消息（用于风格数据采集，需要用户授权）"""
    try:
        result = await agent.submit_message(
            user_id=request.user_id,
            message=request.message,
            message_type=request.message_type,
            conversation_id=request.conversation_id,
        )
        return ChatMessageResponse(
            message_id=result.get("message_id", ""),
            processed=result.get("processed", False),
            chunks_count=result.get("chunks_count", 0),
        )
    except Exception as e:
        logger.error(f"提交聊天消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=ChatDataUploadResponse, summary="批量上传聊天数据")
async def upload_chat_data(
    request: ChatDataUploadRequest,
    agent: ChatAssistantAgent = Depends(get_chat_agent),
):
    """批量上传聊天历史数据（需要用户授权）"""
    try:
        result = await agent.upload_chat_data(
            user_id=request.user_id,
            messages=request.messages,
        )
        return ChatDataUploadResponse(
            chunks_created=result.get("chunks_created", 0),
            total_messages=result.get("total_messages", len(request.messages)),
        )
    except Exception as e:
        logger.error(f"上传聊天数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suggestions", response_model=ChatSuggestionResponse, summary="获取聊天建议")
async def get_chat_suggestions(
    request: ChatSuggestionRequest,
    agent: ChatAssistantAgent = Depends(get_chat_agent),
):
    """根据对话上下文生成聊天建议（需开启聊天助手）"""
    try:
        result = await agent.generate_suggestions(
            user_id=request.user_id,
            context=request.context,
            suggestion_count=request.suggestion_count,
        )
        return ChatSuggestionResponse(
            enabled=result.get("enabled", False),
            data_sufficient=result.get("data_sufficient", False),
            message=result.get("message"),
            suggestions=result.get("suggestions", []),
        )
    except Exception as e:
        logger.error(f"获取聊天建议失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{user_id}", response_model=ChatAssistantStatus, summary="获取聊天助手状态")
async def get_chat_status(
    user_id: str,
    agent: ChatAssistantAgent = Depends(get_chat_agent),
):
    """获取用户的聊天助手状态信息"""
    try:
        result = await agent.get_status(user_id)
        return ChatAssistantStatus(**result)
    except Exception as e:
        logger.error(f"获取聊天助手状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
