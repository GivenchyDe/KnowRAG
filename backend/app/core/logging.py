"""日志配置。

遵守 `docs/CODING_CONVENTIONS.md` 第 8 节：
- 必须能记录 trace_id、user_id、请求路径、耗时、错误码；
- 禁止记录明文密码、明文 API Key、JWT token、Cookie、完整 Authorization header、用户文档全文。

Phase 0 使用标准库 logging，避免为了脚手架引入 structlog 依赖；
Phase 5 增加结构化日志与指标时再评估是否升级。
"""

from __future__ import annotations

import logging
import os
import sys

from app.core.config import Settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _quiet_third_party_progress_bars() -> None:
    """关闭第三方库的进度条与闲聊输出。

    必须在导入 sentence_transformers / transformers / huggingface_hub 之前设置，
    因为它们是在导入时读取这些环境变量的。

    为什么需要：sentence-transformers 每做一次 Rerank 都会往 stderr 写
    `Batches: 100%|██████████| 1/1 [00:01<00:00, 1.07s/it]`。
    一次问答就是一条，批量摄取时会把日志彻底淹没，而且这些内容既不是应用日志、
    也无法通过 logging 配置关掉（它直接写 stderr）。
    """
    os.environ.setdefault("TQDM_DISABLE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # 关闭 Chroma 的匿名遥测。
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


def configure_logging(settings: Settings) -> None:
    """初始化根 logger。应在应用启动时调用一次。"""
    _quiet_third_party_progress_bars()
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

    # httpx 默认按 INFO 记录每一个出站请求。我们通过 httpx 与 Chroma 通信，
    # 一次批量摄取会产生几十条「HTTP Request: POST .../upsert "HTTP/1.1 200 OK"」，
    # 足以把应用自身的日志淹没（实测一条 873 字节的文档就能刷出多条）。
    # 只保留 WARNING 及以上：连接失败等异常仍然可见，正常请求不再刷屏。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Chroma 客户端同样有自己的 INFO 日志。
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    # pymongo 的连接与心跳日志在长连接下会持续输出。
    logging.getLogger("pymongo").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。"""
    return logging.getLogger(name)
