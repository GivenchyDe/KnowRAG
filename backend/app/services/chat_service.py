"""问答业务逻辑与 RAG 流式生成。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 5.7、7.3、7.4 节。

线程模型说明（重要）：
本模块的「同步重活」（embedding、向量检索、Reranker、LLM 流式调用）全部是阻塞式 I/O
或 CPU 密集操作。如果直接在 async 生成器里调用，会**阻塞整个事件循环**——
表现是流式输出期间其他请求（包括同一个人的任务轮询）全部卡住。
因此这里用 `run_in_threadpool` 把阻塞调用扔进线程池，主协程只负责把增量文本推给 SSE。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.db.base import utc_now
from app.models.conversation import Conversation
from app.models.knowledge_base_index import IndexStatus
from app.models.message import Message, MessageRole
from app.models.model_config import ModelConfig
from app.rag import prompts, retrieval
from app.services import config_service, index_service
from app.services.crypto_service import decrypt_api_key

logger = get_logger(__name__)

# 带入 Prompt 的历史消息条数上限。太多会挤占上下文并增加成本，
# 太少则模型记不住上一轮说了什么。6 条（3 轮往返）是常见取值。
_HISTORY_LIMIT = 6
# 会话标题的长度上限（自动取自首条提问）。
_TITLE_MAX_LEN = 30

# 用前缀把「流中途的错误」与正常文本区分开，避免把错误信息当成回答内容拼进去。
# 必须定义在 _stream_llm 之前：该函数在运行时读取这个模块级常量。
_LLM_ERROR_PREFIX = "\x00LLM_ERROR\x00"


# --------------------------------------------------------------------------- #
# 会话
# --------------------------------------------------------------------------- #


def create_conversation(db: Session, user_id: int, title: str | None = None) -> Conversation:
    """新建会话。

    `conversation_id` 由后端生成 UUID——设计文档允许前端或后端生成，
    后端生成的好处是前端不需要关心 UUID 的构造规则，也不依赖 `crypto.randomUUID` 的可用性。
    """
    conversation = Conversation(
        user_id=user_id,
        conversation_id=str(uuid.uuid4()),
        title=(title or "新会话").strip() or "新会话",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(db: Session, user_id: int, conversation_id: str) -> Conversation:
    """取当前用户的会话，不存在时抛出 404。

    不区分「会话不存在」与「属于别人」：区分开会让攻击者通过响应差异
    枚举出系统中存在哪些会话 ID。
    """
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.user_id == user_id, Conversation.conversation_id == conversation_id
        )
    )
    if conversation is None:
        raise AppError(ErrorCode.RESOURCE_NOT_FOUND, "会话不存在")
    return conversation


def ensure_conversation(db: Session, user_id: int, conversation_id: str) -> Conversation:
    """取会话；不存在则自动创建。

    前端可能在用户首次提问前就生成好了 conversation_id（设计文档允许前端生成），
    此时数据库里还没有对应记录。自动创建比报错更符合使用预期。
    """
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.user_id == user_id, Conversation.conversation_id == conversation_id
        )
    )
    if conversation is not None:
        return conversation

    conversation = Conversation(user_id=user_id, conversation_id=conversation_id, title="新会话")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_conversations(db: Session, user_id: int, page: int, page_size: int) -> tuple[list[Conversation], int]:
    """列出用户的会话，按最近更新倒序。"""
    all_items = list(
        db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        ).all()
    )
    total = len(all_items)
    start = (page - 1) * page_size
    return all_items[start : start + page_size], total


def delete_conversation(db: Session, user_id: int, conversation_id: str) -> None:
    """删除会话及其全部消息。

    先删消息再删会话：messages 表没有外键约束到 conversations（按设计，
    消息用 UUID 关联而非主键），因此需要显式清理，否则会留下孤儿消息。
    """
    conversation = get_conversation(db, user_id, conversation_id)
    messages = db.scalars(
        select(Message).where(
            Message.user_id == user_id, Message.conversation_id == conversation_id
        )
    ).all()
    for message in messages:
        db.delete(message)
    db.delete(conversation)
    db.commit()
    logger.info(
        "会话已删除 user_id=%s conversation_id=%s 消息数=%d",
        user_id,
        conversation_id,
        len(messages),
    )


def touch_conversation(db: Session, conversation: Conversation, first_query: str) -> None:
    """更新会话的更新时间；标题仍是默认值时用首条提问生成标题。

    这样用户不必手动命名会话，历史列表里也能一眼看出聊的是什么。
    """
    if conversation.title == "新会话" and first_query.strip():
        title = first_query.strip().replace("\n", " ")
        conversation.title = title[:_TITLE_MAX_LEN] + ("…" if len(title) > _TITLE_MAX_LEN else "")
    conversation.updated_at = utc_now()
    db.commit()


# --------------------------------------------------------------------------- #
# 消息
# --------------------------------------------------------------------------- #


def save_message(
    db: Session,
    *,
    user_id: int,
    conversation_id: str,
    role: MessageRole,
    content: str,
    sources: list[dict[str, Any]] | None = None,
    trace_id: str | None = None,
) -> Message:
    """持久化一条消息。"""
    message = Message(
        user_id=user_id,
        conversation_id=conversation_id,
        role=role.value,
        content=content,
        source_entries=sources,
        trace_id=trace_id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_messages(db: Session, user_id: int, conversation_id: str) -> list[Message]:
    """按时间正序列出会话消息。"""
    return list(
        db.scalars(
            select(Message)
            .where(Message.user_id == user_id, Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        ).all()
    )


def _load_history(db: Session, user_id: int, conversation_id: str) -> list[Message]:
    """取最近若干条历史消息，用于构造多轮上下文。

    只取 user / assistant 两种角色：system 消息是每次现场构造的，
    历史里的 system 属于过期指令，带进 Prompt 只会造成冲突。
    """
    rows = list(
        db.scalars(
            select(Message)
            .where(
                Message.user_id == user_id,
                Message.conversation_id == conversation_id,
                Message.role.in_([MessageRole.USER.value, MessageRole.ASSISTANT.value]),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(_HISTORY_LIMIT)
        ).all()
    )
    return list(reversed(rows))


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #


def _build_llm(config: ModelConfig, *, model: str | None, temperature: float | None, max_tokens: int | None):
    """按全局配置创建 LLM 实例。

    单次请求的覆盖项（model / temperature / max_tokens）优先于全局配置，
    这样前端可以在不修改全局设置的前提下临时调整。
    """
    resolved_model = (model or config.llm_model or "").strip()
    resolved_temperature = config.llm_temperature if temperature is None else temperature
    resolved_max_tokens = config.llm_max_tokens if max_tokens is None else max_tokens

    if not config.llm_api_key_encrypted:
        raise AppError(
            ErrorCode.MODEL_CONFIG_INVALID,
            "尚未配置 LLM API Key，请先到「模型设置」页填写",
        )
    api_key = decrypt_api_key(config.llm_api_key_encrypted)

    if config.llm_provider == "deepseek":
        from llama_index.llms.deepseek import DeepSeek

        kwargs: dict[str, Any] = {
            "model": resolved_model or "deepseek-chat",
            "api_key": api_key,
            "temperature": resolved_temperature,
            "max_tokens": resolved_max_tokens,
        }
        if config.llm_base_url:
            kwargs["api_base"] = config.llm_base_url
        return DeepSeek(**kwargs)

    if config.llm_provider == "qwen":
        from llama_index.llms.dashscope import DashScope

        # DashScope 走阿里云兼容模式端点，base_url 由 SDK 内部管理，这里不额外传。
        return DashScope(
            model_name=resolved_model or "qwen-plus",
            api_key=api_key,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            incremental_output=True,
        )

    raise AppError(
        ErrorCode.MODEL_CONFIG_INVALID, f"不支持的 LLM provider：{config.llm_provider}"
    )


def _stream_llm(llm: Any, messages: list[Any]) -> AsyncIterator[str]:
    """把阻塞式的 LLM 流式迭代器适配为异步生成器。

    直接在 async 生成器里 `for chunk in llm.stream_chat(...)` 会阻塞事件循环：
    整个流式回答期间（可能几十秒），其他请求全部无法处理。
    这里把迭代放进线程池，每次只取一块并通过队列交回主协程。
    """
    import asyncio
    import threading

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def produce() -> None:
        # 已推出的累积文本。用于在 provider 不提供 delta 时自行算出增量。
        emitted = ""
        try:
            for chunk in llm.stream_chat(messages):
                delta = getattr(chunk, "delta", None)

                if not delta:
                    # 增量兜底。**这一步不能省**：
                    # `ChatResponse.delta` 的默认值是 None，只有部分 provider 的流式实现
                    # 会填它；另一些只填 `message.content`（且是**累积全文**而不是增量）。
                    # 如果只认 delta，遇到后者就会一个字都推不出去——
                    # 现象是后端日志显示「问答完成、回答长度 779」，前端却收到空白回答，
                    # 而且流正常以 complete 结束、不报任何错，极难定位。
                    # 这里从累积全文里截出本次新增的部分，保证两种实现都能正确流式输出。
                    full = ""
                    message = getattr(chunk, "message", None)
                    if message is not None:
                        full = getattr(message, "content", None) or ""

                    if full.startswith(emitted):
                        delta = full[len(emitted) :]
                    elif full:
                        # 累积文本与已推出内容对不上（例如 provider 每次给的是片段而非累积），
                        # 保守地整段推出，宁可重复也不要丢内容。
                        delta = full
                    else:
                        continue

                    emitted = full if full.startswith(emitted) else emitted + str(delta)

                if delta:
                    loop.call_soon_threadsafe(queue.put_nowait, str(delta))
        except Exception as exc:  # 供应商调用失败
            logger.warning("LLM 流式调用失败：%s: %s", type(exc).__name__, str(exc)[:200])
            loop.call_soon_threadsafe(queue.put_nowait, _LLM_ERROR_PREFIX + type(exc).__name__)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=produce, name="llm-stream", daemon=True).start()

    async def iterator() -> AsyncIterator[str]:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return iterator()


# --------------------------------------------------------------------------- #
# 流式问答主流程
# --------------------------------------------------------------------------- #


async def stream_rag_answer(
    db: Session,
    *,
    user_id: int,
    conversation_id: str,
    query: str,
    knowledge_bool: bool,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
    trace_id: str,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """执行一次问答，产出 `(event_name, payload)` 序列。

    事件类型与 `docs/CODING_CONVENTIONS.md` 第 6.5 节一致。
    """
    conversation = ensure_conversation(db, user_id, conversation_id)

    # 历史必须在写入本次提问**之前**读取。若先写后读，刚存进去的用户消息
    # 会同时出现在历史里和下面显式追加的「当前提问」中，导致同一个问题发给模型两次。
    history_rows = _load_history(db, user_id, conversation_id)

    save_message(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=query,
    )
    touch_conversation(db, conversation, query)

    config = config_service.get_or_create_config(db)

    # --- 检索 ---
    result = retrieval.RetrievalResult(query=query)
    if knowledge_bool:
        index = index_service.get_latest_index(db, user_id)
        if index is None or index.status != IndexStatus.READY:
            yield ("error", {
                "code": ErrorCode.INDEX_NOT_READY.value,
                "message": "当前知识库索引不可用，请先到文档页上传文档并重建索引",
                "trace_id": trace_id,
            })
            return
        if index_service.signature_changed(index, config):
            yield ("error", {
                "code": ErrorCode.INDEX_STALE.value,
                "message": "Embedding 配置已变更，索引已过期，请到文档页重建索引",
                "trace_id": trace_id,
            })
            return

        try:
            result = await run_in_threadpool(
                retrieval.retrieve,
                query=query,
                user_id=user_id,
                collection_name=index.collection_name,
                config=config,
            )
        except AppError as exc:
            yield ("error", {"code": exc.code.value, "message": exc.message, "trace_id": trace_id})
            return
        except Exception as exc:
            logger.exception("检索异常 trace_id=%s error=%s", trace_id, type(exc).__name__)
            yield ("error", {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": f"检索失败（{type(exc).__name__}）",
                "trace_id": trace_id,
            })
            return

    sources = result.sources()

    # --- 空结果：直接给出固定回答，**不调用 LLM** ---
    #
    # 只在 knowledge_bool=True 时走这条分支。含义是「知识库是本轮回答的唯一依据」：
    # 既然没有检索到任何相关资料，那么调用 LLM 只会得到两种结果——编造，或者
    # 依赖系统提示词勉强拒答。前者是幻觉，后者也要付出一次 token 成本与额外延迟，
    # 而拒答本身是一句完全确定的话，没有任何生成的必要。
    #
    # knowledge_bool=False 时刻意**不**走这里：那是用户明确关闭知识库、要求自由对话
    # （例如打招呼），此时空结果不构成「无法回答」。
    if knowledge_bool and result.is_empty:
        answer = prompts.NO_CONTEXT_ANSWER
        save_message(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            sources=None,
            trace_id=trace_id,
        )
        touch_conversation(db, conversation, "")
        logger.info(
            "无相关资料，未调用 LLM trace_id=%s user_id=%s 初检=%d 采纳=0",
            trace_id,
            user_id,
            result.candidate_count,
        )
        # 与正常回答保持同样的事件序列：先 token（把文案推给前端），再 complete。
        # 这样前端不需要为「拒答」维护一条特殊路径。
        yield ("token", {"text": answer})
        # 带上完整回答：前端以它为准覆盖逐字累积的文本，漏字时不必刷新页面。
        yield ("complete", {"trace_id": trace_id, "sources": [], "content": answer})
        return

    if sources:
        yield ("sources", {"sources": sources})

    # --- 构造 Prompt ---
    from llama_index.core.llms import ChatMessage as LlamaChatMessage

    if knowledge_bool:
        # 知识库模式：带上检索到的资料，并要求严格基于资料作答。
        system_content = prompts.build_rag_system_prompt(retrieval.build_context(result.passages))
    else:
        # 自由对话模式：不加 RAG 约束。
        # 之前这里无论开关如何都用同一套 system prompt，导致关闭知识库后
        # 单纯打个招呼也会被「只能依据参考资料回答」的规则拒答。
        system_content = prompts.FREE_CHAT_PROMPT

    messages: list[Any] = [LlamaChatMessage(role="system", content=system_content)]
    for history in history_rows:
        messages.append(LlamaChatMessage(role=history.role, content=history.content))
    messages.append(LlamaChatMessage(role="user", content=query))

    try:
        llm = _build_llm(config, model=model, temperature=temperature, max_tokens=max_tokens)
    except AppError as exc:
        yield ("error", {"code": exc.code.value, "message": exc.message, "trace_id": trace_id})
        return

    # --- 流式生成 ---
    pieces: list[str] = []
    failure: str | None = None
    try:
        async for delta in _stream_llm(llm, messages):
            if delta.startswith(_LLM_ERROR_PREFIX):
                # 已经有部分输出时，说明是流中途断开：保留已生成内容并明确告知，
                # 直接丢弃会让用户看到「回答到一半突然没了」且没有解释。
                failure = delta[len(_LLM_ERROR_PREFIX) :]
                break
            pieces.append(delta)
            yield ("token", {"text": delta})
    except Exception as exc:
        logger.exception("流式生成异常 trace_id=%s", trace_id)
        failure = type(exc).__name__

    answer = "".join(pieces).strip()

    if failure and not answer:
        yield ("error", {
            "code": ErrorCode.MODEL_PROVIDER_ERROR.value,
            "message": f"模型调用失败（{failure}），请检查 API Key 与网络后重试",
            "trace_id": trace_id,
        })
        return

    if failure:
        answer = f"{answer}\n\n（回答未完成：模型调用中断，{failure}）"

    save_message(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=answer,
        sources=sources or None,
        trace_id=trace_id,
    )
    touch_conversation(db, conversation, "")

    logger.info(
        "问答完成 trace_id=%s user_id=%s 引用=%d 回答长度=%d 估算tokens=%d",
        trace_id,
        user_id,
        len(sources),
        len(answer),
        retrieval.count_tokens_estimate(answer),
    )
    # `content` 与落库、日志用的是同一个 `answer`，因此前端显示的文本与历史记录
    # 必然一致——不会出现「流式显示的和刷新后看到的不一样」。
    yield ("complete", {"trace_id": trace_id, "sources": sources, "content": answer})
