import { MarkdownProps } from "../../types";
import { useProviderContext } from "@/components/agentscope-chat";

interface RawProps {
  content: MarkdownProps["content"];
  baseFontSize?: number;
  baseLineHeight?: number;
}

export default function Raw(props: RawProps) {
  const prefixCls = useProviderContext().getPrefixCls("markdown");

  return (
    <div
      className={prefixCls}
      style={{
        fontSize: props.baseFontSize,
        lineHeight: props.baseLineHeight,
        whiteSpace: "pre-wrap",
        overflowWrap: "anywhere",
        wordBreak: "break-word",
      }}
    >
      {props.content}
    </div>
  );
}
