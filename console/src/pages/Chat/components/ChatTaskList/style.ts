import { createGlobalStyle } from "antd-style";
import { DESIGN_TOKENS } from "@/config/designTokens";

export default createGlobalStyle`
.chat-task-list {
  padding: 0 20px;
  margin-bottom: 8px;

  &-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 21px;
    margin-bottom: 6px;
    cursor: pointer;
  }

  &-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 500;
    color: ${DESIGN_TOKENS.colorTextPrimary};
  }

  &-toggle {
    width: 10px;
    height: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.2s ease;

    &--collapsed {
      transform: rotate(-90deg);
    }
  }

  &-items {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  &-item {
    position: relative;
    padding: 8px 12px;
    cursor: pointer;
    border-radius: 4px;
    background-color: transparent;
    transition: background-color 0.15s ease;
    overflow: hidden;

    &:hover {
      background: rgba(55, 105, 252, 0.04);
    }

    &--paused {
      background: rgba(223, 146, 33, 0.06);
    }

    &--running {
      background: rgba(55, 105, 252, 0.06);
    }

    &--selected {
      background: rgba(55, 105, 252, 0.10);

      &::before {
        content: "";
        position: absolute;
        left: 0;
        top: 4px;
        bottom: 4px;
        width: 3px;
        border-radius: 0 2px 2px 0;
        background-color: #3769FC;
      }
    }
  }

  &-item-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 2px;
  }

  &-item-title {
    font-size: 14px;
    line-height: 20px;
    font-weight: 500;
    color: ${DESIGN_TOKENS.colorTextPrimary};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
  }

  &-item-badge {
    flex-shrink: 0;
    min-width: 14px;
    height: 14px;
    padding: 0 4px;
    border-radius: 7px;
    background-color: ${DESIGN_TOKENS.colorBadgeRed};
    color: #FFFFFF;
    font-size: 10px;
    line-height: 14px;
    text-align: center;
  }

  &-item-trailing {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    gap: 6px;
  }

  &-item-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 4px;
    flex: 0 0 auto;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.15s ease;
  }

  &-item:hover &-item-actions,
  &-item:focus-within &-item-actions {
    opacity: 1;
    pointer-events: auto;
  }

  &-item-action-trigger {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    padding: 0;
    border: none;
    border-radius: 7px;
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

  &-item-status {
    margin-bottom: 4px;
    font-size: 12px;
    line-height: 16px;
    font-weight: 600;

    &--auto {
      color: #A15C07;
    }

    &--manual {
      color: ${DESIGN_TOKENS.colorTextMuted};
    }

  }

  &-item-subtitle {
    font-size: 12px;
    line-height: 16px;
    color: ${DESIGN_TOKENS.colorTextMuted};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &-item-next-run {
    margin-top: 4px;
    font-size: 12px;
    line-height: 16px;
    color: ${DESIGN_TOKENS.colorTextSecondary};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &-item-time {
    margin-right: 8px;
    color: ${DESIGN_TOKENS.colorTextMuted};
  }

  &-paused-group {
    margin: 2px 0 6px;
  }

  &-paused-toggle {
    width: 100%;
    min-height: 40px;
    padding: 0 10px 0 8px;
    display: flex;
    align-items: center;
    gap: 9px;
    border: 1px solid rgba(55, 105, 252, 0.10);
    border-radius: 9px;
    background: rgba(55, 105, 252, 0.035);
    color: ${DESIGN_TOKENS.colorTextSecondary};
    font-size: 13px;
    line-height: 20px;
    cursor: pointer;
    box-shadow: 0 1px 2px rgba(17, 20, 45, 0.025);
    transition:
      background-color 0.18s ease,
      border-color 0.18s ease,
      box-shadow 0.18s ease;

    &:hover {
      background: rgba(55, 105, 252, 0.065);
      border-color: rgba(55, 105, 252, 0.18);
      box-shadow: 0 3px 10px rgba(55, 105, 252, 0.07);
    }

    &:focus-visible {
      outline: 2px solid rgba(55, 105, 252, 0.32);
      outline-offset: 1px;
    }

    .chat-task-list-toggle {
      flex: 0 0 auto;
      margin-left: auto;
    }
  }

  &-paused-icon {
    width: 24px;
    height: 24px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
    border-radius: 7px;
    background: rgba(55, 105, 252, 0.10);
    color: ${DESIGN_TOKENS.colorPrimary};
  }

  &-paused-label {
    min-width: 0;
    color: ${DESIGN_TOKENS.colorTextPrimary};
    font-weight: 500;
    letter-spacing: 0.01em;
  }

  &-paused-count {
    min-width: 22px;
    height: 20px;
    padding: 0 6px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
    border: 1px solid rgba(55, 105, 252, 0.10);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.76);
    color: ${DESIGN_TOKENS.colorTextSecondary};
    font-size: 11px;
    font-weight: 600;
    line-height: 18px;
  }

  &-paused-items {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 4px;

    &[hidden] {
      display: none;
    }
  }

  &-empty {
    padding: 16px 0;
    text-align: center;
    color: ${DESIGN_TOKENS.colorTextMuted};
    font-size: 13px;
  }
}

/* Dark mode support */
.dark-mode .chat-task-list-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.dark-mode .chat-task-list-item--selected {
  background: rgba(255, 255, 255, 0.12);
}

.dark-mode .chat-task-list-item--selected::before {
  background-color: #5B8AFF;
}

.dark-mode .chat-task-list-paused-group {
  border-top-color: transparent;
}

.dark-mode .chat-task-list-paused-toggle {
  background: rgba(91, 138, 255, 0.08);
  border-color: rgba(91, 138, 255, 0.14);
}

.dark-mode .chat-task-list-paused-toggle:hover {
  background: rgba(91, 138, 255, 0.13);
  border-color: rgba(91, 138, 255, 0.24);
}

.dark-mode .chat-task-list-paused-icon {
  background: rgba(91, 138, 255, 0.16);
  color: #8EADFF;
}

.dark-mode .chat-task-list-paused-count {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.08);
}

@media (prefers-reduced-motion: reduce) {
  .chat-task-list-toggle,
  .chat-task-list-paused-toggle {
    transition: none;
  }
}
`;
