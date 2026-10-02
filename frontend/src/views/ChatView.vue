<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import ChatInput from "@/components/ChatInput.vue";
import ChatMessage from "@/components/ChatMessage.vue";
import SourceList from "@/components/SourceList.vue";
import { useChatStore } from "@/stores/chat";
import { useConfigStore } from "@/stores/config";
import { useDocumentStore } from "@/stores/documents";
import { useSettingsStore } from "@/stores/settings";
import { IndexStatus } from "@/types/documents";

/**
 * 知识库问答主页面（Phase 4）。
 *
 * 布局依据 `docs/UI_DESIGN_PROMPT.md` 的「AI Chat + Knowledge Base 工作台」：
 * 会话列表在左侧栏（`AppSidebar` 的 chat 分区），中间是聊天流与底部输入区，
 * 右侧是**可选**的开发者信息面板（引用来源、索引状态、trace_id）。
 *
 * 右侧面板的显隐由「通用设置 → 开发者信息」控制（`stores/settings.ts`，
 * 持久化到 localStorage，默认关闭）。之前是在顶栏放一个「隐藏信息」按钮，
 * 已移除：那是**调试开关**，不属于日常问答操作，放在顶栏会一直占位并诱导点击。
 */

const chat = useChatStore();
const configStore = useConfigStore();
const documents = useDocumentStore();
const settings = useSettingsStore();

const scroller = ref<HTMLElement | null>(null);

const indexReady = computed(() => documents.indexInfo?.status === IndexStatus.READY);

const indexMessage = computed(() => documents.indexInfo?.message ?? "正在读取知识库状态…");
const modelLabel = computed(() => {
  const config = configStore.config;
  const override = chat.activeConversation;
  void override;
  if (!config) {
    return "模型读取中…";
  }
  const keyReady = config.llm_api_key_masked !== null;
  return keyReady ? `${config.llm_model} · ${config.llm_provider}` : "未配置 API Key";
});

const panelSources = computed(() => chat.lastSources);

/** 空状态示例问题。点击后直接填入输入框并发送，降低首次使用门槛。 */
const examples = [
  "这份文档的核心结论是什么？",
  "总结一下我上传资料的要点",
  "文档里提到了哪些技术选型？",
] as const;

function handleExample(text: string): void {
  void chat.send(text);
}

/** 自动滚动到底部：流式输出时也要跟着走。 */
async function scrollToBottom(): Promise<void> {
  await nextTick();
  const el = scroller.value;
  if (el) {
    el.scrollTop = el.scrollHeight;
  }
}

watch(() => chat.messages.length, () => void scrollToBottom());
// 监听最后一条消息的内容长度：流式追加时长度持续变化，从而持续滚动。
watch(
  () => chat.messages[chat.messages.length - 1]?.content.length ?? 0,
  () => void scrollToBottom(),
);

async function handleSend(text: string): Promise<void> {
  await chat.send(text);
}

onMounted(async () => {
  await Promise.all([chat.loadConversations(), configStore.load(), documents.loadIndexStatus()]);
  // 默认打开最近一次会话，让用户回到上次的上下文；
  // 没有历史会话时保持空状态，等用户提问时再创建。
  if (!chat.conversationId && chat.conversations.length > 0) {
    await chat.openConversation(chat.conversations[0].conversation_id);
  }
  await scrollToBottom();
});

onBeforeUnmount(() => {
  // 离开页面时中止未完成的流式请求，避免后台继续消耗 token。
  chat.stopStreaming();
});
</script>

