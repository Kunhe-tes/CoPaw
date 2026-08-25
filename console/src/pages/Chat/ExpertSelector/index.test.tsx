import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ExpertSelector from "./index";

const mocks = vi.hoisted(() => {
  const messageError = vi.fn();
  return {
    listExperts: vi.fn(),
    messageError,
    message: { error: messageError },
  };
});

vi.mock("../../../api/modules/experts", () => ({
  expertsApi: {
    listExperts: mocks.listExperts,
  },
}));

vi.mock("../../../hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: mocks.message,
  }),
}));

vi.mock("@agentscope-ai/icons", () => ({
  SparkDownLine: () => <span data-testid="expert-selector-arrow" />,
}));

describe("ExpertSelector inline menu", () => {
  beforeEach(() => {
    mocks.listExperts.mockResolvedValue([
      {
        definition_id: "expert-1",
        enabled: true,
        valid: true,
        definition: {
          name: "专家一号",
          description: "处理复杂问题",
        },
      },
    ]);
    mocks.messageError.mockReset();
  });

  afterEach(() => {
    cleanup();
    mocks.listExperts.mockReset();
  });

  it("selects an expert from the inline quick menu", async () => {
    const onChange = vi.fn();

    render(
      <ExpertSelector
        inline
        planModeEnabled={false}
        selectedExpertId={null}
        onChange={onChange}
        onDisablePlanMode={vi.fn()}
      />,
    );

    const expert = await screen.findByRole("menuitem");
    expect(expert).toHaveTextContent("专家一号");
    fireEvent.click(expert);

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith("expert-1");
    });
  });

  it("disables inline expert options while Goal Mode is enabled", async () => {
    const onChange = vi.fn();

    render(
      <ExpertSelector
        inline
        planModeEnabled={false}
        goalModeEnabled
        selectedExpertId={null}
        onChange={onChange}
        onDisablePlanMode={vi.fn()}
      />,
    );

    const expert = await screen.findByRole("menuitem");
    expect(expert).toBeDisabled();

    fireEvent.click(expert);
    await waitFor(() => {
      expect(onChange).not.toHaveBeenCalled();
    });
  });
});
