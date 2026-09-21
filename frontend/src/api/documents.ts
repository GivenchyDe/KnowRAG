import { request } from "@/api/client";
import type {
  DeleteDocumentResponse,
  DocumentListResponse,
  IndexStatusInfo,
  RebuildResponse,
  TaskResponse,
  UploadResponse,
} from "@/types/documents";

/**
 * 文档与索引接口。
 *
 * 路径自带 `/api` 前缀，与 `API_BASE_URL` 默认值重复，因此统一用
 * `absolutePath: true` 绕过前缀拼接。
 * 认证头由 store 传入，保持 token 来源单一。
 */

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchDocuments(
  token: string | null,
  params: { page?: number; page_size?: number } = {},
): Promise<DocumentListResponse> {
  return request<DocumentListResponse>("/api/docs", {
    absolutePath: true,
    headers: authHeaders(token),
    query: { page: params.page ?? 1, page_size: params.page_size ?? 50 },
  });
}

export async function uploadDocument(
  token: string | null,
  file: File,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResponse>("/api/docs/upload", {
    method: "POST",
    form,
    absolutePath: true,
    headers: authHeaders(token),
    // 上传大文件可能超过默认 15 秒超时；这里放宽到 2 分钟。
    // 注意服务端是「读完整个文件才返回 202」，因此超时时间要覆盖上传耗时。
    timeoutMs: 120_000,
  });
}

export async function fetchTask(token: string | null, taskId: string): Promise<TaskResponse> {
  return request<TaskResponse>(`/api/docs/tasks/${encodeURIComponent(taskId)}`, {
    absolutePath: true,
    headers: authHeaders(token),
  });
}

export async function deleteDocument(
  token: string | null,
  documentId: number,
): Promise<DeleteDocumentResponse> {
  return request<DeleteDocumentResponse>(`/api/docs/${documentId}`, {
    method: "DELETE",
    absolutePath: true,
    headers: authHeaders(token),
  });
}

export async function fetchIndexStatus(token: string | null): Promise<IndexStatusInfo> {
  return request<IndexStatusInfo>("/api/index/status", {
    absolutePath: true,
    headers: authHeaders(token),
    // 该接口会真实探测 Chroma 与 MongoDB 连通性，首次探测可能较慢。
    timeoutMs: 30_000,
  });
}

export async function rebuildIndex(token: string | null): Promise<RebuildResponse> {
  return request<RebuildResponse>("/api/index/rebuild", {
    method: "POST",
    absolutePath: true,
    headers: authHeaders(token),
  });
}
