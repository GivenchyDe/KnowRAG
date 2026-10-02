"""全局模型配置路由。

路径规范（`docs/CODING_CONVENTIONS.md` 第 6.1 节）：配置接口挂在 `/api/config/...`。
本模块只做参数接收、鉴权依赖与响应组装：业务逻辑在 `config_service`（配置读写、
已保存凭据解析）与 `connection_test_service`（三类模型的测试判据）。
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import TRACE_ID_STATE_KEY, AppError, ErrorCode
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.schemas.config import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    ModelConfigResponse,
    ModelConfigUpdate,
    ModelConfigUpdateResponse,
    ProvidersResponse,
)
from app.security.dependencies import get_current_active_user
from app.services import config_service, connection_test_service, index_service
from app.services.crypto_service import mask_api_key
from app.services.provider_catalog import (
    default_for,
    requires_explicit_base_url,
    supported_values,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/model", response_model=ModelConfigResponse, summary="获取全局模型配置（脱敏）")
def read_model_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, object]:
    """返回全局模型配置。

    首次调用时若配置行不存在，会自动创建默认行，因此本接口同时承担「初始化」职责。
    """
    config = config_service.get_or_create_config(db)
    return config_service.build_config_response(config)


@router.put("/model", response_model=ModelConfigUpdateResponse, summary="更新全局模型配置")
def update_model_config(
    payload: ModelConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ModelConfigUpdateResponse:
    """更新模型配置。

    若 Embedding 相关配置发生变化，响应中的 `index_stale` 为 true，
    前端据此提示用户重建知识库索引。
    """
    result = config_service.update_config(db, payload, current_user)

    # 审计日志：记录「谁改了什么字段」，绝不记录字段的值——
    # 其中包含 API Key，即使是脱敏值也不应进入日志（第 8.2 节）。
    logger.info(
        "全局模型配置已更新 user_id=%s changed_fields=%s embedding_changed=%s",
        current_user.id,
        ",".join(result.changed_fields) if result.changed_fields else "(无实际变化)",
        result.embedding_changed_fields,
    )

    if result.index_stale:
        message = "配置已更新，Embedding 变更后需要重建知识库索引"
    elif not result.changed_fields:
        message = "配置未发生变化"
    else:
        message = "配置已更新"

    return ModelConfigUpdateResponse(
        status="success",
        index_stale=result.index_stale,
        message=message,
    )


@router.get("/providers", response_model=ProvidersResponse, summary="获取支持的 provider 列表")
def read_providers(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, object]:
    """返回 provider 目录。

    前端不硬编码 provider 与模型名，一律从这里取值，便于后端替换模型时不改前端。
    """
    return config_service.build_providers_response()


@router.post("/model/test", response_model=ConnectionTestResponse, summary="测试模型连接")
def test_connection(
    payload: ConnectionTestRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ConnectionTestResponse:
    """测试 LLM / Embedding / Reranker 三类模型的可用性。

    两种取 Key 的方式：
    - `use_saved_key=False`（默认）：用请求体里的 `api_key`，用于"先测再存"；
    - `use_saved_key=True`：用数据库里已保存的 Key，且**地址与模型名也取已保存的值**，
      用户不必为了测试而重新粘贴一遍 Key。

    三类测试各自的判据（见 `services/connection_test_service.py`）：
    - LLM：发一次最小对话请求，看是否 200；
    - Embedding：真的算一次向量，并核对维度与配置一致；
    - Reranker：给一正一负两条候选，看重排后相关片段是否排在前面。

    安全（`docs/CODING_CONVENTIONS.md` 第 8、9 节）：
    - 依赖 `get_current_active_user`，未登录直接 401，接口不对外匿名开放；
    - 使用已保存的 Key 时地址不由调用方决定（见 `config_service.load_saved_connection_target`），
      否则接口会变成"把服务端密钥发到任意地址"的外泄通道；
    - 日志只出现脱敏 Key 与 user_id，不打印明文/密文 Key、Authorization 头；
    - 响应体不含 Key 的任何形态；供应商原始报文只进服务端日志。
    """
    trace_id = str(getattr(request.state, TRACE_ID_STATE_KEY, ""))

    if payload.provider not in supported_values(payload.kind):
        raise AppError(
            ErrorCode.MODEL_CONFIG_INVALID,
            f"不支持的 {payload.kind} provider：{payload.provider}",
        )

    if payload.use_saved_key:
        target = config_service.load_saved_connection_target(
            db, kind=payload.kind, provider=payload.provider
        )
        api_key = target.api_key
        # LLM 用已保存的地址；Embedding / Reranker 的端点由 SDK/常量决定，这里为 None。
        base_url = target.base_url or ""
        model = target.model
        key_from = "saved"
    else:
        api_key = (payload.api_key or "").strip()
        # 没给 Key 又不让用已保存的 Key → 请求本身不完整，属于参数问题而非配置问题。
        # 本系统只有远程 provider，所有 provider 都需要 Key。
        if not api_key:
            raise AppError(ErrorCode.VALIDATION_ERROR, "未提供 API Key")

        option = default_for(payload.kind, payload.provider)
        # base_url 允许留空：留空时按 provider 目录的地址兜底，让用户不填也能测。
        base_url = (payload.base_url or "").strip() or (
            (option["default_base_url"] or "") if option else ""
        )
        model = (payload.model or "").strip() or (option["default_model"] if option else "")
        key_from = "request"

    if not base_url and (
        payload.kind == "llm"
        or requires_explicit_base_url(payload.kind, payload.provider)
    ):
        # LLM 的地址是必填的（DeepSeek 之外都是 OpenAI 兼容端点，没有地址无从发起请求）；
        # Embedding / Reranker 里只有 custom 需要用户提供地址，其余两类的端点
        # 由代码固定或目录给出，因此不在这里拦。
        raise AppError(
            ErrorCode.MODEL_CONFIG_INVALID,
            "缺少 base_url，且该 provider 没有默认地址",
        )

    # 记录尝试本身（trace_id 便于与访问日志、错误响应串起来）。
    # 只写脱敏 Key：明文与密文都不进日志。
    logger.info(
        "连接测试 trace_id=%s user_id=%s kind=%s provider=%s base_url=%s key=%s key_source=%s",
        trace_id,
        current_user.id,
        payload.kind,
        payload.provider,
        base_url or "-",
        mask_api_key(api_key),
        key_from,
    )

    if payload.kind == "llm":
        outcome = connection_test_service.test_llm(
            provider=payload.provider, base_url=base_url, model=model, api_key=api_key
        )
    elif payload.kind == "embed":
        outcome = connection_test_service.test_embedding(
            provider=payload.provider, model=model, api_key=api_key, base_url=base_url
        )
        outcome = _sync_measured_dimension(
            db, outcome, provider=payload.provider, model=model
        )
    else:
        outcome = connection_test_service.test_reranker(
            provider=payload.provider, model=model, api_key=api_key, base_url=base_url
        )

    return ConnectionTestResponse(
        success=outcome.success,
        code=outcome.code,
        message=outcome.message,
        detail=outcome.detail,
    )


def _sync_measured_dimension(
    db: Session,
    outcome: connection_test_service.ConnectionTestOutcome,
    *,
    provider: str,
    model: str,
) -> connection_test_service.ConnectionTestOutcome:
    """把 Embedding 实测维度写回配置（仅当测的就是当前生效的那个模型）。

    为什么只在这个条件下写：`embed_dimension` 是**模型的属性**，由后端按实测值维护
    （前端已无输入框）。用户完全可能拿草稿里的新模型来测——那测出来的维度属于
    "还没保存的模型"，写回配置会让正在生效的配置记上一个不属于它的维度。
    因此判据是"实测的 provider + 模型 == 已保存的 provider + 模型"。

    为什么写回后要提示重建：维度是指纹的一部分，改它等于宣布旧索引无法证明与当前模型一致。
    """
    dimension = (outcome.detail or {}).get("dimension")
    if not outcome.success or not isinstance(dimension, int) or dimension <= 0:
        return outcome

    config = config_service.get_or_create_config(db)
    if config.embed_provider != provider or config.embed_model != model:
        return outcome

    change = index_service.sync_embedding_dimension(db, config, dimension=dimension)
    if not change.changed:
        return outcome

    message = (
        f"{outcome.message}；已把配置中的向量维度更新为 {change.current} 维"
        f"（原 {change.previous} 维）"
    )
    if change.stale_indexes:
        message += "，已有索引需要重建后才能用于问答"

    return replace(
        outcome,
        message=message,
        detail={
            **(outcome.detail or {}),
            "dimension_synced": True,
            "previous_dimension": change.previous,
            "stale_indexes": change.stale_indexes,
        },
    )

