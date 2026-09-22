import { computed, ref, watch } from "vue";
import { defineStore } from "pinia";

import * as chatApi from "@/api/chat";
import { useDocumentStore } from "@/stores/documents";
import { toErrorMessage } from "@/types/errors";
import type { ChatMessage, Conversation, SourceItem } from "@/types/chat";

/**
 * 知识库开关的持久化 key。
 *
 * 只有一个布尔偏好，用 `localStorage` 足够；为此引入 Pinia 持久化插件
 * （及其序列化配置）不划算。
 */
const KNOWLEDGE_PREFERENCE_KEY = "knowrag.chat.knowledgeEnabled";

/**
 * 读取用户上次的知识库开关选择。
 *
 * **默认 `false`**：新用户的知识库通常是空的，默认开启只会让第一次提问必然落空，
 * 所以默认走普通对话，等上传文档后由用户自己打开。
 *
 * 只在取值严格等于 `"true"` 时返回 `true`：这样 `null`（从未写入）与被手工改坏的
 * 任意字符串都会自然退回默认值，不需要额外的合法性校验。
 */
function readKnowledgePreference(): boolean {
  try {
    return window.localStorage.getItem(KNOWLEDGE_PREFERENCE_KEY) === "true";
  } catch {
    // 隐私模式或存储被禁用时访问 `localStorage` 会抛异常。
    // 读不到只是回到默认值，不该让整个 store 初始化失败。
    return false;
  }
}

/** 记住用户的选择。失败时静默忽略——记不住偏好不影响问答本身。 */
function persistKnowledgePreference(value: boolean): void {
  try {
    window.localStorage.setItem(KNOWLEDGE_PREFERENCE_KEY, String(value));
  } catch {
    // 隐私模式、配额已满等情况写不进去，忽略即可。
  }
}

/**
 * 问答状态。
 *
 * 流式过程中的消息只存在于内存（`messages`），**不**随每个 token 写库；
 * 后端在流结束时一次性持久化完整回答。因此刷新页面后看到的是完整回答，
 * 不会出现「库里存着半截回答」。
 */
