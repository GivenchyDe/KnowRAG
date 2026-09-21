"""密码哈希。

偏离设计文档说明：`docs/DESIGN_IMPLEMENTATION.md` 第 2.1 节写的是 `passlib[bcrypt]`，
这里改为**直接调用 bcrypt 库**，原因：
1. passlib 最后一个正式版本为 1.7.4（2020 年），此后长期未更新；
2. passlib 1.7.4 与本机已装的 bcrypt 5.x 存在已知兼容问题，社区做法是
   要么把 bcrypt 钉到 5 以下，要么移除 passlib 直调 bcrypt；
3. passlib 只是 bcrypt 的薄封装，本项目的需求只有「哈希」与「校验」两个动作，
   直调 bcrypt 无需牺牲任何能力。

安全边界：
- 密码一律以 bcrypt 哈希存储，禁止明文入库，也禁止在日志中打印；
- bcrypt 只处理前 72 字节，超过部分会被静默忽略。为避免「两个不同密码校验通过」，
  这里直接拒绝超过 72 字节的输入，而不是静默截断。
"""

from __future__ import annotations

import bcrypt

# bcrypt 算法本身的输入上限，超出部分会被忽略，因此必须显式拒绝而不是截断。
MAX_PASSWORD_BYTES = 72

# bcrypt 代价因子。12 是当前主流取值：单次哈希约 200-300ms，
# 足以抵抗离线暴力破解，同时不至于让登录接口明显变慢。
_BCRYPT_ROUNDS = 12

# 进程启动时生成一次的哨兵哈希，仅用于在「用户不存在」时消耗与真实校验相当的时间。
# 用真实生成的哈希而不是硬编码常量：硬编码值一旦与 _BCRYPT_ROUNDS 不一致，
# 耗时会与真实路径明显偏离，抹平耗时的目的就失效了。
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode(
    "ascii"
)


def hash_password(password: str) -> str:
    """把明文密码转换为 bcrypt 哈希串。

    返回的字符串形如 `$2b$12$...`，可直接存入 `users.hashed_password`。
    """
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        # 理论上不会走到这里：schema 层已做同样的长度校验并返回 422。
        # 保留此检查是纵深防御，防止将来有调用方绕过 schema 直接调用本函数。
        raise ValueError(f"密码不能超过 {MAX_PASSWORD_BYTES} 字节")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, hashed_password: str) -> bool:
    """校验明文密码与库中哈希是否匹配。

    任何异常（哈希格式损坏、非法 base64 等）都视为校验失败，
    不向调用方抛出，避免登录接口因脏数据返回 500 而泄露内部状态。
    """
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, hashed_password.encode("ascii"))
    except (ValueError, TypeError):
        return False


def verify_password_or_dummy(password: str, hashed_password: str | None) -> bool:
    """在「用户不存在」时也执行一次等价的哈希校验，用于抹平响应耗时。

    背景：bcrypt 校验约 200ms，而「用户不存在」时若直接返回只需几毫秒。
    这个 10 倍以上的耗时差异可以被远程测量出来，从而枚举出系统中存在哪些用户名，
    使 `authenticate_user` 里「用户名或密码错误」的统一文案失去意义。

    这里对 `hashed_password` 为 None 的情况也跑一次真实的 bcrypt 校验
    （对象为一个固定的无效哈希），使两条路径的耗时处于同一量级。
    """
    if hashed_password is None:
        # 对空哈希也做一次真实校验，返回值无意义，只为消耗与正常路径相当的时间。
        verify_password(password, _DUMMY_HASH)
        return False

    return verify_password(password, hashed_password)
