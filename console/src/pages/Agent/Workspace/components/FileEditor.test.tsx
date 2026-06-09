import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MarkdownFile } from "../../../../api/types";
import { FileEditor } from "./FileEditor";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("../../../../hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

const selectedFile: MarkdownFile = {
  filename: "PROFILE.md",
  path: "/workspace/PROFILE.md",
  size: 256,
  created_time: "2026-06-08T00:00:00Z",
  modified_time: "2026-06-08T00:00:00Z",
  updated_at: Date.now(),
};

describe("FileEditor", () => {
  it("renders GFM markdown tables in preview mode", () => {
    render(
      <FileEditor
        selectedFile={selectedFile}
        fileContent={[
          "### 基本信息",
          "",
          "| 字段 | 值 |",
          "|------|-----|",
          "| 客户经理CustomerId (agentCustomerId) | 1D66666666 |",
          "| 客户经理工号 (agentId) | SU222 |",
          "| 客户经理名字 (agentName) | 张三 |",
          "| 客户经理编号 (sapId) | 066666 |",
          "| 客户经理ID (ystId) | 188888 |",
        ].join("\n")}
        loading={false}
        hasChanges={false}
        onContentChange={vi.fn()}
        onSave={vi.fn()}
        onReset={vi.fn()}
      />,
    );

    const table = screen.getByRole("table");
    expect(within(table).getByText("字段")).toBeInTheDocument();
    expect(within(table).getByText("客户经理CustomerId (agentCustomerId)")).toBeInTheDocument();
    expect(within(table).getByText("1D66666666")).toBeInTheDocument();
  });
});
