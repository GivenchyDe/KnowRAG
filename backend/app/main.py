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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.errors import TRACE_ID_STATE_KEY, register_exception_handlers
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建 FastAPI 应用实例。

    以工厂函数形式暴露，便于 Phase 5 编写集成测试时为每个用例构造独立 app。
    """
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
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
