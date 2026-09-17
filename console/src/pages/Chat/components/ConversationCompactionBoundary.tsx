import type { ChatCompactionBoundary } from "@/api/types/chat";

export default function ConversationCompactionBoundary({
  data,
}: {
  data: ChatCompactionBoundary;
}) {
  const label = "会话已压缩 · 上滚查看历史内容";

  return (
    <div
      role="separator"
      aria-label={label}
      data-conversation-compaction-boundary-id={data.id}
      style={{
        display: "flex",
        alignItems: "center",
        width: "100%",
        gap: 20,
        margin: "28px 0",
        color: "#8A94A6",
        fontSize: 14,
        fontWeight: 500,
        lineHeight: "20px",
      }}
    >
      <span
        aria-hidden="true"
        style={{ height: 1, flex: 1, background: "#E5E7EB" }}
      />
      <span style={{ whiteSpace: "nowrap" }}>{label}</span>
      <span
        aria-hidden="true"
        style={{ height: 1, flex: 1, background: "#E5E7EB" }}
      />
    </div>
  );
}
