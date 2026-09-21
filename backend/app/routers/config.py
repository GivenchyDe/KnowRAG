"""全局模型配置路由。

路径规范（`docs/CODING_CONVENTIONS.md` 第 6.1 节）：配置接口挂在 `/api/config/...`。
本模块只做参数接收、鉴权依赖与响应组装，业务逻辑在 `config_service`。
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
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
from app.services import config_service
from app.services.provider_catalog import default_for, supported_values

logger = get_logger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

# 连接测试超时。取值偏短是有意的：这是交互式操作，用户需要即时反馈，
# 而模型供应商在密钥错误时通常秒级返回。
_TEST_TIMEOUT_SECONDS = 12.0


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
) -> ConnectionTestResponse:
    """校验 API Key 与 base_url 是否可用。

    只支持远程 provider：本地模型是加载磁盘上的权重文件，不存在「连接」概念，
    它们的可用性检查属于 Phase 3/4 的模型加载流程。

    返回信息刻意保持通用：供应商的原始错误可能包含账号、额度、请求 ID 等
    敏感细节，这些只写服务端日志，不回传前端（`docs/CODING_CONVENTIONS.md` 第 9 节）。
    """
    if payload.kind != "llm":
        raise AppError(
            ErrorCode.MODEL_CONFIG_INVALID,
            "当前仅支持测试 LLM 连接；本地 Embedding / Reranker 的可用性在索引构建时校验",
        )

    if payload.provider not in supported_values("llm"):
        raise AppError(
            ErrorCode.MODEL_CONFIG_INVALID,
            f"不支持的 LLM provider：{payload.provider}",
        )

    api_key = (payload.api_key or "").strip()
    if not api_key:
        raise AppError(ErrorCode.MODEL_CONFIG_INVALID, "请先填写 API Key 再测试连接")

    # base_url 允许留空：留空时按 provider 目录的官方地址兜底，
    # 让用户不填也能完成测试。
    option = default_for("llm", payload.provider)
    base_url = (payload.base_url or "").strip() or (
        option["default_base_url"] if option else None
    )
    if not base_url:
        raise AppError(ErrorCode.MODEL_CONFIG_INVALID, "缺少 base_url，且该 provider 没有默认地址")

    model = (payload.model or "").strip() or (option["default_model"] if option else "")

    return _probe_llm(provider=payload.provider, base_url=base_url, model=model, api_key=api_key)


def _probe_llm(*, provider: str, base_url: str, model: str, api_key: str) -> ConnectionTestResponse:
    """对 OpenAI 兼容接口发起一次最小对话请求。"""
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = httpx.post(url, json=body, headers=headers, timeout=_TEST_TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        logger.warning("连接测试超时 provider=%s base_url=%s", provider, base_url)
        raise AppError(
            ErrorCode.MODEL_PROVIDER_ERROR, "连接超时，请检查网络或 base_url 是否正确"
        ) from exc
    except httpx.HTTPError as exc:
        # 这里不把异常文本回传：可能包含内网地址、证书信息等。
        logger.warning("连接测试失败 provider=%s error=%s", provider, type(exc).__name__)
        raise AppError(
            ErrorCode.MODEL_PROVIDER_ERROR, "无法连接到模型服务，请检查网络与 base_url"
        ) from exc

    if response.status_code == 200:
        return ConnectionTestResponse(success=True, code="OK", message="连接成功，API Key 有效")

    # 只按状态码给出用户可操作的原因；具体报文只留在服务端日志里（也不含 Key）。
    status = response.status_code
    logger.warning(
        "连接测试返回非 200 provider=%s status=%s body_len=%s",
        provider,
        status,
        len(response.text),
    )
    if status in (401, 403):
        return ConnectionTestResponse(
            success=False, code="MODEL_CONFIG_INVALID", message="API Key 无效或没有访问权限"
        )
    if status == 404:
        return ConnectionTestResponse(
            success=False,
            code="MODEL_CONFIG_INVALID",
            message="接口地址或模型名不正确，请检查 base_url 与模型名",
        )
    if status == 429:
        return ConnectionTestResponse(
            success=False, code="RATE_LIMITED", message="请求过于频繁或额度已用尽"
        )
    return ConnectionTestResponse(
        success=False,
        code="MODEL_PROVIDER_ERROR",
        message=f"模型服务返回异常状态（HTTP {status}）",
    )
