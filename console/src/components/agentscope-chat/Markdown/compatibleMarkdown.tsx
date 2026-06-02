import { useMemo } from "react";
import classNames from "classnames";

import { useProviderContext } from "@/components/agentscope-chat";
import type { MarkdownProps } from "./types";
import { renderCompatibleMarkdownHtml } from "./compatibleMarkdownHtml";

export default function CompatibleMarkdownFallback(props: MarkdownProps) {
  const { content = "", allowHtml = false } = props;
  const prefixCls = useProviderContext().getPrefixCls("markdown");
  const html = useMemo(
    () => renderCompatibleMarkdownHtml(content, allowHtml),
    [content, allowHtml],
  );

  return (
    <div
      className={classNames(prefixCls, props.className)}
      style={{
        fontSize: props.baseFontSize,
        lineHeight: props.baseLineHeight,
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export { renderCompatibleMarkdownHtml };
