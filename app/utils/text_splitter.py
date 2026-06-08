"""文本分片工具"""
from typing import List, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config.settings import settings
from app.utils.logger import logger


def create_text_splitter(
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    separators: Optional[List[str]] = None,
) -> RecursiveCharacterTextSplitter:
    """
    创建文本分片器

    Args:
        chunk_size: 每片大小
        chunk_overlap: 重叠大小
        separators: 分隔符列表

    Returns:
        RecursiveCharacterTextSplitter 实例
    """
    if separators is None:
        separators = ["\n\n", "\n", "。", "！", "？", "，", " ", ""]

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.POST_CHUNK_SIZE,
        chunk_overlap=chunk_overlap or settings.POST_CHUNK_OVERLAP,
        separators=separators,
        length_function=len,
        is_separator_regex=False,
    )


def split_text(
    text: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    separators: Optional[List[str]] = None,
) -> List[str]:
    """
    切分文本

    Args:
        text: 待切分文本
        chunk_size: 每片大小
        chunk_overlap: 重叠大小
        separators: 分隔符列表

    Returns:
        切分后的文本列表
    """
    if not text or not text.strip():
        return []

    splitter = create_text_splitter(chunk_size, chunk_overlap, separators)
    chunks = splitter.split_text(text)

    # 过滤空字符串
    chunks = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]

    logger.debug(f"文本分片完成：原文长度={len(text)}，分片数={len(chunks)}")
    return chunks


def split_chat_message(message: str) -> List[str]:
    """
    针对聊天消息的分片策略

    Args:
        message: 聊天消息

    Returns:
        分片列表
    """
    return split_text(
        text=message,
        chunk_size=settings.CHAT_CHUNK_SIZE,
        chunk_overlap=settings.CHAT_CHUNK_OVERLAP,
    )


def split_post_content(title: str, content: str) -> List[str]:
    """
    针对帖子内容的分片策略

    Args:
        title: 帖子标题
        content: 帖子内容

    Returns:
        分片列表
    """
    full_content = f"标题：{title}\n内容：{content}"
    return split_text(
        text=full_content,
        chunk_size=settings.POST_CHUNK_SIZE,
        chunk_overlap=settings.POST_CHUNK_OVERLAP,
    )
