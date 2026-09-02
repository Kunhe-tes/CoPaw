import { describe, expect, it } from "vitest";
import {
  AgentScopeRuntimeContentType,
  AgentScopeRuntimeMessageType,
  AgentScopeRuntimeRunStatus,
  type IAgentScopeRuntimeMessage,
} from "../types";
import {
  OPERATION_GROUP_SAFE_TITLE,
  aggregateGroupStatus,
  extractOperationGroup,
  getToolStepKey,
  getToolStepStatus,
  getToolStepText,
  groupOperationMessages,
} from "./operationGrouping";

function toolMessage(options: {
  id: string;
  toolName?: string;
  group?: { id: string; title: string } | null;
  inputStatus?: string;
  outputStatus?: string;
  governance?: string;
  outputSummary?: string;
  summary?: string;
  callId?: string;
  messageStatus?: AgentScopeRuntimeRunStatus;
}): IAgentScopeRuntimeMessage {
  const toolName = options.toolName || "execute_shell_command";
  const inputData: Record<string, unknown> = {
    name: toolName,
    arguments: "{}",
    summary: options.summary || "开始执行操作",
  };
  if (options.callId) inputData.call_id = options.callId;
  if (options.group) {
    inputData.operation_group = options.group;
  }
  if (options.inputStatus) inputData.tool_status = options.inputStatus;

  const content: IAgentScopeRuntimeMessage["content"] = [
    {
      type: AgentScopeRuntimeContentType.DATA,
      status: AgentScopeRuntimeRunStatus.Completed,
      data: inputData,
    },
  ];
  if (options.outputStatus || options.governance || options.outputSummary) {
    const outputData: Record<string, unknown> = { name: toolName };
    if (options.outputStatus) outputData.tool_status = options.outputStatus;
    if (options.governance) {
      outputData.tool_governance = options.governance;
    }
    if (options.outputSummary)
      outputData.output_summary = options.outputSummary;
    content.push({
      type: AgentScopeRuntimeContentType.DATA,
      status: AgentScopeRuntimeRunStatus.Completed,
      data: outputData,
    });
  }

  return {
    id: options.id,
    object: "message",
    role: "assistant",
    type: AgentScopeRuntimeMessageType.PLUGIN_CALL,
    status: options.messageStatus || AgentScopeRuntimeRunStatus.InProgress,
    content,
  };
}

function textMessage(id: string): IAgentScopeRuntimeMessage {
  return {
    id,
    object: "message",
    role: "assistant",
    type: AgentScopeRuntimeMessageType.MESSAGE,
    status: AgentScopeRuntimeRunStatus.InProgress,
    content: [
      {
        type: AgentScopeRuntimeContentType.TEXT,
        status: AgentScopeRuntimeRunStatus.Completed,
        text: "正在处理",
      },
    ],
  };
}

function reasoningMessage(
  id: string,
  text = "正在判断下一步",
  status = AgentScopeRuntimeRunStatus.Completed,
): IAgentScopeRuntimeMessage {
  return {
    id,
    object: "message",
    role: "assistant",
    type: AgentScopeRuntimeMessageType.REASONING,
    status,
    content: [
      {
        type: AgentScopeRuntimeContentType.TEXT,
        status,
        text,
      },
    ],
  };
}

const GROUP_A = { id: "inspect", title: "检查图片" };
const GROUP_B = { id: "verify", title: "校验结果" };

describe("extractOperationGroup", () => {
  it("reads the backend-provided group from a tool message", () => {
    const message = toolMessage({ id: "t1", group: GROUP_A });
    expect(extractOperationGroup(message)).toEqual({
      id: "inspect",
      title: "检查图片",
      instanceKey: "inspect",
    });
  });

  it("returns null for messages without a declaration", () => {
    expect(extractOperationGroup(toolMessage({ id: "t1" }))).toBeNull();
    expect(extractOperationGroup(textMessage("m1"))).toBeNull();
  });

  it("falls back to the generic safe title", () => {
    const message = toolMessage({
      id: "t1",
      group: { id: "g1", title: "" },
    });
    expect(extractOperationGroup(message)?.title).toBe(
      OPERATION_GROUP_SAFE_TITLE,
    );
  });
});

