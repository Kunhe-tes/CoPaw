import type { ChatUploadResponse } from "@/api/modules/chat";

export const DENIED_CHAT_ATTACHMENT_EXECUTABLE_EXTENSIONS = new Set([
  ".py",
  ".pyw",
  ".java",
  ".class",
  ".jar",
  ".js",
  ".mjs",
  ".cjs",
  ".jsx",
  ".ts",
  ".tsx",
  ".sh",
  ".bash",
  ".zsh",
  ".fish",
  ".ps1",
  ".bat",
  ".cmd",
  ".php",
  ".rb",
  ".pl",
  ".lua",
  ".go",
  ".rs",
  ".c",
  ".cc",
  ".cpp",
  ".cxx",
  ".h",
  ".hpp",
  ".cs",
  ".kt",
  ".kts",
  ".swift",
  ".exe",
  ".dll",
  ".so",
  ".dylib",
]);

export const CHAT_ATTACHMENT_ACCEPT_HINT = [
  "image/*",
  "video/*",
  "audio/*",
  ".pdf",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".ppt",
  ".pptx",
  ".txt",
  ".md",
  ".csv",
  ".json",
  ".xml",
  ".zip",
  ".tar",
  ".gz",
  ".7z",
].join(",");

type Translate = (
  key: string,
  options?: Record<string, string | number>,
) => string;

type ChatAttachmentMessageApi = {
  warning: (content: string) => unknown;
  error: (content: string) => unknown;
};

type MultimodalCapabilities = {
  supportsMultimodal: boolean;
  supportsImage: boolean;
  supportsVideo: boolean;
};

export type ChatAttachmentUploadOptions = {
  file: File;
  onSuccess: (body: { url?: string; thumbUrl?: string }) => void;
  onError?: (e: Error) => void;
  onProgress?: (e: { percent?: number }) => void;
  message: ChatAttachmentMessageApi;
  t: Translate;
  multimodalCaps: MultimodalCapabilities;
  maxUploadMb: number;
  uploadFile: (file: File) => Promise<ChatUploadResponse>;
  filePreviewUrl: (filename: string) => string;
};

export function hasDeniedChatAttachmentExtension(fileName: string): boolean {
  const lastDotIndex = fileName.lastIndexOf(".");
  if (lastDotIndex < 0) return false;
  const outerExtension = fileName.slice(lastDotIndex).toLowerCase();
  return DENIED_CHAT_ATTACHMENT_EXECUTABLE_EXTENSIONS.has(outerExtension);
}

export async function uploadChatAttachment(
  options: ChatAttachmentUploadOptions,
) {
  const {
    file,
    onSuccess,
    onError,
    onProgress,
    message,
    t,
    multimodalCaps,
    maxUploadMb,
    uploadFile,
    filePreviewUrl,
  } = options;

  try {
    if (hasDeniedChatAttachmentExtension(file.name)) {
      const errorMessage = t("chat.attachments.executableFileUnsupported");
      message.error(errorMessage);
      onError?.(new Error(errorMessage));
      return;
    }

    if (!multimodalCaps.supportsMultimodal) {
      message.warning(t("chat.attachments.multimodalWarning"));
    } else if (
      multimodalCaps.supportsImage &&
      !multimodalCaps.supportsVideo &&
      !file.type.startsWith("image/")
    ) {
      message.warning(t("chat.attachments.imageOnlyWarning"));
    }
    const sizeMb = file.size / 1024 / 1024;
    const isWithinLimit = sizeMb < maxUploadMb;

    if (!isWithinLimit) {
      message.error(
        t("chat.attachments.fileSizeExceeded", {
          limit: maxUploadMb,
          size: sizeMb.toFixed(2),
        }),
      );
      onError?.(new Error(`File size exceeds ${maxUploadMb}MB`));
      return;
    }

    const res = await uploadFile(file);
    onProgress?.({ percent: 100 });
    onSuccess({ url: filePreviewUrl(res.url) });
  } catch (e) {
    onError?.(e instanceof Error ? e : new Error(String(e)));
  }
}
