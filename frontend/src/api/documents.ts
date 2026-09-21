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
 * `absolutePath: true` 绕过前缀拼接。认证头由 `api/client.ts` 统一注入。
 */

export async function fetchDocuments(
  params: { page?: number; page_size?: number } = {},
): Promise<DocumentListResponse> {
  return request<DocumentListResponse>("/api/docs", {
    absolutePath: true,
    query: { page: params.page ?? 1, page_size: params.page_size ?? 50 },
  });
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResponse>("/api/docs/upload", {
    method: "POST",
    form,
    absolutePath: true,
    // 上传大文件可能超过默认 15 秒超时；服务端是「读完整个文件才返回 202」，
    // 因此超时时间要覆盖上传耗时。
    timeoutMs: 120_000,
  });
}

export async function fetchTask(taskId: string): Promise<TaskResponse> {
  return request<TaskResponse>(`/api/docs/tasks/${encodeURIComponent(taskId)}`, {
    absolutePath: true,
  });
}

export async function deleteDocument(documentId: number): Promise<DeleteDocumentResponse> {
  return request<DeleteDocumentResponse>(`/api/docs/${documentId}`, {
    method: "DELETE",
    absolutePath: true,
  });
}

export async function fetchIndexStatus(): Promise<IndexStatusInfo> {
  return request<IndexStatusInfo>("/api/index/status", {
    absolutePath: true,
    // 该接口会真实探测 Chroma 与 MongoDB 连通性，首次探测可能较慢。
    timeoutMs: 30_000,
  });
}

export async function rebuildIndex(): Promise<RebuildResponse> {
  return request<RebuildResponse>("/api/index/rebuild", {
    method: "POST",
    absolutePath: true,
  });
}
