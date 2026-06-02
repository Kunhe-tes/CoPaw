import { describe, expect, it } from "vitest";

import { renderCompatibleMarkdownHtml } from "./compatibleMarkdownHtml";

describe("compatible Markdown fallback", () => {
  it("renders GFM tables instead of raw pipe text", () => {
    const html = renderCompatibleMarkdownHtml(
      "| A | B |\n| --- | --- |\n| 1 | 2 |",
      false,
    );

    expect(html).toContain("<table>");
    expect(html).toContain("<td>1</td>");
    expect(html).not.toContain("| --- | --- |");
  });

  it("escapes HTML when allowHtml is false", () => {
    const html = renderCompatibleMarkdownHtml(
      "<script>alert(1)</script>",
      false,
    );

    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });
});
