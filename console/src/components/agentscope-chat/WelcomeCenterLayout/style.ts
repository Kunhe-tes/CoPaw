import { createGlobalStyle } from "antd-style";
import { DESIGN_TOKENS } from "@/config/designTokens";

export default createGlobalStyle`
.welcome-center-layout {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  padding: 40px 20px;
  gap: 0;
  background: url('/chat-bg.png') center/cover no-repeat;
  background: linear-gradient(180deg, #E8EEFF 0%, #F1F2F7 40%, #F5F5FA 100%);
}

.welcome-greeting {
  font-size: 22px;
  font-weight: 600;
  color: ${DESIGN_TOKENS.colorTextDark};
  line-height: 33px;
  margin-bottom: 40px;
  text-align: center;
}

.welcome-input-card {
  position: relative;
  width: ${DESIGN_TOKENS.inputCardWidth}px;
  max-width: 100%;
  background-color: ${DESIGN_TOKENS.colorBgCard};
  border-radius: ${DESIGN_TOKENS.radiusCard}px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 28px;
  box-shadow: 0px 0px 8px 0px rgba(0, 0, 0, 0.08);
}

.welcome-input-placeholder {
  font-size: 14px;
  line-height: 22px;
  color: ${DESIGN_TOKENS.colorTextMuted};
  resize: none;
  border: none;
  outline: none;
  background: transparent;
  width: 100%;
  min-height: 24px;
  max-height: 200px;
  font-family: inherit;
  padding: 4px 0;
  overflow: auto;
}

.welcome-skill-editor {
  min-height: 24px;
  white-space: pre-wrap;

  &:empty::before {
    color: ${DESIGN_TOKENS.colorTextMuted};
    content: attr(data-placeholder);
    pointer-events: none;
  }
}

.welcome-input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-left: -6px;
}

.welcome-input-actions-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.welcome-input-send-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: ${DESIGN_TOKENS.colorPrimary};
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.15s ease;

  &:hover {
    opacity: 0.85;
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
}

.welcome-tabs-area {
  width: ${DESIGN_TOKENS.inputCardWidth}px;
  max-width: 100%;
  margin-bottom: 28px;
}

.welcome-cases-area {
  width: 935px;
  margin: 0 auto;
}

.scenario-preset-selector {
  --capsule-bg: #F1F2F6;
  --capsule-text: #6D7C96;
  --capsule-border: #E7EAF0;
  --capsule-hover-bg: #E9ECF2;
  --capsule-hover-text: #63728B;
  --capsule-hover-border: #DDE2EA;
  --capsule-active-bg: #697892;
  --capsule-active-text: #FFFFFF;
  --capsule-active-hover-bg: #5E6D87;
  --capsule-pressed-bg: #53627C;
  width: ${DESIGN_TOKENS.inputCardWidth}px;
  max-width: 100%;
  margin-bottom: 0;
}

.scenario-preset-domain-selector,
.scenario-preset-capability-row,
.welcome-scene-list {
  display: flex;
  gap: 8px;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: thin;
}

.scenario-preset-domain-selector {
  justify-content: center;
  padding: 2px 0 16px;
}

.scenario-preset-domain-track {
  align-items: center;
  background: var(--capsule-border);
  border: 1px solid var(--capsule-border);
  border-radius: 999px;
  border-bottom-left-radius: 999px;
  border-bottom-right-radius: 999px;
  border-top-left-radius: 999px;
  border-top-right-radius: 999px;
  display: inline-flex;
  gap: 0;
  max-width: 100%;
  overflow-x: auto;
  padding: 4px;
  scrollbar-width: thin;
}

.scenario-preset-domain-card {
  align-items: center;
  background: var(--capsule-bg);
  border: 1px solid var(--capsule-border);
  border-radius: 999px;
  border-bottom-left-radius: 999px;
  border-bottom-right-radius: 999px;
  border-top-left-radius: 999px;
  border-top-right-radius: 999px;
  color: var(--capsule-text);
  cursor: pointer;
  display: inline-flex;
  flex: 0 0 auto;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  gap: 6px;
  justify-content: center;
  height: 36px;
  min-height: 36px;
  min-width: 112px;
  padding: 0 14px;
  transition: background-color 160ms ease, color 160ms ease;

  &:hover:not(:disabled) {
    background: var(--capsule-hover-bg);
    border-color: var(--capsule-hover-border);
    color: var(--capsule-hover-text);
  }

  &:focus-visible {
    outline: 2px solid ${DESIGN_TOKENS.colorPrimary};
    outline-offset: 2px;
  }

  &.is-active {
    background: var(--capsule-active-bg);
    border-color: var(--capsule-active-bg);
    color: var(--capsule-active-text);
  }

  &.is-active:hover:not(:disabled) {
    background: var(--capsule-active-hover-bg);
    border-color: var(--capsule-active-hover-bg);
    color: var(--capsule-active-text);
  }

  &:active:not(:disabled) {
    background: var(--capsule-pressed-bg);
    border-color: var(--capsule-pressed-bg);
    color: var(--capsule-active-text);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: .55;
  }
}

.scenario-preset-capability-row {
  margin: 0 -20px;
  padding: 8px 20px 14px;
}

.scenario-preset-capability-tab,
.welcome-scene-button {
  background: var(--capsule-bg);
  border: 1px solid var(--capsule-border);
  border-radius: 999px;
  border-bottom-left-radius: 999px;
  border-bottom-right-radius: 999px;
  border-top-left-radius: 999px;
  border-top-right-radius: 999px;
  color: var(--capsule-text);
  cursor: pointer;
  flex: 0 0 auto;
  font: inherit;
  font-size: 13px;
  height: 32px;
  line-height: 18px;
  padding: 0 14px;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease;

  &:hover:not(:disabled) {
    background: var(--capsule-hover-bg);
    border-color: var(--capsule-hover-border);
    color: var(--capsule-hover-text);
  }

  &:focus-visible {
    outline: 2px solid ${DESIGN_TOKENS.colorPrimary};
    outline-offset: 2px;
  }

  &.is-active {
    background: var(--capsule-active-bg);
    border-color: var(--capsule-active-bg);
    color: var(--capsule-active-text);
    font-weight: 500;
  }

  &.is-active:hover:not(:disabled) {
    background: var(--capsule-active-hover-bg);
    border-color: var(--capsule-active-hover-bg);
    color: var(--capsule-active-text);
  }

  &:active:not(:disabled) {
    background: var(--capsule-pressed-bg);
    border-color: var(--capsule-pressed-bg);
    color: var(--capsule-active-text);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: .55;
  }
}

.welcome-scene-strip {
  align-items: center;
  background: #F7F9FC;
  border: 1px solid #E5E7EB;
  border-bottom: 1px solid #E5E7EB;
  border-top-left-radius: 12px;
  border-top-right-radius: 12px;
  display: flex;
  gap: 12px;
  margin: -16px -20px 8px;
  min-height: 48px;
  overflow: hidden;
  padding: 6px 16px;
}

.welcome-scene-title {
  color: ${DESIGN_TOKENS.colorTextDark};
  flex: 0 0 auto;
  font-size: 14px;
  font-weight: 600;
}

.welcome-scene-list {
  width: 100%;
}

.welcome-scenario-marker {
  color: ${DESIGN_TOKENS.colorPrimary};
  font-size: 14px;
  font-weight: 500;
}
`;
