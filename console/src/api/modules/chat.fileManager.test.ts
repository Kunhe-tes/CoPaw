import { beforeEach, describe, expect, it, vi } from "vitest";
import { chatApi } from "./chat";
import { request } from "../request";

const authMocks = vi.hoisted(() => ({
  buildAuthHeaders: vi.fn(),
}));

const externalTokenMocks = vi.hoisted(() => ({
  ensureValidToken: vi.fn(),
  isExternalTokenEnabled: vi.fn(),
  clearExternalToken: vi.fn(),
}));

vi.mock("../request", () => ({
  request: vi.fn(),
}));

vi.mock("../config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
  getApiToken: () => "",
}));

vi.mock("../authHeaders", () => ({
  buildAuthHeaders: authMocks.buildAuthHeaders,
}));

vi.mock("../externalToken", () => ({
  ensureValidToken: externalTokenMocks.ensureValidToken,
  isExternalTokenEnabled: externalTokenMocks.isExternalTokenEnabled,
  clearExternalToken: externalTokenMocks.clearExternalToken,
}));

describe("chatApi.fileManager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMocks.buildAuthHeaders.mockReturnValue({
      Authorization: "Bearer api-token",
      "X-Agent-Id": "agent-a",
      "X-Tenant-Id": "tenant-a",
      "X-Source-Id": "portal",
    });
    externalTokenMocks.isExternalTokenEnabled.mockReturnValue(false);
  });

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

  it("downloads a blob through authenticated agent and source headers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("archive", {
          status: 200,
          headers: {
            "Content-Disposition":
              "attachment; filename*=UTF-8''build%20archive.zip",
          },
        }),
      ),
    );

    const download = await chatApi.fileManager.downloadFile({
      root: "download",
      path: "build/a b.zip",
    });

    expect(download.filename).toBe("build archive.zip");
    expect(await download.blob.text()).toBe("archive");

    expect(authMocks.buildAuthHeaders).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(
      "/api/console/file-manager/files/download?root=download&path=build%2Fa+b.zip",
      {
        method: "GET",
        headers: {
          Authorization: "Bearer api-token",
          "X-Agent-Id": "agent-a",
          "X-Tenant-Id": "tenant-a",
          "X-Source-Id": "portal",
        },
      },
    );
  });

  it("refreshes external auth and retries the blob request with rebuilt headers", async () => {
    externalTokenMocks.isExternalTokenEnabled.mockReturnValue(true);
    externalTokenMocks.ensureValidToken.mockResolvedValue("fresh-token");
    authMocks.buildAuthHeaders
      .mockReturnValueOnce({ "X-Auth-Authorization": "Bearer stale" })
      .mockReturnValueOnce({ "X-Auth-Authorization": "Bearer fresh" });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response("", { status: 401 }))
        .mockResolvedValueOnce(
          new Response("content", {
            status: 200,
            headers: {
              "Content-Disposition": 'attachment; filename="note.md"',
            },
          }),
        ),
    );

    await expect(
      chatApi.fileManager.downloadFile({ root: "working", path: "note.md" }),
    ).resolves.toMatchObject({ filename: "note.md" });

    expect(externalTokenMocks.ensureValidToken).toHaveBeenCalledWith(true);
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/console/file-manager/files/download?root=working&path=note.md",
      { method: "GET", headers: { "X-Auth-Authorization": "Bearer fresh" } },
    );
  });
});
