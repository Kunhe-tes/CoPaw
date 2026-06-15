import { describe, expect, it } from "vitest";

import { parseToolOutput } from "./CopyFileToStatic";

describe("parseToolOutput", () => {
  it("prefers structured url while keeping filename from markdown path", () => {
    const result = parseToolOutput({
      ok: true,
      path: "![report.html](https://office.example/static/s/a/report.html)",
      url: "https://business.example/static/s/a/report.html",
      network: "business",
      message: "done",
    });

    expect(result).toEqual({
      success: true,
      fileName: "report.html",
      url: "https://business.example/static/s/a/report.html",
    });
  });

  it("keeps parsing the legacy markdown-only output", () => {
    const result = parseToolOutput({
      ok: true,
      path: "![legacy.html](https://office.example/static/s/a/legacy.html)",
      message: "done",
    });

    expect(result).toEqual({
      success: true,
      fileName: "legacy.html",
      url: "https://office.example/static/s/a/legacy.html",
    });
  });

  it("derives filename from structured url when path is absent", () => {
    const result = parseToolOutput({
      ok: true,
      url: "https://business.example/static/s/a/monthly%20report.html",
      network: "business",
      message: "done",
    });

    expect(result).toEqual({
      success: true,
      fileName: "monthly report.html",
      url: "https://business.example/static/s/a/monthly%20report.html",
    });
  });
});
