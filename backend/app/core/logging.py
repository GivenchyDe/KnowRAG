"""日志配置。

遵守 `docs/CODING_CONVENTIONS.md` 第 8 节：
- 必须能记录 trace_id、user_id、请求路径、耗时、错误码；
- 禁止记录明文密码、明文 API Key、JWT token、Cookie、完整 Authorization header、用户文档全文。

Phase 0 使用标准库 logging，避免为了脚手架引入 structlog 依赖；
Phase 5 增加结构化日志与指标时再评估是否升级。
"""

from __future__ import annotations

import logging
import sys

from app.core.config import Settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(settings: Settings) -> None:
    """初始化根 logger。应在应用启动时调用一次。"""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root_logger = logging.getLogger()
    # 先清空既有 handler，避免 uvicorn --reload 重复启动时日志成倍输出。
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # uvicorn 自带 access log 不含 trace_id，统一交给应用中间件记录，避免同一请求出现两套日志。
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。"""
    return logging.getLogger(name)
