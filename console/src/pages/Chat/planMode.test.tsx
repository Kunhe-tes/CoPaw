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
  ActivePlanModeButton,
  PlanModeMenuItem,
  getPlanModeEnabled,
  persistPlanModeState,
  preparePlanModeSubmit,
  resolveActivePlanModeSession,
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
        label="计划模式"
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("switch", { name: "计划模式" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("persists toggle changes through the provided handler", async () => {
    const onChange = vi.fn();

    render(
      <PlanModeMenuItem enabled={false} label="计划模式" onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole("switch", { name: "计划模式" }));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(true);
    });
  });

  it("does not dispatch toggle changes when the menu item is disabled", async () => {
    const onChange = vi.fn();

    render(
      <PlanModeMenuItem
        enabled={false}
        disabled
        label="计划模式"
        onChange={onChange}
      />,
    );

    expect(screen.getByRole("switch", { name: "计划模式" })).toBeDisabled();
    fireEvent.click(screen.getByRole("switch", { name: "计划模式" }));

    await waitFor(() => {
      expect(onChange).not.toHaveBeenCalled();
    });
  });

  it("renders the active Plan Mode button only when enabled and dispatches disable clicks", async () => {
    const onDisable = vi.fn();
    const { rerender } = render(
      <ActivePlanModeButton
        enabled={false}
        label="计划模式"
        onDisable={onDisable}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "计划模式" }),
    ).not.toBeInTheDocument();

    rerender(
      <ActivePlanModeButton enabled label="计划模式" onDisable={onDisable} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "计划模式" }));

    await waitFor(() => {
      expect(onDisable).toHaveBeenCalledTimes(1);
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

  it("turns /plan alone into a persisted state change without a request", async () => {
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

    expect(persistPlanMode).toHaveBeenCalledWith(true);
    expect(setPlanModeEnabled).not.toHaveBeenCalled();
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

  it("resolves the active Plan Mode session across id aliases without leaking between chats", () => {
    const sessions = [
      {
        id: "chat-enabled",
        realId: "real-enabled",
        sessionId: "logical-enabled",
        meta: { plan_mode_enabled: true },
      },
      {
        id: "chat-disabled",
        session_id: "logical-disabled",
        meta: { plan_mode_enabled: false },
      },
    ];

    expect(
      resolveActivePlanModeSession(sessions, ["real-enabled"])?.meta
        ?.plan_mode_enabled,
    ).toBe(true);
    expect(
      resolveActivePlanModeSession(sessions, ["logical-enabled"])?.meta
        ?.plan_mode_enabled,
    ).toBe(true);
    expect(
      resolveActivePlanModeSession(sessions, ["logical-disabled"])?.meta
        ?.plan_mode_enabled,
    ).toBe(false);
  });

  it("persists Plan Mode changes through chat metadata updates", async () => {
    const session = {
      id: "chat-1",
      meta: { plan_mode_enabled: true, title: "demo" },
    };
    const ensureChatId = vi.fn(async () => "chat-1");
    const updateChat = vi.fn(async () => ({
      meta: { plan_mode_enabled: false, title: "demo" },
    }));
    const updateSession = vi.fn(async () => undefined);
    const setPlanModeEnabled = vi.fn();

    await persistPlanModeState({
      enabled: false,
      session,
      ensureChatId,
      updateChat,
      updateSession,
      setPlanModeEnabled,
    });

    expect(setPlanModeEnabled).toHaveBeenNthCalledWith(1, false);
    expect(ensureChatId).toHaveBeenCalledWith(session, {
      plan_mode_enabled: false,
      title: "demo",
    });
    expect(updateChat).toHaveBeenCalledWith("chat-1", {
      meta: {
        plan_mode_enabled: false,
        title: "demo",
      },
    });
    expect(updateSession).toHaveBeenCalledWith({
      id: "chat-1",
      meta: {
        plan_mode_enabled: false,
        title: "demo",
      },
    });
  });

  it("rolls back local Plan Mode state when persistence fails", async () => {
    const session = {
      id: "chat-1",
      meta: { plan_mode_enabled: true },
    };
    const setPlanModeEnabled = vi.fn();
    const onPersistError = vi.fn();

    await expect(
      persistPlanModeState({
        enabled: false,
        session,
        ensureChatId: vi.fn(async () => "chat-1"),
        updateChat: vi.fn(async () => {
          throw new Error("persist failed");
        }),
        updateSession: vi.fn(async () => undefined),
        setPlanModeEnabled,
        onPersistError,
      }),
    ).rejects.toThrow("persist failed");

    expect(setPlanModeEnabled).toHaveBeenNthCalledWith(1, false);
    expect(setPlanModeEnabled).toHaveBeenNthCalledWith(2, true);
    expect(onPersistError).toHaveBeenCalledTimes(1);
  });
});
