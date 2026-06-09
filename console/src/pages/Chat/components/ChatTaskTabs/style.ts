import { createGlobalStyle } from "antd-style";
import { DESIGN_TOKENS } from "@/config/designTokens";

export default createGlobalStyle`
.chat-task-tabs {
  flex: 0 1 auto;
  min-width: 0;
  max-width: min(760px, 56vw);
  height: 34px;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0;
  margin: 0 12px 0 0;
  border: 1px solid transparent;
  border-radius: 0;
  scrollbar-width: none;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;

  &::-webkit-scrollbar {
    display: none;
  }
}

.chat-task-tabs--idle {
  border-color: transparent;
  background: transparent;
}

.chat-task-tabs--has-selection {
  background: transparent;
}

.chat-task-tabs-label {
  flex: 0 0 auto;
  height: 30px;
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border: 1px solid rgba(55, 105, 252, 0.14);
  border-radius: 7px;
  background: rgba(55, 105, 252, 0.08);
  color: ${DESIGN_TOKENS.colorPrimary};
  font-size: 12px;
  line-height: 16px;
  font-weight: 700;
  white-space: nowrap;
}

.chat-task-tabs-empty {
  flex: 0 0 auto;
  height: 30px;
  display: inline-flex;
  align-items: center;
  padding: 0 11px;
  border: 1px solid rgba(17, 20, 45, 0.08);
  border-radius: 7px;
  background: rgba(17, 20, 45, 0.035);
  color: ${DESIGN_TOKENS.colorTextSecondary};
  font-size: 12px;
  line-height: 18px;
  font-weight: 600;
  white-space: nowrap;
}

.chat-task-tab {
  flex: 0 0 auto;
  max-width: 238px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px;
  border: 1px solid rgba(17, 20, 45, 0.08);
  border-radius: 7px;
  background: #FFFFFF;
  color: ${DESIGN_TOKENS.colorTextSecondary};
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease,
    box-shadow 0.15s ease;

  &:hover {
    border-color: rgba(55, 105, 252, 0.22);
    background: rgba(55, 105, 252, 0.04);
    color: ${DESIGN_TOKENS.colorTextPrimary};
  }

  &:focus-visible {
    outline: 2px solid rgba(55, 105, 252, 0.34);
    outline-offset: 2px;
  }

  &--selected {
    border-color: ${DESIGN_TOKENS.colorPrimary};
    background: ${DESIGN_TOKENS.colorPrimary};
    color: #FFFFFF;
    box-shadow: none;
  }

  &--running {
    border-color: rgba(55, 105, 252, 0.28);
  }

  &--auto-paused,
  &--manual-paused {
    border-color: rgba(223, 146, 33, 0.28);
    background: rgba(223, 146, 33, 0.06);
  }
}

.chat-task-tab-state {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: ${DESIGN_TOKENS.colorPrimary};
  opacity: 0.7;
}

.chat-task-tab--running .chat-task-tab-state {
  background: ${DESIGN_TOKENS.colorPrimary};
  box-shadow: 0 0 0 3px rgba(55, 105, 252, 0.12);
}

.chat-task-tab--selected .chat-task-tab-state {
  background: #FFFFFF;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.18);
}

.chat-task-tab--manual-paused .chat-task-tab-state,
.chat-task-tab--auto-paused .chat-task-tab-state {
  background: #DF9221;
  box-shadow: 0 0 0 3px rgba(223, 146, 33, 0.12);
}

.chat-task-tab-title {
  min-width: 0;
  max-width: 112px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  line-height: 18px;
  font-weight: 600;
}

.chat-task-tab-badge {
  flex: 0 0 auto;
  min-width: 14px;
  height: 14px;
  padding: 0 4px;
  border-radius: ${DESIGN_TOKENS.radiusBadge}px;
  background-color: ${DESIGN_TOKENS.colorBadgeRed};
  color: #FFFFFF;
  font-size: ${DESIGN_TOKENS.badgeFontSize}px;
  line-height: 14px;
  text-align: center;
}

.chat-task-tab-status {
  flex: 0 0 auto;
  max-width: 48px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: ${DESIGN_TOKENS.colorTextMuted};
  font-size: 12px;
  line-height: 16px;
  font-weight: 500;
}

.chat-task-tab--selected .chat-task-tab-status {
  color: rgba(255, 255, 255, 0.82);
}

.chat-task-tab-actions {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  margin-left: -2px;
}

.chat-task-tab-action-trigger {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: ${DESIGN_TOKENS.colorTextMuted};
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    color 0.15s ease;

  &:hover,
  &--open {
    background: rgba(132, 130, 231, 0.14);
    color: ${DESIGN_TOKENS.colorPrimary};
  }

  &:focus-visible {
    outline: 2px solid rgba(55, 105, 252, 0.32);
    outline-offset: 2px;
  }
}

.dark-mode .chat-task-tab {
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.72);
}

.dark-mode .chat-task-tabs--idle {
  border-color: transparent;
  background: transparent;
}

.dark-mode .chat-task-tabs--has-selection {
  background: transparent;
}

.dark-mode .chat-task-tabs-label {
  border-color: rgba(91, 138, 255, 0.24);
  background: rgba(91, 138, 255, 0.14);
  color: #DDE7FF;
}

.dark-mode .chat-task-tabs-empty {
  border-color: rgba(255, 255, 255, 0.10);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.62);
}

.dark-mode .chat-task-tab--selected {
  border-color: rgba(91, 138, 255, 0.52);
  background: rgba(91, 138, 255, 0.18);
  color: #DDE7FF;
}
`;
