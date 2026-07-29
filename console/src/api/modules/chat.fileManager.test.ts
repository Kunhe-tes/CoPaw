import { describe, expect, it, vi } from "vitest";
import { chatApi } from "./chat";
import { request } from "../request";

vi.mock("../request", () => ({
  request: vi.fn(),
}));

vi.mock("../config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
  getApiToken: () => "",
}));

describe("chatApi.fileManager", () => {
  it("serializes a directory page request including its cursor and filter", async () => {
    vi.mocked(request).mockResolvedValue({ items: [] });

    await chatApi.fileManager.listDirectory({
      root: "working",
      path: "docs/read me",
      cursor: "signed+cursor",
      query: "draft notes",
    });

    expect(request).toHaveBeenCalledWith(
      "/console/file-manager/directories?root=working&path=docs%2Fread+me&cursor=signed%2Bcursor&q=draft+notes",
    );
  });

  it("sends revision-checked text saves as a JSON body", async () => {
    vi.mocked(request).mockResolvedValue({ path: "notes.md" });

    await chatApi.fileManager.saveText({
      root: "working",
      path: "notes.md",
      content: "draft",
      revision: "sha256:before",
    });

    expect(request).toHaveBeenCalledWith("/console/file-manager/files/text", {
      method: "PUT",
      body: JSON.stringify({
        root: "working",
        path: "notes.md",
        content: "draft",
        revision: "sha256:before",
      }),
    });
  });

  it("uses the controlled download route with encoded root and path", () => {
    expect(
      chatApi.fileManager.downloadUrl({
        root: "download",
        path: "build/a b.zip",
      }),
    ).toContain(
      "/console/file-manager/files/download?root=download&path=build%2Fa+b.zip",
    );
  });
});
