import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { formatMessageTime } from "../messageMeta";
import RuntimeRequestCard from "./RuntimeRequestCard";
import RuntimeResponseCard, {
  getAssistantMessageName,
} from "./RuntimeResponseCard";

vi.mock(
  "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Request/Card",
  () => ({
    default: () => <div data-testid="request-card-body">request-body</div>,
  }),
);

vi.mock(
  "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/Card",
  () => ({
    default: ({ beforeActions }: { beforeActions?: React.ReactNode }) => (
      <div data-testid="response-card-body">
        response-body
        {beforeActions}
      </div>
    ),
  }),
);

vi.mock("./PlanInteractionCards", () => ({
  PlanReviewMessageCard: ({ data }: { data: { title: string } }) => (
    <div data-testid="plan-review">{data.title}</div>
  ),
}));

afterEach(() => {
  cleanup();
  window.history.pushState({}, "", "/");
});

describe("runtime message header cards", () => {
  it("renders user header meta above the request card on the right side", () => {
    const timestamp = Date.parse("2026-04-17T08:00:00Z");
    const { container } = render(
      <RuntimeRequestCard
        data={
          {
            input: [],
            headerMeta: { timestamp },
          } as never
        }
      />,
    );

    expect(screen.getByText("我")).toBeInTheDocument();
    expect(screen.getByText(formatMessageTime(timestamp))).toBeInTheDocument();
    expect(screen.getByTestId("request-card-body")).toBeInTheDocument();
    expect(container.firstElementChild?.className).toContain("messageBlockEnd");
  });

  it("renders agent header meta above the response card on the left side", () => {
    const timestamp = Date.parse("2026-04-17T09:30:00Z");
    const { container } = render(
      <RuntimeResponseCard
        data={
          {
            output: [],
            headerMeta: { timestamp },
          } as never
        }
      />,
    );

    expect(screen.getByText("小助 Claw")).toBeInTheDocument();
    expect(screen.getByText(formatMessageTime(timestamp))).toBeInTheDocument();
    expect(screen.getByTestId("response-card-body")).toBeInTheDocument();
    expect(container.firstElementChild?.className).toContain(
      "messageBlockStart",
    );
  });

  it("places the plan review before response actions", () => {
    render(
      <RuntimeResponseCard
        data={
          {
            output: [],
            planReviewCard: {
              card_type: "plan_review",
              plan_id: "plan-1",
              title: "Implementation plan",
              summary: "Review before execution",
              steps: [],
              risks: [],
              verification: [],
            },
          } as never
        }
      />,
    );

    expect(screen.getByTestId("response-card-body")).toHaveTextContent(
      "response-bodyImplementation plan",
    );
  });

  it("uses AI伙伴 for response card name when URL origin is Y", () => {
    window.history.pushState({}, "", "/chat?origin=Y");

    render(
      <RuntimeResponseCard
        data={
          {
            output: [],
            headerMeta: { timestamp: Date.parse("2026-04-17T10:00:00Z") },
          } as never
        }
      />,
    );

    expect(screen.getByText("AI伙伴")).toBeInTheDocument();
    expect(screen.queryByText("小助 Claw")).not.toBeInTheDocument();
  });

  it("keeps 小助 Claw unless URL origin is Y", () => {
    expect(getAssistantMessageName("?origin=N")).toBe("小助 Claw");
    expect(getAssistantMessageName("?foo=bar")).toBe("小助 Claw");
  });

  it("keeps AI伙伴 after origin Y initializes iframe context", () => {
    expect(
      getAssistantMessageName("", {
        hideMenu: true,
        source: "RMASSIST",
      }),
    ).toBe("AI伙伴");
  });
});

it("shows persisted expert execution identity instead of the current agent label", () => {
  render(
    <RuntimeResponseCard
      data={
        {
          output: [
            {
              role: "assistant",
              metadata: {
                metadata: {
                  execution_identity: {
                    kind: "expert_main",
                    expert_id: "e",
                    expert_name: "历史专家",
                    binding_revision: 3,
                  },
                },
              },
            },
          ],
        } as never
      }
    />,
  );
  expect(screen.getByText("历史专家")).toBeInTheDocument();
  expect(screen.queryByText("小助 Claw")).not.toBeInTheDocument();
});
it("shows direct response execution identity", () => {
  render(
    <RuntimeResponseCard
      data={
        {
          output: [],
          metadata: {
            execution_identity: {
              kind: "expert_main",
              expert_id: "e",
              expert_name: "实时专家",
              binding_revision: 1,
            },
          },
        } as never
      }
    />,
  );
  expect(screen.getByText("实时专家")).toBeInTheDocument();
});
