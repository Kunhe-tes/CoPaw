import { describe, expect, it } from "vitest";
import { AgentScopeRuntimeRunStatus } from "../types";
import { isToolMessageLoading, resolveToolMessageStatus } from "./ToolStatus";

describe("tool status presentation", () => {
  it("maps backend failed tool_status to failed message status", () => {
    expect(
      resolveToolMessageStatus({
        messageStatus: AgentScopeRuntimeRunStatus.Completed,
        outputData: {
          tool_status: "failed",
          tool_error:
            "Shell command contains path outside the allowed workspace.",
        },
      }),
    ).toBe(AgentScopeRuntimeRunStatus.Failed);
  });

  it("maps backend success tool_status to completed message status", () => {
    expect(
      resolveToolMessageStatus({
        messageStatus: AgentScopeRuntimeRunStatus.Completed,
        outputData: {
          tool_status: "success",
          output: "Error: this is normal output text",
        },
      }),
    ).toBe(AgentScopeRuntimeRunStatus.Completed);
  });

  it("maps backend running tool_status to in-progress message status", () => {
    const status = resolveToolMessageStatus({
      messageStatus: AgentScopeRuntimeRunStatus.Completed,
      inputData: {
        tool_status: "running",
      },
    });

    expect(status).toBe(AgentScopeRuntimeRunStatus.InProgress);
    expect(isToolMessageLoading(status)).toBe(true);
  });

  it("prefers terminal output status over the earlier running input status", () => {
    expect(
      resolveToolMessageStatus({
        messageStatus: AgentScopeRuntimeRunStatus.Completed,
        hasOutputContent: true,
        inputData: {
          tool_status: "running",
        },
        outputData: {
          tool_status: "failed",
          tool_error: "Tool error",
        },
      }),
    ).toBe(AgentScopeRuntimeRunStatus.Failed);
  });

  it("does not use input running status after output content has arrived without terminal status", () => {
    expect(
      resolveToolMessageStatus({
        messageStatus: AgentScopeRuntimeRunStatus.Completed,
        hasOutputContent: true,
        inputData: {
          tool_status: "running",
        },
        outputData: {
          output: "legacy output without tool_status",
        },
      }),
    ).toBe(AgentScopeRuntimeRunStatus.Completed);
  });

  it("falls back to the original message status when backend fields are absent", () => {
    expect(
      resolveToolMessageStatus({
        messageStatus: AgentScopeRuntimeRunStatus.Completed,
      }),
    ).toBe(AgentScopeRuntimeRunStatus.Completed);
  });
});
