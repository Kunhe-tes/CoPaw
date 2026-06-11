import React from "react";
import ChatSessionItem from "../ChatSessionItem";
import type { HistorySession } from "./historySessions";
import { getHistorySessionTargetId } from "./historySessions";
import { formatListTime } from "../../listTimeFormat";

export interface HistorySessionRowProps {
  name?: string;
  session: HistorySession & {
    realId?: string;
  };
  active: boolean;
  onSessionClick: (sessionId: string) => void;
  onSessionDelete: (
    sessionId: string,
    backendId: string | null,
    sessionName: string,
  ) => void;
}

function resolveBackendChatId(
  session: HistorySession & {
    realId?: string;
  },
): string | null {
  if (session.realId) {
    return session.realId;
  }
  if (!session.id || /^\d+$/.test(session.id)) {
    return null;
  }
  return session.id;
}

function HistorySessionRowInner(props: HistorySessionRowProps) {
  const { session, active, onSessionClick, onSessionDelete } = props;
  const targetId = getHistorySessionTargetId(session);
  const backendId = resolveBackendChatId(session);
  const sessionName = session.name || "新会话";

  const handleClick = React.useCallback(() => {
    onSessionClick(targetId);
  }, [onSessionClick, targetId]);

  const handleDelete = React.useCallback(() => {
    onSessionDelete(targetId, backendId, sessionName);
  }, [backendId, onSessionDelete, sessionName, targetId]);

  return (
    <ChatSessionItem
      name={sessionName}
      time={formatListTime(session.createdAt)}
      active={active}
      onClick={handleClick}
      onDelete={handleDelete}
      showEdit={false}
      showTimeline={false}
      showChannel={false}
    />
  );
}

function areEqual(
  prevProps: HistorySessionRowProps,
  nextProps: HistorySessionRowProps,
): boolean {
  return (
    prevProps.active === nextProps.active &&
    prevProps.onSessionClick === nextProps.onSessionClick &&
    prevProps.onSessionDelete === nextProps.onSessionDelete &&
    prevProps.session.id === nextProps.session.id &&
    prevProps.session.realId === nextProps.session.realId &&
    prevProps.session.name === nextProps.session.name &&
    prevProps.session.createdAt === nextProps.session.createdAt
  );
}

export const HistorySessionRow = React.memo(HistorySessionRowInner, areEqual);