<template>
  <div class="chat">
    <header class="topbar">
      <div class="topbar__title">
        <h1>{{ chat.activeConversation?.title ?? "新的对话" }}</h1>
        <!-- 会话 ID 只在「通用设置 → 开发者信息」开启时显示。
             它对普通用户没有任何用途，却一直占着标题下方一行，属于噪音。
             关闭时用 v-if **不渲染**该元素（而不是 CSS 隐藏）：CSS 隐藏的 ID 仍留在 DOM 里，
             随手复制页面源码或截图就会带出去。 -->
        <p v-if="settings.showDevPanel && chat.conversationId" class="topbar__id">
          <code>{{ chat.conversationId }}</code>
        </p>
        <!-- 没有会话时给一句引导。它不是 ID，因此在任何模式下都显示：
             否则标题下方会空一块，用户也不知道标题什么时候才会有内容。 -->
        <p v-else-if="!chat.conversationId" class="topbar__id">提问后会自动创建会话</p>
      </div>
      <div class="topbar__status">
        <span
          class="kr-badge"
          :class="configStore.config?.llm_api_key_masked ? 'kr-badge--success' : 'kr-badge--warning'"
        >
          <span class="kr-dot"></span>
          {{ configStore.config?.llm_api_key_masked ? "模型已配置" : "模型待配置" }}
        </span>
        <span class="kr-badge" :class="indexReady ? 'kr-badge--success' : 'kr-badge--warning'">
          <span class="kr-dot"></span>
          {{ indexReady ? "知识库就绪" : "知识库未就绪" }}
        </span>
      </div>
    </header>

    <div class="body">
      <div class="stream-wrap">
        <div ref="scroller" class="stream">
          <!-- 空状态：欢迎语 + 示例问题 -->
          <div v-if="!chat.hasMessages" class="welcome">
            <div class="welcome__mark" aria-hidden="true">◆</div>
            <h2 class="welcome__title">开始基于你的知识库提问</h2>
            <p class="welcome__desc">{{ indexMessage }}</p>
            <ul class="welcome__examples">
              <li v-for="example in examples" :key="example">
                <button class="example" type="button" @click="handleExample(example)">
                  {{ example }}
                </button>
              </li>
            </ul>
            <p v-if="!indexReady" class="welcome__link">
              <RouterLink to="/documents">去上传文档并建立索引 →</RouterLink>
            </p>
          </div>

          <div v-else class="messages">
            <ChatMessage
              v-for="message in chat.messages"
              :key="message.key"
              :message="message"
              :show-dev-info="settings.showDevPanel"
            />
          </div>
        </div>

        <ChatInput
          :streaming="chat.isStreaming"
          :knowledge-enabled="chat.knowledgeEnabled"
          :model-label="modelLabel"
          :index-ready="indexReady"
          :knowledge-empty="chat.knowledgeEmpty"
          @send="handleSend"
          @stop="chat.stopStreaming()"
          @update:knowledge-enabled="chat.knowledgeEnabled = $event"
        />
      </div>

      <!-- 右侧开发者信息面板：引用来源、索引状态、trace_id。
           显隐由「通用设置 → 开发者信息」控制，默认关闭。
           它是**卡片**，与侧边栏 / 顶栏 / 消息区同一套语言（圆角 16 + 1px 边框 + 毛玻璃 + 轻阴影）；
           高度由 align-self: stretch 撑满可用高度，滚动只发生在内部的 .panel__inner 上。
           过渡用 <Transition> 只对 width / opacity 做动画（见样式里的 .devpanel-*）：
           面板是 flex 行里的固定宽列，宽度动画能让聊天区平滑地接管空间，而不是内容突然跳变。
           这里**不**用 Element Plus 的折叠过渡（el-collapse-transition）：它动的是
           max-height / padding，适合纵向折叠的内容块；对固定宽度的横向列会用错维度。 -->
      <Transition name="devpanel">
        <aside v-if="settings.showDevPanel" class="panel" aria-label="开发者信息">
          <div class="panel__inner">
            <section class="panel__block">
              <h2 class="panel__title">引用来源</h2>
              <SourceList v-if="panelSources.length > 0" :sources="panelSources" compact />
              <p v-else class="panel__empty">提问后这里会显示本次回答依据的文档片段。</p>
            </section>

            <section class="panel__block">
              <h2 class="panel__title">知识库</h2>
              <dl class="panel__meta">
                <div>
                  <dt>状态</dt>
                  <dd>{{ indexReady ? "可用" : "不可用" }}</dd>
                </div>
                <div>
                  <dt>集合</dt>
                  <dd>{{ documents.indexInfo?.collection_name ?? "未创建" }}</dd>
                </div>
                <div>
                  <dt>版本</dt>
                  <dd>{{ documents.indexInfo?.index_version ?? "-" }}</dd>
                </div>
                <div>
                  <dt>已索引文档</dt>
                  <dd>{{ documents.indexInfo?.document_count ?? 0 }}</dd>
                </div>
              </dl>
              <p class="panel__hint">{{ indexMessage }}</p>
            </section>

            <section class="panel__block">
              <h2 class="panel__title">本次问答</h2>
              <dl class="panel__meta">
                <div>
                  <dt>trace_id</dt>
                  <dd>
                    <code v-if="chat.lastTraceId">{{ chat.lastTraceId }}</code>
                    <template v-else>-</template>
                  </dd>
                </div>
                <div>
                  <dt>引用数</dt>
                  <dd>{{ panelSources.length }}</dd>
                </div>
                <div>
                  <dt>检索</dt>
                  <dd>Dense + Rerank</dd>
                </div>
              </dl>
            </section>
          </div>
        </aside>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  /* 顶栏与下方主体之间留出卡片间隙；外边距由 .shell 统一提供 */
  gap: var(--kr-space-3);
}

