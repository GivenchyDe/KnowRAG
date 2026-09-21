/**
 * Markdown 安全渲染。
 *
 * 安全边界（`docs/CODING_CONVENTIONS.md` 第 4.4 节：Markdown 渲染必须经过 DOMPurify 清洗）：
 * 回答内容来自 LLM，而 LLM 的内容又可能被用户上传的文档影响（Prompt Injection），
 * 因此这里必须当成**不可信输入**处理。
 *
 * 三层防护，缺一不可：
 * 1. markdown-it 关闭 `html`：让原文里的 `<script>`、`<img onerror=...>` 不被当作 HTML 解析；
 * 2. 链接协议白名单：拦掉 `javascript:` / `data:` 这类可执行协议；
 * 3. DOMPurify 再清洗一遍：即使前两层被绕过（例如 markdown-it 的漏洞），
 *    最终进入 DOM 的字符串仍然经过白名单过滤。
 */

import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";

const md = new MarkdownIt({
  // 关键：不允许原始 HTML。默认值就是 false，这里显式写出以表明这是有意为之，
  // 避免将来有人为了「支持更多格式」把它改成 true。
  html: false,
  // 把换行转成 <br>，模型输出的自然换行才能正确断行。
  breaks: true,
  // 自动识别 http(s) 链接。协议白名单由下面的 validateLink 兜底。
  linkify: true,
  typographer: false,
});

/** 允许的链接协议。 */
const ALLOWED_LINK_SCHEMES = ["http:", "https:", "mailto:"];

const defaultValidateLink = md.validateLink.bind(md);
md.validateLink = (url: string): boolean => {
  const trimmed = url.trim().toLowerCase();
  // 先让 markdown-it 自己的规则判断一次，再用协议白名单二次确认。
  if (!defaultValidateLink(url)) {
    return false;
  }
  if (ALLOWED_LINK_SCHEMES.some((scheme) => trimmed.startsWith(scheme))) {
    return true;
  }
  // 站内相对链接与锚点放行。
  return !trimmed.includes(":");
};

/** DOMPurify 允许的标签与属性。收紧到回答里真正会用到的范围。 */
const PURIFY_CONFIG = {
  ALLOWED_TAGS: [
    "p", "br", "hr", "strong", "em", "del", "code", "pre", "blockquote",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td", "a", "span",
  ],
  ALLOWED_ATTR: ["href", "title", "target", "rel", "class"],
  // 禁止 data-* 属性：回答里不需要，而它们常被用于配合脚本做坏事。
  ALLOW_DATA_ATTR: false,
};

/**
 * 把 Markdown 渲染为可安全插入 DOM 的 HTML。
 */
export function renderMarkdown(source: string): string {
  if (!source) {
    return "";
  }
  const html = md.render(source);
  return DOMPurify.sanitize(html, PURIFY_CONFIG);
}

/**
 * 纯文本预览：去掉 Markdown 标记，用于会话列表标题等场景。
 */
export function stripMarkdown(source: string, maxLength = 60): string {
  const plain = source
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^[>#\-*+]+\s*/gm, "")
    .replace(/[*_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return plain.length > maxLength ? `${plain.slice(0, maxLength)}…` : plain;
}
