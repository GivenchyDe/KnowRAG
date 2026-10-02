"""全局模型配置业务逻辑。

核心约定：
1. 本表**只有一行**。`get_or_create_config` 是唯一的读取入口，不存在记录时
   立即用系统默认值创建，而不是返回空配置——否则前端的设置页会是空白，
   用户无从知道当前默认用的是什么模型。
2. API Key 只以密文形态出现在数据库与本模块内部；对外一律经 `mask_api_key` 脱敏。
3. 判断「Embedding 配置是否变化」时，比较 provider、model 与维度
   （见 `_EMBEDDING_FIELDS`）：三者任一变化都会改变向量空间，旧索引必须重建。
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
    resolve_base_url,
    supported_values,
)

logger = get_logger(__name__)

# 会影响向量空间、因而必须重建索引的字段。
# Reranker 相关字段刻意不在此列：重排只作用于检索结果的顺序，
# 不改变入库向量的语义空间，因此只需失效检索器缓存而不必重建索引。
_EMBEDDING_FIELDS: tuple[str, ...] = (
    "embed_provider",
    "embed_model",
    # `embed_dimension` 也在其中（它同样改变向量空间），但请求体里已经没有这个字段：
    # 它由 `index_service.sync_embedding_dimension` 按模型实测值维护，那条路径自己负责
    # 标记索引过期。留在这里是为了让"影响向量空间的字段"这份清单保持完整。
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

    # 默认值来自 provider 目录，保证「数据库默认值」与「前端看到的可选值」同源；
    # 具体选哪个 provider 由环境变量决定（见 `_default_provider`）。
    llm_provider = _default_provider("llm", settings_default="default_llm_provider")
    embed_provider = _default_provider("embed", settings_default="default_embed_provider")
    rerank_provider = _default_provider("rerank", settings_default="default_rerank_provider")

    llm_default = default_for("llm", llm_provider)
    embed_default = default_for("embed", embed_provider)
    rerank_default = default_for("rerank", rerank_provider)

    config = ModelConfig(
        user_id=None,
        llm_provider=llm_provider,
        llm_base_url=llm_default["default_base_url"] if llm_default else None,
        llm_model=llm_default["default_model"] if llm_default else "deepseek-v4-pro",
        embed_provider=embed_provider,
        embed_base_url=embed_default["default_base_url"] if embed_default else None,
        embed_model=embed_default["default_model"] if embed_default else "text-embedding-v4",
        rerank_provider=rerank_provider,
        rerank_base_url=rerank_default["default_base_url"] if rerank_default else None,
        rerank_model=rerank_default["default_model"] if rerank_default else "gte-rerank-v2",
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    logger.info("已创建全局模型配置默认行 id=%s", config.id)
    return config


def _default_provider(kind: str, *, settings_default: str) -> str:
    """取该类别新建配置时使用的 provider。

    为什么要这个函数：默认值应当可运维调整（例如把默认 LLM 从 DeepSeek 换成 Qwen），
    而不是把某个 provider 名写死在创建逻辑里。

    环境变量取值不在目录里时**回退到目录第一项并告警**，而不是抛错：
    一个拼错的变量不该让整个服务起不来。
    """
    settings = get_settings()
    configured = str(getattr(settings, settings_default, "") or "").strip()
    if configured and configured in supported_values(kind):
        return configured

    fallback = get_catalog()[kind][0]["value"]
    if configured:
        logger.warning(
            "%s=%s 不是合法的 %s provider，已回退为 %s（可选值：%s）",
            settings_default.upper(),
            configured,
            kind,
            fallback,
            "、".join(sorted(supported_values(kind))),
        )
    return fallback


def build_config_response(config: ModelConfig) -> dict[str, object]:
    """把 ORM 对象转换为响应字段，负责解密→脱敏。

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

    return {
        "llm_provider": config.llm_provider,
        "llm_api_key_masked": masked(config.llm_api_key_encrypted),
        "llm_base_url": config.llm_base_url,
        "llm_model": config.llm_model,
        "llm_temperature": config.llm_temperature,
        "llm_max_tokens": config.llm_max_tokens,
        "embed_provider": config.embed_provider,
        "embed_api_key_masked": masked(config.embed_api_key_encrypted),
        "embed_base_url": config.embed_base_url,
        "embed_model": config.embed_model,
        "embed_dimension": config.embed_dimension,
        "rerank_provider": config.rerank_provider,
        "rerank_api_key_masked": masked(config.rerank_api_key_encrypted),
        "rerank_base_url": config.rerank_base_url,
        "rerank_model": config.rerank_model,
        "updated_at": config.updated_at,
    }


@dataclass(frozen=True)
class SavedConnectionTarget:
    """连接测试用的一组凭据（来自数据库里已保存的配置）。

    `api_key` 是**解密后的明文**，只允许在内存中传给发起请求的那一处，
    绝不写日志、绝不进响应体。要展示时一律用 `crypto_service.mask_api_key` 脱敏。
    """

    api_key: str
    base_url: str | None
    model: str
    provider: str


