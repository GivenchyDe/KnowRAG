import { request } from "@/api/client";
import { getAccessToken } from "@/auth/tokenStorage";
import type {
  ChatStreamRequest,
  Conversation,
  ConversationListResponse,
  MessageListResponse,
  SourceItem,
  StreamHandlers,
} from "@/types/chat";

/**
 * 问答与会话接口。
 *
 * 流式接口不能用 `api/client.ts` 的通用 `request`：它会把响应读成完整文本，
 * 而 SSE 需要边到达边处理。因此这里单独实现，但保持与 client 一致的
 * 错误契约解析（`{code, message, trace_id}`）。
 */

function authHeaders(): Record<string, string> {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchConversations(): Promise<ConversationListResponse> {
  return request<ConversationListResponse>("/api/chat/conversations", {
    absolutePath: true,
    headers: authHeaders(),
    query: { page: 1, page_size: 100 },
  });
}

export async function createConversation(title?: string): Promise<Conversation> {
  return request<Conversation>("/api/chat/conversations", {
    method: "POST",
    json: { title: title ?? null },
    absolutePath: true,
    headers: authHeaders(),
  });
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await request<unknown>(`/api/chat/conversations/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
    absolutePath: true,
    headers: authHeaders(),
  });
}

export async function fetchMessages(conversationId: string): Promise<MessageListResponse> {
  return request<MessageListResponse>(
    `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
    { absolutePath: true, headers: authHeaders() },
  );
}

/**
 * 发起流式问答。
 *
 * SSE 解析要点：网络分片不保证按消息边界到达，一个 `data:` 行可能被切成两次收到，
 * 因此必须维护 buffer，只在遇到空行（消息结束）时才解析整条消息。
 * 直接对每个 chunk 做 `split("\n\n")` 是常见错误，会在长回答下偶发 JSON 解析失败。
 */
export async function streamChat(
  payload: ChatStreamRequest,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    // 请求在进入流式之前就失败（如参数错误、未登录），此时响应是普通 JSON 错误体。
    let code = "INTERNAL_ERROR";
    let message = `请求失败（HTTP ${response.status}）`;
    let traceId: string | undefined;
    try {
      const body = (await response.json()) as { code?: string; message?: string; trace_id?: string };
      if (body.code) code = body.code;
      if (body.message) message = body.message;
      traceId = body.trace_id;
    } catch {
      // 响应体不是 JSON，保留默认文案
    }
    handlers.onError?.({ code, message, trace_id: traceId });
    return;
  }

  if (!response.body) {
    handlers.onError?.({ code: "INTERNAL_ERROR", message: "服务未返回响应流" });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });

      // 以空行分隔完整消息；最后一段可能不完整，留在 buffer 里等下一个分片。
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";

      for (const block of blocks) {
        dispatchSseBlock(block, handlers);
      }
    }
    // 流结束时 buffer 里可能还有最后一条没有以空行结尾的消息。
    if (buffer.trim()) {
      dispatchSseBlock(buffer, handlers);
    }
  } finally {
    reader.releaseLock();
  }
}

/** 解析一个 SSE 消息块并分发到对应回调。 */
function dispatchSseBlock(block: string, handlers: StreamHandlers): void {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      // 规范允许 `data:xxx` 与 `data: xxx` 两种写法，统一去掉一个前导空格。
      dataLines.push(line.slice(5).replace(/^ /, ""));
    }
  }

  if (dataLines.length === 0) {
    return;
  }

  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    // 单条消息解析失败不应中断整个流：继续处理后续消息，
    // 否则一次偶发的脏数据会让用户看到回答戛然而止。
    return;
  }

  if (eventName === "token") {
    const text = (payload as { text?: string }).text;
    if (text) handlers.onToken?.(text);
  } else if (eventName === "sources") {
    handlers.onSources?.((payload as { sources?: SourceItem[] }).sources ?? []);
  } else if (eventName === "complete") {
    const data = payload as { trace_id: string; sources?: SourceItem[] };
    handlers.onComplete?.({ trace_id: data.trace_id, sources: data.sources ?? [] });
  } else if (eventName === "error") {
    const data = payload as { code: string; message: string; trace_id?: string };
    handlers.onError?.({ code: data.code, message: data.message, trace_id: data.trace_id });
  }
}
