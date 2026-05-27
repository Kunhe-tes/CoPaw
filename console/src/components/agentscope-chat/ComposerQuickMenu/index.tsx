import { PlusOutlined } from "@ant-design/icons";
import classNames from "classnames";
import React, { useEffect, useMemo, useRef, useState } from "react";
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
}

export function ComposerQuickMenuItem(props: ComposerQuickMenuItemProps) {
  const { className, extra, icon, label, onClick } = props;

  return (
    <div
      className={classNames(styles.item, onClick && styles.itemClickable, className)}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
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
  const items = useMemo(
    () => React.Children.toArray(children).filter(Boolean),
    [children],
  );

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (
        rootRef.current &&
        event.target instanceof Node &&
        !rootRef.current.contains(event.target)
      ) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [open]);

  if (items.length === 0) {
    return null;
  }

  return (
    <div className={styles.root} ref={rootRef}>
      <button
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
      {open ? (
        <div className={styles.panel} onClick={() => setOpen(false)}>
          {items.map((item, index) => (
            <div
              key={(React.isValidElement(item) && item.key) || index}
              className={styles.itemWrap}
            >
              {item}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
