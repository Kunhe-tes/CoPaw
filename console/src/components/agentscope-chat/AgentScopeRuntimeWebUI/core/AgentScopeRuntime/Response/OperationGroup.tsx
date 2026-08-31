import { memo, useState } from "react";
import type { ReactNode } from "react";
import {
  SparkCheckCircleFill,
  SparkDownLine,
  SparkErrorCircleFill,
  SparkLoadingLine,
  SparkLockFill,
  SparkStopCircleLine,
  SparkTimeLine,
  SparkUpLine,
  SparkWarningCircleFill,
} from "@agentscope-ai/icons";
import { useProviderContext } from "@/components/agentscope-chat";
import Style from "./style";
import type { IAgentScopeRuntimeMessage } from "../types";
import type {
  GroupSummaryStatus,
  OperationGroupEntry,
  ToolStepStatus,
} from "./operationGrouping";
import {
  aggregateGroupStatus,
  getToolStepKey,
  getToolStepStatus,
  getToolStepText,
} from "./operationGrouping";

function getGroupStatusIcon(
  status: GroupSummaryStatus,
): (props: { spin?: boolean }) => ReactNode {
  switch (status) {
    case "running":
      return SparkLoadingLine;
    case "pending":
      return SparkTimeLine;
    case "warning":
      return SparkWarningCircleFill;
    case "failed":
      return SparkErrorCircleFill;
    case "canceled":
      return SparkStopCircleLine;
    default:
      return SparkCheckCircleFill;
  }
}

function getStepStatusIcon(
  status: ToolStepStatus,
): (props: { spin?: boolean }) => ReactNode {
  switch (status) {
    case "running":
      return SparkLoadingLine;
    case "pending":
      return SparkTimeLine;
    case "rejected":
      return SparkWarningCircleFill;
    case "blocked":
      return SparkLockFill;
    case "failed":
      return SparkErrorCircleFill;
    case "canceled":
      return SparkStopCircleLine;
    default:
      return SparkCheckCircleFill;
  }
}

const STEP_STATUS_LABEL: Record<ToolStepStatus, string> = {
  running: "执行中",
  success: "成功",
  failed: "失败",
  pending: "待审批",
  rejected: "已拒绝",
  blocked: "已拦截",
  canceled: "已取消",
};

const GROUP_STATUS_LABEL: Record<GroupSummaryStatus, string> = {
  running: "执行中",
  success: "成功",
  failed: "失败",
  pending: "待审批",
  warning: "治理警告",
  canceled: "已取消",
};

function StepRow({ message }: { message: IAgentScopeRuntimeMessage }) {
  const { getPrefixCls } = useProviderContext();
  const prefixCls = getPrefixCls("response-operation-group");
  const status = getToolStepStatus(message);
  const text = getToolStepText(message);
  const Icon = getStepStatusIcon(status);

  return (
    <div
      className={prefixCls + "-step"}
      role="listitem"
      aria-label={text + "，" + STEP_STATUS_LABEL[status]}
      data-status={status}
    >
      <span
        className={prefixCls + "-step-icon"}
        data-status={status}
        aria-hidden="true"
      >
        <Icon spin={status === "running"} />
      </span>
      <span className={prefixCls + "-step-text"}>{text}</span>
      <span className={prefixCls + "-step-status"}>
        {STEP_STATUS_LABEL[status]}
      </span>
    </div>
  );
}

function OperationGroupComponent({ entry }: { entry: OperationGroupEntry }) {
  const { getPrefixCls } = useProviderContext();
  const prefixCls = getPrefixCls("response-operation-group");
  const [open, setOpen] = useState(false);
  const summary = aggregateGroupStatus(entry.steps);
  const Icon = getGroupStatusIcon(summary);
  const statusLabel = GROUP_STATUS_LABEL[summary];

  const toggle = () => {
    setOpen((current) => !current);
  };

  return (
    <>
      <Style />
      <div className={prefixCls}>
        <button
          type="button"
          className={prefixCls + "-trigger"}
          aria-expanded={open}
          aria-label={
            (open ? "收起" : "展开") +
            "操作组：" +
            entry.group.title +
            "，" +
            statusLabel
          }
          data-status={summary}
          onClick={toggle}
        >
          <span
            className={prefixCls + "-icon"}
            data-status={summary}
            aria-hidden="true"
          >
            <Icon spin={summary === "running"} />
          </span>
          <span className={prefixCls + "-title"}>{entry.group.title}</span>
          <span className={prefixCls + "-chevron"} aria-hidden="true">
            {open ? <SparkUpLine /> : <SparkDownLine />}
          </span>
        </button>
        <div
          className={
            prefixCls + "-body" + (open ? " " + prefixCls + "-body-open" : "")
          }
          hidden={!open}
          role="list"
        >
          {entry.steps.map((message) => (
            <StepRow
              key={entry.key + ":" + getToolStepKey(message)}
              message={message}
            />
          ))}
        </div>
      </div>
    </>
  );
}

const OperationGroup = memo(OperationGroupComponent);
export default OperationGroup;
