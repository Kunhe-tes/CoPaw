import React from 'react';
import { CopyOutlined, EditOutlined } from '@ant-design/icons';
import { Tooltip } from '@agentscope-ai/design';
import { emit } from '../../Context/useChatAnywhereEventEmitter';

interface MessageActionsProps {
  content: string;
  onEdit?: (content: string) => void;
  timestamp?: number;
  messageId?: string;
  isHistory?: boolean;
}

export default function MessageActions({ content, onEdit, timestamp, messageId, isHistory }: MessageActionsProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Copy failed:', error);
    }
  };

  const handleEdit = () => {
    // 发送编辑事件，让 Chat 组件更新输入框内容
    emit({
      type: 'handleEdit',
      data: {
        content,
        messageId,
        isHistory,
      }
    });
    onEdit?.(content);
  };

  const formatTime = (timestamp?: number) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);

    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    if (hours < 24) return `${hours}小时前`;

    const month = date.getMonth() + 1;
    const day = date.getDate();
    const hour = date.getHours().toString().padStart(2, '0');
    const minute = date.getMinutes().toString().padStart(2, '0');
    return `${month}月${day}日 ${hour}:${minute}`;
  };

  if (!timestamp) return null;

  return (
    <div className="message-actions">
      <div className="message-timestamp">{formatTime(timestamp)}</div>
      <div className="message-actions-divider">•</div>
      <div className="message-actions-buttons">
        <Tooltip title="复制">
          <div
            className={`action-icon ${copied ? 'copied' : ''}`}
            onClick={handleCopy}
          >
            {copied ? '✓' : <CopyOutlined />}
          </div>
        </Tooltip>
        <Tooltip title="编辑">
          <div className="action-icon" onClick={handleEdit}>
            <EditOutlined />
          </div>
        </Tooltip>
      </div>

      <style>{`
        .message-actions {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 6px;
          margin-top: 4px;
        }

        .message-timestamp {
          color: #9ca3af;
          font-size: 11px;
          font-weight: 400;
        }

        .message-actions-divider {
          color: #e5e7eb;
          font-size: 10px;
          line-height: 1;
        }

        .message-actions-buttons {
          display: flex;
          align-items: center;
          gap: 2px;
        }

        .action-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 20px;
          height: 20px;
          border-radius: 4px;
          cursor: pointer;
          color: #9ca3af;
          transition: all 0.2s ease;
          font-size: 11px;
        }

        .action-icon:hover {
          background: rgba(97, 92, 237, 0.08);
          color: #615ced;
        }

        .action-icon.copied {
          color: #52c41a;
        }
      `}</style>
    </div>
  );
}
