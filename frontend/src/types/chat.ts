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
  /** 是否置顶。列表排序为「置顶优先，其次按更新时间」 */
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

/** 修改会话请求，对应 PATCH /api/chat/conversations/{id}。只提交要改的字段。 */
export interface UpdateConversationRequest {
  title?: string;
  is_pinned?: boolean;
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
  /**
   * 本次回答是否因知识库为空而降级为普通对话。
   *
   * 需要在气泡上显式说明：开关仍是开着的，不说明的话用户会以为这条回答
   * 来自自己的文档。刷新后该标记不保留（历史消息由后端提供，后端并不知道
   * 前端做过降级），此时由输入区上方的提示条继续说明当前状态。
   */
  degraded?: boolean;
}

/** SSE 流式回调 */
export interface StreamHandlers {
  onSources?: (sources: SourceItem[]) => void;
  onToken?: (text: string) => void;
  /**
   * 流结束。
   *
   * `content` 是后端给出的**完整回答**。它是可选字段（老后端不发），
   * 存在的意义是兜住「逐 token 累积过程中漏字」的情况：以完整内容为准覆盖，
   * 用户就不必刷新页面才能看到正确的回答。
   */
  onComplete?: (payload: { trace_id: string; sources: SourceItem[]; content?: string }) => void;
  onError?: (payload: { code: string; message: string; trace_id?: string }) => void;
}
