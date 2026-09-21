"""API Key 的对称加密与脱敏。

API Key 必须加密入库（`docs/CODING_CONVENTIONS.md` 第 9 节），本模块是唯一的
加解密入口：任何地方都不允许自己拼接密文，也不允许把明文写进日志。

算法说明：Fernet 是 `cryptography` 提供的封装，内部为 AES-128-CBC + HMAC-SHA256，
带时间戳与版本号，属于「带认证的加密」——密文被篡改会在解密时报错，
而不是悄悄解出错误内容。本项目需要的就是这种「加密 + 完整性校验」，
不需要自行组合 AES 与 HMAC。
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CryptoKeyMissingError(RuntimeError):
    """未配置 FERNET_KEY，无法加密或解密。"""


class DecryptError(RuntimeError):
    """密文无法解密：密钥被更换，或数据已被篡改。"""


def _build_fernet() -> Fernet:
    """用配置中的密钥构造 Fernet 实例。

    每次调用都重新读取配置，而不是在模块导入时缓存：
    这样测试可以临时改环境变量，也不依赖导入顺序。
    开销可忽略——Fernet 构造只做一次 base64 解码与长度校验。
    """
    key = get_settings().fernet_key.strip()
    if not key:
        raise CryptoKeyMissingError(
            "未配置 FERNET_KEY，无法保存 API Key。生成方式："
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        # 密钥格式非法（不是 32 字节 urlsafe-base64）时给出可操作的提示，
        # 而不是抛出 cryptography 内部的 ValueError。
        raise CryptoKeyMissingError(
            "FERNET_KEY 格式非法，必须是 32 字节的 urlsafe-base64 字符串"
        ) from exc


def encrypt_api_key(plaintext: str) -> str:
    """加密 API Key，返回可存库的 ASCII 字符串。"""
    return _build_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_api_key(ciphertext: str) -> str:
    """解密 API Key。

    解密失败只说明「密钥不匹配或数据损坏」，不应把原始密文或异常细节暴露给调用方。
    """
    try:
        return _build_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptError("API Key 解密失败：FERNET_KEY 可能已被更换，请重新填写 API Key") from exc


def mask_api_key(value: str | None) -> str | None:
    """把 API Key 脱敏为 `sk-****abcd` 形式，用于接口返回与日志。

    两个细节：
    - 若前 3 位本身以 `-` 结尾（绝大多数供应商的 Key 形如 `sk-xxx`、`sk-...`），
      直接拼接会得到 `sk--****abcd` 这种重复连字符，因此这里先剥掉尾部的 `-`；
    - 短于 8 个字符时不展示任何片段，否则「前 3 位 + 后 4 位」可能覆盖整个密钥，
      脱敏就失去意义了。
    """
    if not value:
        return None
    if len(value) < 8:
        return "****"
    prefix = value[:3].rstrip("-")
    return f"{prefix}-****{value[-4:]}"
