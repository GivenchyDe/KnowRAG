"""统一错误定义与异常处理器。

`docs/CODING_CONVENTIONS.md` 第 6.4 节规定错误响应统一为：

    {"code": "...", "message": "...", "trace_id": "..."}

本模块提供错误码枚举、业务异常基类和 FastAPI 异常处理器，
保证 Phase 1 起的任何 router 只要抛出 `AppError` 就自动符合该契约。
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)

# trace_id 由中间件写入 request.state，异常处理器从这里读取，
# 保证错误响应与访问日志使用同一个 trace_id。
TRACE_ID_STATE_KEY = "trace_id"


class ErrorCode(StrEnum):
    """标准错误码。取值必须与 `docs/CODING_CONVENTIONS.md` 第 6.4 节保持一致。"""

    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    INDEX_NOT_READY = "INDEX_NOT_READY"
    INDEX_STALE = "INDEX_STALE"
    MODEL_CONFIG_INVALID = "MODEL_CONFIG_INVALID"
    MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
    INGESTION_FAILED = "INGESTION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# 错误码到默认 HTTP 状态码的映射，避免每个调用点重复指定。
_DEFAULT_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHORIZED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.FORBIDDEN: status.HTTP_403_FORBIDDEN,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.RESOURCE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.INDEX_NOT_READY: status.HTTP_409_CONFLICT,
    ErrorCode.INDEX_STALE: status.HTTP_409_CONFLICT,
    ErrorCode.MODEL_CONFIG_INVALID: status.HTTP_400_BAD_REQUEST,
    ErrorCode.MODEL_PROVIDER_ERROR: status.HTTP_502_BAD_GATEWAY,
    ErrorCode.INGESTION_FAILED: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


class AppError(Exception):
    """业务异常基类。

    抛出本异常即表示“这是一个可预期的业务失败”，其 message 允许直接展示给前端；
    未捕获的其它异常一律按 INTERNAL_ERROR 处理，且不向外暴露堆栈细节。
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status or _DEFAULT_HTTP_STATUS.get(
            code, status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _trace_id_of(request: Request) -> str:
    """从 request.state 取 trace_id；中间件尚未执行时回退为空串。"""
    return str(getattr(request.state, TRACE_ID_STATE_KEY, ""))


def _error_response(request: Request, code: str, message: str, http_status: int) -> JSONResponse:
    """构造统一格式的错误响应。"""
    return JSONResponse(
        status_code=http_status,
        content={"code": code, "message": message, "trace_id": _trace_id_of(request)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """把所有异常处理统一注册到 app。"""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "业务异常 trace_id=%s path=%s code=%s message=%s",
            _trace_id_of(request),
            request.url.path,
            exc.code,
            exc.message,
        )
        return _error_response(request, exc.code, exc.message, exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 安全边界：只回传字段位置和错误类型，不回显输入值。
        # 否则密码、API Key 这类字段会随 422 响应体泄漏到日志或前端。
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.get('loc', ()))}: {error.get('type', '')}"
            for error in exc.errors()
        )
        logger.warning(
            "参数校验失败 trace_id=%s path=%s details=%s",
            _trace_id_of(request),
            request.url.path,
            details,
        )
        return _error_response(
            request,
            ErrorCode.VALIDATION_ERROR,
            "请求参数校验失败",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # 兼容 FastAPI/Starlette 自身抛出的 HTTPException（如 404 路由不存在），
        # 使所有错误出口都符合统一契约。
        code = {
            status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
            status.HTTP_404_NOT_FOUND: ErrorCode.RESOURCE_NOT_FOUND,
            status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
        }.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return _error_response(request, code, str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # 未预期异常只记录服务端，响应体不包含异常细节，防止泄漏内部实现。
        logger.exception(
            "未处理异常 trace_id=%s path=%s error=%s",
            _trace_id_of(request),
            request.url.path,
            type(exc).__name__,
        )
        return _error_response(
            request,
            ErrorCode.INTERNAL_ERROR,
            "服务器内部错误",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
