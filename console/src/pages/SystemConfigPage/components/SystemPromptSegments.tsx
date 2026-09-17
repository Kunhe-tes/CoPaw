import { Button, Input, Space } from "antd";

import styles from "../index.module.less";

interface SystemPromptSegmentsProps {
  disabled: boolean;
  prompts: readonly string[];
  onAdd: () => void;
  onChange: (index: number, value: string) => void;
  onMove: (index: number, direction: -1 | 1) => void;
  onRemove: (index: number) => void;
}

export function SystemPromptSegments({
  disabled,
  prompts,
  onAdd,
  onChange,
  onMove,
  onRemove,
}: SystemPromptSegmentsProps) {
  return (
    <div className={styles.promptSegments}>
      {prompts.map((prompt, index) => (
        <section key={`${index}-${prompt}`} className={styles.promptSegment}>
          <span className={styles.promptSegmentLabel}>
            提示词片段 {index + 1}
          </span>
          <Input.TextArea
            aria-label={`提示词片段 ${index + 1}`}
            autoSize={{ minRows: 4, maxRows: 12 }}
            disabled={disabled}
            value={prompt}
            onChange={(event) => onChange(index, event.target.value)}
          />
          <Space size={4} wrap>
            <Button
              disabled={disabled || index === 0}
              onClick={() => onMove(index, -1)}
            >
              上移提示词片段 {index + 1}
            </Button>
            <Button
              disabled={disabled || index === prompts.length - 1}
              onClick={() => onMove(index, 1)}
            >
              下移提示词片段 {index + 1}
            </Button>
            <Button danger disabled={disabled} onClick={() => onRemove(index)}>
              删除提示词片段 {index + 1}
            </Button>
          </Space>
        </section>
      ))}
      <Button disabled={disabled} onClick={onAdd}>
        新增提示词片段
      </Button>
    </div>
  );
}
