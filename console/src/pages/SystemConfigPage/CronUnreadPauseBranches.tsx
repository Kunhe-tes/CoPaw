import { useState } from "react";
import { Button, Input, InputNumber, Space, Switch } from "antd";
import { getBbkDisplayName } from "@/constants/bbk";
import type {
  CronUnreadAutoPauseConfig,
  CronUnreadPauseBranches as BranchRules,
} from "./registry";
import styles from "./index.module.less";

export function CronUnreadPauseBranches({
  config,
  disabled,
  onChange,
}: {
  config: CronUnreadAutoPauseConfig;
  disabled: boolean;
  onChange: (rules: BranchRules) => void;
}) {
  const [code, setCode] = useState("");
  const branch = code.trim();
  const rules = config.by_branch ?? {};
  const canAdd =
    /^[A-Za-z0-9_-]{1,64}$/.test(branch) &&
    !Object.prototype.hasOwnProperty.call(rules, branch);
  return (
    <details className={styles.advancedParameters}>
      <summary>按分行配置未读暂停（{Object.keys(rules).length}）</summary>
      <Space direction="vertical">
        <span className={styles.switchDescription}>
          有分行规则时按个人信息中的分行应用，其余任务使用渠道默认值。
        </span>
        <Space wrap>
          <Input
            aria-label="分行代码"
            placeholder="分行代码，例如 110"
            maxLength={64}
            value={code}
            disabled={disabled}
            onChange={(event) => setCode(event.target.value)}
          />
          <Button
            disabled={disabled || !canAdd}
            onClick={() => {
              onChange({
                ...rules,
                [branch]: {
                  enabled: config.enabled,
                  threshold: config.threshold,
                },
              });
              setCode("");
            }}
          >
            添加分行
          </Button>
        </Space>
        {Object.entries(rules).map(([id, rule]) => (
          <Space key={id} wrap>
            <span>
              {getBbkDisplayName(id) === id
                ? id
                : `${getBbkDisplayName(id)}（${id}）`}
            </span>
            <Switch
              aria-label={`${id} 分行未读暂停`}
              checked={rule.enabled ?? config.enabled}
              disabled={disabled}
              onChange={(enabled) =>
                onChange({ ...rules, [id]: { ...rule, enabled } })
              }
            />
            <InputNumber
              aria-label={`${id} 分行未读暂停条数`}
              min={1}
              step={1}
              precision={0}
              value={rule.threshold ?? config.threshold}
              disabled={disabled || !(rule.enabled ?? config.enabled)}
              onChange={(threshold) => {
                if (threshold !== null)
                  onChange({ ...rules, [id]: { ...rule, threshold } });
              }}
            />
            <Button
              type="link"
              disabled={disabled}
              onClick={() => {
                const next = { ...rules };
                delete next[id];
                onChange(next);
              }}
            >
              恢复渠道默认
            </Button>
          </Space>
        ))}
      </Space>
    </details>
  );
}
