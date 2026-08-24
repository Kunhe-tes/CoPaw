import { createGlobalStyle } from "antd-style";

export const ModelCallFailedStyle = createGlobalStyle`
.${(p) => p.theme.prefixCls}-model-call-failed {
  container-type: inline-size;
  width: 100%;
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.colorErrorBorder};
  border-radius: 12px;
  background: ${({ theme }) => theme.colorErrorBg};
  color: ${({ theme }) => theme.colorText};
  box-shadow: 0 2px 8px rgba(35, 31, 27, 0.05);
  margin-top: 4px;

  &-main {
    padding: 14px 18px;
  }

  &-header,
  &-header-copy,
  &-detail-header,
  &-detail-trigger,
  &-detail-copy,
  &-settings-link {
    display: flex;
    align-items: center;
  }

  &-header {
    justify-content: space-between;
    gap: 16px;
  }

  &-header-copy {
    min-width: 0;
    gap: 10px;
  }

  &-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    flex: 0 0 20px;
    border-radius: 50%;
    background: ${({ theme }) => theme.colorErrorBgHover};
    color: ${({ theme }) => theme.colorError};

    svg {
      width: 17px;
      height: 17px;
    }
  }

  &-title {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    line-height: 22px;
    color: ${({ theme }) => theme.colorText};
  }

  &-status {
    flex: 0 0 auto;
    padding: 2px 7px;
    border-radius: 6px;
    background: ${({ theme }) => theme.colorFillTertiary};
    color: ${({ theme }) => theme.colorTextSecondary};
    font-size: 12px;
    font-weight: 500;
    line-height: 18px;
  }

  &-message {
    margin: 12px 0 0;
    color: ${({ theme }) => theme.colorText};
    font-size: 14px;
    line-height: 22px;
  }

  &-guidance {
    margin: 2px 0 0;
    color: ${({ theme }) => theme.colorTextSecondary};
    font-size: 13px;
    line-height: 21px;
  }

  &-settings-link {
    width: fit-content;
    gap: 5px;
    margin-top: 10px;
    color: #3769fc;
    font-size: 13px;
    font-weight: 500;
    line-height: 20px;
    text-decoration: none;

    svg {
      width: 14px;
      height: 14px;
    }

    &:hover {
      color: #2957dc;
      text-decoration: underline;
      text-underline-offset: 3px;
    }
  }

  &-detail {
    border-top: 1px solid ${({ theme }) => theme.colorErrorBorder};
  }

  &-detail-header {
    min-height: 42px;
    justify-content: space-between;
    gap: 12px;
    padding: 6px 18px;
  }

  &-detail-trigger,
  &-detail-copy {
    gap: 7px;
    padding: 5px 0;
    border: 0;
    background: transparent;
    color: ${({ theme }) => theme.colorTextSecondary};
    cursor: pointer;
    font: inherit;
    font-size: 13px;
    font-weight: 500;
    line-height: 20px;

    svg {
      width: 14px;
      height: 14px;
      flex: 0 0 14px;
    }

    &:hover {
      color: ${({ theme }) => theme.colorText};
    }
  }

  &-detail-copy {
    font-weight: 400;
  }

  &-details {
    margin: 0;
    padding: 0 18px 14px;
  }

  &-detail-row {
    display: grid;
    grid-template-columns: minmax(72px, max-content) minmax(0, 1fr);
    gap: 14px;
    padding: 7px 0;
    border-top: 1px solid ${({ theme }) => theme.colorErrorBorder};

    &:first-of-type {
      border-top: 0;
    }
  }

  &-detail-label,
  &-detail-value {
    margin: 0;
    font-size: 12px;
    line-height: 19px;
  }

  &-detail-label {
    color: ${({ theme }) => theme.colorTextSecondary};
    font-weight: 500;
  }

  &-detail-value {
    min-width: 0;
    overflow-wrap: anywhere;
    color: ${({ theme }) => theme.colorText};
    font-family: SFMono-Regular, Consolas, "Liberation Mono", monospace;
  }

  button:focus-visible,
  a:focus-visible {
    outline: 2px solid #3769fc;
    outline-offset: 2px;
  }

  @media (max-width: 640px) {
    &-main {
      padding: 14px;
    }

    &-header {
      align-items: flex-start;
    }

    &-header-copy {
      flex-wrap: wrap;
    }

    &-detail-header,
    &-details {
      padding-left: 14px;
      padding-right: 14px;
    }

    &-detail-row {
      grid-template-columns: 1fr;
      gap: 2px;
    }
  }

  @container (max-width: 420px) {
    &-main {
      padding: 14px;
    }

    &-header,
    &-detail-header {
      flex-wrap: wrap;
    }

    &-header-copy {
      display: grid;
      width: 100%;
      flex: 1 1 100%;
      grid-template-columns: 30px minmax(0, 1fr);
    }

    &-icon {
      grid-row: 1 / span 2;
    }

    &-title {
      white-space: nowrap;
    }

    &-status {
      width: fit-content;
      grid-column: 2;
    }

    &-detail-header,
    &-details {
      padding-left: 14px;
      padding-right: 14px;
    }

    &-detail-row {
      grid-template-columns: 1fr;
      gap: 2px;
    }
  }
}
`;
