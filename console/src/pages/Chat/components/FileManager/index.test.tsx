import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FileManager from "./index";

const { listDirectory } = vi.hoisted(() => ({ listDirectory: vi.fn() }));

vi.mock("@/api/modules/chat", () => ({
  chatApi: {
    fileManager: {
      listDirectory,
      readFile: vi.fn(),
      saveText: vi.fn(),
      upload: vi.fn(),
      downloadUrl: vi.fn(() => "/download"),
      downloadFile: vi.fn(),
      archive: vi.fn(),
      restore: vi.fn(),
      purge: vi.fn(),
    },
  },
}));

vi.mock("@/components/agentscope-chat/FilePreviewModal/fileUtils", () => ({
  getFileIcon: () => ({ icon: <span>file</span>, color: "#1677ff" }),
  getContentType: () => "text/plain",
}));

vi.mock("@/components/agentscope-chat/Markdown", () => ({ default: () => <div>Markdown</div> }));

const rootPage = {
  root: "working" as const,
  path: "",
  items: [
    {
      name: "docs",
      path: "docs",
      kind: "directory" as const,
      capabilities: { browse: true, read: true, upload: true, edit: true, download: true, archive: true },
    },
  ],
  next_cursor: null,
  has_child_directory: true,
  first_child_directory: "docs",
  capabilities: { browse: true, read: true, upload: true, edit: true, download: true, archive: true },
};

describe("FileManager", () => {
  afterEach(cleanup);
  beforeEach(() => {
    listDirectory.mockReset();
    listDirectory.mockResolvedValue(rootPage);
  });

  it("opens the reference-style overlay with shortcut toolbar and three column roles", async () => {
    render(<FileManager />);

    fireEvent.click(screen.getByRole("button", { name: "文件管理器" }));

    expect(await screen.findByRole("dialog", { name: "文件管理器" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "工作目录" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "上传目录" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下载目录" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "对话目录" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "回收站" })).toBeInTheDocument();
    expect(screen.getByLabelText("文件列表第 1 栏")).toBeInTheDocument();
    expect(screen.getByLabelText("文件列表第 2 栏")).toBeInTheDocument();
    expect(screen.getByLabelText("文件列表第 3 栏")).toBeInTheDocument();
  });

  it("explains why uploads are unavailable in conversation and recycle roots", async () => {
    render(<FileManager />);
    fireEvent.click(screen.getByRole("button", { name: "文件管理器" }));
    await screen.findByRole("dialog", { name: "文件管理器" });

    fireEvent.click(screen.getByRole("button", { name: "对话目录" }));
    expect(await screen.findByText("对话目录仅供浏览，不能上传文件。")).toBeInTheDocument();
  });
});
