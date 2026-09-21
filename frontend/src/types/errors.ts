/**
 * 统一错误码。
 *
 * 取值与 docs/CODING_CONVENTIONS.md 第 6.4 节表格严格一致；
 * 后端 app/core/errors.py 的 ErrorCode 是唯一来源，这里做前端镜像。
 */
export const ErrorCode = {
  UNAUTHORIZED: "UNAUTHORIZED",
  FORBIDDEN: "FORBIDDEN",
  VALIDATION_ERROR: "VALIDATION_ERROR",
  RESOURCE_NOT_FOUND: "RESOURCE_NOT_FOUND",
  INDEX_NOT_READY: "INDEX_NOT_READY",
  INDEX_STALE: "INDEX_STALE",
  MODEL_CONFIG_INVALID: "MODEL_CONFIG_INVALID",
  MODEL_PROVIDER_ERROR: "MODEL_PROVIDER_ERROR",
  INGESTION_FAILED: "INGESTION_FAILED",
  RATE_LIMITED: "RATE_LIMITED",
  INTERNAL_ERROR: "INTERNAL_ERROR",
} as const;

export type ErrorCodeValue = (typeof ErrorCode)[keyof typeof ErrorCode];

/** 后端统一错误响应体：{ code, message, trace_id } */
export interface ApiErrorBody {
  code: string;
  message: string;
  trace_id?: string;
}

/** 前端侧包装后的 API 错误，便于组件统一判断与展示。 */
export class ApiError extends Error {
  readonly code: string;
  readonly traceId: string | undefined;
  readonly httpStatus: number;

  constructor(params: {
    code: string;
    message: string;
    httpStatus: number;
    traceId?: string | undefined;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.code = params.code;
    this.httpStatus = params.httpStatus;
    this.traceId = params.traceId;
  }
}

/** 判断任意异常是否为 ApiError。 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** 把任意异常转换为可展示的文案；trace_id 一并附上便于排查。 */
export function toErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    return error.traceId ? `${error.message}（trace_id: ${error.traceId}）` : error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "未知错误";
}
