<script setup lang="ts">
import AppSidebar from "@/components/AppSidebar.vue";

/**
 * 工作台布局：左侧边栏 + 右侧主区。
 *
 * 登录与注册页通过路由 meta.plain 跳过本布局（见 App.vue）。
 */
</script>

<template>
  <div class="shell">
    <AppSidebar />
    <main class="shell__main">
      <!-- 路由视图统一放进滚动容器。
           聊天页自己管理内部滚动（.chat 高 100%，内部 .stream / .panel 各自滚），
           文档/历史/设置页则交给这个容器滚动。
           两种模式能并存的前提是这里必须有**确定**高度，
           否则内层的 overflow-y: auto 全部失效（见 .shell 处说明）。 -->
      <div class="shell__view">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
/**
 * 布局的高度约定（整条「页面不滚动、各区域内部滚动」的链路都建立在这里）。
 *
 * 原先是 `min-height: 100%`，语义是「**至少**一屏、可随内容继续变高」。
 * 于是侧边栏会话变多、消息变多时 `.shell` 就跟着长高，主区高度也随之变成
 * 「内容有多高就多高」——下游所有 `height: 100%` 因为父容器高度不确定而失效，
 * `flex: 1` 也不再收缩，`overflow-y: auto` 因此永远不会被触发，
 * 最终表现为整个页面出现一条滚动条、左右两栏还互相关联。
 *
 * 改法就是给它一个**确定的**视口高度：只要这一层定死，下游的
 * `min-height: 0` + `flex: 1` + `overflow-y: auto` 就会立即按设计生效。
 */
.shell {
  display: flex;
  /* 先用 vh 兜底，再用 dvh 覆盖：移动端浏览器地址栏收放时
     vh 不会跟着变，dvh 才是实际可见高度。不支持的浏览器自动忽略第二行。 */
  height: 100vh;
  height: 100dvh;
  /* 内容一律在内部滚动，shell 自身绝不出现滚动条 */
  overflow: hidden;
  /* 全站卡片语言的"画框"：给页面留出 12px 外边距，侧边栏与主区之间也留 12px，
     这样每一块结构面（侧边栏、顶栏、消息区、右侧面板）都是独立的圆角卡片，
     彼此有均匀的间隙，而不是拼在一起再用分隔线切。
     用 box-sizing: border-box（全局已设），所以 padding 不会把高度撑出视口。 */
  padding: var(--kr-space-3);
  gap: var(--kr-space-3);
}

.shell__main {
  flex: 1;
  min-width: 0;
  /* flex 子项的 min-height 默认是 auto，含义是「不小于内容高度」，
     会把容器重新顶高。必须显式置 0，它才允许收缩到父容器高度以内
     ——这是让子元素能滚动起来的必要条件，漏了它前面所有努力都白费。 */
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/*
 * 路由视图的滚动容器。
 *
 * 需要它是因为各页对高度的诉求不同：聊天页要「自己撑满、内部再分栏滚动」，
 * 文档/历史/设置页则是普通的长页面。统一放在这里滚动，两种页面都不用改，
 * 聊天页因为 `.chat` 正好等于容器高度、不产生溢出，也就不会出现双滚动条。
 */
.shell__view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  /* 这里**刻意不留**滚动条槽位（不用 scrollbar-gutter: stable）。
     槽位会让这一侧的可用宽度少掉 6px，卡片化之后表现为"右边距 18px、左边距 12px"，
     一眼就能看出偏了——而外层 .shell 的 12px 画框本该是四周等宽的。
     动态增长的滚动容器（消息流 .stream、会话列表、右侧面板、输入框）各自保留了槽位，
     那里才是"内容变多时突然出现滚动条导致文字横向跳动"的真正场景；
     页面级只在首次加载后可能滚动一次，代价可以忽略。 */
}
</style>
