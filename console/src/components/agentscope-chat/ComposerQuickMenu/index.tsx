import { PlusOutlined } from "@ant-design/icons";
import classNames from "classnames";
import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import styles from "./index.module.less";

export interface ComposerQuickMenuProps {
  children?: React.ReactNode;
  disabled?: boolean;
  triggerLabel: string;
}

export interface ComposerQuickMenuItemProps {
  icon?: React.ReactNode;
  label: React.ReactNode;
  extra?: React.ReactNode;
  onClick?: () => void;
  className?: string;
  disabled?: boolean;
}

export function ComposerQuickMenuItem(props: ComposerQuickMenuItemProps) {
  const { className, disabled = false, extra, icon, label, onClick } = props;
  const clickable = Boolean(onClick) && !disabled;

  return (
    <div
      className={classNames(
        styles.item,
        clickable && styles.itemClickable,
        disabled && styles.itemDisabled,
        className,
      )}
      aria-disabled={onClick ? disabled : undefined}
      onClick={clickable ? onClick : undefined}
      role={onClick ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      {icon ? <span className={styles.icon}>{icon}</span> : null}
      <span className={styles.label}>{label}</span>
      {extra ? <span className={styles.extra}>{extra}</span> : null}
    </div>
  );
}

export default function ComposerQuickMenu(props: ComposerQuickMenuProps) {
  const { children, disabled = false, triggerLabel } = props;
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelStyle, setPanelStyle] = useState<React.CSSProperties | null>(
    null,
  );
  const items = useMemo(
    () => React.Children.toArray(children).filter(Boolean),
    [children],
  );

  const updatePanelPosition = useCallback(() => {
    if (!triggerRef.current || !panelRef.current) {
      return;
    }

    const gap = 12;
    const viewportPadding = 16;
    const triggerRect = triggerRef.current.getBoundingClientRect();
    const panelRect = panelRef.current.getBoundingClientRect();
    const maxLeft = Math.max(
      viewportPadding,
      window.innerWidth - panelRect.width - viewportPadding,
    );
    const left = Math.min(
      Math.max(triggerRect.left, viewportPadding),
      maxLeft,
    );
    const openAbove =
      triggerRect.top >= panelRect.height + gap + viewportPadding;
    const maxTop = Math.max(
      viewportPadding,
      window.innerHeight - panelRect.height - viewportPadding,
    );
    const top = openAbove
      ? triggerRect.top - panelRect.height - gap
      : Math.min(triggerRect.bottom + gap, maxTop);

    setPanelStyle({
      left,
      top,
      visibility: "visible",
    });
  }, []);

  useEffect(() => {
    if (disabled) {
      setOpen(false);
    }
  }, [disabled]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (
        event.target instanceof Node &&
        !rootRef.current?.contains(event.target) &&
        !panelRef.current?.contains(event.target)
      ) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open) {
      setPanelStyle(null);
      return;
    }

    updatePanelPosition();

    const handleReposition = () => {
      updatePanelPosition();
    };

    window.addEventListener("resize", handleReposition);
    window.addEventListener("scroll", handleReposition, true);

    return () => {
      window.removeEventListener("resize", handleReposition);
      window.removeEventListener("scroll", handleReposition, true);
    };
  }, [open, updatePanelPosition]);

  if (items.length === 0) {
    return null;
  }

  const panel =
    open && !disabled
      ? createPortal(
          <div className={styles.portal}>
            <div
              ref={panelRef}
              className={styles.panel}
              style={panelStyle || { visibility: "hidden" }}
              onClick={() => setOpen(false)}
            >
              {items.map((item, index) => (
                <div
                  key={(React.isValidElement(item) && item.key) || index}
                  className={styles.itemWrap}
                >
                  {item}
                </div>
              ))}
            </div>
          </div>,
          document.body,
        )
      : null;

  return (
    <div className={styles.root} ref={rootRef}>
      <button
        ref={triggerRef}
        aria-label={triggerLabel}
        className={styles.trigger}
        disabled={disabled}
        type="button"
        onClick={() => {
          if (!disabled) {
            setOpen((prev) => !prev);
          }
        }}
      >
        <PlusOutlined />
      </button>
      {panel}
    </div>
  );
}