describe("getToolStepStatus", () => {
  it("uses terminal output status when present", () => {
    const message = toolMessage({
      id: "t1",
      group: GROUP_A,
      inputStatus: "running",
      outputStatus: "failed",
    });
    expect(getToolStepStatus(message)).toBe("failed");
  });

  it("falls back to the running input status", () => {
    const message = toolMessage({ id: "t1", group: GROUP_A });
    expect(getToolStepStatus(message)).toBe("running");
  });

  it("prefers governance status over execution status", () => {
    const message = toolMessage({
      id: "t1",
      group: GROUP_A,
      inputStatus: "running",
      governance: "pending",
    });
    expect(getToolStepStatus(message)).toBe("pending");
  });

  it("maps message-level canceled to canceled", () => {
    const message = toolMessage({
      id: "t1",
      group: GROUP_A,
      messageStatus: AgentScopeRuntimeRunStatus.Canceled,
    });
    expect(getToolStepStatus(message)).toBe("canceled");
  });
});

describe("getToolStepKey", () => {
  it("uses the stable call id instead of the replaceable message id", () => {
    const message = toolMessage({
      id: "output-message-id",
      callId: "call-1",
      group: GROUP_A,
    });

    expect(getToolStepKey(message)).toBe("call-1");
  });
});

describe("getToolStepText", () => {
  it("uses fixed shell texts per status", () => {
    expect(
      getToolStepText(
        toolMessage({ id: "t1", group: GROUP_A, inputStatus: "running" }),
      ),
    ).toBe("正在执行命令行操作");
    expect(
      getToolStepText(
        toolMessage({
          id: "t1",
          group: GROUP_A,
          inputStatus: "running",
          outputStatus: "success",
        }),
      ),
    ).toBe("命令行操作已完成");
    expect(
      getToolStepText(
        toolMessage({
          id: "t1",
          group: GROUP_A,
          inputStatus: "running",
          governance: "rejected",
        }),
      ),
    ).toBe("命令行操作已拒绝");
  });

  it("uses fixed background-process texts per status", () => {
    const message = toolMessage({
      id: "t1",
      toolName: "start_background_process",
      group: GROUP_A,
      inputStatus: "running",
      governance: "pending",
    });
    expect(getToolStepText(message)).toBe("后台任务待审批");
  });

  it("falls back to the backend summary for other tools", () => {
    const message = toolMessage({
      id: "t1",
      toolName: "read_file",
      group: GROUP_A,
      inputStatus: "running",
      outputStatus: "success",
      outputSummary: "读取完成",
    });
    expect(getToolStepText(message)).toBe("读取完成");
  });

  it("prefers the call action summary over the result summary", () => {
    const message = toolMessage({
      id: "t1",
      toolName: "glob_search",
      group: GROUP_A,
      inputStatus: "running",
      outputStatus: "success",
      summary: "正在查看工作目录文件",
      outputSummary: "共找到 1 项内容",
    });

    expect(getToolStepText(message)).toBe("正在查看工作目录文件");
  });
});

describe("aggregateGroupStatus", () => {
  it("returns success when every step succeeded", () => {
    const steps = [
      toolMessage({ id: "t1", group: GROUP_A, outputStatus: "success" }),
      toolMessage({ id: "t2", group: GROUP_A, outputStatus: "success" }),
    ];
    expect(aggregateGroupStatus(steps)).toBe("success");
  });

  it("returns failed when any step really failed", () => {
    const steps = [
      toolMessage({ id: "t1", group: GROUP_A, outputStatus: "success" }),
      toolMessage({ id: "t2", group: GROUP_A, outputStatus: "failed" }),
    ];
    expect(aggregateGroupStatus(steps)).toBe("failed");
  });

  it("returns pending when a step awaits approval and nothing failed", () => {
    const steps = [
      toolMessage({ id: "t1", group: GROUP_A, outputStatus: "success" }),
      toolMessage({ id: "t2", group: GROUP_A, governance: "pending" }),
    ];
    expect(aggregateGroupStatus(steps)).toBe("pending");
  });

  it("returns warning when only rejected/blocked steps exist", () => {
    const steps = [
      toolMessage({ id: "t1", group: GROUP_A, governance: "blocked" }),
      toolMessage({ id: "t2", group: GROUP_A, governance: "rejected" }),
    ];
    expect(aggregateGroupStatus(steps)).toBe("warning");
  });

  it("keeps a real failure above governance warnings", () => {
    const steps = [
      toolMessage({ id: "t1", group: GROUP_A, governance: "blocked" }),
      toolMessage({ id: "t2", group: GROUP_A, outputStatus: "failed" }),
    ];
    expect(aggregateGroupStatus(steps)).toBe("failed");
  });

  it("returns running while any step is still running", () => {
    const steps = [
      toolMessage({ id: "t1", group: GROUP_A, inputStatus: "running" }),
      toolMessage({ id: "t2", group: GROUP_A, outputStatus: "success" }),
    ];
    expect(aggregateGroupStatus(steps)).toBe("running");
  });

  it("ignores reasoning status when aggregating tool status", () => {
    const steps = [
      toolMessage({ id: "t1", group: GROUP_A, outputStatus: "success" }),
      reasoningMessage(
        "reason-1",
        "思考失败字样",
        AgentScopeRuntimeRunStatus.Failed,
      ),
    ];

    expect(aggregateGroupStatus(steps)).toBe("success");
  });
});

