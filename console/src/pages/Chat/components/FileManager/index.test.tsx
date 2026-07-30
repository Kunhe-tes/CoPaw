import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FileColumn from "./FileColumn";
import FileManager from "./index";
import FileDetail from "./FileDetail";

const { listDirectory, readFile } = vi.hoisted(() => ({
  listDirectory: vi.fn(),
  readFile: vi.fn(),
}));

class ResizeObserverMock {
  observe() {}
  disconnect() {}
  unobserve() {}
}

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

vi.mock("@/components/agentscope-chat/Markdown", () => ({
  default: () => <div>Markdown</div>,
}));

const rootPage = {
  root: "working" as const,
  path: "",
  items: [
    {
      name: "docs",
      path: "docs",
      kind: "directory" as const,
      capabilities: {
        browse: true,
        read: true,
        upload: true,
        edit: true,
        download: true,
        archive: true,
      },
    },
  ],
  next_cursor: null,
  has_child_directory: true,
  first_child_directory: "docs",
  capabilities: {
    browse: true,
    read: true,
    upload: true,
    edit: true,
    download: true,
    archive: true,
  },
};

describe("FileManager", () => {
  afterEach(() => {
    cleanup();
    document.querySelector("[data-chat-shell]")?.remove();
    document.querySelector("[data-chat-messages-area]")?.remove();
    vi.unstubAllGlobals();
  });
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
    listDirectory.mockReset();
    listDirectory.mockResolvedValue(rootPage);
    readFile.mockReset();
  });

  it("opens the reference-style overlay with shortcut toolbar and three column roles", async () => {
    render(<FileManager />);

    fireEvent.click(screen.getByRole("button", { name: "文件管理器" }));

    expect(
      await screen.findByRole("dialog", { name: "文件管理器" }),
    ).toBeInTheDocument();
    const shortcuts = screen.getByRole("navigation", {
      name: "文件目录快捷方式",
    });
    expect(
      within(shortcuts).getByRole("button", { name: "工作目录" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(shortcuts).getByRole("button", { name: "上传目录" }),
    ).toBeInTheDocument();
    expect(
      within(shortcuts).getByRole("button", { name: "下载目录" }),
    ).toBeInTheDocument();
    expect(
      within(shortcuts).getByRole("button", { name: "对话目录" }),
    ).toBeInTheDocument();
    expect(
      within(shortcuts).getByRole("button", { name: "回收站" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("文件列表第 1 栏")).toBeInTheDocument();
    expect(screen.getByLabelText("文件列表第 2 栏")).toBeInTheDocument();
    expect(screen.getByLabelText("文件列表第 3 栏")).toBeInTheDocument();
  });

  it("anchors a shortcut root in the left column before listing its contents in the middle column", async () => {
    const docsPage = {
      ...rootPage,
      path: "docs",
      items: [
        {
          name: "guides",
          path: "docs/guides",
          kind: "directory" as const,
          capabilities: rootPage.capabilities,
        },
      ],
    };
    listDirectory.mockImplementation(({ path }: { path: string }) =>
      Promise.resolve(path === "docs" ? docsPage : rootPage),
    );
    render(<FileManager />);

    fireEvent.click(screen.getByRole("button", { name: "文件管理器" }));

    const left = await screen.findByLabelText("文件列表第 1 栏");
    const middle = screen.getByLabelText("文件列表第 2 栏");
    const right = screen.getByLabelText("文件列表第 3 栏");
    expect(
      within(left).getByRole("button", { name: "工作目录" }),
    ).toBeInTheDocument();
    expect(
      within(middle).getByRole("button", { name: "docs" }),
    ).toBeInTheDocument();
    expect(
      within(right).getByRole("button", { name: "guides" }),
    ).toBeInTheDocument();
  });

  it("backfills the shortcut anchor when a folder is selected from the left column", async () => {
    const rootWithProjects = {
      ...rootPage,
      items: [
        {
          name: "docs",
          path: "docs",
          kind: "directory" as const,
          capabilities: rootPage.capabilities,
        },
        {
          name: "projects",
          path: "projects",
          kind: "directory" as const,
          capabilities: rootPage.capabilities,
        },
      ],
    };
    const docsPage = {
      ...rootPage,
      path: "docs",
      items: [
        {
          name: "guides",
          path: "docs/guides",
          kind: "directory" as const,
          capabilities: rootPage.capabilities,
        },
      ],
    };
    const guidesPage = {
      ...rootPage,
      path: "docs/guides",
      items: [
        {
          name: "chapter.md",
          path: "docs/guides/chapter.md",
          kind: "file" as const,
          capabilities: rootPage.capabilities,
        },
      ],
    };
    const projectsPage = {
      ...rootPage,
      path: "projects",
      items: [
        {
          name: "plan.md",
          path: "projects/plan.md",
          kind: "file" as const,
          capabilities: rootPage.capabilities,
        },
      ],
    };
    listDirectory.mockImplementation(({ path }: { path: string }) =>
      Promise.resolve(
        {
          "": rootWithProjects,
          docs: docsPage,
          "docs/guides": guidesPage,
          projects: projectsPage,
        }[path] || rootWithProjects,
      ),
    );
    render(<FileManager />);

    fireEvent.click(screen.getByRole("button", { name: "文件管理器" }));
    const right = await screen.findByLabelText("文件列表第 3 栏");
    fireEvent.click(
      await within(right).findByRole("button", { name: "guides" }),
    );
    fireEvent.click(
      await within(screen.getByLabelText("文件列表第 1 栏")).findByRole(
        "button",
        { name: "projects" },
      ),
    );

    expect(
      await within(screen.getByLabelText("文件列表第 1 栏")).findByRole(
        "button",
        { name: "工作目录" },
      ),
    ).toBeInTheDocument();
    expect(
      await within(screen.getByLabelText("文件列表第 2 栏")).findByRole(
        "button",
        { name: "projects" },
      ),
    ).toBeInTheDocument();
    expect(
      await within(screen.getByLabelText("文件列表第 3 栏")).findByRole(
        "button",
        { name: "plan.md" },
      ),
    ).toBeInTheDocument();
  });

  it("moves the right directory into the middle column before loading its child", async () => {
    const docsPage = {
      ...rootPage,
      path: "docs",
      items: [
        {
          name: "guides",
          path: "docs/guides",
          kind: "directory" as const,
          capabilities: rootPage.capabilities,
        },
      ],
    };
    const guidesPage = {
      ...rootPage,
      path: "docs/guides",
      items: [
        {
          name: "chapter.md",
          path: "docs/guides/chapter.md",
          kind: "file" as const,
          capabilities: rootPage.capabilities,
        },
      ],
    };
    listDirectory.mockImplementation(({ path }: { path: string }) =>
      Promise.resolve(
        path === "docs"
          ? docsPage
          : path === "docs/guides"
          ? guidesPage
          : rootPage,
      ),
    );
    render(<FileManager />);

    fireEvent.click(screen.getByRole("button", { name: "文件管理器" }));
    const right = await screen.findByLabelText("文件列表第 3 栏");
    fireEvent.click(
      await within(right).findByRole("button", { name: "guides" }),
    );

    expect(
      await within(screen.getByLabelText("文件列表第 1 栏")).findByRole(
        "button",
        { name: "docs" },
      ),
    ).toBeInTheDocument();
    expect(
      await within(screen.getByLabelText("文件列表第 2 栏")).findByRole(
        "button",
        { name: "guides" },
      ),
    ).toBeInTheDocument();
    expect(
      await within(screen.getByLabelText("文件列表第 3 栏")).findByRole(
        "button",
        { name: "chapter.md" },
      ),
    ).toBeInTheDocument();
  });

  it("uses the full chat shell width instead of only the message area", async () => {
    const chatShell = document.createElement("div");
    chatShell.dataset.chatShell = "";
    vi.spyOn(chatShell, "getBoundingClientRect").mockReturnValue({
      left: 80,
      top: 0,
      right: 980,
      bottom: 800,
      width: 900,
      height: 800,
      x: 80,
      y: 0,
      toJSON: () => ({}),
    });
    const chatArea = document.createElement("div");
    chatArea.dataset.chatMessagesArea = "";
    vi.spyOn(chatArea, "getBoundingClientRect").mockReturnValue({
      left: 240,
      top: 0,
      right: 880,
      bottom: 800,
      width: 640,
      height: 800,
      x: 240,
      y: 0,
      toJSON: () => ({}),
    });
    chatShell.append(chatArea);
    document.body.append(chatShell);

    render(<FileManager />);
    fireEvent.click(screen.getByRole("button", { name: "文件管理器" }));

    expect(
      await screen.findByRole("dialog", { name: "文件管理器" }),
    ).toHaveStyle({
      width: "900px",
      left: "80px",
    });
  });

  it("explains why uploads are unavailable in conversation and recycle roots", async () => {
    render(<FileManager />);
    fireEvent.click(screen.getByRole("button", { name: "文件管理器" }));
    await screen.findByRole("dialog", { name: "文件管理器" });

    fireEvent.click(screen.getByRole("button", { name: "对话目录" }));
    expect(
      await screen.findByText("对话目录仅供浏览，不能上传文件。"),
    ).toBeInTheDocument();
  });

  it("keeps the available 1 MB text visible while marking a truncated preview read-only", () => {
    render(
      <FileDetail
        entry={{
          name: "large.txt",
          path: "large.txt",
          kind: "file",
          capabilities: rootPage.capabilities,
        }}
        preview={{
          path: "large.txt",
          size_bytes: 2_000_000,
          is_text: true,
          content: "first megabyte",
          is_truncated: true,
          editable: false,
          revision: "r1",
        }}
        editable
        onDownload={() => undefined}
        onSave={async () => undefined}
        onArchive={() => undefined}
        onRestore={() => undefined}
        onPurge={() => undefined}
      />,
    );

    expect(screen.getByText("仅预览前 1 MB 内容")).toBeInTheDocument();
    expect(screen.getByText("first megabyte")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "编辑" }),
    ).not.toBeInTheDocument();
  });

  it("does not render the selected file as a navigable breadcrumb", async () => {
    const docsPage = {
      ...rootPage,
      path: "docs",
      items: [
        {
          name: "note.txt",
          path: "docs/note.txt",
          kind: "file" as const,
          capabilities: rootPage.capabilities,
        },
      ],
    };
    listDirectory.mockImplementation(({ path }: { path: string }) =>
      Promise.resolve(path === "" ? rootPage : docsPage),
    );
    readFile.mockResolvedValue({
      path: "docs/note.txt",
      size_bytes: 5,
      is_text: true,
      content: "hello",
      is_truncated: false,
      editable: true,
      revision: "r1",
    });
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

  it("keeps file size out of directory rows", () => {
    render(
      <FileColumn
        column={1}
        directory={{
          ...rootPage,
          items: [
            {
              name: "report.txt",
              path: "report.txt",
              kind: "file",
              size_bytes: 1536,
              modified_at: "2026-07-29T00:00:00Z",
              capabilities: rootPage.capabilities,
            },
          ],
        }}
        selectedPath={null}
        onSelect={() => undefined}
      />,
    );

    expect(screen.getByText("7/29/2026", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("1.5 KB")).not.toBeInTheDocument();
  });

  it("shows file size in details and abandons the draft by leaving edit mode", () => {
    render(
      <FileDetail
        entry={{
          name: "note.txt",
          path: "note.txt",
          kind: "file",
          size_bytes: 1536,
          capabilities: rootPage.capabilities,
        }}
        preview={{
          path: "note.txt",
          size_bytes: 1536,
          is_text: true,
          content: "original",
          is_truncated: false,
          editable: true,
          revision: "r1",
        }}
        editable
        onDownload={() => undefined}
        onSave={async () => undefined}
        onArchive={() => undefined}
        onRestore={() => undefined}
        onPurge={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "详情" }));
    expect(
      screen.getByRole("row", { name: "大小 1.5 KB" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "预览" }));
    fireEvent.click(screen.getByRole("button", { name: /编辑/ }));
    fireEvent.change(screen.getByLabelText("文件内容"), {
      target: { value: "draft" },
    });
    fireEvent.click(screen.getByRole("button", { name: /放弃修改/ }));

    expect(screen.queryByLabelText("文件内容")).not.toBeInTheDocument();
    expect(screen.getByText("original")).toBeInTheDocument();
  });
});
