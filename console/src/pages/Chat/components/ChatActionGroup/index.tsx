import React, { useEffect, useState } from "react";
import { IconButton } from "@agentscope-ai/design";
import { SparkNewChatFill } from "@agentscope-ai/icons";
import { useChatAnywhereSessions } from "@/components/agentscope-chat";
import { useTranslation } from "react-i18next";
import { Button, Checkbox, Flex, Tooltip, message } from "antd";
import {
  CloseOutlined,
  GlobalOutlined,
  LinkOutlined,
  ShareAltOutlined,
} from "@ant-design/icons";
import { chatApi } from "@/api/modules/chat";
import type { ChatShareOptions } from "@/api/types";
import { buildChatShareUrl } from "./shareUrl";
import { useChatShareSelection } from "../../chatShareContext";
import { copyToClipboard } from "@/utils/clipboard";
import styles from "./index.module.less";

interface ChatActionGroupProps {
  chatId?: string;
}

const ChatActionGroup: React.FC<ChatActionGroupProps> = ({ chatId }) => {
  const { t } = useTranslation();
  const { createSession } = useChatAnywhereSessions();
  const shareSelection = useChatShareSelection();
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    shareSelection.close();
  }, [chatId, shareSelection.close]);

  const openShare = async () => {
    if (!chatId) {
      message.warning("请先打开一个已有会话");
      return;
    }
    setLoading(true);
    try {
      const options: ChatShareOptions = await chatApi.getChatShareOptions(
        chatId,
      );
      shareSelection.open(options.messages || [], options.turn_statuses || {});
    } catch {
      message.error("加载会话记录失败");
    } finally {
      setLoading(false);
    }
  };

  const getShareUrl = async () => {
    if (shareSelection.shareUrl) return shareSelection.shareUrl;
    if (!chatId || shareSelection.selectedTurnIds.length === 0) return null;
    setGenerating(true);
    try {
      const result = await chatApi.createChatShare(
        chatId,
        shareSelection.selectedTurnIds,
      );
      const url = buildChatShareUrl(result.share_path);
      shareSelection.setShareUrl(url);
      return url;
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "生成分享链接失败",
      );
      return null;
    } finally {
      setGenerating(false);
    }
  };

  const copyShareUrl = async () => {
    const url = await getShareUrl();
    if (!url) return;
    try {
      const copied = await copyToClipboard(url);
      if (!copied) throw new Error("clipboard unavailable");
      message.success("分享链接已复制");
      shareSelection.close();
    } catch {
      message.error("复制分享链接失败");
    }
  };

  const openShareUrl = async () => {
    const url = await getShareUrl();
    if (!url) return;
    window.open(url, "_blank", "noopener,noreferrer");
    shareSelection.close();
  };

  const selectableCount = shareSelection.selectableTurnIds.length;
  const selectedCount = shareSelection.selectedTurnIds.length;
  const allSelected = selectableCount > 0 && selectedCount === selectableCount;

  return (
    <>
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
      </Flex>
      {shareSelection.active ? (
        <div className={styles.toolbar} role="region" aria-label="分享选择操作">
          <div className={styles.toolbarSelection}>
            <Checkbox
              checked={allSelected}
              indeterminate={selectedCount > 0 && !allSelected}
              disabled={selectableCount === 0}
              onChange={(event) =>
                shareSelection.selectAll(event.target.checked)
              }
            >
              全选
            </Checkbox>
            <span className={styles.count}>
              {selectableCount === 0
                ? "暂无可分享的完整回答轮次"
                : `已选 ${selectedCount} / ${selectableCount} 轮`}
            </span>
          </div>
          <div className={styles.toolbarActions}>
            <Button
              type="primary"
              icon={<LinkOutlined />}
              loading={generating}
              disabled={selectedCount === 0}
              onClick={() => void copyShareUrl()}
            >
              复制链接
            </Button>
            <Button
              icon={<GlobalOutlined />}
              loading={generating}
              disabled={selectedCount === 0}
              onClick={() => void openShareUrl()}
            >
              浏览器打开
            </Button>
            <Button
              type="text"
              aria-label="退出分享模式"
              icon={<CloseOutlined />}
              onClick={shareSelection.close}
            />
          </div>
        </div>
      ) : null}
    </>
  );
};

export default ChatActionGroup;
