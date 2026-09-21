<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import TaskProgress from "@/components/TaskProgress.vue";
import { useDocumentStore } from "@/stores/documents";
import { IndexStatus } from "@/types/documents";
import type { DocumentItem } from "@/types/documents";

/**
 * 文档管理页。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`「文档管理页」。
 * 必须覆盖的状态：空文档、上传中、解析中、索引成功、索引失败、索引 stale 需重建。
 *
 * 状态来源说明：索引状态**完全来自后端** `/api/index/status`，
 * 前端不自己推断「是否需要重建」——后端已经把配置比对的结果算好并附上了说明文案，
 * 两处各算一次必然会不一致。
 */

const store = useDocumentStore();
const fileInput = ref<HTMLInputElement | null>(null);
const dragActive = ref(false);
const confirmDeleteId = ref<number | null>(null);

const ACCEPT = ".pdf,.docx,.txt,.md,.markdown,.csv";

onMounted(async () => {
  await store.refreshAll();
});

onBeforeUnmount(() => {
  // 必须停止轮询：组件卸载后定时器仍在运行会持续发请求，
  // 且回调里引用的已卸载组件状态可能失效。
  store.stopPolling();
});

function openPicker(): void {
  fileInput.value?.click();
}

async function onFilesPicked(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  input.value = ""; // 清空以便同一文件可以再次选择
  if (files.length > 0) {
    await store.upload(files);
  }
}

