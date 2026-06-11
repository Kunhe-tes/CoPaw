import { createGlobalStyle } from "antd-style";
import { DESIGN_TOKENS } from "@/config/designTokens";

export default createGlobalStyle`
.chat-task-tabs-shell {
  flex: 1 1 min(880px, 68vw);
  min-width: 0;
  max-width: min(980px, 72vw);
  height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0;
  margin: 0 12px 0 0;
  border: 1px solid transparent;
  border-radius: 0;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;
}

.chat-task-tabs-viewport {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  height: 34px;
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;

  &::before,
  &::after {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    width: 34px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.16s ease;
    z-index: 1;
  }

  &::before {
    left: 32px;
    background: linear-gradient(90deg, #F7F9FF 18%, rgba(247, 249, 255, 0));
  }

  &::after {
    right: 32px;
    background: linear-gradient(270deg, #F7F9FF 18%, rgba(247, 249, 255, 0));
  }

  &--left::before,
  &--right::after {
    opacity: 1;
  }
}

.chat-task-tabs {
  flex: 1 1 auto;
  min-width: 0;
  height: 34px;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 2px 0;
  scrollbar-width: none;
  scroll-behavior: smooth;
  margin-right: 8px;

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
  height: 32px;
  display: inline-flex;
  align-items: center;
  padding: 0 12px;
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
  color: ${DESIGN_TOKENS.colorTextPrimary};
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
    border-color: rgba(55, 105, 252, 0.42);
    background: rgba(55, 105, 252, 0.09);
    color: ${DESIGN_TOKENS.colorTextPrimary};
    box-shadow: 0 2px 8px rgba(55, 105, 252, 0.12);
  }

  &--selected:hover {
    border-color: rgba(55, 105, 252, 0.52);
    background: rgba(55, 105, 252, 0.14);
    color: ${DESIGN_TOKENS.colorTextPrimary};
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
  background: ${DESIGN_TOKENS.colorPrimary};
  box-shadow: 0 0 0 3px rgba(55, 105, 252, 0.16);
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
  color: inherit;
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
  color: ${DESIGN_TOKENS.colorTextSecondary};
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

.chat-task-tabs-scroll {
  position: relative;
  z-index: 3;
  flex: 0 0 26px;
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid rgba(55, 105, 252, 0.18);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.96);
  color: ${DESIGN_TOKENS.colorPrimary};
  cursor: pointer;
  // box-shadow: 0 6px 16px rgba(31, 42, 68, 0.10);
  transition:
    background-color 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease;

  &:hover {
    border-color: rgba(55, 105, 252, 0.34);
    background: #FFFFFF;
    box-shadow: 0 8px 18px rgba(31, 42, 68, 0.14);
  }

  &:focus-visible {
    outline: 2px solid rgba(55, 105, 252, 0.32);
    outline-offset: 2px;
  }
}

.chat-task-tabs-scroll--left {
  order: 0;
}

.chat-task-tabs-scroll--right {
  order: 2;
}

.chat-task-tabs-scroll--left + .chat-task-tabs {
  order: 1;
}

.dark-mode .chat-task-tab {
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.82);
}

.dark-mode .chat-task-tabs-viewport::before {
  background: linear-gradient(90deg, #1D2230 18%, rgba(29, 34, 48, 0));
}

.dark-mode .chat-task-tabs-viewport::after {
  background: linear-gradient(270deg, #1D2230 18%, rgba(29, 34, 48, 0));
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
  background: rgba(91, 138, 255, 0.20);
  color: #DDE7FF;
  box-shadow: 0 2px 10px rgba(91, 138, 255, 0.18);
}

.dark-mode .chat-task-tab--selected .chat-task-tab-status {
  color: rgba(221, 231, 255, 0.72);
}

.dark-mode .chat-task-tabs-scroll {
  border-color: rgba(91, 138, 255, 0.28);
  background: rgba(32, 38, 54, 0.96);
  color: #DDE7FF;
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.24);
}
`;
