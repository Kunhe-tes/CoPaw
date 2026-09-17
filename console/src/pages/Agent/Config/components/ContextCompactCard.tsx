import { Form, Card, Switch, Input } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import { SliderWithValue } from "./SliderWithValue";
import styles from "../index.module.less";

interface ContextCompactCardProps {
  maxInputLength: number;
  extra?: React.ReactNode;
}

export function ContextCompactCard({
  maxInputLength,
  extra,
}: ContextCompactCardProps) {
  const { t } = useTranslation();

  const memoryCompactRatio = Form.useWatch([
    "context_compact",
    "memory_compact_ratio",
  ]);
  const lightweightGovernanceRatio = Form.useWatch([
    "context_compact",
    "lightweight_governance_ratio",
  ]);
  const precompactionStepRatio = Form.useWatch([
    "context_compact",
    "precompaction_step_ratio",
  ]);
  const emergencyCompactRatio = Form.useWatch([
    "context_compact",
    "emergency_compact_ratio",
  ]);
  const memoryReserveRatio = Form.useWatch([
    "context_compact",
    "memory_reserve_ratio",
  ]);

  const contextCompactThreshold = Math.floor(
    (maxInputLength ?? 0) * (memoryCompactRatio ?? 0),
  );
  const lightweightGovernanceThreshold = Math.floor(
    (maxInputLength ?? 0) * (lightweightGovernanceRatio ?? 0),
  );
  const precompactionStepThreshold = Math.floor(
    (maxInputLength ?? 0) * (precompactionStepRatio ?? 0),
  );
  const emergencyCompactThreshold = Math.floor(
    (maxInputLength ?? 0) * (emergencyCompactRatio ?? 0),
  );
  const contextCompactReserveThreshold = Math.floor(
    (maxInputLength ?? 0) * (memoryReserveRatio ?? 0),
  );

  return (
    <Card
      className={styles.formCard}
      title={t("agentConfig.contextCompactTitle")}
      style={{ marginTop: 16 }}
      extra={extra}
    >
      <Form.Item
        label={t("agentConfig.contextCompactEnabled")}
        name={["context_compact", "context_compact_enabled"]}
        valuePropName="checked"
        tooltip={t("agentConfig.contextCompactEnabledTooltip")}
      >
        <Switch />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.tokenCountEstimateDivisor")}
        name={["context_compact", "token_count_estimate_divisor"]}
        rules={[
          {
            required: true,
            message: t("agentConfig.tokenCountEstimateDivisorRequired"),
          },
        ]}
        tooltip={t("agentConfig.tokenCountEstimateDivisorTooltip")}
      >
        <SliderWithValue
          min={2}
          max={5}
          step={0.25}
          marks={{ 2: "2", 3: "3", 4: "4", 5: "5" }}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.lightweightGovernanceRatio")}
        name={["context_compact", "lightweight_governance_ratio"]}
        rules={[
          {
            required: true,
            message: t("agentConfig.lightweightGovernanceRatioRequired"),
          },
        ]}
        tooltip={t("agentConfig.lightweightGovernanceRatioTooltip")}
      >
        <SliderWithValue
          min={0.3}
          max={0.79}
          step={0.01}
          marks={{ 0.3: "0.3", 0.65: "0.65", 0.79: "0.79" }}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.lightweightGovernanceThreshold")}
        tooltip={t("agentConfig.lightweightGovernanceThresholdTooltip")}
      >
        <Input
          disabled
          value={
            lightweightGovernanceThreshold > 0
              ? lightweightGovernanceThreshold.toLocaleString()
              : ""
          }
          placeholder={t("agentConfig.contextCompactThresholdPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.precompactionStepRatio")}
        name={["context_compact", "precompaction_step_ratio"]}
        rules={[
          {
            required: true,
            message: t("agentConfig.precompactionStepRatioRequired"),
          },
        ]}
        tooltip={t("agentConfig.precompactionStepRatioTooltip")}
      >
        <SliderWithValue
          min={0.01}
          max={0.2}
          step={0.01}
          marks={{ 0.01: "0.01", 0.05: "0.05", 0.2: "0.2" }}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.precompactionStepThreshold")}
        tooltip={t("agentConfig.precompactionStepThresholdTooltip")}
      >
        <Input
          disabled
          value={
            precompactionStepThreshold > 0
              ? precompactionStepThreshold.toLocaleString()
              : ""
          }
          placeholder={t("agentConfig.contextCompactThresholdPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.contextCompactRatio")}
        name={["context_compact", "memory_compact_ratio"]}
        rules={[
          {
            required: true,
            message: t("agentConfig.contextCompactRatioRequired"),
          },
        ]}
        tooltip={t("agentConfig.contextCompactRatioTooltip")}
      >
        <SliderWithValue
          min={0.31}
          max={0.89}
          step={0.01}
          marks={{ 0.31: "0.31", 0.8: "0.80", 0.89: "0.89" }}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.contextCompactThreshold")}
        tooltip={t("agentConfig.contextCompactThresholdTooltip")}
      >
        <Input
          disabled
          value={
            contextCompactThreshold > 0
              ? contextCompactThreshold.toLocaleString()
              : ""
          }
          placeholder={t("agentConfig.contextCompactThresholdPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.emergencyCompactRatio")}
        name={["context_compact", "emergency_compact_ratio"]}
        rules={[
          {
            required: true,
            message: t("agentConfig.emergencyCompactRatioRequired"),
          },
        ]}
        tooltip={t("agentConfig.emergencyCompactRatioTooltip")}
      >
        <SliderWithValue
          min={0.32}
          max={0.95}
          step={0.01}
          marks={{ 0.32: "0.32", 0.9: "0.90", 0.95: "0.95" }}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.emergencyCompactThreshold")}
        tooltip={t("agentConfig.emergencyCompactThresholdTooltip")}
      >
        <Input
          disabled
          value={
            emergencyCompactThreshold > 0
              ? emergencyCompactThreshold.toLocaleString()
              : ""
          }
          placeholder={t("agentConfig.contextCompactThresholdPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.contextCompactReserveRatio")}
        name={["context_compact", "memory_reserve_ratio"]}
        rules={[
          {
            required: true,
            message: t("agentConfig.contextCompactReserveRatioRequired"),
          },
        ]}
        tooltip={t("agentConfig.contextCompactReserveRatioTooltip")}
      >
        <SliderWithValue
          min={0.05}
          max={0.3}
          step={0.01}
          marks={{ 0.05: "0.05", 0.15: "0.15", 0.3: "0.3" }}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.contextCompactReserveThreshold")}
        tooltip={t("agentConfig.contextCompactReserveThresholdTooltip")}
      >
        <Input
          disabled
          value={
            contextCompactReserveThreshold > 0
              ? contextCompactReserveThreshold.toLocaleString()
              : ""
          }
          placeholder={t(
            "agentConfig.contextCompactReserveThresholdPlaceholder",
          )}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.compactWithThinkingBlock")}
        name={["context_compact", "compact_with_thinking_block"]}
        valuePropName="checked"
        tooltip={t("agentConfig.compactWithThinkingBlockTooltip")}
      >
        <Switch />
      </Form.Item>
    </Card>
  );
}
