import { Button, Drawer, Empty, Popconfirm, Select, Space, Tag } from "antd";
import type { ReactNode } from "react";

import { eventMetadata } from "../eventMetadata";
import type {
  HookEventName,
  HookHandlerType,
  HookMatcherGroupDraft,
} from "../types";

import styles from "../index.module.less";

type EventEditorDrawerProps = {
  event: HookEventName | null;
  groups: HookMatcherGroupDraft[];
  templateLabel?: string;
  details: ReactNode;
  onAddGroup: () => void;
  onAddHandler: (groupId: string, type: HookHandlerType) => void;
  onClose: () => void;
  onMoveHandler: (groupId: string, fromIndex: number, toIndex: number) => void;
  onRemoveEvent: () => void;
  onRemoveGroup: (groupId: string) => void;
  onRemoveHandler: (groupId: string, handlerId: string) => void;
  onSelectGroup: (groupId: string) => void;
  onSelectHandler: (groupId: string, handlerId: string) => void;
};

function describeMatcher(group: HookMatcherGroupDraft): string {
  return group.matcher.tools.length
    ? `仅 ${group.matcher.tools.join("、")} 工具`
    : "所有工具";
}

export function EventEditorDrawer({
  event,
  groups,
  templateLabel,
  details,
  onAddGroup,
  onAddHandler,
  onClose,
  onMoveHandler,
  onRemoveEvent,
  onRemoveGroup,
  onRemoveHandler,
  onSelectGroup,
  onSelectHandler,
}: EventEditorDrawerProps) {
  if (!event) return null;
  const metadata = eventMetadata[event];
  return (
    <Drawer
      aria-label={`编辑 ${event}`}
      destroyOnClose
      open
      placement="right"
      title={`编辑 ${event}`}
      width="min(760px, 100vw)"
      onClose={onClose}
      extra={
        <Space>
          <Popconfirm
            cancelText="取消"
            description="删除后该事件不会再执行任何 Hook。"
            okButtonProps={{ danger: true }}
            okText="确认删除"
            title={`删除 ${event} 事件？`}
            onConfirm={onRemoveEvent}
          >
            <Button danger>删除事件</Button>
          </Popconfirm>
          <Button onClick={onClose}>完成</Button>
        </Space>
      }
    >
      {templateLabel && <Tag color="blue">{templateLabel}</Tag>}
      <section className={styles.drawerSection}>
        <h3>何时触发</h3>
        <p>{metadata.description}</p>
      </section>
      <section className={styles.drawerSection}>
        <h3>适用范围</h3>
        {groups.length ? (
          groups.map((group) => (
            <div key={group.id} className={styles.groupPanel}>
              <div className={styles.groupSummary}>
                <Button
                  type="text"
                  onClick={() => onSelectGroup(group.id)}
                >
                  <strong>{describeMatcher(group)}</strong>
                </Button>
                <span>{group.hooks.length} 个处理器</span>
                <Button danger size="small" type="text" onClick={() => onRemoveGroup(group.id)}>
                  删除分组
                </Button>
              </div>
              <div className={styles.handlerCards}>
                {group.hooks.map((handler, index) => (
                  <div key={handler.id} className={styles.handlerCard}>
                    <Button
                      type="text"
                      onClick={() => onSelectHandler(group.id, handler.id)}
                    >
                      {handler.id} <Tag>{handler.type}</Tag>
                    </Button>
                    <Button
                      danger
                      size="small"
                      type="text"
                      onClick={() => onRemoveHandler(group.id, handler.id)}
                    >
                      删除
                    </Button>
                    <Button
                      aria-label={`${handler.id} 上移`}
                      disabled={index === 0}
                      size="small"
                      type="text"
                      onClick={() => onMoveHandler(group.id, index, index - 1)}
                    >
                      上移
                    </Button>
                    <Button
                      aria-label={`${handler.id} 下移`}
                      disabled={index === group.hooks.length - 1}
                      size="small"
                      type="text"
                      onClick={() => onMoveHandler(group.id, index, index + 1)}
                    >
                      下移
                    </Button>
                  </div>
                ))}
                <Select
                  className={styles.handlerTypeSelect}
                  placeholder="添加处理器"
                  options={(["command", "http", "prompt"] as HookHandlerType[]).map(
                    (type) => ({ value: type, label: type }),
                  )}
                  onChange={(type: HookHandlerType) => onAddHandler(group.id, type)}
                />
              </div>
            </div>
          ))
        ) : (
          <Empty description="尚未添加匹配分组" />
        )}
        <Button type="dashed" onClick={onAddGroup}>
          添加分组
        </Button>
      </section>
      <section className={styles.drawerSection}>
        <h3>依序执行的处理器</h3>
        {details}
      </section>
    </Drawer>
  );
}
