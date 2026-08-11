import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  hasDeniedChatAttachmentExtension,
  uploadChatAttachment,
} from "./attachmentUploadPolicy";

const t = vi.fn((key: string) => {
  if (key === "chat.attachments.executableFileUnsupported") {
    return "不能上传可执行代码文件";
  }
  return key;
});

const message = {
  warning: vi.fn(),
  error: vi.fn(),
};

const uploadFile = vi.fn();
const filePreviewUrl = vi.fn((filename: string) => `/preview/${filename}`);

const multimodalCaps = {
  supportsMultimodal: true,
  supportsImage: true,
  supportsVideo: true,
};

describe("chat attachment upload policy", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    uploadFile.mockResolvedValue({
      url: "archive.zip",
      file_name: "archive.zip",
    });
  });

  it("matches only the outer filename extension case-insensitively", () => {
    expect(hasDeniedChatAttachmentExtension("script.py")).toBe(true);
    expect(hasDeniedChatAttachmentExtension("Example.JAVA")).toBe(true);
    expect(hasDeniedChatAttachmentExtension("app.min.js")).toBe(true);
    expect(hasDeniedChatAttachmentExtension("Program.cs")).toBe(true);
    expect(hasDeniedChatAttachmentExtension("script.py.zip")).toBe(false);
  });

  it("shows the localized error and skips the upload API for blocked files", async () => {
    const file = new File(["code"], "main.ts", {
      type: "text/plain",
    });
    const onSuccess = vi.fn();
    const onError = vi.fn();

    await uploadChatAttachment({
      file,
      onSuccess,
      onError,
      message,
      t,
      multimodalCaps,
      maxUploadMb: 10,
      uploadFile,
      filePreviewUrl,
    });

    expect(message.error).toHaveBeenCalledWith("不能上传可执行代码文件");
    expect(onError).toHaveBeenCalledWith(expect.any(Error));
    expect(uploadFile).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("uploads archive filenames with blocked inner extensions", async () => {
    const file = new File(["content"], "script.py.zip", {
      type: "application/zip",
    });
    const onSuccess = vi.fn();
    const onProgress = vi.fn();

    await uploadChatAttachment({
      file,
      onSuccess,
      onProgress,
      message,
      t,
      multimodalCaps,
      maxUploadMb: 10,
      uploadFile,
      filePreviewUrl,
    });

    expect(uploadFile).toHaveBeenCalledWith(file);
    expect(onProgress).toHaveBeenCalledWith({ percent: 100 });
    expect(onSuccess).toHaveBeenCalledWith({ url: "/preview/archive.zip" });
  });

  it("shows an upload error when the API request fails", async () => {
    const file = new File(["content"], "report.pdf", {
      type: "application/pdf",
    });
    const onError = vi.fn();
    uploadFile.mockRejectedValueOnce(new Error("network unavailable"));

    await uploadChatAttachment({
      file,
      onSuccess: vi.fn(),
      onError,
      message,
      t,
      multimodalCaps,
      maxUploadMb: 10,
      uploadFile,
      filePreviewUrl,
    });

    expect(message.error).toHaveBeenCalledWith("chat.attachments.uploadFailed");
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: "network unavailable" }),
    );
  });
});
