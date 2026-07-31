import { describe, expect, it } from "vitest";

import type {
  WPlusSopSession,
  WPlusSopSessionEvent,
  WPlusSopStage,
} from "@/api/types/wplusSop";
import {
  applySessionEvent,
  buildResultTable,
  validateStageQueue,
} from "./sessionView";

function makeSession(
  overrides: Partial<WPlusSopSession> = {},
): WPlusSopSession {
  return {
    session_id: "sop-1",
    chat_id: "chat-1",
    logical_chat_session_id: "logical-1",
    title: "客户经营 SOP",
    state: "AwaitingQueueConfirmation",
    state_version: 4,
    revision: 1,
    round: 1,
    stages: [],
    current_stage_id: null,
    updated_at: "2026-07-28T08:00:00Z",
    ...overrides,
  };
}

describe("validateStageQueue", () => {
  const stages: WPlusSopStage[] = [
    {
      stage_id: "stage-1",
      title: "确认名单范围",
      description: "定义筛选条件",
      status: "current",
    },
    {
      stage_id: "stage-2",
      title: "生成触达任务",
      description: "确认任务参数",
      status: "pending",
    },
  ];

  it("accepts two to four unique stages while keeping stable ids", () => {
    expect(validateStageQueue(stages)).toEqual({ valid: true, message: null });
  });

  it("rejects duplicate, empty, or undersized queues", () => {
    expect(validateStageQueue(stages.slice(0, 1)).valid).toBe(false);
    expect(
      validateStageQueue([stages[0], { ...stages[1], title: "确认名单范围" }])
        .valid,
    ).toBe(false);
    expect(
      validateStageQueue([
        stages[0],
        { ...stages[1], stage_id: "", title: " " },
      ]).valid,
    ).toBe(false);
  });
});

describe("buildResultTable", () => {
  it("keeps nested object-list values attached to their parent field", () => {
    const table = buildResultTable(
      [
        {
          product: "稳健理财",
          owner: { team: "A 组" },
          tasks: [{ type: "回访", due: "2026-08-01" }],
        },
      ],
      [
        { field: "product", label: "产品" },
        { field: "owner", label: "归属" },
        { field: "tasks", label: "任务" },
      ],
    );

    expect(table.columns.map((column) => column.field)).toEqual([
      "product",
      "owner",
      "tasks",
    ]);
    expect(table.rows[0].owner).toBe('{"team":"A 组"}');
    expect(table.rows[0].tasks).toBe('[{"type":"回访","due":"2026-08-01"}]');
  });

  it("derives deterministic columns without flattening nested keys", () => {
    const table = buildResultTable([
      { zeta: 1, customer: { masked_id: "C***9" } },
      { alpha: 2 },
    ]);

    expect(table.columns.map((column) => column.field)).toEqual([
      "alpha",
      "customer",
      "zeta",
    ]);
    expect(table.columns).not.toContainEqual(
      expect.objectContaining({ field: "customer.masked_id" }),
    );
  });
});

describe("applySessionEvent", () => {
  const current = makeSession();

  it("ignores stale and foreign-session events", () => {
    const stale: WPlusSopSessionEvent = {
      event_id: "evt-3",
      session_id: "sop-1",
      state_version: 3,
      kind: "session_snapshot",
      snapshot: makeSession({ state_version: 3 }),
    };
    const foreign: WPlusSopSessionEvent = {
      ...stale,
      event_id: "evt-5",
      session_id: "sop-2",
      state_version: 5,
      snapshot: makeSession({ session_id: "sop-2", state_version: 5 }),
    };

    expect(applySessionEvent(current, stale)).toEqual({
      action: "ignore",
      session: current,
    });
    expect(applySessionEvent(current, foreign)).toEqual({
      action: "ignore",
      session: current,
    });
  });

  it("applies the next authoritative projection", () => {
    const next = makeSession({
      state: "GeneratingQuestions",
      state_version: 5,
    });
    const event: WPlusSopSessionEvent = {
      event_id: "evt-5",
      session_id: "sop-1",
      state_version: 5,
      kind: "session_snapshot",
      snapshot: next,
    };

    expect(applySessionEvent(current, event)).toEqual({
      action: "apply",
      session: next,
    });
  });

  it("requests a reload when an event creates a version gap", () => {
    const event: WPlusSopSessionEvent = {
      event_id: "evt-6",
      session_id: "sop-1",
      state_version: 6,
      kind: "session_snapshot",
      snapshot: makeSession({ state_version: 6 }),
    };

    expect(applySessionEvent(current, event)).toEqual({
      action: "reload",
      session: current,
    });
  });
});