describe("groupOperationMessages", () => {
  it("renders a group from the first still-running tool call", () => {
    const message = toolMessage({
      id: "t1",
      group: GROUP_A,
      inputStatus: "running",
      messageStatus: AgentScopeRuntimeRunStatus.InProgress,
    });

    const { items, groups } = groupOperationMessages([message]);

    expect(groups).toHaveLength(1);
    expect(groups[0].steps).toEqual([message]);
    expect(items).toEqual([groups[0]]);
  });

  it("groups consecutive tool calls sharing the same explicit id", () => {
    const messages = [
      toolMessage({ id: "t1", group: GROUP_A }),
      toolMessage({ id: "t2", group: GROUP_A }),
      toolMessage({ id: "t3", group: GROUP_A }),
      textMessage("m1"),
    ];
    const { items, groups } = groupOperationMessages(messages);

    expect(groups).toHaveLength(1);
    expect(groups[0].steps).toHaveLength(3);
    expect(items).toHaveLength(2);
    expect(items[0]).toEqual(groups[0]);
    expect(items[1]).toMatchObject({ kind: "message", message: messages[3] });
  });

  it("splits groups on a user-facing text boundary (R4)", () => {
    const messages = [
      toolMessage({ id: "t1", group: GROUP_A }),
      textMessage("m1"),
      toolMessage({ id: "t2", group: GROUP_A }),
    ];
    const { groups } = groupOperationMessages(messages);

    expect(groups).toHaveLength(2);
    expect(groups[0].group.instanceKey).toBe("inspect:t1");
    expect(groups[1].group.instanceKey).toBe("inspect:t2");
    expect(groups[1].group.title).toBe("检查图片");
  });

  it("splits groups when the declared group id changes", () => {
    const messages = [
      toolMessage({ id: "t1", group: GROUP_A }),
      toolMessage({ id: "t2", group: GROUP_B }),
      toolMessage({ id: "t3", group: GROUP_A }),
    ];
    const { groups } = groupOperationMessages(messages);

    expect(groups).toHaveLength(3);
  });

  it("keeps reasoning between same-group tools in stream order", () => {
    const firstTool = toolMessage({ id: "t1", group: GROUP_A });
    const reasoning = reasoningMessage("reason-1");
    const secondTool = toolMessage({ id: "t2", group: GROUP_A });

    const { groups } = groupOperationMessages([
      firstTool,
      reasoning,
      secondTool,
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0].steps).toEqual([firstTool, reasoning, secondTool]);
  });

  it("keeps ungrouped tool messages as individual items (R16)", () => {
    const messages = [
      toolMessage({ id: "t1", group: GROUP_A }),
      toolMessage({ id: "t2" }),
      toolMessage({ id: "t3", group: GROUP_A }),
    ];
    const { items, groups } = groupOperationMessages(messages);

    expect(groups).toHaveLength(2);
    expect(items.filter((item) => item.kind === "group")).toHaveLength(2);
    expect(items.filter((item) => item.kind !== "group")).toEqual([
      { kind: "message", message: messages[1] },
    ]);
  });
});
