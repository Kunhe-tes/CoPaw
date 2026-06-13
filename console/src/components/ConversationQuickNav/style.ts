import { createGlobalStyle } from "antd-style";
import { DESIGN_TOKENS } from "@/config/designTokens";

export default createGlobalStyle`
/* ─── Main Navigation Bar ─── */
.conversation-quick-nav {
  position: absolute;
  right: 8px;
  top: 24px;
  bottom: 24px;
  width: 36px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  opacity: 0;
  animation: quick-nav-fade-in 300ms ease-out forwards;
  pointer-events: none;
}

.conversation-quick-nav::before,
.conversation-quick-nav::after {
  content: '';
  position: absolute;
  right: 0;
  width: 36px;
  height: 14px;
  z-index: 1;
  pointer-events: none;
}

.conversation-quick-nav::before {
  top: 0;
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.9), transparent);
}

.conversation-quick-nav::after {
  bottom: 0;
  background: linear-gradient(to top, rgba(255, 255, 255, 0.9), transparent);
}

.conversation-quick-nav__scroll {
  width: 36px;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 14px 0;
  box-sizing: border-box;
  pointer-events: none;
  scrollbar-width: none;
  scrollbar-color: transparent transparent;
  -ms-overflow-style: none;
  overscroll-behavior: contain;
}

.conversation-quick-nav__items {
  width: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 15px;
}

.conversation-quick-nav__scroll::-webkit-scrollbar {
  width: 0 !important;
  height: 0 !important;
  background: transparent !important;
}

.conversation-quick-nav__scroll::-webkit-scrollbar-thumb,
.conversation-quick-nav__scroll::-webkit-scrollbar-track {
  background: transparent !important;
}

.quick-nav-overflow-hint {
  position: absolute;
  right: 22px;
  z-index: 3;
  height: 24px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0 7px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.96);
  color: rgba(0, 0, 0, 0.65);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  font-size: 11px;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  pointer-events: auto;
  transition: color 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}

.quick-nav-overflow-hint:hover,
.quick-nav-overflow-hint:focus-visible {
  color: ${DESIGN_TOKENS.colorPrimary};
  border-color: ${DESIGN_TOKENS.colorPrimary};
  box-shadow: 0 2px 10px rgba(55, 105, 252, 0.2);
  outline: none;
}

.quick-nav-overflow-hint--top {
  top: 4px;
}

.quick-nav-overflow-hint--bottom {
  bottom: 4px;
}

/* 当整个导航组件被hover时，所有横线都有宽度变化 */
.conversation-quick-nav--hovered .quick-nav-dot {
  width: 20px;
}

@keyframes quick-nav-fade-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

/* ─── Navigation Item (Short Line) ─── */
.quick-nav-dot {
  position: relative;
  right: 0;
  width: 14px;
  height: 4px;
  background-color: rgba(120, 120, 120, 0.5);
  cursor: pointer;
  transition: all 150ms ease;
  border-radius: 2px;
  outline: none;
  pointer-events: auto;
}

/* Invisible touch target for accessibility */
.quick-nav-dot::before {
  content: '';
  position: absolute;
  top: -8px;
  left: -8px;
  right: -16px;
  bottom: -8px;
}

/* Hover state - line extends and color changes */
.quick-nav-dot:hover {
  width: 28px;
  height: 4px;
  background-color: ${DESIGN_TOKENS.colorPrimary};
}

.quick-nav-dot--active {
  width: 14px;
  height: 4px;
  background-color: ${DESIGN_TOKENS.colorPrimary};
}

/* Focus state for keyboard accessibility */
.quick-nav-dot:focus-visible {
  outline: 2px solid ${DESIGN_TOKENS.colorPrimary};
  outline-offset: 4px;
  width: 24px;
  background-color: ${DESIGN_TOKENS.colorPrimary};
}

/* ─── Tooltip ─── */
.quick-nav-tooltip {
  position: fixed;
  transform: translateY(-50%);
  background: linear-gradient(135deg, rgba(55, 105, 252, 0.95), rgba(55, 105, 252, 0.85));
  color: #FFFFFF;
  padding: 8px 12px;
  border-radius: 8px;
  min-width: 180px;
  max-width: 280px;
  font-size: 13px;
  line-height: 1.5;
  white-space: normal;
  word-break: break-word;
  opacity: 0;
  transform: translateY(-50%) translateX(8px);
  transition: all 200ms ease;
  pointer-events: none;
  box-shadow: 0 2px 8px rgba(55, 105, 252, 0.3);
  z-index: 101;
}

.quick-nav-tooltip--visible {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
  pointer-events: auto;
}

.quick-nav-tooltip::before {
  content: '';
  position: absolute;
  right: -6px;
  top: 50%;
  transform: translateY(-50%);
  width: 0;
  height: 0;
  border-left: 6px solid rgba(55, 105, 252, 0.85);
  border-top: 6px solid transparent;
  border-bottom: 6px solid transparent;
}

.quick-nav-tooltip-content {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.quick-nav-tooltip-content strong {
  flex-shrink: 0;
  font-weight: 600;
  white-space: nowrap;
  display: inline;
}

.quick-nav-tooltip-content span {
  flex: 1;
  display: inline;
  white-space: normal;
}

/* ─── Message Highlight Flash ─── */
.quick-nav-highlight-flash {
  animation: highlight-flash 1.5s ease-out;
  border-radius: 6px;
}

@keyframes highlight-flash {
  0%, 100% {
    background-color: transparent;
  }
  20%, 60% {
    background-color: rgba(55, 105, 252, 0.08);
  }
}

/* ─── Dark Mode Adaptation ─── */
[data-theme='dark'] .quick-nav-dot {
  background-color: rgba(180, 180, 180, 0.4);
}

[data-theme='dark'] .quick-nav-dot:hover,
[data-theme='dark'] .quick-nav-dot--active {
  background-color: ${DESIGN_TOKENS.colorPrimary};
}

[data-theme='dark'] .quick-nav-tooltip {
  background: linear-gradient(135deg, rgba(55, 105, 252, 0.9), rgba(55, 105, 252, 0.75));
  box-shadow: 0 2px 8px rgba(55, 105, 252, 0.2);
}

[data-theme='dark'] .quick-nav-overflow-hint {
  border-color: rgba(255, 255, 255, 0.16);
  background: rgba(32, 32, 32, 0.96);
  color: rgba(255, 255, 255, 0.72);
}

[data-theme='dark'] .quick-nav-overflow-hint:hover,
[data-theme='dark'] .quick-nav-overflow-hint:focus-visible {
  color: ${DESIGN_TOKENS.colorPrimary};
  border-color: ${DESIGN_TOKENS.colorPrimary};
}

[data-theme='dark'] .conversation-quick-nav::before {
  background: linear-gradient(to bottom, rgba(20, 20, 20, 0.9), transparent);
}

[data-theme='dark'] .conversation-quick-nav::after {
  background: linear-gradient(to top, rgba(20, 20, 20, 0.9), transparent);
}

[data-theme='dark'] .quick-nav-tooltip::before {
  border-left-color: rgba(55, 105, 252, 0.75);
}

[data-theme='dark'] .quick-nav-tooltip-content span {
  color: rgba(255, 255, 255, 0.9);
}

[data-theme='dark'] .quick-nav-highlight-flash {
  animation: highlight-flash-dark 1.5s ease-out;
}

@keyframes highlight-flash-dark {
  0%, 100% {
    background-color: transparent;
  }
  20%, 60% {
    background-color: rgba(55, 105, 252, 0.12);
  }
}
`;
