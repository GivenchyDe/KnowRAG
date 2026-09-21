"""文档服务：文件落盘、去重、记录维护。

上传接口只做「校验 + 落盘 + 建记录 + 建任务」，实际的解析与向量化在后台线程里做，
这样大文件上传不会阻塞 HTTP 请求（Phase 3 验收要求）。
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.rag import loaders

logger = get_logger(__name__)

# 分块读取大小。1MB 是读取速度与内存占用的折中：
# 一次性读入 50MB 文件会占用同样大小的内存，并发上传时容易把内存打满。
_READ_CHUNK = 1024 * 1024


@dataclass
class StoredFile:
    """落盘结果。"""

    path: Path
    size_bytes: int
    sha256: str


def user_upload_dir(user_id: int) -> Path:
    """返回该用户的上传目录，不存在则创建。

    按用户分目录是隔离的第一道防线：即使后续某个查询漏写 user_id 条件，
    文件层面也不会互相覆盖。
    """
    settings = get_settings()
    if settings.upload_dir.strip():
        root = Path(settings.upload_dir)
    else:
        root = Path(__file__).resolve().parents[2] / "file"
    target = root / "users" / str(user_id) / "documents"
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_stored_path(user_id: int, original_filename: str) -> Path:
    """生成服务端存储路径。

    安全边界（`docs/CODING_CONVENTIONS.md` 第 9 节：文件保存路径必须由后端生成）：
    文件名改用随机 UUID，只保留**经过白名单校验的扩展名**。
    这样原始文件名里的 `../`、`..\\`、绝对路径、空字节等都无法影响落盘位置，
    不需要额外做路径穿越过滤——因为用户输入根本没有参与路径拼接。
    """
    extension = Path(original_filename).suffix.lower()
    if extension not in loaders.SUPPORTED_EXTENSIONS:
        raise loaders.UnsupportedFileTypeError(original_filename)
    return user_upload_dir(user_id) / f"{uuid.uuid4().hex}{extension}"


def save_upload(user_id: int, original_filename: str, content: bytes) -> StoredFile:
    """把上传内容写入磁盘，返回路径、大小与内容哈希。

    上传内容由路由层一次性读出（已受 `max_upload_bytes` 限制），
    这里做最后一次体积校验并计算 sha256。
    """
    settings = get_settings()
    size = len(content)
    if size == 0:
        raise AppError(ErrorCode.VALIDATION_ERROR, "上传的文件为空")
    if size > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / 1024 / 1024
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"文件过大（{size / 1024 / 1024:.1f}MB），上限为 {limit_mb:.0f}MB",
        )

    target = safe_stored_path(user_id, original_filename)
    target.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    logger.info(
        "文件已保存 user_id=%s stored=%s size=%d sha256=%s",
        user_id,
        target.name,
        size,
        digest[:12],
    )
    return StoredFile(path=target, size_bytes=size, sha256=digest)


def find_duplicate(db: Session, user_id: int, sha256: str) -> Document | None:
    """按内容哈希查找该用户已上传的同一文件。

    同用户内去重：同一份文件重复上传没有意义，会白白消耗 embedding 算力并
    在检索时产生重复片段，人为抬高该文档的命中概率。

    不跨用户去重：其他用户是否上传过同一文件属于隐私信息，
    通过「重复」提示能推断出别人上传过什么。
    """
    return db.scalar(
        select(Document).where(
            Document.user_id == user_id,
            Document.sha256 == sha256,
            Document.status != DocumentStatus.DELETED,
        )
    )


def create_document(
    db: Session,
    *,
    user_id: int,
    original_filename: str,
    stored: StoredFile,
) -> Document:
    """创建文档记录。"""
    document = Document(
        user_id=user_id,
        filename=original_filename,
        stored_path=str(stored.path),
        content_type=loaders.content_type_for(original_filename),
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        status=DocumentStatus.UPLOADED,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session, user_id: int, *, include_deleted: bool = False) -> list[Document]:
    """列出用户的文档。

    始终按 user_id 过滤——这是用户隔离的硬性要求，
    不允许调用方通过传参绕过。
    """
    statement = select(Document).where(Document.user_id == user_id)
    if not include_deleted:
        statement = statement.where(Document.status != DocumentStatus.DELETED)
    return list(db.scalars(statement.order_by(Document.created_at.desc(), Document.id.desc())).all())


def get_document(db: Session, user_id: int, document_id: int) -> Document:
    """取用户自己的文档，不存在或不属于该用户时抛出 404。

    刻意不区分「不存在」与「属于别人」：区分开会让攻击者通过响应差异
    枚举出系统中存在哪些文档 ID。
    """
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )
    if document is None or document.status == DocumentStatus.DELETED:
        raise AppError(ErrorCode.RESOURCE_NOT_FOUND, "文档不存在")
    return document


def remove_stored_file(document: Document) -> None:
    """删除磁盘上的原始文件。

    删除失败只告警不抛错：数据库记录已标记删除，残留文件属于可清理的垃圾，
    不应让用户看到「删除失败」而记录其实已经没了。
    """
    try:
        path = Path(document.stored_path)
        if path.exists():
            path.unlink()
            logger.info("已删除文件 %s", path.name)
    except Exception as exc:
        logger.warning("删除文件失败 path=%s error=%s", document.stored_path, type(exc).__name__)
