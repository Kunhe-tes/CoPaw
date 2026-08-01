import type { ChatCompactionBoundary } from "@/api/types/chat";

export default function ConversationCompactionBoundary({
  archived_message_count,
}: ChatCompactionBoundary) {
  return (
    <div
      role="separator"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        margin: "18px 0",
        color: "#7a7f87",
        fontSize: 12,
      }}
    >
      <span style={{ height: 1, flex: 1, background: "#e3e5e8" }} />
      <span>会话已压缩 · {archived_message_count} 条消息已归档</span>
      <span style={{ height: 1, flex: 1, background: "#e3e5e8" }} />
    </div>
  );
}
