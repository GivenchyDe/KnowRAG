/**
 * 问答与会话类型。
 *
 * 字段与 `docs/DESIGN_IMPLEMENTATION.md` 第 6.5 节的 API 契约一一对应，
 * 后端 `backend/app/schemas/chat.py` 是唯一来源。
 */

/** 引用来源。后端刻意不返回磁盘路径 */
export interface SourceItem {
  document_id: number;
  filename: string;
  chunk_id: string;
  score: number | null;
}

/** 流式问答请求，对应 POST /api/chat/stream */
export interface ChatStreamRequest {
  conversation_id: string;
  query: string;
  knowledge_bool?: boolean;
  model?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
}

/** 会话信息 */
export interface Conversation {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

/** 会话列表响应 */
export interface ConversationListResponse {
  items: Conversation[];
  total: number;
  page: number;
  page_size: number;
}

/** 历史消息 */
export interface MessageItem {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  source_entries: SourceItem[] | null;
  trace_id: string | null;
  created_at: string;
}

/** 消息列表响应 */
export interface MessageListResponse {
  items: MessageItem[];
  total: number;
  conversation_id: string;
}

/** 前端界面使用的消息。比后端模型多两个流式过程中才有的字段 */
export interface ChatMessage {
  /** 本地唯一 ID，用于列表 key 与滚动定位 */
  key: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceItem[];
  traceId: string | null;
  /** 是否正在流式接收（用于显示光标与阻止重复发送） */
  streaming?: boolean;
  /** 该条消息对应的错误提示 */
  error?: string | null;
}

/** SSE 流式回调 */
export interface StreamHandlers {
  onSources?: (sources: SourceItem[]) => void;
  onToken?: (text: string) => void;
  onComplete?: (payload: { trace_id: string; sources: SourceItem[] }) => void;
  onError?: (payload: { code: string; message: string; trace_id?: string }) => void;
}
