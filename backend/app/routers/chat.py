"""问答与会话路由。

路径规范（`docs/CODING_CONVENTIONS.md` 第 6.1 节）：聊天接口挂在 `/api/chat/...`。
SSE 事件类型与该文档第 6.5 节一致：`token` / `sources` / `complete` / `error`。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatStreamRequest,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    DeleteConversationResponse,
    MessageListResponse,
    MessageResponse,
    UpdateConversationRequest,
)
from app.security.dependencies import get_current_active_user
from app.services import chat_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: str, payload: dict[str, object]) -> str:
    """构造一条 SSE 消息。

    只使用 `event:` 与 `data:` 两个字段，保持与 `docs/CODING_CONVENTIONS.md`
    第 6.5 节的示例格式一致。不用 `id:` / `retry:`——本项目不需要断线重连续传。
    """
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/conversations", response_model=ConversationResponse, summary="新建会话")
def create_conversation(
    payload: CreateConversationRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ConversationResponse:
    """新建会话，返回后端生成的 conversation_id。"""
    conversation = chat_service.create_conversation(
        db, current_user.id, payload.title if payload else None
    )
    return ConversationResponse.model_validate(conversation)


@router.get("/conversations", response_model=ConversationListResponse, summary="会话列表")
def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ConversationListResponse:
    """列出当前用户的会话，按最近更新倒序。"""
    items, total = chat_service.list_conversations(db, current_user.id, page, page_size)
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete(
    "/conversations/{conversation_id}",
    response_model=DeleteConversationResponse,
    summary="删除会话",
)
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DeleteConversationResponse:
    """删除会话及其全部消息。"""
    chat_service.delete_conversation(db, current_user.id, conversation_id)
    return DeleteConversationResponse(
        message="会话已删除", conversation_id=conversation_id
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="修改会话（重命名 / 置顶）",
)
def update_conversation(
    conversation_id: str,
    payload: UpdateConversationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ConversationResponse:
    """重命名会话或切换置顶。

    用 `model_fields_set` 判断「要改哪些字段」，与 `PATCH /auth/me` 同一套约定：
    请求体里没出现的键一律不动。
    """
    changes: dict[str, object] = {}
    if "title" in payload.model_fields_set:
        changes["title"] = payload.title
    if "is_pinned" in payload.model_fields_set:
        changes["is_pinned"] = payload.is_pinned

    if not changes:
        raise AppError(ErrorCode.VALIDATION_ERROR, "请求体里没有需要更新的字段")

    conversation = chat_service.update_conversation(
        db, current_user.id, conversation_id, changes
    )
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="会话消息列表",
)
def list_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MessageListResponse:
    """取某个会话的历史消息，用于打开历史会话时回填界面。"""
    # 先校验会话归属，避免仅凭 UUID 就能读到别人的消息。
    chat_service.get_conversation(db, current_user.id, conversation_id)
    messages = chat_service.list_messages(db, current_user.id, conversation_id)
    return MessageListResponse(
        items=[MessageResponse.model_validate(item) for item in messages],
        total=len(messages),
        conversation_id=conversation_id,
    )


@router.post("/stream", summary="流式问答（SSE）")
async def stream_chat(
    payload: ChatStreamRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """以 SSE 流式返回回答。

    `trace_id` 在这里生成并沿途携带：日志、错误响应、消息记录三处用同一个值，
    便于按一次问答串起全链路。
    """
    trace_id = uuid.uuid4().hex

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event, data in chat_service.stream_rag_answer(
                db,
                user_id=current_user.id,
                conversation_id=payload.conversation_id,
                query=payload.query,
                knowledge_bool=payload.knowledge_bool,
                model=payload.model,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                trace_id=trace_id,
            ):
                # 客户端断开时停止继续生成：既省算力，也避免把半截回答写进数据库。
                if await request.is_disconnected():
                    logger.info("客户端已断开，终止生成 trace_id=%s", trace_id)
                    return
                yield _sse(event, data)
        except Exception as exc:
            # 生成器内部未捕获的异常会直接断流，前端只能看到「连接中断」。
            # 这里兜底发一条 error 事件，让用户看到可读原因。
            logger.exception("流式接口异常 trace_id=%s", trace_id)
            yield _sse(
                "error",
                {"code": "INTERNAL_ERROR", "message": f"服务内部错误（{type(exc).__name__}）", "trace_id": trace_id},
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            # 关闭 Nginx/其他中间代理的缓冲，否则 SSE 会被攒成一整块才发出，
            # 流式效果完全消失。
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
