"""FastAPI 应用入口。

Phase 0 只提供：
- `GET /health` 健康检查；
- 统一 trace_id、访问日志、错误响应契约、CORS 等基础设施。

不包含任何用户、文档、配置、索引、问答相关路由。
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, get_settings
from app.core.errors import TRACE_ID_STATE_KEY, register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.routers import auth, chat, config, documents, index
from app.services import auth_service, config_service, ingestion_service
from app.services.model_loader import preload_local_models

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期钩子。

    启动时做两件事：
    1. 清理上次进程退出遗留的 pending / running 摄取任务——
       线程池里的任务不会跨进程存活，不清理的话前端会一直轮询一个永不推进的任务；
    2. 在**后台线程**里预热本地模型。实测首次检索约 8 秒，其中 bge-m3 加载占 7.5 秒，
       这 8 秒正好落在用户第一次提问的关键路径上，表现就是「一直卡在正在检索」。
       预热把这段耗时挪到启动阶段，且不阻塞启动（后台线程）。
    """
    reaped = ingestion_service.reap_stale_tasks()
    if reaped:
        logger.warning("启动清理：已将 %d 个中断的摄取任务标记为失败", reaped)

    # 只有本地 provider 才需要预热：远程 provider 不加载本地权重。
    try:
        db = SessionLocal()
        try:
            config = config_service.get_or_create_config(db)
            needs_local = (
                config.embed_provider == "local" or config.rerank_provider == "local"
            )
        finally:
            db.close()
        if needs_local:
            preload_local_models()
        else:
            logger.info("Embedding 与 Reranker 均为远程 provider，跳过本地模型预热")
    except Exception as exc:
        # 预热失败不应阻止应用启动：数据库暂时不可用时也要能把服务拉起来，
        # 否则运维会陷入「连健康检查都看不到，无法判断是库的问题还是代码的问题」。
        logger.warning("启动预热未执行（不影响服务启动）：%s", type(exc).__name__)

    yield
    ingestion_service.shutdown_executor()


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建 FastAPI 应用实例。

    以工厂函数形式暴露，便于 Phase 5 编写集成测试时为每个用例构造独立 app。
    """
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        # 生产环境关闭交互式文档，减少对外暴露的接口信息面。
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # 安全边界：CORS 只允许白名单来源，且必须显式列出方法与请求头，
    # 不使用 allow_origins=["*"]，避免携带凭证的跨站请求被任意站点发起。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Trace-Id"],
    )

    @app.middleware("http")
    async def _trace_and_access_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        """为每个请求生成 trace_id，并记录一条不含敏感信息的访问日志。

        trace_id 同时写入 request.state 与响应头 X-Trace-Id：
        前端拿到错误响应后可以按 trace_id 直接检索后端日志。
        """
        incoming = request.headers.get("X-Trace-Id")
        trace_id = incoming or uuid.uuid4().hex
        setattr(request.state, TRACE_ID_STATE_KEY, trace_id)

        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started_at) * 1000

        response.headers["X-Trace-Id"] = trace_id
        logger.info(
            "trace_id=%s method=%s path=%s status=%s duration_ms=%.1f",
            trace_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    register_exception_handlers(app)

    # 头像等可公开图片的静态服务。
    #
    # 挂在 `/api/media` 而**不是**顶层 `/media`：前端在开发环境通过 Vite 访问，
    # 而 Vite 只把配置过的前缀（/api、/auth、/health）转发给后端。
    # 顶层 `/media` 会被 Vite 自己接管并返回 404 —— 表现就是"后端日志显示上传成功、
    # 前端 Toast 也提示成功，但头像死活不显示"。放在 `/api` 之下就直接复用了
    # 已有的代理规则，开发环境与将来的反向代理都不需要再额外加一条。
    #
    # 只挂载 `file/media`，**不能**挂载 `file/` 整棵子树：后者包含
    # `users/<id>/documents/`，那是用户的私有原始文档，挂上去等于全站公开。
    # 头像文件名是随机 UUID，所以 URL 不可枚举；这是它能安全公开的前提。
    app.mount("/api/media", StaticFiles(directory=str(auth_service.media_root())), name="media")

    # 认证接口按 docs/CODING_CONVENTIONS.md 第 6.1 节挂在 /auth 前缀下。
    app.include_router(auth.router)
    # 配置接口挂在 /api/config 前缀下。
    app.include_router(config.router)
    # 文档与索引接口。
    app.include_router(documents.router)
    app.include_router(index.router)
    # 问答与会话接口。
    app.include_router(chat.router)

    @app.get("/health", tags=["system"], summary="健康检查")
    async def health() -> dict[str, str]:
        """返回服务状态。用于前端连通性检查与容器 healthcheck。"""
        return {"status": "ok"}

    logger.info(
        "应用已初始化 env=%s version=%s cors_origins=%s",
        settings.app_env,
        settings.app_version,
        settings.cors_origin_list,
    )
    if settings.jwt_secret_is_weak:
        # 显式告警而不是静默使用：用弱密钥签发的 JWT 可被伪造，
        # 而接口行为完全正常，问题很难被察觉。
        logger.warning(
            "JWT_SECRET 仍是占位值或长度不足（当前 %d 字节，建议至少 32 字节）。"
            "本地开发可忽略，部署前必须替换："
            'python -c "import secrets; print(secrets.token_urlsafe(48))"',
            len(settings.jwt_secret.encode("utf-8")),
        )
    return app


app = create_app()


if __name__ == "__main__":
    # 便于 `python -m app.main` 直接本地启动，正式启动仍推荐 uvicorn 命令。
    import uvicorn

    _settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=logging.getLevelName(logging.getLogger().level).lower(),
    )
