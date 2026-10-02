<script setup lang="ts">
import ModelConfigForm from "@/components/ModelConfigForm.vue";

/**
 * 模型设置页。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`「模型设置页」。
 * 页面本身只负责标题与容器，表单逻辑集中在 ModelConfigForm，
 * 避免视图组件承担业务状态（`docs/CODING_CONVENTIONS.md` 第 4.3 节）。
 */
</script>

<template>
  <div class="settings">
    <header class="page-head">
      <div>
        <h1 class="page-head__title">模型设置</h1>
        <p class="page-head__desc">
          配置对话模型、向量模型与重排模型。API Key 由你自己填写，加密后存储，接口只返回脱敏值。
        </p>
      </div>
    </header>

    <div class="page-body">
      <ModelConfigForm />
    </div>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.page-head {
  /* 页头不是"框框"：全站统一卡片语言后，页面里所有带表面的容器都是卡片，
     页头只保留标题与留白，不再是一层带底色的通栏条——否则一屏里会同时出现
     "有底色的条"和"圆角卡片"两种东西。 */
  padding: var(--kr-space-5);
}

.page-head__title {
  font-size: 17px;
}

.page-head__desc {
  margin-top: 3px;
  font-size: 12.5px;
  color: var(--kr-text-secondary);
  max-width: 70ch;
}

.page-body {
  width: 100%;
  max-width: 880px;
  margin: 0 auto;
  padding: var(--kr-space-5);
}

@media (max-width: 640px) {
  .page-head,
  .page-body {
    padding: var(--kr-space-4);
  }
}
</style>
