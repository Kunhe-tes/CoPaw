import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EventEditorDrawer } from "./EventEditorDrawer";

const noop = () => undefined;

function renderDrawer(onSelectHandler = vi.fn()) {
  render(
    <EventEditorDrawer
      basicDetails={null}
      details={null}
      dirty={false}
      event="Stop"
      groups={[
        {
          id: "stop-output",
          matcher: { tools: [] },
          hooks: [
            {
              id: "transformer",
              type: "command",
              argv: ["node", "transform.js"],
              outputTransform: true,
            },
            {
              id: "ordinary",
              type: "http",
              url: "https://example.test",
            },
          ],
        },
      ]}
      saving={false}
      scopeDetails={null}
      testDetails={null}
      onAddGroup={noop}
      onAddHandler={noop}
      onClose={noop}
      onMoveHandler={noop}
      onRemoveEvent={noop}
      onRemoveGroup={noop}
      onRemoveHandler={noop}
      onSave={noop}
      onSelectGroup={noop}
      onSelectHandler={onSelectHandler}
    />,
  );
}

describe("EventEditorDrawer", () => {
  it("labels output transformers while preserving handler type and edit selection", () => {
    const onSelectHandler = vi.fn();

    renderDrawer(onSelectHandler);

    expect(screen.getByText("输出转换")).toHaveClass("ant-tag-blue");
    expect(screen.getAllByText("command")).toHaveLength(1);
    expect(screen.getAllByText("http")).toHaveLength(1);
    expect(screen.queryAllByText("输出转换")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "编辑 transformer" }));
    fireEvent.click(screen.getByRole("button", { name: "编辑 ordinary" }));

    expect(onSelectHandler).toHaveBeenNthCalledWith(1, "stop-output", "transformer");
    expect(onSelectHandler).toHaveBeenNthCalledWith(2, "stop-output", "ordinary");
  });
});
