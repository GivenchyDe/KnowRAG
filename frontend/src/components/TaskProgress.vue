<script setup lang="ts">
import type { ActiveTask } from "@/types/documents";

/**
 * 摄取任务进度条。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md` 文档管理页要求「摄取任务进度条」「失败原因展示」。
 * 失败时进度条不再有意义（进度可能停在 60%），因此失败态改为整条红色并展示错误原因，
 * 而不是继续显示一个停在中间的数字——后者会让用户以为还在处理。
 */

defineProps<{
  tasks: ActiveTask[];
  /** 任务状态到中文标签的转换函数，由 store 提供以保证措辞统一 */
  statusLabel: (status: ActiveTask["status"]) => string;
}>();
</script>

<template>
  <section v-if="tasks.length > 0" class="kr-panel panel">
    <h2 class="panel__title">处理进度</h2>
    <ul class="tasks">
      <li v-for="task in tasks" :key="task.taskId" class="task">
        <div class="task__head">
          <span class="task__name">{{ task.filename }}</span>
          <span
            class="kr-badge"
            :class="
              task.status === 'failed'
                ? 'kr-badge--danger'
                : task.status === 'success'
                  ? 'kr-badge--success'
                  : 'kr-badge--neutral'
            "
          >
            <span class="kr-dot"></span>
            {{ statusLabel(task.status) }}
            <template v-if="task.status === 'running'"> {{ task.progress }}%</template>
          </span>
        </div>

        <div class="bar" :class="{ 'bar--failed': task.status === 'failed' }">
          <div
            class="bar__fill"
            :style="{ width: (task.status === 'failed' ? 100 : task.progress) + '%' }"
          ></div>
        </div>

        <p v-if="task.error" class="task__error">{{ task.error }}</p>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.panel {
  padding: var(--kr-space-5);
}

.panel__title {
  font-size: 15px;
  margin-bottom: var(--kr-space-4);
}

.tasks {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-4);
}

.task {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
}

.task__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--kr-space-3);
}

.task__name {
  font-size: 13px;
  word-break: break-all;
  min-width: 0;
}

.bar {
  height: 4px;
  border-radius: var(--kr-radius-pill);
  background: rgba(20, 24, 35, 0.07);
  overflow: hidden;
}

.bar__fill {
  height: 100%;
  background: var(--kr-primary);
  border-radius: var(--kr-radius-pill);
  transition: width 300ms ease;
}

.bar--failed .bar__fill {
  background: var(--kr-danger);
}

.task__error {
  font-size: 12px;
  color: var(--kr-danger);
  word-break: break-word;
}
</style>