/* 顶栏：卡片（不再是"通栏 + border-bottom"） */
.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--kr-space-4);
  padding: var(--kr-space-4) var(--kr-space-5);
  border: 1px solid var(--kr-border);
  border-radius: var(--kr-radius-card);
  box-shadow: var(--kr-shadow);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  flex: none;
}

.topbar__title {
  min-width: 0;
}

.topbar__title h1 {
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 46ch;
}

.topbar__id {
  margin-top: 2px;
  font-size: 11px;
  color: var(--kr-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 46ch;
}

.topbar__status {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  flex: none;
}

/* 主区：消息区卡片 + 可选右侧面板卡片，两张卡片之间留 12px 间隙 */
.body {
  flex: 1;
  display: flex;
  min-height: 0;
  gap: var(--kr-space-3);
}

.stream-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 消息区：卡片。滚动发生在这个卡片内部（overflow-y: auto），
   卡片本身的高度由 flex 决定，不受消息多少影响。 */
.stream {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  /* 预留滚动条槽位：消息由少变多时滚动条出现，否则居中的消息列
     会横向偏移 3px（消息区两侧各让出一半宽度）而明显跳动。 */
  scrollbar-gutter: stable;
  padding: var(--kr-space-5);
  border: 1px solid var(--kr-border);
  border-radius: var(--kr-radius-card);
  box-shadow: var(--kr-shadow);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.messages {
  width: 100%;
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-5);
}

/* --- 空状态 --- */
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--kr-space-3);
  text-align: center;
  padding: var(--kr-space-7) var(--kr-space-4);
  max-width: 560px;
  margin: 0 auto;
}

.welcome__mark {
  font-size: 26px;
  color: var(--kr-text-muted);
  line-height: 1;
}

.welcome__title {
  font-size: 17px;
}

.welcome__desc {
  font-size: 12.5px;
  color: var(--kr-text-secondary);
}

.welcome__examples {
  list-style: none;
  margin: var(--kr-space-2) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
  width: 100%;
}

.example {
  font: inherit;
  font-size: 13px;
  width: 100%;
  text-align: left;
  padding: 9px 14px;
  border-radius: var(--kr-radius-btn);
  border: 1px solid var(--kr-border);
  background: var(--kr-panel-solid);
  color: var(--kr-text-secondary);
  cursor: pointer;
  transition:
    border-color var(--kr-transition),
    color var(--kr-transition);
}

.example:hover {
  border-color: var(--kr-primary);
  color: var(--kr-primary);
}

.welcome__link {
  font-size: 12.5px;
  margin-top: var(--kr-space-2);
}