async function onDrop(event: DragEvent): Promise<void> {
  dragActive.value = false;
  const files = Array.from(event.dataTransfer?.files ?? []);
  if (files.length > 0) {
    await store.upload(files);
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(raw: string): string {
  // 后端按 UTC 输出且不带时区后缀，补 Z 后再本地化，否则会按时区偏移显示。
  const date = new Date(raw.endsWith("Z") ? raw : `${raw}Z`);
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleString();
}

function documentStatusText(status: DocumentItem["status"]): string {
  if (status === "uploaded") return "待索引";
  if (status === "indexed") return "已索引";
  if (status === "failed") return "失败";
  return "已删除";
}

function documentStatusClass(status: DocumentItem["status"]): string {
  if (status === "indexed") return "kr-badge--success";
  if (status === "failed") return "kr-badge--danger";
  if (status === "uploaded") return "kr-badge--warning";
  return "kr-badge--neutral";
}

/** 索引状态徽标。文案与配色由状态决定，前端不再自行判断是否需要重建。 */
const indexBadgeClass = computed(() => {
  const status = store.indexInfo?.status;
  if (status === IndexStatus.READY) return "kr-badge--success";
  if (status === IndexStatus.BUILDING) return "kr-badge--neutral";
  if (status === IndexStatus.FAILED) return "kr-badge--danger";
  return "kr-badge--warning";
});

const indexStatusText = computed(() => {
  const status = store.indexInfo?.status;
  if (status === IndexStatus.READY) return "索引可用";
  if (status === IndexStatus.BUILDING) return "构建中";
  if (status === IndexStatus.FAILED) return "构建失败";
  return "需要重建";
});

/** 向量库 / 文档存储的连通性，用于排查「索引建不起来」的原因。 */
const infraWarnings = computed(() => {
  const warnings: string[] = [];
  const vs = store.indexInfo?.vector_store as { available?: boolean; error?: string } | undefined;
  const ds = store.indexInfo?.doc_store as { available?: boolean; error?: string } | undefined;
  if (vs && vs.available === false) {
    warnings.push(`向量库不可用：${vs.error ?? "连接失败"}`);
  }
  if (ds && ds.available === false) {
    warnings.push(`文档存储不可用：${ds.error ?? "连接失败"}`);
  }
  return warnings;
});

async function handleDelete(documentId: number): Promise<void> {
  if (confirmDeleteId.value !== documentId) {
    // 两段式确认：删除会同时清理向量与文件，属于不可逆操作，
    // 但用原生 confirm 弹窗会打断工作台体验，因此改为按钮二次点击确认。
    confirmDeleteId.value = documentId;
    return;
  }
  confirmDeleteId.value = null;
  await store.remove(documentId);
}
</script>

<template>
  <div class="docs">
    <header class="page-head">
      <div class="page-head__left">
        <h1 class="page-head__title">文档管理</h1>
        <p class="page-head__desc">
          上传文档后会自动解析、切块并写入向量库，可在此查看处理进度与索引状态。
        </p>
      </div>
      <div class="page-head__right">
        <span class="kr-badge" :class="indexBadgeClass">
          <span class="kr-dot"></span>
          {{ indexStatusText }}
        </span>
        <button
          class="btn btn--ghost"
          type="button"
          :disabled="store.rebuilding || store.isBusy"
          @click="store.rebuild()"
        >
          {{ store.rebuilding ? "提交中…" : "重建索引" }}
        </button>
      </div>
    </header>

    <div class="content">
      <!-- 索引状态与基础设施连通性 -->
      <section v-if="store.indexInfo" class="kr-panel panel">
        <div class="index-row">
          <div class="index-main">
            <span class="index-label">索引状态</span>
            <span class="index-message">{{ store.indexInfo.message }}</span>
          </div>
        </div>
        <dl class="index-meta">
          <div class="index-meta__item">
            <dt>集合</dt>
            <dd>{{ store.indexInfo.collection_name ?? "未创建" }}</dd>
          </div>
          <div class="index-meta__item">
            <dt>版本</dt>
            <dd>{{ store.indexInfo.index_version ?? "-" }}</dd>
          </div>
          <div class="index-meta__item">
            <dt>向量模型</dt>
            <dd>
              {{ store.indexInfo.embedding_model ?? "-" }}
              <template v-if="store.indexInfo.embedding_dimension">
                （{{ store.indexInfo.embedding_dimension }} 维）
              </template>
            </dd>
          </div>
          <div class="index-meta__item">
            <dt>切块</dt>
            <dd>
              <template v-if="store.indexInfo.chunk_size">
                {{ store.indexInfo.chunk_size }} / {{ store.indexInfo.chunk_overlap }}
              </template>
              <template v-else>-</template>
            </dd>
          </div>
          <div class="index-meta__item">
            <dt>已索引文档</dt>
            <dd>{{ store.indexInfo.document_count }}</dd>
          </div>
        </dl>
      </section>

      <p v-for="warning in infraWarnings" :key="warning" class="alert alert--error" role="alert">
        {{ warning }}
      </p>

      <!-- 上传区 -->
      <section
        class="kr-panel dropzone"
        :class="{ 'dropzone--active': dragActive, 'dropzone--disabled': store.uploading }"
        @dragover.prevent="dragActive = true"
        @dragleave.prevent="dragActive = false"
        @drop.prevent="onDrop"
      >
        <input
          ref="fileInput"
          class="dropzone__input"
          type="file"
          multiple
          :accept="ACCEPT"
          @change="onFilesPicked"
        />
        <div class="dropzone__mark" aria-hidden="true">＋</div>
        <p class="dropzone__title">
          {{ store.uploading ? "正在上传…" : "拖拽文件到此处，或" }}
          <button v-if="!store.uploading" class="link" type="button" @click="openPicker">
            选择文件
          </button>
        </p>
        <p class="dropzone__hint">支持 PDF、DOCX、TXT、Markdown、CSV，单文件不超过 50MB</p>
      </section>

      <!-- 处理进度 -->
      <TaskProgress :tasks="store.activeTasks" :status-label="store.taskStatusLabel" />

      <p v-if="store.errorMessage" class="alert alert--error" role="alert">
        {{ store.errorMessage }}
      </p>
      <p v-else-if="store.noticeMessage" class="alert alert--success" role="status">
        {{ store.noticeMessage }}
        <button class="link" type="button" @click="store.clearNotice()">知道了</button>
      </p>

      <!-- 文档列表 -->
      <section class="kr-panel panel">
        <div class="panel__head">
          <h2 class="panel__title">文档列表（{{ store.documents.length }}）</h2>
          <button class="link" type="button" :disabled="store.loading" @click="store.refreshAll()">
            {{ store.loading ? "刷新中…" : "刷新" }}
          </button>
        </div>

        <p v-if="store.loading && !store.hasDocuments" class="state">正在加载…</p>

        <div v-else-if="!store.hasDocuments" class="empty">
          <p class="empty__title">还没有文档</p>
          <p class="empty__desc">上传第一份文档后，系统会自动完成解析与索引，之后即可开始问答。</p>
        </div>

        <!-- 桌面端表格 -->
        <table v-else class="table">
          <thead>
            <tr>
              <th>文件名</th>
              <th class="table__num">大小</th>
              <th>状态</th>
              <th class="table__time">上传时间</th>
              <th class="table__ops">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in store.documents" :key="item.id">
              <td class="table__name" :data-label="item.filename">{{ item.filename }}</td>
              <td class="table__num" data-label="大小">{{ formatSize(item.size_bytes) }}</td>
              <td data-label="状态">
                <span class="kr-badge" :class="documentStatusClass(item.status)">
                  {{ documentStatusText(item.status) }}
                </span>
              </td>
              <td class="table__time" data-label="上传时间">{{ formatTime(item.created_at) }}</td>
              <td class="table__ops">
                <button
                  class="link"
                  :class="{ 'link--danger': confirmDeleteId === item.id }"
                  type="button"
                  @click="handleDelete(item.id)"
                >
                  {{ confirmDeleteId === item.id ? "确认删除？" : "删除" }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>

<style scoped>
.docs {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--kr-space-4);
  padding: var(--kr-space-4) var(--kr-space-5);
  border-bottom: 1px solid var(--kr-border);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.page-head__title {
  font-size: 17px;
}

.page-head__desc {
  margin-top: 3px;
  font-size: 12.5px;
  color: var(--kr-text-secondary);
  max-width: 62ch;
}

.page-head__right {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  flex: none;
}

.content {
  flex: 1;
  width: 100%;
  max-width: 880px;
  margin: 0 auto;
  padding: var(--kr-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-5);
}

.panel {
  padding: var(--kr-space-5);
}

.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--kr-space-3);
  margin-bottom: var(--kr-space-4);
}

.panel__title {
  font-size: 15px;
}

/* --- 索引状态 --- */
.index-row {
  margin-bottom: var(--kr-space-4);
}

.index-label {
  display: block;
  font-size: 12px;
  color: var(--kr-text-muted);
  margin-bottom: 2px;
}

.index-message {
  font-size: 13.5px;
}

.index-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--kr-space-3);
  margin: 0;
  padding-top: var(--kr-space-4);
  border-top: 1px solid var(--kr-border);
}

