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


def _prepare_third_party_env() -> None:
    """在第三方库导入之前调整环境变量。

    必须尽早调用（`configure_logging` 在应用启动时执行），
    因为这些库是在**导入时或首次构造客户端时**读取环境变量的。

    1. 关闭进度条与闲聊输出。
       sentence-transformers 每做一次 Rerank 都会往 stderr 写
       `Batches: 100%|██████████| 1/1 [00:01<00:00, 1.07s/it]`。
       一次问答就是一条，批量摄取时会把日志彻底淹没；而且它直接写 stderr，
       无法通过 logging 配置关掉。

    2. 让本地回环地址绕过系统代理。**这是必须的**：
       httpx 在 Windows 上会读取注册表里的系统代理设置
       （本机 `ProxyEnable=1`、`ProxyServer=127.0.0.1:7897`），
       而它的 ProxyOverride 解析不支持 `127.*` 这类通配写法，
       于是连 `127.0.0.1` 的请求也会被交给代理。后果是：
       - Chroma 未启动时返回的是**代理的 502 Bad Gateway**，而不是清晰的
         「连接被拒绝」。错误信息完全误导排查方向（实测被带偏两轮，
         还误以为是超时配置写错）；
       - 每次这类请求白等约 2.4 秒的代理超时。

       用 NO_PROXY 而不是清空 HTTP_PROXY：前者只影响本地地址，
       保留了访问外部服务（如模型 API）时走代理的正常能力。
    """
    os.environ.setdefault("TQDM_DISABLE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # 关闭 Chroma 的匿名遥测。
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

    # 本地地址绕过代理。大小写两种写法都设置：不同库的读取方式不一致。
    local_hosts = "127.0.0.1,localhost,::1"
    existing = os.environ.get("NO_PROXY", "")
    if local_hosts not in existing:
        merged = f"{existing},{local_hosts}" if existing else local_hosts
        os.environ["NO_PROXY"] = merged
        os.environ["no_proxy"] = merged


def configure_logging(settings: Settings) -> None:
    """初始化根 logger。应在应用启动时调用一次。"""
    _prepare_third_party_env()
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
