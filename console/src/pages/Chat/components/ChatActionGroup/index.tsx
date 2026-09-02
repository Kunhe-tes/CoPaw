import React from "react";
import { IconButton } from "@agentscope-ai/design";
import { SparkNewChatFill } from "@agentscope-ai/icons";
// ==================== 组件引入方式变更 (Kun He) ====================
import { useChatAnywhereSessions } from "@/components/agentscope-chat";
// ==================== 组件引入方式变更结束 ====================
import { useTranslation } from "react-i18next";
import { Checkbox, Flex, Modal, Tooltip, message } from "antd";
import { ShareAltOutlined } from "@ant-design/icons";
import { useState } from "react";
import { chatApi } from "@/api/modules/chat";
import type { ChatShareOptions, Message } from "@/api/types";
import { buildChatShareUrl } from "./shareUrl";
import { isShareableTurn } from "./shareSelection";
// ==================== 首页改版 (Kun He) ====================
// 历史记录已迁移到左侧 ChatSidebar，不再需要右侧 Drawer 和历史按钮
// import ChatSessionDrawer from "../ChatSessionDrawer";
// ==================== 首页改版结束 ====================

interface ChatActionGroupProps {
  chatId?: string;
}

const ChatActionGroup: React.FC<ChatActionGroupProps> = ({ chatId }) => {
  const { t } = useTranslation();
  const { createSession } = useChatAnywhereSessions();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [turnStatuses, setTurnStatuses] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string[]>([]);

  const turns = messages.filter((item) => item.role === "user");
  const messageId = (item: Message) => {
    const metadata = item.metadata;
    if (metadata && typeof metadata === "object") {
      const originalId = (metadata as Record<string, unknown>).original_id;
      if (typeof originalId === "string" && originalId) return originalId;
    }
    return typeof item.id === "string" ? item.id : "";
  };

  const openShare = async () => {
    if (!chatId) {
      message.warning("请先打开一个已有会话");
      return;
    }
    setLoading(true);
    try {
      const options: ChatShareOptions = await chatApi.getChatShareOptions(chatId);
      setMessages(options.messages || []);
      setTurnStatuses(options.turn_statuses || {});
      setSelected([]);
      setOpen(true);
    } catch {
      message.error("加载会话记录失败");
    } finally {
      setLoading(false);
    }
  };

  const createShare = async () => {
    if (!chatId || selected.length === 0) return;
    setGenerating(true);
    try {
      const result = await chatApi.createChatShare(chatId, selected);
      const url = buildChatShareUrl(result.share_path);
      await navigator.clipboard.writeText(url);
      message.success("分享链接已复制");
      setOpen(false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "生成分享链接失败");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <Flex gap={8} align="center">
      <Tooltip title={t("chat.newChatTooltip")} mouseEnterDelay={0.5}>
        <IconButton
          bordered={false}
          icon={<SparkNewChatFill />}
          onClick={() => createSession()}
        />
      </Tooltip>
      <Tooltip title="分享会话" mouseEnterDelay={0.5}>
        <IconButton
          bordered={false}
          icon={<ShareAltOutlined />}
          loading={loading}
          onClick={() => void openShare()}
        />
      </Tooltip>
      <Modal
        open={open}
        title="选择要分享的回答轮次"
        okText="生成分享链接"
        cancelText="取消"
        okButtonProps={{ disabled: selected.length === 0, loading: generating }}
        onOk={() => void createShare()}
        onCancel={() => setOpen(false)}
      >
        <Flex vertical gap={8}>
          {turns.map((turn, index) => {
            const id = messageId(turn);
            const status = turnStatuses[id];
            const disabled = !isShareableTurn(id, turnStatuses);
            return (
              <Checkbox
                key={id || index}
                disabled={disabled || !id}
                checked={selected.includes(id)}
                onChange={(event) => {
                  setSelected((current) => event.target.checked
                    ? [...current, id]
                    : current.filter((value) => value !== id));
                }}
              >
                {`第 ${index + 1} 轮：${String(turn.content || "").slice(0, 60)}${
                  status && status !== "completed" ? `（${status}）` : ""
                }`}
              </Checkbox>
            );
          })}
        </Flex>
      </Modal>
    </Flex>
  );
};

export default ChatActionGroup;
