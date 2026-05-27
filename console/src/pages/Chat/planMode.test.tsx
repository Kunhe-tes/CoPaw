import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PlanModeMenuItem,
  getPlanModeEnabled,
  preparePlanModeSubmit,
} from "./planMode";

describe("Plan Mode frontend helpers", () => {
  afterEach(() => {
    cleanup();
  });

  it("initializes the toggle from ChatSpec meta", () => {
    render(
      <PlanModeMenuItem
        enabled={getPlanModeEnabled({
          meta: { plan_mode_enabled: true },
        })}
        label="Plan"
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("switch", { name: "Plan" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("persists toggle changes through the provided handler", async () => {
    const onChange = vi.fn();

    render(
      <PlanModeMenuItem enabled={false} label="Plan" onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole("switch", { name: "Plan" }));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(true);
    });
  });

  it("turns /plan with text into a planning request", async () => {
    const persistPlanMode = vi.fn(async () => {});
    const setPlanModeEnabled = vi.fn();

    const result = await preparePlanModeSubmit(
      {
        query: "/plan investigate this bug",
        fileList: [],
      },
      {
        planModeEnabled: false,
        persistPlanMode,
        setPlanModeEnabled,
      },
    );

    expect(persistPlanMode).toHaveBeenCalledWith(true);
    expect(setPlanModeEnabled).not.toHaveBeenCalled();
    expect(result).toMatchObject({
      query: "investigate this bug",
      biz_params: { mode: "plan" },
    });
  });

  it("turns /plan alone into a state change without a request", async () => {
    const persistPlanMode = vi.fn(async () => {});
    const setPlanModeEnabled = vi.fn();

    const result = await preparePlanModeSubmit(
      {
        query: "/plan",
        fileList: [],
      },
      {
        planModeEnabled: false,
        persistPlanMode,
        setPlanModeEnabled,
      },
    );

    expect(persistPlanMode).not.toHaveBeenCalled();
    expect(setPlanModeEnabled).toHaveBeenCalledWith(true);
    expect(result).toEqual({
      shouldSubmit: false,
      clearInput: true,
    });
  });

  it("adds explicit normal mode metadata when Plan Mode is disabled", async () => {
    const result = await preparePlanModeSubmit(
      {
        query: "hello",
        fileList: [],
        biz_params: { user_prompt_params: { source: "test" } },
      },
      {
        planModeEnabled: false,
        persistPlanMode: vi.fn(async () => {}),
      },
    );

    expect(result).toMatchObject({
      query: "hello",
      biz_params: {
        mode: "normal",
        user_prompt_params: { source: "test" },
      },
    });
  });

  it("preserves explicit card-submitted request mode", async () => {
    const result = await preparePlanModeSubmit(
      {
        query: "Execute plan",
        fileList: [],
        biz_params: {
          mode: "normal",
          plan_interaction_response: {
            decision: "execute",
          },
        },
      },
      {
        planModeEnabled: true,
        persistPlanMode: vi.fn(async () => {}),
      },
    );

    expect(result).toMatchObject({
      biz_params: {
        mode: "normal",
        plan_interaction_response: {
          decision: "execute",
        },
      },
    });
  });
});
