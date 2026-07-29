import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FileColumn from "./FileColumn";
import FileManager from "./index";
import FileDetail from "./FileDetail";

const { listDirectory, readFile } = vi.hoisted(() => ({ listDirectory: vi.fn(), readFile: vi.fn() }));

vi.mock("@/api/modules/chat", () => ({
  chatApi: {
    fileManager: {
      listDirectory,
      readFile,
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
    readFile.mockReset();
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

  it("keeps the available 1 MB text visible while marking a truncated preview read-only", () => {
    render(<FileDetail
      entry={{ name: "large.txt", path: "large.txt", kind: "file", capabilities: rootPage.capabilities }}
      preview={{ path: "large.txt", size_bytes: 2_000_000, is_text: true, content: "first megabyte", is_truncated: true, editable: false, revision: "r1" }}
      editable
      onDownload={() => undefined}
      onSave={async () => undefined}
      onArchive={() => undefined}
      onRestore={() => undefined}
      onPurge={() => undefined}
    />);

    expect(screen.getByText("仅预览前 1 MB 内容")).toBeInTheDocument();
    expect(screen.getByText("first megabyte")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
  });

  it("does not render the selected file as a navigable breadcrumb", async () => {
    const docsPage = { ...rootPage, path: "docs", items: [{ name: "note.txt", path: "docs/note.txt", kind: "file" as const, capabilities: rootPage.capabilities }] };
    listDirectory.mockImplementation(({ path }: { path: string }) => Promise.resolve(path === "" ? rootPage : docsPage));
    readFile.mockResolvedValue({ path: "docs/note.txt", size_bytes: 5, is_text: true, content: "hello", is_truncated: false, editable: true, revision: "r1" });
    render(<FileManager />);
    fireEvent.click(screen.getByRole("button", { name: "文件管理器" }));
    await screen.findByRole("button", { name: "note.txt" });

    fireEvent.click(screen.getByRole("button", { name: "note.txt" }));
    await screen.findByRole("region", { name: "文件详情" });
    expect(screen.getAllByRole("button", { name: "note.txt" })).toHaveLength(1);
  });

  it("keeps directory columns compact with an item count and no disclosure arrow", () => {
    render(
      <FileColumn
        column={1}
        directory={rootPage}
        selectedPath={null}
        onSelect={() => undefined}
      />,
    );

    expect(screen.getByText("1 项")).toBeInTheDocument();
    expect(screen.queryByText("工作区")).not.toBeInTheDocument();
    expect(screen.queryByText("›")).not.toBeInTheDocument();
  });

});
