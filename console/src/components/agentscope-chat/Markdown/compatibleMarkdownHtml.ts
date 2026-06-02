/**
 * 旧浏览器兜底渲染只处理 Markdown 到安全 HTML 的转换，不绑定 React 上下文。
 */
import DOMPurify from "dompurify";
import { marked } from "marked";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function renderCompatibleMarkdownHtml(
  content: string,
  allowHtml: boolean,
): string {
  const renderer = new marked.Renderer();

  if (!allowHtml) {
    renderer.html = (token: { text?: string; raw?: string }) =>
      escapeHtml(token.text || token.raw || "");
  }

  const html = marked.parse(content, {
    async: false,
    breaks: false,
    gfm: true,
    renderer,
  }) as string;

  return DOMPurify.sanitize(html, {
    ADD_TAGS: ["custom-cursor", "citation"],
  });
}
