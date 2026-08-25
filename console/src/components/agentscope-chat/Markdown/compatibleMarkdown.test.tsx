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

  it.each(["<br>", "<br/>", "<br />"])(
    "allows the safe line break tag %s inside GFM table cells",
    (lineBreak) => {
      const html = renderCompatibleMarkdownHtml(
        `| A | B |\n| --- | --- |\n| first${lineBreak}second | value |`,
        false,
      );

      expect(html).toContain("<td>first<br>second</td>");
      expect(html).not.toContain("&lt;br");
    },
  );

  it("keeps unsafe HTML escaped when allowing line breaks", () => {
    const html = renderCompatibleMarkdownHtml(
      "safe<br><br onclick=alert(1)><img src=x onerror=alert(1)>",
      false,
    );

    expect(html).toContain("safe<br>");
    expect(html).toContain("&lt;br onclick=alert(1)&gt;");
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(html).not.toContain("<img");
  });
});
