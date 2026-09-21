"""全局模型配置业务逻辑。

核心约定：
1. 本表**只有一行**。`get_or_create_config` 是唯一的读取入口，不存在记录时
   立即用系统默认值创建，而不是返回空配置——否则前端的设置页会是空白，
   用户无从知道当前默认用的是什么模型。
2. API Key 只以密文形态出现在数据库与本模块内部；对外一律经 `mask_api_key` 脱敏。
3. 判断「Embedding 配置是否变化」时，同时比较 provider、model 与**本地模型路径**。
   只比较 provider/model 是不够的：切换本地模型目录（例如从 bge-m3 换到
   bge-large-zh）同样会改变向量空间，旧索引必须重建。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.models.model_config import ModelConfig
from app.models.user import User
from app.schemas.config import ModelConfigUpdate
from app.services.crypto_service import decrypt_api_key, encrypt_api_key, mask_api_key
from app.services.provider_catalog import (
    default_for,
    get_catalog,
    supported_values,
)

logger = get_logger(__name__)

# 会影响向量空间、因而必须重建索引的字段。
# Reranker 相关字段刻意不在此列：重排只作用于检索结果的顺序，
# 不改变入库向量的语义空间，因此只需失效检索器缓存而不必重建索引。
_EMBEDDING_FIELDS: tuple[str, ...] = (
    "embed_provider",
    "embed_model",
    "embed_model_path",
    "embed_dimension",
)

# 三个 API Key 字段。它们支持「传空字符串以清除」的语义，与其他字段不同。
_API_KEY_FIELDS: tuple[str, ...] = (
    "llm_api_key",
    "embed_api_key",
    "rerank_api_key",
)

# API Key 字段到数据库列名的映射。
_ENCRYPTED_COLUMN_BY_FIELD: dict[str, str] = {
    "llm_api_key": "llm_api_key_encrypted",
    "embed_api_key": "embed_api_key_encrypted",
    "rerank_api_key": "rerank_api_key_encrypted",
}


@dataclass
class ConfigUpdateResult:
    """更新结果，供路由层构造响应与写审计日志。"""

    index_stale: bool
    changed_fields: list[str] = field(default_factory=list)
    embedding_changed_fields: list[str] = field(default_factory=list)


def get_or_create_config(db: Session) -> ModelConfig:
    """读取全局配置；不存在时创建默认行。

    用 `ORDER BY id LIMIT 1` 取第一行而不是 `db.get(ModelConfig, 1)`：
    自增主键不保证一定从 1 开始（例如经过数据清理后），按顺序取更稳健。
    """
    config = db.scalar(select(ModelConfig).order_by(ModelConfig.id).limit(1))
    if config is not None:
        return config

    # 默认值来自 provider 目录，保证「数据库默认值」与「前端看到的可选值」同源。
    llm_default = default_for("llm", "deepseek")
    embed_default = default_for("embed", "local")
    rerank_default = default_for("rerank", "local")

    config = ModelConfig(
        user_id=None,
        llm_provider="deepseek",
        llm_base_url=llm_default["default_base_url"] if llm_default else None,
        llm_model=llm_default["default_model"] if llm_default else "deepseek-chat",
        embed_provider="local",
        embed_model=embed_default["default_model"] if embed_default else "BAAI/bge-m3",
        rerank_provider="local",
        rerank_model=rerank_default["default_model"] if rerank_default else "bge-reranker-large",
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    logger.info("已创建全局模型配置默认行 id=%s", config.id)
    return config


def _local_model_path_defaults() -> tuple[str, str]:
    """本地模型路径的部署级默认值。

    路径属于部署环境信息，不适合固化进数据库默认值（换机器就失效），
    因此未配置时从环境变量读取，由前端展示为当前生效值。
    """
    settings = get_settings()
    return settings.local_bge_m3_path, settings.local_bge_reranker_path


def build_config_response(config: ModelConfig) -> dict[str, object]:
    """把 ORM 对象转换为响应字段，负责解密→脱敏与本地路径兜底。

    解密在这里发生而不是在 schema 层：schema 应保持纯数据转换，
    不应触碰密钥材料。
    """

    def masked(column_value: str | None) -> str | None:
        if not column_value:
            return None
        try:
            return mask_api_key(decrypt_api_key(column_value))
        except Exception:
            # 密钥被更换导致无法解密时，返回一个明确的占位符而不是抛错：
            # 否则整个设置页会打不开，用户连「重新填写 Key」这个操作都做不了。
            logger.warning("模型配置中的 API Key 无法解密，可能是 FERNET_KEY 已更换")
            return "****（解密失败，请重新填写）"

    m3_default, reranker_default = _local_model_path_defaults()

    return {
        "llm_provider": config.llm_provider,
        "llm_api_key_masked": masked(config.llm_api_key_encrypted),
        "llm_base_url": config.llm_base_url,
        "llm_model": config.llm_model,
        "llm_temperature": config.llm_temperature,
        "llm_max_tokens": config.llm_max_tokens,
        "embed_provider": config.embed_provider,
        "embed_api_key_masked": masked(config.embed_api_key_encrypted),
        "embed_model": config.embed_model,
        "embed_model_path": config.embed_model_path or (m3_default or None),
        "embed_dimension": config.embed_dimension,
        "rerank_provider": config.rerank_provider,
        "rerank_api_key_masked": masked(config.rerank_api_key_encrypted),
        "rerank_model": config.rerank_model,
        "rerank_model_path": config.rerank_model_path or (reranker_default or None),
        "updated_at": config.updated_at,
    }


def _validate_providers(payload: ModelConfigUpdate) -> None:
    """校验 provider 取值是否在目录内。

    provider 决定后续走哪条模型创建分支，取值非法会在 Phase 4 才炸；
    在写入前拦下可以给出明确的错误位置。
    """
    for kind, value in (
        ("llm", payload.llm_provider),
        ("embed", payload.embed_provider),
        ("rerank", payload.rerank_provider),
    ):
        if value is None:
            continue
        if value not in supported_values(kind):
            raise AppError(
                ErrorCode.MODEL_CONFIG_INVALID,
                f"不支持的 {kind} provider：{value}",
            )


def _apply_provider_defaults(
    config: ModelConfig, changes: dict[str, object], *, provider_field: str, kind: str
) -> None:
    """切换 provider 时补齐该 provider 的默认 base_url 与模型名。

    否则会出现「provider 已改成 qwen，但模型名仍是 deepseek-chat」这类
    内部不一致的配置，直到 Phase 4 真正调用模型时才报错。
    """
    provider = changes.get(provider_field)
    if provider is None:
        return

    option = default_for(kind, str(provider))
    if option is None:
        return

    # 只在用户没有显式提交对应字段时兜底，避免覆盖用户的明确选择。
    model_field = f"{kind}_model"
    if model_field not in changes and option["default_model"]:
        changes[model_field] = option["default_model"]

    if kind == "llm":
        base_url_field = "llm_base_url"
        if base_url_field not in changes and option["default_base_url"]:
            changes[base_url_field] = option["default_base_url"]


def update_config(
    db: Session, payload: ModelConfigUpdate, current_user: User
) -> ConfigUpdateResult:
    """更新全局配置。

    `exclude_unset=True` 是关键：它让「字段未出现在请求中」与「字段显式传 null」
    被区分开，前者保持原值。这也是把语义定为「未提供 = 不变」所依赖的机制。
    """
    config = get_or_create_config(db)
    _validate_providers(payload)

    changes: dict[str, object] = payload.model_dump(exclude_unset=True, exclude=_API_KEY_FIELDS)

    _apply_provider_defaults(config, changes, provider_field="llm_provider", kind="llm")
    _apply_provider_defaults(config, changes, provider_field="embed_provider", kind="embed")
    _apply_provider_defaults(config, changes, provider_field="rerank_provider", kind="rerank")

    # 先算出「实际发生变化的字段」，再写入。顺序很重要：
    # 写入之后旧值就没了，无法再判断是否真的变化。
    changed_fields = [
        name for name, new_value in changes.items() if getattr(config, name) != new_value
    ]

    for name, new_value in changes.items():
        setattr(config, name, new_value)

    # 处理 API Key：区分「未提供」（保持）、「空字符串」（清除）、「非空」（替换）
    for key_field in _API_KEY_FIELDS:
        if key_field not in payload.model_fields_set:
            continue
        raw_value = getattr(payload, key_field)
        column = _ENCRYPTED_COLUMN_BY_FIELD[key_field]
        if raw_value is None:
            # 显式传 null 视为「不变」，与「未提供」同义，避免前端把 null 当成清除。
            continue
        if raw_value == "":
            setattr(config, column, None)
            changed_fields.append(key_field + "_cleared")
        else:
            setattr(config, column, encrypt_api_key(raw_value))
            # 日志只记录字段名，绝不记录 Key 本身或其长度之外的任何信息。
            changed_fields.append(key_field + "_updated")

    # 记录修改者用于审计（设计文档第 4.2 节的实现要求）。
    config.user_id = current_user.id

    embedding_changed_fields = [name for name in changed_fields if name in _EMBEDDING_FIELDS]

    db.commit()
    db.refresh(config)

    if embedding_changed_fields:
        # Embedding 配置变化会让**所有用户**的向量空间失效，因此标记全部索引。
        # 只标记当前用户是不够的：其他用户会继续用与当前配置不匹配的旧索引检索，
        # 静默返回错误的检索结果，而这种问题极难被发现。
        # 延迟导入避免循环依赖：index_service 也需要读取模型配置。
        from app.services import index_service

        stale_count = index_service.mark_all_stale(db)
        # 同时清空本地模型缓存：换了模型却继续用旧实例，会产出与新索引版本不匹配的向量。
        from app.services.model_loader import reset_model_cache

        reset_model_cache()
        logger.warning(
            "Embedding 配置变更 fields=%s，已标记 %d 个索引为 stale 并清空模型缓存",
            embedding_changed_fields,
            stale_count,
        )

    return ConfigUpdateResult(
        index_stale=bool(embedding_changed_fields),
        changed_fields=changed_fields,
        embedding_changed_fields=embedding_changed_fields,
    )


def build_providers_response() -> dict[str, object]:
    """返回 provider 目录。"""
    return get_catalog()