/* --- 右侧开发者信息面板 ---
   卡片：与侧边栏 / 顶栏 / 消息区同一套语言（圆角 16 + 1px 边框 + 毛玻璃 + 轻阴影）。
   之前做成"整块通栏 + border-left"是为了消除"卡片比页面背景更白、内容少时读成漏白"的错觉；
   现在全站统一为卡片语言，卡片本身有四边边框与阴影，边界是明确可见的，
   那个错觉不再存在——所以它回到卡片，与其他区域保持一致。

   高度：`.body` 是行向 flex，靠 `align-self: stretch` 让面板恒等于 `.body` 高度
   （即"顶栏下沿 → 页面底部"，再减去卡片自身的间隙）。**显式写出**而不是依赖默认值：
   默认的 align-items: normal 在 flex 容器里等价于 stretch，但将来若给 `.body`
   加上 align-items 就会静默失效，失效表现正是"面板只有内容那么高"。

   宽度 304px 落在产品要求的 280–320px 区间；`flex: none` 固定宽度，
   聊天区用 flex: 1 + min-width: 0 取剩余空间，不会挤出横向滚动条。 */
.panel {
  flex: none;
  width: 304px;
  align-self: stretch;
  display: flex;
  min-height: 0;
  /* 折叠动画期间裁剪内容：宽度变窄时面板内容不应溢出到聊天区上 */
  overflow: hidden;
  border: 1px solid var(--kr-border);
  border-radius: var(--kr-radius-card);
  box-shadow: var(--kr-shadow);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

/* 滚动容器：撑满 .panel 的整个高度（flex 行向里的 align-self: stretch 同样显式写出），
   内容超长时滚动发生在这里，面板本身的高度不受内容影响。 */
.panel__inner {
  flex: 1;
  align-self: stretch;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  /* 预留滚动条槽位，理由同 .stream：引用条目由少变多时面板内容不应横向抖动 */
  scrollbar-gutter: stable;
  padding: var(--kr-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-5);
}

/* 显隐过渡：只动 width 与 opacity。
   不动 padding —— padding 参与 box-sizing 的宽度计算，一起动会让内容在动画期间被挤压变形。
   全局的 prefers-reduced-motion 已把过渡时长压到 0.01ms，无需在这里再判断。 */
.devpanel-enter-active,
.devpanel-leave-active {
  transition:
    width 220ms ease,
    opacity 180ms ease;
}

.devpanel-enter-from,
.devpanel-leave-to {
  width: 0;
  opacity: 0;
}

.panel__title {
  font-size: 12px;
  font-weight: 500;
  color: var(--kr-text-muted);
  margin-bottom: var(--kr-space-3);
}

.panel__empty,
.panel__hint {
  font-size: 12px;
  line-height: 1.7;
  color: var(--kr-text-muted);
  word-break: break-word;
}

.panel__meta {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
}

.panel__meta div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--kr-space-2);
}

.panel__meta dt {
  font-size: 11.5px;
  color: var(--kr-text-muted);
  flex: none;
}

.panel__meta dd {
  margin: 0;
  font-size: 12px;
  text-align: right;
  word-break: break-all;
  min-width: 0;
}

.panel__meta code {
  font-size: 10.5px;
}

/* 平板端：开发者信息面板收窄但仍可见（它由用户在设置里显式开启，
   不该在中等屏幕上被无声地丢掉）。窄屏时直接隐藏，见下面 900px 的规则。 */
@media (max-width: 1100px) {
  .panel {
    width: 272px;
  }
}

/* 窄屏：开发者信息属于调试信息，不值得为它牺牲阅读宽度。
   **产品已确认**：窄屏就是看不到右侧面板，开关只在宽屏生效——
   此时「通用设置」里的开关仍可切换并会被记住，但面板不会出现。 */
@media (max-width: 900px) {
  .panel {
    display: none;
  }
}

@media (max-width: 640px) {
  .topbar {
    flex-direction: column;
    padding: var(--kr-space-3) var(--kr-space-4);
  }

  .stream {
    padding: var(--kr-space-4);
  }
}
</style>
