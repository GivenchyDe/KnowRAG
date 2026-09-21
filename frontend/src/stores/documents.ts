import { computed, ref } from "vue";
import { defineStore } from "pinia";

import * as docsApi from "@/api/documents";
import { toErrorMessage } from "@/types/errors";
import type {
  ActiveTask,
  DocumentItem,
  IndexStatusInfo,
  IngestionStatusValue,
} from "@/types/documents";

/** 轮询间隔。1.5 秒是「用户感知足够快」与「不给后端添压力」的折中。 */
const POLL_INTERVAL_MS = 1500;
/** 单个任务的最长等待时间。超过后停止轮询并提示用户手动刷新。 */
const POLL_TIMEOUT_MS = 10 * 60 * 1000;

/**
 * 文档与索引状态。
 *
 * 轮询设计：用 `setTimeout` 递归而不是 `setInterval`。
 * `setInterval` 在前一次请求未返回时会继续发下一次，任务多时容易堆积请求；
 * 递归定时器保证「上一次结束才排下一次」。
 * 退出本页时必须调用 `stopPolling()`，否则组件卸载后定时器仍在跑。
 *
 * 认证由 `api/client.ts` 统一处理（注入 token、过期提前刷新、401 重试），
 * 本 store 不再需要持有或传递 token。
 */
export const useDocumentStore = defineStore("documents", () => {
  const documents = ref<DocumentItem[]>([]);
  const statusSummary = ref<Record<string, number>>({});
  const indexInfo = ref<IndexStatusInfo | null>(null);
  const activeTasks = ref<ActiveTask[]>([]);

  const loading = ref(false);
  const uploading = ref(false);
  const rebuilding = ref(false);
  const errorMessage = ref<string | null>(null);
  /** 最近一次操作的成功提示，由页面展示后清除。 */
  const noticeMessage = ref<string | null>(null);

  const hasDocuments = computed(() => documents.value.length > 0);
  const isPolling = computed(() => activeTasks.value.length > 0);
  /** 是否正在处理任何文档（上传后到索引完成之间）。 */
  const isBusy = computed(() => uploading.value || isPolling.value);

  let timer: ReturnType<typeof setTimeout> | null = null;
  /** 每个任务的开始时间，用于超时判断。 */
  const taskStartedAt = new Map<string, number>();

  function clearNotice(): void {
    noticeMessage.value = null;
  }

  async function loadDocuments(): Promise<void> {
    loading.value = true;
    try {
      const result = await docsApi.fetchDocuments({ page: 1, page_size: 100 });
      documents.value = result.items;
      statusSummary.value = result.status_summary;
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
      throw error;
    } finally {
      loading.value = false;
    }
  }

  async function loadIndexStatus(): Promise<void> {
    try {
      indexInfo.value = await docsApi.fetchIndexStatus();
    } catch (error) {
      // 索引状态失败不应连带让文档列表也报错：
      // 例如 Chroma 不可用时，用户仍然需要看到自己的文档列表才能排查问题。
      errorMessage.value = toErrorMessage(error);
    }
  }

  async function refreshAll(): Promise<void> {
    errorMessage.value = null;
    await Promise.all([loadDocuments(), loadIndexStatus()]);
  }

  /** 轮询一个任务直到它结束。结束后刷新列表与索引状态。 */
  async function pollTask(task: ActiveTask): Promise<void> {
    const startedAt = taskStartedAt.get(task.taskId) ?? Date.now();

    const tick = async (): Promise<void> => {
      if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
        task.status = "failed";
        task.error = "等待超时，请刷新页面查看最新状态";
        finishTask(task.taskId);
        return;
      }

      try {
        const result = await docsApi.fetchTask(task.taskId);
        task.status = result.status;
        task.progress = result.progress;
        task.error = result.error;
      } catch (error) {
        // 轮询失败（网络抖动、后端重启）不立即放弃：记录错误并继续，
        // 但要给用户可见的提示，避免看起来「卡住了却什么都不说」。
        task.error = toErrorMessage(error);
      }

      if (task.status === "success" || task.status === "failed") {
        finishTask(task.taskId);
        await Promise.all([loadDocuments(), loadIndexStatus()]);
        return;
      }
      scheduleTick(tick);
    };

    scheduleTick(tick);
  }

  function scheduleTick(tick: () => Promise<void>): void {
    if (timer !== null) {
      return;
    }
    timer = setTimeout(() => {
      timer = null;
      void tick();
    }, POLL_INTERVAL_MS);
  }

  function finishTask(taskId: string): void {
    taskStartedAt.delete(taskId);
    activeTasks.value = activeTasks.value.filter((item) => item.taskId !== taskId);
  }

  /** 停止轮询。页面卸载时必须调用。 */
  function stopPolling(): void {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  async function upload(files: File[]): Promise<void> {
    uploading.value = true;
    errorMessage.value = null;
    noticeMessage.value = null;
    const failures: string[] = [];

    for (const file of files) {
      try {
        const result = await docsApi.uploadDocument(file);
        const task: ActiveTask = {
          taskId: result.task_id,
          documentId: result.document_id,
          filename: result.filename,
          status: "pending",
          progress: 0,
          error: null,
        };
        activeTasks.value = [...activeTasks.value, task];
        taskStartedAt.set(result.task_id, Date.now());
        void pollTask(task);
      } catch (error) {
        // 逐个文件记录失败原因并继续处理后续文件：
        // 一个文件不支持格式不应该让整批上传全部中止。
        failures.push(`${file.name}：${toErrorMessage(error)}`);
      }
    }

    uploading.value = false;
    if (failures.length > 0) {
      errorMessage.value = failures.join("；");
    }
    await loadDocuments();
  }

  async function remove(documentId: number): Promise<void> {
    errorMessage.value = null;
    noticeMessage.value = null;
    try {
      const result = await docsApi.deleteDocument(documentId);
      noticeMessage.value = result.message;
      await refreshAll();
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
      throw error;
    }
  }

  async function rebuild(): Promise<void> {
    rebuilding.value = true;
    errorMessage.value = null;
    noticeMessage.value = null;
    try {
      const result = await docsApi.rebuildIndex();
      noticeMessage.value = result.message;
      if (result.task_id) {
        const task: ActiveTask = {
          taskId: result.task_id,
          documentId: 0,
          filename: "索引重建",
          status: "pending",
          progress: 0,
          error: null,
        };
        activeTasks.value = [...activeTasks.value, task];
        taskStartedAt.set(result.task_id, Date.now());
        void pollTask(task);
      }
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
    } finally {
      rebuilding.value = false;
    }
  }

  /** 把任务状态转成展示用的中文标签。 */
  function taskStatusLabel(status: IngestionStatusValue): string {
    if (status === "pending") return "排队中";
    if (status === "running") return "处理中";
    if (status === "success") return "已完成";
    return "失败";
  }

  return {
    documents,
    statusSummary,
    indexInfo,
    activeTasks,
    loading,
    uploading,
    rebuilding,
    errorMessage,
    noticeMessage,
    hasDocuments,
    isPolling,
    isBusy,
    loadDocuments,
    loadIndexStatus,
    refreshAll,
    upload,
    remove,
    rebuild,
    stopPolling,
    clearNotice,
    taskStatusLabel,
  };
});
