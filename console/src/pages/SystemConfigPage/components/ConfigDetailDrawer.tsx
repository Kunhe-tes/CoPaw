import type { ReactNode } from "react";
import { Button, Drawer, Tag } from "antd";

import type { CapabilitySummary } from "../workbench";
import styles from "../index.module.less";

interface ConfigDetailDrawerProps {
  capability: CapabilitySummary | null;
  hasUnsavedChanges: boolean;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function ConfigDetailDrawer({
  capability,
  hasUnsavedChanges,
  open,
  onClose,
  children,
}: ConfigDetailDrawerProps) {
  if (!capability) {
    return null;
  }

  return (
    <Drawer
      destroyOnClose={false}
      footer={
        <div className={styles.drawerFooter}>
          <span className={hasUnsavedChanges ? styles.dirtySummary : undefined}>
            {hasUnsavedChanges ? "草稿尚未保存" : "修改将在页面底部统一保存"}
          </span>
          <Button onClick={onClose}>关闭</Button>
        </div>
      }
      open={open}
      width={560}
      title={`${capability.title}配置`}
      onClose={onClose}
    >
      <div className={styles.drawerIntro}>
        <div className={styles.drawerIntroHeader}>
          <Tag>{capability.sourceLabel}</Tag>
          {capability.highImpact ? <Tag color="orange">高影响</Tag> : null}
        </div>
        <p>{capability.description}</p>
        <span>调整在保存前不会生效，所有修改仍会通过页面底部统一保存。</span>
      </div>
      {children}
    </Drawer>
  );
}
