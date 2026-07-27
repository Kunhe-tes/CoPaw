import { Button, Card, Empty, Switch, Tag } from "antd";

import { eventMetadata } from "../eventMetadata";
import type { HookConfigDraft, HookEventName } from "../types";

import styles from "../index.module.less";

type EventOverviewProps = {
  config: HookConfigDraft;
  dirty: boolean;
  onEnabledChange: (enabled: boolean) => void;
  onEdit: (event: HookEventName) => void;
  onCreate: () => void;
};

function getHandlerCount(config: HookConfigDraft, event: HookEventName): number {
  return (config.events[event] ?? []).reduce(
    (count, group) => count + group.hooks.length,
    0,
  );
}

export function EventOverview({
  config,
  dirty,
  onEnabledChange,
  onEdit,
  onCreate,
}: EventOverviewProps) {
  return (
    <section className={styles.overview}>
      <div className={styles.overviewHeader}>
        <div>
          <h2>事件配置</h2>
          <p>选择一个事件，配置其匹配范围和按顺序执行的处理器。</p>
        </div>
        <div className={styles.overviewActions}>
          {dirty && <Tag color="processing">未保存更改</Tag>}
          <span className={styles.globalSwitch}>
            <Switch
              checked={config.enabled}
              onChange={onEnabledChange}
              aria-label="启用 Hook"
            />
            启用 Hook
          </span>
          <Button type="primary" onClick={onCreate}>
            新建事件
          </Button>
        </div>
      </div>
      <div className={styles.eventGrid}>
        {Object.entries(eventMetadata)
          .sort(([, left], [, right]) => left.order - right.order)
          .map(([event, metadata]) => {
            const eventName = event as HookEventName;
            const groups = config.events[eventName] ?? [];
            const handlerCount = getHandlerCount(config, eventName);
            const configured = Boolean(config.events[eventName]);
            return (
              <Card
                key={event}
                className={styles.eventCard}
                size="small"
                title={
                  <span>
                    <strong>{event}</strong>
                    <span className={styles.eventLabel}>{metadata.label}</span>
                  </span>
                }
                extra={
                  configured ? (
                    <Tag color="success">已配置</Tag>
                  ) : (
                    <Tag>未配置</Tag>
                  )
                }
              >
                <p>{metadata.description}</p>
                {configured ? (
                  <p className={styles.eventStats}>
                    {groups.length} 个分组 · {handlerCount} 个处理器
                  </p>
                ) : (
                  <Empty
                    className={styles.eventEmpty}
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="尚未配置，不会执行 Hook"
                  />
                )}
                <Button
                  block
                  onClick={() => onEdit(eventName)}
                  type={configured ? "default" : "dashed"}
                >
                  {configured ? `编辑 ${event}` : `开始配置 ${event}`}
                </Button>
              </Card>
            );
          })}
      </div>
    </section>
  );
}
