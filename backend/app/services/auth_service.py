"""认证业务逻辑。

分层约定（`docs/CODING_CONVENTIONS.md` 第 3.3 节）：router 只负责参数接收与依赖注入，
所有数据库读写、密码校验、token 签发都放在本模块。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.security.jwt import (
    TokenError,
    TokenExpiredError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.security.password import hash_password, verify_password_or_dummy

logger = get_logger(__name__)

# 允许的头像 MIME 类型 → 落盘扩展名。
# 用「MIME 定扩展名」而不是沿用用户上传的文件名：扩展名由服务端决定，
# 用户输入不参与路径拼接（`docs/CODING_CONVENTIONS.md` 第 9 节）。
ALLOWED_AVATAR_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# 反向映射（扩展名 → MIME），用于把嗅探结果换算回 MIME 再与声明值比对。
# 不能拿 ALLOWED_AVATAR_TYPES 直接按扩展名取——那是 MIME → 扩展名 的方向。
_AVATAR_MIME_BY_EXTENSION: dict[str, str] = {
    extension: mime for mime, extension in ALLOWED_AVATAR_TYPES.items()
}

# 头像对外 URL 的前缀（对应 `main.py` 里 StaticFiles 的挂载点）。
#
# 刻意放在 `/api` 之下而不是顶层 `/media`：前端开发环境经 Vite 访问后端，
# 而 Vite 只把 `/api`、`/auth`、`/health` 转发给 FastAPI。顶层路径会被 Vite
# 自己接管并返回 404，表现为「接口 200、Toast 成功，但头像死活不显示」。
AVATAR_URL_PREFIX = "/api/media/avatars"

# 魔数校验：只信 MIME 头是不够的，客户端可以随便声明 Content-Type。
# 校验首字节能挡住「把 .txt 改名成 .png」这类最省事的伪装，
# 不引入 Pillow 也能做到（后端目前没有图片处理依赖）。
_AVATAR_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"RIFF", ".webp"),  # 更严格需再校验第 8-12 字节为 WEBP，见下
)


def _sniff_image_extension(data: bytes) -> str | None:
    """按文件头判断真实格式，无法识别时返回 None。"""
    for magic, extension in _AVATAR_MAGIC:
        if not data.startswith(magic):
            continue
        if extension == ".webp":
            # RIFF 容器有多种格式（wav/avi），必须再看 WEBP 标识
            if len(data) >= 12 and data[8:12] == b"WEBP":
                return extension
            return None
        return extension
    return None


def media_root() -> Path:
    """对外静态资源的根目录（不存在则创建），由 `main.py` 挂载到 `/media`。

    与用户上传统一使用 `settings.upload_dir`，但在其下另起 `media/` 子树：
    `users/<id>/documents/` 是私有的原始文档，绝不能被静态挂载公开，
    因此可公开的图片必须与它分开存放。
    """
    settings = get_settings()
    root = (
        Path(settings.upload_dir)
        if settings.upload_dir.strip()
        else Path(__file__).resolve().parents[2] / "file"
    )
    target = root / "media"
    target.mkdir(parents=True, exist_ok=True)
    return target


def avatar_dir() -> Path:
    """头像落盘目录（不存在则创建）。

    文件名由服务端用随机 UUID 生成，用户输入不参与路径拼接
    （`docs/CODING_CONVENTIONS.md` 第 9 节），因此无需再做路径穿越过滤。
    """
    target = media_root() / "avatars"
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """按主键查询用户。"""
    return db.get(User, user_id)


def get_user_by_username(db: Session, username: str) -> User | None:
    """按用户名查询用户。

    这里使用普通的等值比较，不做 `lower()` 归一化：库的排序规则
    `utf8mb4_0900_ai_ci` 已经保证大小写不敏感匹配，
    应用层再转换一次反而会掩盖排序规则被意外改动的风险。
    """
    return db.scalar(select(User).where(User.username == username))


def get_user_by_email(db: Session, email: str) -> User | None:
    """按邮箱查询用户。大小写行为同上，依赖库级排序规则。"""
    return db.scalar(select(User).where(User.email == email))


def authenticate_user(db: Session, username: str, password: str) -> User:
    """校验用户名密码，成功返回用户对象。

    错误处理策略：
    - 「用户不存在」与「密码错误」返回**完全相同**的错误码与文案，
      避免攻击者通过响应差异枚举出系统中存在哪些用户名；
    - 同时用 `verify_password_or_dummy` 让两条路径都执行一次 bcrypt 校验，
      否则「用户不存在」只需几毫秒而「密码错误」需要约 200ms，
      这个耗时差异本身就能被远程测量出来，使统一文案失去意义；
    - 「账号已禁用」单独提示，因为它不是敏感信息，且用户需要明确原因才能求助。
    """
    user = get_user_by_username(db, username)
    password_ok = verify_password_or_dummy(password, user.hashed_password if user else None)

    if user is None or not password_ok:
        raise AppError(ErrorCode.UNAUTHORIZED, "用户名或密码错误")

    if not user.is_active:
        raise AppError(ErrorCode.FORBIDDEN, "账号已被禁用，请联系管理员")

    return user


def create_user(db: Session, username: str, password: str, email: str | None) -> User:
    """创建用户。

    唯一性检查放在插入前显式查询，而不是捕获数据库的 IntegrityError：
    这样能给出「哪一个字段重复」的明确提示，且不依赖具体驱动抛出的异常形态
    （pymysql 与 psycopg 的异常码并不一致，捕获型实现难以跨驱动复用）。
    """
    if get_user_by_username(db, username) is not None:
        raise AppError(ErrorCode.VALIDATION_ERROR, "该用户名已被注册")

    if email:
        if get_user_by_email(db, email) is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "该邮箱已被注册")

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def issue_tokens(user: User) -> TokenResponse:
    """为用户签发 access + refresh token。"""
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


def refresh_access_token(db: Session, refresh_token: str) -> TokenResponse:
    """用 refresh token 换取新的 token 对。

    这里同时轮换 refresh token（返回新的 refresh_token），而不是原样返回旧的：
    旧 token 在客户端被替换后会自然失效，缩小长期 token 泄漏后的可用窗口。
    """
    try:
        user_id = decode_token(refresh_token, TokenType.REFRESH)
    except TokenExpiredError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, "登录已过期，请重新登录") from exc
    except TokenError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, "刷新凭据无效") from exc

    user = get_user_by_id(db, user_id)
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED, "用户不存在")
    if not user.is_active:
        raise AppError(ErrorCode.FORBIDDEN, "账号已被禁用，请联系管理员")

    return issue_tokens(user)


def update_profile(db: Session, user: User, changes: dict[str, Any]) -> User:
    """按 `changes` 里的字段更新资料。

    只接受调用方**明确要改**的键：`changes` 里没有的字段一律保持原值。
    这样前端可以只提交改动过的字段，也避免了「空值」与「不修改」的歧义
    ——`{"email": None}` 表示清空邮箱，而键不存在表示不动它。

    唯一性检查沿用 `create_user` 的显式查询方式（而不是捕获 IntegrityError）：
    能明确告诉用户是哪个字段重复，也不依赖具体驱动的异常形态。
    与 `create_user` 的差别是必须排除自己——否则「不改用户名直接保存」会被判为重复。
    """
    if "username" in changes:
        new_username = changes["username"]
        if new_username and new_username != user.username:
            existing = get_user_by_username(db, new_username)
            if existing is not None and existing.id != user.id:
                raise AppError(ErrorCode.VALIDATION_ERROR, "该用户名已被占用")
            user.username = new_username

    if "email" in changes:
        new_email = changes["email"] or None
        if new_email != user.email:
            if new_email is not None:
                existing = get_user_by_email(db, new_email)
                if existing is not None and existing.id != user.id:
                    raise AppError(ErrorCode.VALIDATION_ERROR, "该邮箱已被占用")
            user.email = new_email

    db.commit()
    db.refresh(user)
    logger.info("资料已更新 user_id=%s 字段=%s", user.id, sorted(changes))
    return user


def save_avatar(
    db: Session,
    user: User,
    *,
    data: bytes,
    content_type: str | None,
    filename: str | None,
) -> User:
    """校验并保存头像，返回更新后的用户。

    三道校验，缺一不可：
    1. **大小**（调用方按 `max_avatar_bytes` 限长读取，这里再复核一次）；
    2. **声明类型**（Content-Type）在允许列表内；
    3. **真实类型**（文件头魔数）与声明一致 —— 只信 Content-Type 挡不住伪装。

    文件名用随机 UUID：既让 URL 不可枚举，也天然解决了「换了头像但浏览器还在用旧缓存」
    —— URL 变了，缓存自然失效，不需要再拼 `?v=时间戳`。
    """
    settings = get_settings()

    if not data:
        raise AppError(ErrorCode.VALIDATION_ERROR, "上传内容为空")

    max_bytes = settings.max_avatar_bytes
    if len(data) > max_bytes:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"头像不能超过 {max_bytes // (1024 * 1024)}MB",
        )

    # **真实格式由文件头决定，它是唯一的权威。**
    #
    # 这里刻意不再要求「声明类型与文件头一致」。原因：
    #   1. 落盘扩展名用的是下面嗅探出的 `sniffed` 而不是声明的类型，
    #      声明值不参与任何安全决策，"两者必须一致"是多余的要求；
    #   2. 防住「把文本 / HTML / SVG 改名成 .png」靠的是内容嗅探本身
    #      （非图片内容会嗅探失败），与声明值无关；
    #   3. 浏览器是按**扩展名**推断 MIME 的，因此「后缀名不对但内容完好的图片」
    #      （例如下载或截图工具存出来的 `xx.png` 其实是 JPEG）必然出现不一致。
    #      硬性比对会把完全正常的图片挡在门外，而它恰恰是最常见的情况。
    sniffed = _sniff_image_extension(data)
    if sniffed is None:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "这个文件不是有效的图片，请选择 JPG / PNG / WebP 格式的图片文件",
        )

    # 声明类型只用于诊断：客户端声明的与真实格式不符本身不是错误，
    # 但持续出现说明有客户端按扩展名推断 MIME，值得记一条便于排查。
    declared = (content_type or "").split(";")[0].strip().lower()
    actual_mime = _AVATAR_MIME_BY_EXTENSION[sniffed]
    if declared and declared != actual_mime:
        logger.info(
            "头像声明类型与真实格式不一致（按真实格式接收）user_id=%s declared=%s actual=%s file=%s",
            user.id,
            declared,
            actual_mime,
            (filename or "")[:80],
        )

    target = avatar_dir() / f"{uuid.uuid4().hex}{sniffed}"
    target.write_bytes(data)

    previous = user.avatar_url
    # URL 前缀必须是 `/api/media`（而不是顶层 `/media`）：前端开发环境经 Vite 访问，
    # 只有 `/api`、`/auth`、`/health` 会被转发到后端，顶层路径会被 Vite 自己接管并 404。
    user.avatar_url = f"{AVATAR_URL_PREFIX}/{target.name}"
    db.commit()
    db.refresh(user)

    # 换头像后删掉旧文件，避免磁盘上无限堆积孤儿图片。
    # 只删本目录下、由本服务生成的文件：路径来自数据库里的 avatar_url，仍做一次前缀校验，
    # 防止将来某处写入异常值导致误删。
    if previous and previous.startswith(f"{AVATAR_URL_PREFIX}/"):
        old_file = avatar_dir() / Path(previous).name
        try:
            old_file.unlink(missing_ok=True)
        except OSError as exc:  # 删不掉不是致命错误，记一条日志即可
            logger.warning("旧头像清理失败 path=%s error=%s", old_file.name, type(exc).__name__)

    logger.info("头像已更新 user_id=%s size=%d type=%s", user.id, len(data), sniffed)
    return user
