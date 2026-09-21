"""索引版本管理。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 4.5 节与第 5.5 节。

核心机制：
1. 每个用户的知识库索引带一个自增 `index_version`，集合名为
   `user_{user_id}_kb_v{version}`。**重建时写新集合，成功后再切换**，
   避免在旧集合上原地清空——那样一旦构建失败，用户连旧的可用索引都没了。
2. 索引记录里保存构建它时的 Embedding 配置（provider / model / dimension）与切块参数。
   判断索引是否仍然可用时，把这套参数与**当前配置**逐项比较，
   逐项比较而不是只看 provider 名：换本地模型目录同样会改变向量空间。
3. 由于模型配置在 Phase 2 被设计为**全局一份**，
   Embedding 配置一旦变更，所有用户的索引都会失效（不是只有改配置的人）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.knowledge_base_index import IndexStatus, KnowledgeBaseIndex
from app.models.model_config import ModelConfig

logger = get_logger(__name__)

# 集合名长度上限来自 Chroma 与 MySQL 列宽（varchar(128)）。
_COLLECTION_NAME_TEMPLATE = "user_{user_id}_kb_v{version}"


def collection_name_for(user_id: int, version: int) -> str:
    """构造集合名。"""
    return _COLLECTION_NAME_TEMPLATE.format(user_id=user_id, version=version)


def build_signature(config: ModelConfig) -> str:
    """构造「会影响向量空间」的配置指纹。

    包含本地模型路径：从 bge-m3 换成 bge-large-zh 时 provider 仍是 local、
    模型名可能也被改写为自定义名，只看 provider/model 会漏判，
    导致旧索引被误判为可用，静默返回与新模型不匹配的检索结果。
    """
    settings = get_settings()
    # local 模式下未显式配置路径时，用环境变量里的部署默认值兜底，
    # 保证「同一份配置」始终得出同一个指纹。
    if config.embed_provider == "local":
        model_path = (config.embed_model_path or settings.local_bge_m3_path).strip()
    else:
        model_path = ""
    parts = [
        config.embed_provider,
        config.embed_model,
        str(config.embed_dimension),
        model_path,
    ]
    return "|".join(parts)


def signature_changed(index: KnowledgeBaseIndex, config: ModelConfig) -> bool:
    """索引记录的构建指纹与当前配置是否不一致。

    字符串比较即可，不需要逐列判断——指纹已经涵盖了所有相关参数。
    """
    return index.embedding_signature != build_signature(config)


def get_latest_index(db: Session, user_id: int) -> KnowledgeBaseIndex | None:
    """取用户最新的一条索引记录（无论状态）。"""
    return db.scalar(
        select(KnowledgeBaseIndex)
        .where(KnowledgeBaseIndex.user_id == user_id)
        .order_by(KnowledgeBaseIndex.index_version.desc())
        .limit(1)
    )


def get_ready_index(db: Session, user_id: int, config: ModelConfig) -> KnowledgeBaseIndex | None:
    """取当前**可用**的索引。

    可用 = 状态为 ready，且构建参数与当前配置完全一致。
    同时满足才返回；否则返回 None，由调用方决定是提示重建还是自动重建。
    """
    index = get_latest_index(db, user_id)
    if index is None:
        return None
    if index.status != IndexStatus.READY:
        return None
    if signature_changed(index, config):
        return None
    return index


def ensure_index(db: Session, user_id: int, config: ModelConfig) -> KnowledgeBaseIndex:
    """返回一个状态为 building 的索引记录，用于本次摄取。

    行为：
    - 若已存在参数完全一致且 ready 的索引 → 直接复用（增量上传不新建版本）；
    - 否则新建一条更高版本的记录，状态为 building。

    新版本号取历史最大值 + 1，而不是复用被删掉的版本号：
    Chroma 集合可能残留旧数据，版本号复用会造成新旧向量混入同一集合。
    """
    existing = get_ready_index(db, user_id, config)
    if existing is not None:
        return existing

    latest = get_latest_index(db, user_id)
    next_version = 1 if latest is None else latest.index_version + 1
    settings = get_settings()

    index = KnowledgeBaseIndex(
        user_id=user_id,
        collection_name=collection_name_for(user_id, next_version),
        embedding_provider=config.embed_provider,
        embedding_model=config.embed_model,
        embedding_dimension=config.embed_dimension,
        embedding_signature=build_signature(config),
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        index_version=next_version,
        status=IndexStatus.BUILDING,
    )
    db.add(index)
    db.commit()
    db.refresh(index)
    logger.info(
        "创建索引记录 user_id=%s version=%s collection=%s",
        user_id,
        index.index_version,
        index.collection_name,
    )
    return index


def mark_ready(db: Session, index: KnowledgeBaseIndex) -> None:
    """把索引标记为可用。

    同一用户此前的 ready 索引会被标记为 stale：一个用户同一时间只能有一个
    可用索引，否则检索时不知道该查哪个集合。
    """
    others = db.scalars(
        select(KnowledgeBaseIndex).where(
            KnowledgeBaseIndex.user_id == index.user_id,
            KnowledgeBaseIndex.id != index.id,
            KnowledgeBaseIndex.status == IndexStatus.READY,
        )
    ).all()
    for other in others:
        other.status = IndexStatus.STALE
        logger.info("旧索引已标记为 stale id=%s collection=%s", other.id, other.collection_name)

    index.status = IndexStatus.READY
    db.commit()
    db.refresh(index)


def mark_failed(db: Session, index: KnowledgeBaseIndex) -> None:
    """把索引标记为构建失败。"""
    index.status = IndexStatus.FAILED
    db.commit()


def mark_all_stale(db: Session) -> int:
    """把所有 ready 的索引标记为 stale，返回受影响条数。

    为什么是「所有」而不是「某个用户」：Embedding 配置是全局的，
    配置一变，所有用户的向量空间都失效。若只标记当前用户，
    其他用户会继续用与新配置不匹配的旧索引检索，静默返回错误结果。
    """
    indexes = db.scalars(
        select(KnowledgeBaseIndex).where(KnowledgeBaseIndex.status == IndexStatus.READY)
    ).all()
    for index in indexes:
        index.status = IndexStatus.STALE
    if indexes:
        db.commit()
        logger.warning("Embedding 配置变更，已将 %d 个索引标记为 stale", len(indexes))
    return len(indexes)
