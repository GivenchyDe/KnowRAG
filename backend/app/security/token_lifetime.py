"""Token 有效期策略：**7 天上限 + 每月固定日强制过期**。

业务规则（安全要求，勿在别处重复实现或放宽）：

1. 任何 token 签发后最长有效 `TOKEN_MAX_AGE_DAYS` 天（默认 7）；
2. 所有 token 无论何时签发，都必须在「每月 `TOKEN_MONTHLY_EXPIRE_DAY` 号 00:00:00，
   `TOKEN_TIMEZONE` 时区（默认 Asia/Shanghai）」过期；
3. 实际过期时间取两者中**较早**的一个：

       exp = min(签发时间 + 7 天, 签发时间之后的下一个每月 1 号 00:00:00)

4. 签发时间**恰好**是某月 1 号 00:00:00 时，下一个过期点是**下个月** 1 号，
   而不是立即过期（边界是"严格晚于签发时刻"）。

为什么单独成模块：这段逻辑同时被 access / refresh 两条签发路径使用，
且它属于**安全边界**，需要能被单独审阅与测试。散在 `jwt.py` 里容易被后续改动削弱。

时区与月份运算为什么用标准库 `zoneinfo` + 日偏移而不是自己写：
- 手写"月份 +1"必然要处理 12 月跨年、2 月天数不同这两类边界，是最容易出错的地方；
- 时区必须交给 IANA 数据库（`zoneinfo`），否则"上海时间 00:00"会被算成 UTC 00:00，
  实际提前 8 小时过期。

Windows / 精简容器上可能没有系统时区数据库，此时 `zoneinfo` 依赖 PyPI 的 `tzdata` 包
（已显式写入 `requirements.txt`，不要删）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

# 过期时间由哪条规则决定。仅用于日志与诊断，不参与安全判断。
BOUND_BY_MONTHLY = "monthly"
BOUND_BY_MAX_AGE = "max-age"

# 一个月的最大天数。用于「跳过本月、进入下月」的日期推进：
# 从某月 1 号加 31 天必定落在下个月（最短的 2 月也有 28 天），
# 再 replace(day=1) 就得到下个月 1 号——不需要手写月份加减，也就不会漏掉跨年。
_MAX_DAYS_IN_MONTH = 31


def _local_naive(moment: datetime, tz: ZoneInfo) -> datetime:
    """把 aware 时间换算到目标时区的**朴素本地时间**。

    后续的日期运算都在朴素本地时间上做，最后再挂回 tzinfo。
    这样做的原因：aware datetime 直接加 timedelta 时 Python 只按"墙钟"加减、
    不会重算偏移，跨夏令时切换会得到错误的 UTC 时刻；
    在朴素时间上算完再统一 attach 时区，偏移由 zoneinfo 重新决定。
    """
    return moment.astimezone(tz).replace(tzinfo=None)


def next_monthly_boundary(
    issued_at: datetime,
    *,
    expire_day: int,
    tz_name: str,
) -> datetime:
    """返回 `issued_at` **之后**（严格大于）的下一个「每月 expire_day 号 00:00:00」。

    参数 `issued_at` 必须是 aware datetime。返回值是 UTC 的 aware datetime。

    严格大于这一点是需求明确要求的：签发时刻恰好落在边界上时，过期点应推到下个月，
    否则刚签发的 token 会立刻失效（表现为"登录成功但马上又要求登录"）。
    """
    if issued_at.tzinfo is None:
        raise ValueError("issued_at 必须是带时区的时间（aware datetime）")

    tz = ZoneInfo(tz_name)
    local = _local_naive(issued_at, tz)

    # 本月的候选边界 = 本月 1 号 00:00 再往后推 (expire_day - 1) 天
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    candidate = month_start + timedelta(days=expire_day - 1)

    if candidate <= local:
        # 本月边界已过，或正好等于签发时刻（<= 而非 < 就是为了后者）→ 取下一月
        next_month_start = (month_start + timedelta(days=_MAX_DAYS_IN_MONTH)).replace(day=1)
        candidate = next_month_start + timedelta(days=expire_day - 1)

    # 挂上时区得到该墙钟时刻对应的真实瞬间，再统一转 UTC 比较。
    # 注：若 expire_day 落在夏令时"被跳过"的那一小时（如某些时区的 00:00 不存在），
    # zoneinfo 会取切换前的偏移。Asia/Shanghai 自 1991 年起无夏令时，不受影响。
    return candidate.replace(tzinfo=tz).astimezone(UTC)


def compute_token_expiry(
    issued_at: datetime,
    *,
    max_age: timedelta,
    expire_day: int,
    tz_name: str,
) -> tuple[datetime, str]:
    """按策略算出过期时刻，返回 `(exp, 生效的规则)`。

    `max_age` 是**该类型 token 自身的有效期**，调用方需先把全局上限
    （`TOKEN_MAX_AGE_DAYS`）一并折进去，即 max_age = min(类型有效期, 全局上限)。
    """
    cap = issued_at + max_age
    boundary = next_monthly_boundary(issued_at, expire_day=expire_day, tz_name=tz_name)

    # <= 而不是 < ：两者相等时按"月度边界"记账即可，取哪个结果都一样，
    # 但日志里写明是哪条规则生效，排查过期时间异常时会省很多事。
    if boundary <= cap:
        return boundary, BOUND_BY_MONTHLY
    return cap, BOUND_BY_MAX_AGE
