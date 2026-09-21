/**
 * 文档与索引类型。
 *
 * 字段与 `docs/DESIGN_IMPLEMENTATION.md` 第 6.3、6.4 节的 API 契约一一对应，
 * 后端 `backend/app/schemas/documents.py` 是唯一来源。
 */

/** 文档状态。与后端 `DocumentStatus` 保持一致 */
export const DocumentStatus = {
  UPLOADED: "uploaded",
  INDEXED: "indexed",
  FAILED: "failed",
  DELETED: "deleted",
} as const;

export type DocumentStatusValue = (typeof DocumentStatus)[keyof typeof DocumentStatus];

/** 索引状态。与后端 `IndexStatus` 保持一致 */
export const IndexStatus = {
  BUILDING: "building",
  READY: "ready",
  STALE: "stale",
  FAILED: "failed",
} as const;

export type IndexStatusValue = (typeof IndexStatus)[keyof typeof IndexStatus];

/** 摄取任务状态。与后端 `IngestionStatus` 保持一致 */
export const IngestionStatus = {
  PENDING: "pending",
  RUNNING: "running",
  SUCCESS: "success",
  FAILED: "failed",
} as const;

export type IngestionStatusValue = (typeof IngestionStatus)[keyof typeof IngestionStatus];

/** 单个文档，对应 GET /api/docs 的 items 元素 */
export interface DocumentItem {
  id: number;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  status: DocumentStatusValue;
  created_at: string;
  updated_at: string;
}

/** 文档列表响应 */
export interface DocumentListResponse {
  items: DocumentItem[];
  total: number;
  page: number;
  page_size: number;
  status_summary: Record<string, number>;
}

/** 上传响应，对应 POST /api/docs/upload */
export interface UploadResponse {
  document_id: number;
  task_id: string;
  status: IngestionStatusValue;
  filename: string;
  size_bytes: number;
}

/** 摄取任务状态，对应 GET /api/docs/tasks/{task_id} */
export interface TaskResponse {
  task_id: string;
  document_id: number;
  status: IngestionStatusValue;
  progress: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

/** 重建索引响应，对应 POST /api/index/rebuild */
export interface RebuildResponse {
  task_id: string | null;
  status: string;
  message: string;
  document_count: number;
}

/** 索引状态，对应 GET /api/index/status */
export interface IndexStatusInfo {
  status: IndexStatusValue;
  collection_name: string | null;
  index_version: number | null;
  embedding_model: string | null;
  embedding_dimension: number | null;
  chunk_size: number | null;
  chunk_overlap: number | null;
  document_count: number;
  message: string;
  vector_store: Record<string, unknown>;
  doc_store: Record<string, unknown>;
}

/** 删除文档响应 */
export interface DeleteDocumentResponse {
  status: string;
  message: string;
  document_id: number;
}

/** 前端本地维护的「进行中任务」，用于展示进度 */
export interface ActiveTask {
  taskId: string;
  documentId: number;
  filename: string;
  status: IngestionStatusValue;
  progress: number;
  error: string | null;
}
