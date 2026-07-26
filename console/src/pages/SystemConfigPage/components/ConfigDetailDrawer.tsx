import type { ReactNode } from "react";
import { Button, Drawer, Tag } from "antd";

import type { CapabilitySummary } from "../workbench";
import styles from "../index.module.less";

interface ConfigDetailDrawerProps {
  capability: CapabilitySummary | null;
  open: boolean;
  onClose: () => void;
  onLocate: () => void;
  children: ReactNode;
}

export function ConfigDetailDrawer({
  capability,
  open,
  onClose,
  onLocate,
  children,
}: ConfigDetailDrawerProps) {
  if (!capability) {
    return null;
  }

  return (
    <Drawer
      destroyOnClose={false}
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
        <span>调整在保存前不会生效。</span>
      </div>
      {children}
      <Button type="primary" block onClick={onLocate}>
        定位到配置编辑区
      </Button>
    </Drawer>
  );
}
