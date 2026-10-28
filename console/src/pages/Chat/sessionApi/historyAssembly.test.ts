import { describe, expect, it } from "vitest";
import { convertArchivedPage, convertMessages } from "./index";
import {
  INLINE_COMPACTION_TYPE,
  mergeHistoryResponses,
  normalizeHistoryMessages,
  resolveHistoryAnchorId,
} from "./historyAssembly";

const boundary = {
  id: "boundary",
  archived_message_count: 2,
  first_message_id: "question",
  last_message_id: "call",
  created_at: "2026-10-28T01:00:00Z",
};
const call = {
  id: "call",
  role: "assistant",
  type: "plugin_call",
  content: [{ type: "data", data: { call_id: "tool-a", arguments: "{}" } }],
};
const output = {
  id: "output",
  role: "system",
  type: "plugin_call_output",
  content: [{ type: "data", data: { call_id: "tool-a", output: "ok" } }],
};
const historical = (messages: ReturnType<typeof convertMessages>) =>
  messages.map((message) => ({ ...message, history: true }));

describe("archived history assembly", () => {
  it("keeps legacy fragments with shared IDs and stable source identity", () => {
    const raw = [
      { ...call, id: "source" },
      {
        ...call,
        id: "source",
        content: [{ type: "data", data: { call_id: "tool-b" } }],
      },
      {
        id: "source",
        role: "assistant",
        type: "reasoning",
        content: "thinking",
      },
    ].map((message) => ({ ...message, metadata: { original_id: "source" } }));
    const messages = normalizeHistoryMessages(raw);
    expect(new Set(messages.map((message) => message.id)).size).toBe(3);
    expect(messages.map((message) => message.metadata)).toEqual([
      { original_id: "source" },
      { original_id: "source" },
      { original_id: "source" },
    ]);
    expect(normalizeHistoryMessages(messages)).toEqual(messages);
    expect(raw.map((message) => message.id)).toEqual([
      "source",
      "source",
      "source",
    ]);
  });

  it("assembles one response across a page and compaction boundary", () => {
    const older = convertArchivedPage(
      [{ id: "question", role: "user", content: "question" }, call],
      [boundary],
    );
    const newer = historical(
      convertMessages([
        output,
        { id: "answer", role: "assistant", content: "answer" },
      ]),
    );
    const oldAnchor = older[1].id;
    const merged = mergeHistoryResponses([...historical(older), ...newer]);
    expect(merged.map((message) => message.role)).toEqual([
      "user",
      "assistant",
    ]);
    expect(merged[1].id).toBe(newer[0].id);
    expect(
      merged[1].cards?.[0].data.output.map(
        (item: { type?: string }) => item.type,
      ),
    ).toEqual([
      "plugin_call",
      INLINE_COMPACTION_TYPE,
      "plugin_call_output",
      undefined,
    ]);
    expect(resolveHistoryAnchorId(merged, oldAnchor)).toBe(newer[0].id);
    expect(mergeHistoryResponses(merged)).toEqual(merged);
  });

  it("does not make a compression boundary a new response within one page", () => {
    const result = convertArchivedPage(
      [call, output],
      [{ ...boundary, last_message_id: "call" }],
    );
    expect(result).toHaveLength(1);
    expect(result[0].cards?.[0].data.output).toHaveLength(3);
  });

  it("resolves process anchors through repeated response merges", () => {
    const older = convertArchivedPage([call], []);
    const newer = convertArchivedPage([output], []);
    const processAnchor = (message: (typeof older)[number]) =>
      `process:${message.cards![0].data.id}`;
    expect(older[0].id).not.toBe(older[0].cards![0].data.id);
    const merged = mergeHistoryResponses([...older, ...newer]);
    expect(resolveHistoryAnchorId(merged, processAnchor(older[0]))).toBe(
      processAnchor(newer[0]),
    );
    const latest = convertArchivedPage(
      [{ id: "answer", role: "assistant", content: "answer" }],
      [],
    );
    const remerged = mergeHistoryResponses([...merged, ...latest]);
    for (const response of [...older, ...newer, ...latest]) {
      expect(resolveHistoryAnchorId(remerged, processAnchor(response))).toBe(
        processAnchor(latest[0]),
      );
    }
    expect(resolveHistoryAnchorId(remerged, older[0].id)).toBe(latest[0].id);
    expect(resolveHistoryAnchorId(remerged, "process:unknown")).toBe(
      "process:unknown",
    );
    expect(resolveHistoryAnchorId(remerged, call.id)).toBe(call.id);
  });

  it("keeps user, standalone Stop and live response barriers", () => {
    const first = historical(convertMessages([call]));
    const second = historical(
      convertMessages([{ id: "q2", role: "user", content: "next" }, output]),
    );
    expect(mergeHistoryResponses([...first, ...second])).toHaveLength(3);
    const stop = historical(
      convertMessages([
        {
          id: "append",
          role: "assistant",
          content: "append",
          metadata: { stop_append: { message_id: "append", order: 1 } },
        },
      ]),
    );
    expect(
      mergeHistoryResponses([
        ...first,
        ...stop,
        ...historical(convertMessages([output])),
      ]),
    ).toHaveLength(3);
    expect(
      mergeHistoryResponses([...first, ...convertMessages([output])]),
    ).toHaveLength(2);
  });

  it("uses the same legacy fragment ID in singleton and overlapping pages", () => {
    const first = {
      ...call,
      id: "source",
      metadata: { original_id: "source" },
    };
    const second = { ...first, type: "reasoning", content: "thinking" };
    expect(normalizeHistoryMessages([first])[0].id).toBe(
      normalizeHistoryMessages([second, first])[1].id,
    );
    const normalized = normalizeHistoryMessages([first, { ...first }]);
    expect(normalized[0].id).toBe(normalized[1].id);
  });

  it("keeps distinct task executions separate within a page and across pages", () => {
    const tasks = [
      {
        id: "task-a",
        role: "assistant",
        content: "A",
        metadata: { task_run_id: "run-a" },
      },
      {
        id: "task-b",
        role: "assistant",
        content: "B",
        metadata: { metadata: { task_run_id: "run-b" } },
      },
    ];
    expect(convertArchivedPage(tasks, [])).toHaveLength(2);
    expect(
      mergeHistoryResponses(
        tasks.flatMap((task) => convertArchivedPage([task], [])),
      ),
    ).toHaveLength(2);
  });

  it("keeps tools from the same explicit task run in one response", () => {
    const tasks = [
      { ...call, metadata: { task_run_id: "run-a" } },
      { ...output, metadata: { metadata: { task_run_id: "run-a" } } },
    ];
    expect(convertArchivedPage(tasks, [])).toHaveLength(1);
    expect(
      mergeHistoryResponses(
        tasks.flatMap((task) => convertArchivedPage([task], [])),
      ),
    ).toHaveLength(1);
  });
});
