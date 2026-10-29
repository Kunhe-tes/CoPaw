import { describe, expect, it } from "vitest";
import {
  AgentScopeRuntimeContentType,
  AgentScopeRuntimeMessageType,
  AgentScopeRuntimeRunStatus,
  type IAgentScopeRuntimeMessage,
} from "../types";
import { mergeToolMessages } from "./ToolMessageMerge";

function toolMessage(
  side: "input" | "output",
  data: Record<string, unknown>,
  id: string = side,
): IAgentScopeRuntimeMessage {
  const status =
    side === "input"
      ? AgentScopeRuntimeRunStatus.InProgress
      : AgentScopeRuntimeRunStatus.Completed;
  return {
    id,
    role: side === "input" ? "assistant" : "tool",
    type:
      side === "input"
        ? AgentScopeRuntimeMessageType.PLUGIN_CALL
        : AgentScopeRuntimeMessageType.PLUGIN_CALL_OUTPUT,
    status,
    content: [{ type: AgentScopeRuntimeContentType.DATA, status, data }],
  };
}

describe("mergeToolMessages", () => {
  it.each([false, true])(
    "pairs explicit call IDs regardless of output-first order (%s)",
    (outputFirst) => {
      const input = toolMessage("input", { call_id: "call", arguments: {} });
      const output = toolMessage("output", { call_id: "call", output: "done" });
      const source = outputFirst ? [output, input] : [input, output];

      expect(mergeToolMessages(source)).toEqual([
        { ...output, content: [input.content[0], output.content[0]] },
      ]);
    },
  );

  it.each(["call_id", "id", "tool_call_id"])(
    "matches %s with a tool_call_id on the other side",
    (key) => {
      const input = toolMessage("input", { [key]: "call" });
      const output = toolMessage("output", { tool_call_id: "call" });
      expect(mergeToolMessages([output, input])).toHaveLength(1);
    },
  );

  it("keeps independent same-name calls and their outputs separate", () => {
    const first = toolMessage("input", { call_id: "a", name: "shell" }, "a");
    const second = toolMessage("input", { call_id: "b", name: "shell" }, "b");
    const secondOut = toolMessage("output", { call_id: "b", output: "B" });
    const firstOut = toolMessage("output", { call_id: "a", output: "A" });
    const merged = mergeToolMessages([first, secondOut, second, firstOut]);
    expect(merged).toEqual([
      { ...firstOut, content: [first.content[0], firstOut.content[0]] },
      { ...secondOut, content: [second.content[0], secondOut.content[0]] },
    ]);
  });

  it("never pairs different explicit IDs using the tool name", () => {
    const messages = [
      toolMessage("input", { call_id: "a", name: "shell" }),
      toolMessage("output", { call_id: "b", name: "shell" }),
    ];
    expect(mergeToolMessages(messages)).toEqual(messages);
  });

  it("preserves ambiguous name-only calls", () => {
    const messages = [
      toolMessage("input", { name: "shell", arguments: "A" }, "a"),
      toolMessage("input", { name: "shell", arguments: "B" }, "b"),
      toolMessage("output", { name: "shell", output: "unknown call" }),
    ];
    expect(mergeToolMessages(messages)).toEqual(messages);
  });

  it("pairs an unambiguous legacy name-only call in either order", () => {
    const input = toolMessage("input", { name: "shell", arguments: {} });
    const output = toolMessage("output", { name: "shell", output: "done" });
    expect(mergeToolMessages([output, input])).toEqual([
      { ...output, content: [input.content[0], output.content[0]] },
    ]);
  });

  it("retains an output-side explicit ID when reprocessing a legacy pair", () => {
    const input = toolMessage("input", { name: "shell", arguments: {} });
    const output = toolMessage("output", {
      name: "shell",
      tool_call_id: "call",
      output: "done",
    });
    const merged = mergeToolMessages([input, output]);
    expect(mergeToolMessages([...merged, output])).toEqual(merged);
  });

  it("keeps missing identities and single-sided calls unchanged", () => {
    const messages = [
      toolMessage("input", { arguments: {} }),
      toolMessage("output", { output: "unidentified" }),
      toolMessage("input", { call_id: "input-only" }),
      toolMessage("output", { call_id: "output-only" }),
    ];
    expect(mergeToolMessages(messages)).toEqual(messages);
  });

  it("retains output error and governance metadata without mutating sources", () => {
    const input = toolMessage("input", { call_id: "call", arguments: {} });
    const output = {
      ...toolMessage("output", {
        call_id: "call",
        output: "denied",
        tool_error: "blocked by policy",
        tool_governance: "blocked",
      }),
      status: AgentScopeRuntimeRunStatus.Rejected,
      code: "policy",
      message: "blocked",
    };
    const source = [output, input];
    const snapshot = structuredClone(source);
    for (const message of source) {
      Object.freeze(message.content[0]);
      Object.freeze(message.content);
      Object.freeze(message);
    }
    expect(mergeToolMessages(source)).toEqual([
      { ...output, content: [input.content[0], output.content[0]] },
    ]);
    expect(source).toEqual(snapshot);
  });

  it("deduplicates repeated explicit frames and is idempotent", () => {
    const input = toolMessage("input", { call_id: "call", arguments: {} });
    const output = toolMessage("output", { call_id: "call", output: "done" });
    const merged = mergeToolMessages([output, input, input, output]);
    expect(merged).toEqual([
      { ...output, content: [input.content[0], output.content[0]] },
    ]);
    expect(mergeToolMessages(merged)).toEqual(merged);
    expect(mergeToolMessages([...merged, input, output])).toEqual(merged);
  });

  it("uses the latest input snapshot for repeated explicit call frames", () => {
    const partial = toolMessage("input", { call_id: "call", arguments: "{" });
    const complete = toolMessage("input", {
      call_id: "call",
      arguments: '{"command":"pwd"}',
    });
    const output = toolMessage("output", { call_id: "call", output: "/tmp" });
    expect(mergeToolMessages([partial, complete, output])).toEqual([
      { ...output, content: [complete.content[0], output.content[0]] },
    ]);
  });

  it("updates already-merged output without duplicating content", () => {
    const input = toolMessage("input", { call_id: "call" });
    const output = toolMessage("output", { call_id: "call", output: "first" });
    const merged = {
      ...output,
      content: [...input.content, ...output.content],
    };
    const latest = toolMessage("output", { call_id: "call", output: "final" });
    expect(mergeToolMessages([merged, latest])).toEqual([
      { ...latest, content: [input.content[0], latest.content[0]] },
    ]);
  });

  it("does not replace a terminal output with a repeated running frame", () => {
    const input = toolMessage("input", { call_id: "call" });
    const output = toolMessage("output", { call_id: "call", output: "done" });
    const running = {
      ...toolMessage("output", { call_id: "call", output: "partial" }),
      status: AgentScopeRuntimeRunStatus.InProgress,
    };
    expect(mergeToolMessages([input, output, running])).toEqual([
      { ...output, content: [input.content[0], output.content[0]] },
    ]);
  });

  it("keeps non-tool messages in source order around the first paired frame", () => {
    const input = toolMessage("input", { call_id: "call" });
    const output = toolMessage("output", { call_id: "call" });
    const boundary = {
      ...toolMessage("input", {}),
      id: "boundary",
      type: "conversation_compaction_boundary" as AgentScopeRuntimeMessageType,
    };
    expect(mergeToolMessages([output, boundary, input])).toEqual([
      { ...output, content: [input.content[0], output.content[0]] },
      boundary,
    ]);
  });
});
