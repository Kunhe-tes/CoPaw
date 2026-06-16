import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  SessionResourceFilter,
  UserStats,
} from "../../../../../api/modules/tracing";
import UserStatsHeader from "./UserStatsHeader";

afterEach(cleanup);

const userStats: UserStats = {
  user_id: "user-001",
  total_tokens: 1000,
  input_tokens: 600,
  output_tokens: 400,
  total_sessions: 3,
  total_conversations: 5,
  avg_duration_ms: 1200,
  model_usage: [
    {
      model_name: "gpt-5",
      count: 3,
      total_tokens: 1000,
      input_tokens: 600,
      output_tokens: 400,
    },
  ],
  tools_used: [],
  skills_used: [
    { skill_name: "risk-check", count: 2, avg_duration_ms: 100 },
  ],
  mcp_tools_used: [
    {
      tool_name: "query_customer",
      mcp_server: "crm",
      count: 1,
      avg_duration_ms: 80,
      error_count: 0,
    },
  ],
};

describe("UserStatsHeader resource filters", () => {
  it("emits structured identities for model, MCP tool, and skill tags", () => {
    const onChange = vi.fn();
    render(
      <UserStatsHeader
        userStats={userStats}
        onResourceFilterChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "筛选模型：gpt-5" }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "筛选MCP 工具：query_customer (crm)",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "筛选技能：risk-check" }),
    );

    expect(onChange.mock.calls).toEqual([
      [{ type: "model", name: "gpt-5" }],
      [{ type: "mcp_tool", name: "query_customer", mcp_server: "crm" }],
      [{ type: "skill", name: "risk-check" }],
    ]);
  });

  it.each<SessionResourceFilter>([
    { type: "model", name: "gpt-5" },
    { type: "skill", name: "risk-check" },
    { type: "mcp_tool", name: "query_customer", mcp_server: "crm" },
  ])("marks only the active $type tag as pressed", (activeFilter) => {
    render(
      <UserStatsHeader
        userStats={userStats}
        activeResourceFilter={activeFilter}
        onResourceFilterChange={vi.fn()}
      />,
    );

    const pressedButtons = screen
      .getAllByRole("button")
      .filter((button) => button.getAttribute("aria-pressed") === "true");
    expect(pressedButtons).toHaveLength(1);
    expect(pressedButtons[0].className).toContain("usageTagButtonSelected");
    expect(screen.getByText("已筛选会话")).toBeInTheDocument();
  });

  it("exposes an active tag as a toggle that can be cleared", () => {
    const onChange = vi.fn();
    render(
      <UserStatsHeader
        userStats={userStats}
        activeResourceFilter={{ type: "skill", name: "risk-check" }}
        onResourceFilterChange={onChange}
      />,
    );

    const activeButton = screen.getByRole("button", {
      name: "取消技能：risk-check",
    });
    expect(activeButton).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(activeButton);
    expect(onChange).toHaveBeenCalledWith({
      type: "skill",
      name: "risk-check",
    });
  });
});