export const useChatStore = defineStore("chat", () => {
  /**
   * 知识库是否为空需要由文档状态推导，因此这里直接取 documents store。
   *
   * 之所以放在 store 而不是页面里：`knowledge_bool` 的取值只在本 store 的
   * `send()` 里装配，把「库为空就降级」这条规则放在同一处，才能保证
   * 所有调用方（输入框、示例问题、将来的任何入口）行为一致。
   */
  const documents = useDocumentStore();

  const conversations = ref<Conversation[]>([]);
  const conversationId = ref<string>("");
  const messages = ref<ChatMessage[]>([]);
  const streaming = ref(false);
  const loadingConversations = ref(false);
  const loadingMessages = ref(false);
  const errorMessage = ref<string | null>(null);

  /** 最近一次问答的引用来源与 trace_id，供右侧信息面板展示。 */
  const lastSources = ref<SourceItem[]>([]);
  const lastTraceId = ref<string | null>(null);

  /**
   * 用户是否希望使用知识库检索。
   *
   * 这只是**用户的意图**，不等于本轮请求实际会启用检索——知识库为空时会降级，
   * 见 `useKnowledge`。默认关闭，且跨刷新保留用户的显式选择。
   */
  const knowledgeEnabled = ref(readKnowledgePreference());

  watch(knowledgeEnabled, persistKnowledgePreference);

  /** 用于中止流式请求。切换会话或点「停止」时调用 abort。 */
  let controller: AbortController | null = null;
  /** 本地消息 key 的自增序号。 */
  let localSeq = 0;

  const activeConversation = computed(
    () => conversations.value.find((item) => item.conversation_id === conversationId.value) ?? null,
  );
  const isStreaming = computed(() => streaming.value);
  const hasMessages = computed(() => messages.value.length > 0);

  /**
   * 知识库是否**确实**为空。
   *
   * 必须与「索引状态还没读到」区分开：`indexInfo` 为 `null` 表示状态接口尚未返回
   * 或调用失败，此时不能判定为空——否则一次网络抖动就会让本轮问答悄悄跳过检索，
   * 用户拿到一个没有任何文档依据的回答却毫不知情。
   * 只有明确读到 `document_count === 0` 才算空。
   */
  const knowledgeEmpty = computed(
    () => documents.indexInfo !== null && documents.indexInfo.document_count === 0,
  );

  /** 用户开着知识库，但库是空的：本轮实际会降级为普通对话，需要在界面上说明。 */
  const knowledgeDegraded = computed(() => knowledgeEnabled.value && knowledgeEmpty.value);

  /** 本轮请求真正要发给后端的 `knowledge_bool` 取值。 */
  const useKnowledge = computed(() => knowledgeEnabled.value && !knowledgeEmpty.value);

  function nextKey(prefix: string): string {
    localSeq += 1;
    return `${prefix}-${localSeq}`;
  }

  async function loadConversations(): Promise<void> {
    loadingConversations.value = true;
    try {
      const result = await chatApi.fetchConversations();
      conversations.value = result.items;
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
    } finally {
      loadingConversations.value = false;
    }
  }

  /** 新建会话。只创建记录，不立即发消息。 */
  async function newConversation(): Promise<void> {
    stopStreaming();
    try {
      const conversation = await chatApi.createConversation();
      conversationId.value = conversation.conversation_id;
      messages.value = [];
      lastSources.value = [];
      lastTraceId.value = null;
      errorMessage.value = null;
      await loadConversations();
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
    }
  }

  /** 打开一个已有会话，回填历史消息。 */
  async function openConversation(targetId: string): Promise<void> {
    if (targetId === conversationId.value) {
      return;
    }
    stopStreaming();
    conversationId.value = targetId;
    lastSources.value = [];
    lastTraceId.value = null;
    errorMessage.value = null;
    loadingMessages.value = true;
    try {
      const result = await chatApi.fetchMessages(targetId);
      messages.value = result.items.map((item) => ({
        key: nextKey("hist"),
        role: item.role === "user" ? "user" : "assistant",
        content: item.content,
        sources: item.source_entries ?? [],
        traceId: item.trace_id,
      }));
      // 首屏就展示最后一条回答的引用，否则用户点开历史会话后
      // 右侧面板是空的，会以为引用信息没有被保存。
      const lastAssistant = [...messages.value].reverse().find((m) => m.role === "assistant");
      lastSources.value = lastAssistant?.sources ?? [];
      lastTraceId.value = lastAssistant?.traceId ?? null;
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
      messages.value = [];
    } finally {
      loadingMessages.value = false;
    }
  }

  function stopStreaming(): void {
    if (controller) {
      controller.abort();
      controller = null;
    }
    streaming.value = false;
    const last = messages.value[messages.value.length - 1];
    if (last && last.streaming) {
      last.streaming = false;
      if (!last.content) {
        // 一个字都没生成就被中止：直接移除占位气泡，
        // 否则会留下一个空白的气泡让用户困惑。
        messages.value = messages.value.filter((m) => m.key !== last.key);
      }
    }
  }

  async function send(query: string): Promise<void> {
    const text = query.trim();
    if (!text || streaming.value) {
      return;
    }
    if (!conversationId.value) {
      // 首次提问前若还没有会话，先建一个，避免后端靠自动创建产生一个没有标题的会话。
      await newConversation();
    }
    if (!conversationId.value) {
      return;
    }

    errorMessage.value = null;
    lastSources.value = [];
    lastTraceId.value = null;

    messages.value = [
      ...messages.value,
      { key: nextKey("user"), role: "user", content: text, sources: [], traceId: null },
    ];

    const assistant: ChatMessage = {
      key: nextKey("ai"),
      role: "assistant",
      content: "",
      sources: [],
      traceId: null,
      streaming: true,
      error: null,
      // 在发送这一刻定稿：库为空而降级时，回答结束时必须在气泡上说明
      // 「这条没有依据知识库」。若不说，用户会以为内容来自自己的文档。
      degraded: knowledgeDegraded.value,
    };
    messages.value = [...messages.value, assistant];

    streaming.value = true;
    controller = new AbortController();

    try {
      await chatApi.streamChat(
        {
          conversation_id: conversationId.value,
          query: text,
          knowledge_bool: useKnowledge.value,
        },
        {
          onSources: (sources) => {
            assistant.sources = sources;
            lastSources.value = sources;
          },
          onToken: (chunk) => {
            assistant.content += chunk;
          },
          onComplete: ({ trace_id, sources }) => {
            assistant.traceId = trace_id;
            lastTraceId.value = trace_id;
            if (sources.length > 0) {
              assistant.sources = sources;
              lastSources.value = sources;
            }
          },
          onError: ({ message, trace_id }) => {
            // 错误信息挂在 assistant 气泡上而不是全局横幅：
            // 这样用户能看出是哪一次提问失败的，历史消息不会受影响。
            assistant.error = message;
            assistant.traceId = trace_id ?? null;
            errorMessage.value = message;
          },
        },
        controller.signal,
      );
    } catch (error) {
      // abort 触发的异常不是错误，忽略；其余情况记录可读提示。
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        assistant.error = toErrorMessage(error);
        errorMessage.value = assistant.error;
      }
    } finally {
      assistant.streaming = false;
      streaming.value = false;
      controller = null;
      // 流结束后刷新会话列表：标题与更新时间由后端在首条提问时更新。
      await loadConversations();
    }
  }

  async function removeConversation(targetId: string): Promise<void> {
    errorMessage.value = null;
    try {
      await chatApi.deleteConversation(targetId);
      if (targetId === conversationId.value) {
        conversationId.value = "";
        messages.value = [];
        lastSources.value = [];
        lastTraceId.value = null;
      }
      await loadConversations();
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
    }
  }

  function reset(): void {
    stopStreaming();
    conversations.value = [];
    conversationId.value = "";
    messages.value = [];
    lastSources.value = [];
    lastTraceId.value = null;
    errorMessage.value = null;
  }

  return {
    conversations,
    conversationId,
    messages,
    streaming,
    loadingConversations,
    loadingMessages,
    errorMessage,
    lastSources,
    lastTraceId,
    knowledgeEnabled,
    knowledgeEmpty,
    knowledgeDegraded,
    useKnowledge,
    activeConversation,
    isStreaming,
    hasMessages,
    loadConversations,
    newConversation,
    openConversation,
    send,
    stopStreaming,
    removeConversation,
    reset,
  };
});