.index-meta__item dt {
  font-size: 11.5px;
  color: var(--kr-text-muted);
}

.index-meta__item dd {
  margin: 2px 0 0;
  font-size: 13px;
  word-break: break-all;
}

/* --- 上传区 --- */
.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--kr-space-2);
  padding: var(--kr-space-6) var(--kr-space-5);
  text-align: center;
  border-style: dashed;
  border-width: 1px;
  transition:
    border-color var(--kr-transition),
    background var(--kr-transition);
}

.dropzone--active {
  border-color: var(--kr-primary);
  background: var(--kr-primary-soft);
}

.dropzone--disabled {
  opacity: 0.7;
}

.dropzone__input {
  display: none;
}

.dropzone__mark {
  font-size: 22px;
  line-height: 1;
  color: var(--kr-text-muted);
}

.dropzone__title {
  font-size: 13.5px;
}

.dropzone__hint {
  font-size: 12px;
  color: var(--kr-text-muted);
}

/* --- 提示条 --- */
.alert {
  font-size: 13px;
  padding: 10px 14px;
  border-radius: var(--kr-radius);
  display: flex;
  align-items: baseline;
  gap: var(--kr-space-3);
  flex-wrap: wrap;
  word-break: break-word;
}

.alert--error {
  color: var(--kr-danger);
  background: var(--kr-danger-soft);
}

.alert--success {
  color: var(--kr-success);
  background: var(--kr-success-soft);
}

/* --- 空状态 --- */
.empty {
  text-align: center;
  padding: var(--kr-space-5) 0;
}

.empty__title {
  font-size: 14px;
  margin-bottom: var(--kr-space-2);
}

.empty__desc {
  font-size: 12.5px;
  color: var(--kr-text-secondary);
}

.state {
  font-size: 13px;
  color: var(--kr-text-secondary);
  padding: var(--kr-space-4) 0;
}

/* --- 表格 --- */
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.table th {
  text-align: left;
  font-weight: 500;
  font-size: 12px;
  color: var(--kr-text-muted);
  padding: 0 var(--kr-space-3) var(--kr-space-3);
  border-bottom: 1px solid var(--kr-border);
  white-space: nowrap;
}

.table td {
  padding: var(--kr-space-3);
  border-bottom: 1px solid var(--kr-border);
  vertical-align: middle;
}

.table tr:last-child td {
  border-bottom: none;
}

.table__name {
  word-break: break-all;
}

.table__num,
.table__time {
  white-space: nowrap;
  color: var(--kr-text-secondary);
}

.table__ops {
  text-align: right;
  white-space: nowrap;
}

/* --- 按钮与链接 --- */
.btn {
  font: inherit;
  font-weight: 500;
  border-radius: var(--kr-radius);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background var(--kr-transition);
}

.btn--ghost {
  padding: 6px 14px;
  font-size: 12.5px;
  color: var(--kr-text-secondary);
  background: transparent;
  border-color: var(--kr-border-strong);
}

.btn--ghost:hover:not(:disabled) {
  background: rgba(20, 24, 35, 0.04);
  color: var(--kr-text);
}

.btn--ghost:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.link {
  font: inherit;
  font-size: 12.5px;
  padding: 0;
  border: none;
  background: none;
  color: var(--kr-primary);
  cursor: pointer;
}

.link:hover:not(:disabled) {
  text-decoration: underline;
}

.link:disabled {
  color: var(--kr-text-muted);
  cursor: not-allowed;
}

.link--danger {
  color: var(--kr-danger);
}

/* --- 移动端：表格降级为卡片列表（UI_DESIGN_PROMPT 要求）--- */
@media (max-width: 720px) {
  .page-head {
    flex-direction: column;
    padding: var(--kr-space-3) var(--kr-space-4);
  }

  .content {
    padding: var(--kr-space-4);
  }

  .table,
  .table thead,
  .table tbody,
  .table tr,
  .table td {
    display: block;
    width: 100%;
  }

  .table thead {
    display: none;
  }

  .table tr {
    padding: var(--kr-space-3) 0;
    border-bottom: 1px solid var(--kr-border);
  }

  .table tr:last-child {
    border-bottom: none;
  }

  .table td {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--kr-space-3);
    padding: 3px 0;
    border-bottom: none;
    text-align: right;
  }

  /* 窄屏下用 data-label 补上字段名，否则只剩一列值无法辨认 */
  .table td::before {
    content: attr(data-label);
    flex: none;
    font-size: 11.5px;
    color: var(--kr-text-muted);
    text-align: left;
  }

  .table__name {
    text-align: left;
    font-weight: 500;
  }

  .table__ops {
    justify-content: flex-end;
  }
}
</style>
