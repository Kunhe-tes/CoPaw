import { expect, it } from "vitest";
import { mergeTaskSources, tagTask, taskOrigin } from "./cronTaskSources";
import type { MigrationOwnership } from "./cronMigration";

const context = {
  actor_id: "a",
  tenant_id: "a",
  source_id: "bank",
  agent_id: "default",
};
const task = (owner: "legacy" | "scheduler", chat = "chat") =>
  tagTask(
    {
      id: "job",
      task: { chat_id: chat, session_id: "session", visible_in_my_tasks: true },
    } as never,
    owner,
    context,
  );
const fact: MigrationOwnership = {
  ...context,
  job_id: "job",
  chat_id: "chat",
  session_id: "session",
  completed: true,
};

it("completed migration selects only new; pending selects only old", () => {
  const snapshot = {
    legacy: [task("legacy")],
    scheduler: [task("scheduler") as never],
    errors: [],
    ownership: [fact],
  };
  expect(mergeTaskSources([], snapshot).map(taskOrigin)).toMatchObject([
    { owner: "scheduler" },
  ]);
  expect(
    mergeTaskSources([], {
      ...snapshot,
      ownership: [{ ...fact, completed: false }],
    }).map(taskOrigin),
  ).toMatchObject([{ owner: "legacy" }]);
});
it("deleted migrated task never resurrects the old task", () => {
  expect(
    mergeTaskSources([], {
      legacy: [task("legacy")],
      scheduler: [],
      errors: [],
      ownership: [fact],
    }),
  ).toEqual([]);
});
it("known migration remains new and read-only on API failures", () => {
  const result = mergeTaskSources(
    [task("scheduler")],
    { legacy: [task("legacy")], scheduler: null, errors: [], ownership: null },
    [fact],
  );
  expect(result.map(taskOrigin)).toMatchObject([
    { owner: "scheduler", unavailable: true },
  ]);
});
it("ignores a stale legacy binding when the completed migration has a matching scheduler task", () => {
  const snapshot = {
    legacy: [task("legacy", "wrong")],
    scheduler: [task("scheduler") as never],
    errors: [] as string[],
    ownership: [fact],
  };
  expect(mergeTaskSources([], snapshot).map(taskOrigin)).toMatchObject([
    { owner: "scheduler" },
  ]);
  expect(snapshot.errors).toEqual([]);
});

it.each([
  { completed: true, legacyChat: "chat", schedulerChat: "wrong" },
  { completed: false, legacyChat: "wrong", schedulerChat: "chat" },
])(
  "rejects a mismatched binding for the migration owner ($completed)",
  ({ completed, legacyChat, schedulerChat }) => {
    const snapshot = {
      legacy: [task("legacy", legacyChat)],
      scheduler: [task("scheduler", schedulerChat) as never],
      errors: [] as string[],
      ownership: [{ ...fact, completed }],
    };
    expect(mergeTaskSources([], snapshot)).toEqual([]);
    expect(snapshot.errors.join()).toContain("绑定冲突");
  },
);
