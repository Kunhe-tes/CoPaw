import { useProviderContext } from "@/components/agentscope-chat";
import DownloadFileCard from "../../../DownloadFileCard";
import {
  extractDecodedFileNameFromUrl,
  isAutoPreviewHtmlLink,
  safeDecodeFileName,
} from "../../../FilePreviewModal/fileUtils";


// 判断是否为文件链接
function isFileLink(href?: string): boolean {
  if (!href) return false;

  let urlObj: URL;
  try {
    urlObj = new URL(href, window.location.origin);
  } catch {
    return false;
  }

  const pathname = urlObj.pathname;
  // 匹配 /files/preview/ 路径
  if (pathname.includes("/files/preview/")) return true;
  if (isAutoPreviewHtmlLink(href)) return true;

  // 匹配常见文件扩展名，html/htm 默认按普通页面链接处理
  const fileExts = [
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg",
    "mp4", "webm", "mp3", "wav", "ogg",
    "pdf",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "md", "mdx", "txt", "json", "xml", "csv", "log", "yaml", "yml",
    "zip", "rar", "7z", "tar", "gz",
  ];
  const fileName = safeDecodeFileName(pathname.split("/").pop() || "");
  const extMatch = fileName.match(/\.([a-zA-Z0-9]+)$/);
  if (extMatch && fileExts.includes(extMatch[1].toLowerCase())) return true;
  return false;
}

// 从 URL 提取文件名
function extractFileName(href: string): string {
  return extractDecodedFileNameFromUrl(href, "文件");
}

export default function Link(props) {
  if (props["data-footnote-ref"] === "") return <Sup {...props} />;
  if (props.children === "↩" && props["data-footnote-backref"] === "")
    return null;

  const href = props.href;
  if (isFileLink(href)) {
    const fileName = extractFileName(href);
    return (
      <DownloadFileCard
        url={href}
        fileName={fileName}
        enableClickTracking={isAutoPreviewHtmlLink(href, fileName)}
      />
    );
  }

  return <a {...props} />;
}

function Sup(props) {
  const { getPrefixCls } = useProviderContext();
  const prefixCls = getPrefixCls("markdown-footnote");
  const rest = { ...props };
  delete rest.href;

  return (
    <a
      {...rest}
      className={prefixCls}
      onClick={() => {
        try {
          const idParts = props.id.split("-");
          const id = idParts[idParts.length - 1];
          const url = document
            .querySelector(`#footnote-${id}`)
            .querySelector("a")
            .getAttribute("href");
          window.open(url, "_blank");
        } catch {
          return;
        }
      }}
    />
  );
}