# 三个类别各自在配置表里的列名。集中成表，避免三处各写一遍字段名而漏掉某一类。
_SAVED_KEY_COLUMN: dict[str, str] = {
    "llm": "llm_api_key_encrypted",
    "embed": "embed_api_key_encrypted",
    "rerank": "rerank_api_key_encrypted",
}
_SAVED_PROVIDER_FIELD: dict[str, str] = {
    "llm": "llm_provider",
    "embed": "embed_provider",
    "rerank": "rerank_provider",
}
_SAVED_MODEL_FIELD: dict[str, str] = {
    "llm": "llm_model",
    "embed": "embed_model",
    "rerank": "rerank_model",
}
# 三类各自的接口地址列。三个类别都有这一列（2026-10-02 起 Embedding / Reranker
# 也各有一列），因此这里可以用同一套取值逻辑，不必再为某一类写特例。
_SAVED_BASE_URL_FIELD: dict[str, str] = {
    "llm": "llm_base_url",
    "embed": "embed_base_url",
    "rerank": "rerank_base_url",
}


def load_saved_connection_target(db: Session, *, kind: str, provider: str) -> SavedConnectionTarget:
    """读取"已保存的" provider 连接信息，供 `use_saved_key` 的连接测试使用。

    **安全边界（这条比功能更重要）**：返回值里的地址与模型名一律取自数据库/目录，
    **不接受调用方传入的地址**。原因是本项目只有一行全局配置，任何登录用户
    （注册接口是公开的）都能调用测试接口；如果允许请求方指定 base_url，
    就等于让服务器把**全局 API Key 发到任意地址**——那是一条直接的密钥外泄通道。
    只信任服务端保存的值，就不存在这个问题：测试的始终是"已保存的那份配置"。

    另外要求请求的 provider 与已保存的一致：不一致说明库里没有该 provider 的 Key，
    此时报"尚未保存"比拿另一家的 Key 去测更诚实，也避免误报"Key 无效"。

    关于"只能测自己的 Key"：`model_configs` 是**全局单行**配置（设计文档 4.2 节），
    没有按用户分库的 Key，因此本函数不做 `user_id` 过滤——那样的过滤会让人误以为
    存在用户级隔离而实际并不存在。真正的边界是"必须登录"+上一条"地址不由调用方决定"。

    关于 base_url：三类模型各有自己的地址列（`llm_base_url` / `embed_base_url` /
    `rerank_base_url`，后两列于 2026-10-02 加入）。取值为「已保存的地址优先，
    其次目录里的默认地址」；两者都没有时为 `None`——qwen 的向量与重排走的是
    DashScope 专属端点，地址由代码固定，这里**不编一个"看起来能用"的地址出来**
    （那种值会被写进配置、被前端回显，却与实际调用地址无关）。
    对 `provider = custom` 而言两者都会是空，此时构造层会明确报"必须填写接口地址"。
    """
    if kind not in _SAVED_KEY_COLUMN:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"不支持的测试类别：{kind}")

    config = get_or_create_config(db)

    if getattr(config, _SAVED_PROVIDER_FIELD[kind]) != provider:
        raise AppError(
            ErrorCode.MODEL_CONFIG_INVALID,
            "尚未保存该模型的 API Key，请先填写并保存",
        )

    ciphertext = getattr(config, _SAVED_KEY_COLUMN[kind])
    option = default_for(kind, provider)
    # 所有 provider 都是远程服务，库里没有 Key 就是"还没填"，直接拒绝测试。
    if not ciphertext:
        raise AppError(
            ErrorCode.MODEL_CONFIG_INVALID,
            "尚未保存该模型的 API Key，请先填写并保存",
        )

    model = (getattr(config, _SAVED_MODEL_FIELD[kind]) or "").strip() or (
        option["default_model"] if option else ""
    )
    # 已保存的地址优先，其次目录里的默认地址；两者都没有则为 None。
    # custom 的地址必须由用户填，因此这种情况下取到的就是用户保存的那一份，
    # 依然满足"地址不由调用方决定"这条安全前提。
    base_url = resolve_base_url(kind, provider, getattr(config, _SAVED_BASE_URL_FIELD[kind]))

    api_key = decrypt_api_key(ciphertext)
    # 只记脱敏后的形态；密钥的任何完整形态都不进日志（CODING_CONVENTIONS 第 8.2 节）。
    logger.info(
        "连接测试将使用已保存的凭据 kind=%s provider=%s key=%s",
        kind,
        provider,
        mask_api_key(api_key),
    )

    return SavedConnectionTarget(
        api_key=api_key, base_url=base_url, model=model, provider=provider
    )


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

    # 地址同理，三类一致处理。切到 custom 时这里写入的是 None（目录里没有默认地址），
    # 于是上一个 provider 的地址被清掉、界面提示用户填写——而不是留下一份
    # 属于别的 provider 的地址继续生效。
    base_url_field = _SAVED_BASE_URL_FIELD[kind]
    if base_url_field not in changes:
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
        logger.warning(
            "Embedding 配置变更 fields=%s，已标记 %d 个索引为 stale",
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
