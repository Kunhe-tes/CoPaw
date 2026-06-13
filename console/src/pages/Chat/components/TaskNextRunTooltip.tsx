import React from "react";
import { Tooltip } from "antd";
import { createGlobalStyle } from "antd-style";

const Style = createGlobalStyle`
.chat-task-next-run-tooltip .ant-tooltip-inner {
  min-width: 168px;
  padding: 8px 9px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.75);
  box-shadow: 0 6px 18px rgba(17, 20, 45, 0.14);
}

.chat-task-next-run-tooltip-title {
  margin-bottom: 5px;
  color: rgba(255, 255, 255, 0.68);
  font-size: 11px;
  line-height: 15px;
  font-weight: 500;
}

.chat-task-next-run-tooltip-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.chat-task-next-run-tooltip-row {
  display: grid;
  grid-template-columns: 34px 1fr;
  align-items: center;
  column-gap: 8px;
  font-size: 12px;
  line-height: 16px;
  white-space: nowrap;
}

.chat-task-next-run-tooltip-index {
  color: rgba(255, 255, 255, 0.56);
  font-size: 11px;
  line-height: 16px;
  font-weight: 400;
}

.chat-task-next-run-tooltip-time {
  color: rgba(255, 255, 255, 0.92);
  font-weight: 500;
}
`;

function TooltipContent({ runTimes }: { runTimes: string[] }) {
  return (
    <div>
      <div className="chat-task-next-run-tooltip-title">之后三次运行时间</div>
      <div className="chat-task-next-run-tooltip-list">
        {runTimes.map((runTime, index) => (
          <div
            className="chat-task-next-run-tooltip-row"
            key={`${runTime}-${index}`}
          >
            <span className="chat-task-next-run-tooltip-index">
              第{index + 1}次
            </span>
            <span className="chat-task-next-run-tooltip-time">{runTime}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TaskNextRunTooltip({
  runTimes,
  children,
}: {
  runTimes: string[];
  children: React.ReactElement;
}) {
  if (runTimes.length === 0) {
    return children;
  }

  return (
    <>
      <Style />
      <Tooltip
        align={{ offset: [0, -10] }}
        classNames={{ root: "chat-task-next-run-tooltip" }}
        mouseEnterDelay={0.15}
        placement="bottomLeft"
        title={<TooltipContent runTimes={runTimes} />}
      >
        {children}
      </Tooltip>
    </>
  );
}
