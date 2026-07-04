import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createContext } from "use-context-selector";
import { ChatAnywhereMessagesContext } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereMessagesContext";
import type { IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/types/IMessages";
import { ChatAnywhereSessionsContext } from "@/components/agentscope-chat";
import {
  ActivePlanClarificationCard,
  ActivePlanInteractionComposer,
  ActivePlanReviewCard,
  PlanClarificationCard,
  PlanReviewCard,
  PlanReviewSnapshot,
} from "./PlanInteractionCards";
import styles from "./PlanInteractionCards.module.less";

vi.mock("@/components/agentscope-chat", () => ({
  ChatAnywhereSessionsContext: createContext({
    currentSessionId: "chat-1",
  }),
  OperateCard: Object.assign(
    ({
      header,
      body,
    }: {
      header: { title: string };
      body: { children: React.ReactNode };
    }) => (
      <section data-testid="generic-operate-card">
        <h3>{header.title}</h3>
        {body.children}
      </section>
    ),
    {
      LineBody: ({ children }: { children: React.ReactNode }) => (
        <div>{children}</div>
      ),
    },
  ),
}));

function captureSubmitEvents() {
  const handler = vi.fn();
  document.addEventListener("handleSubmit", handler);
  return {
    handler,
    cleanup: () => document.removeEventListener("handleSubmit", handler),
  };
}

function createSessionContextValue(sessionId = "chat-1") {
  return {
    sessions: [],
    setSessions: vi.fn(),
    getSessions: () => [],
    currentSessionId: sessionId,
    setCurrentSessionId: vi.fn(),
    getCurrentSessionId: () => sessionId,
    isSessionLoading: false,
    setSessionLoading: vi.fn(),
    isSessionsListLoading: false,
    setSessionsListLoading: vi.fn(),
  };
}

function renderActiveClarification(
  messages: IAgentScopeRuntimeWebUIMessage<unknown>[],
) {
  return render(
    <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
      <ChatAnywhereMessagesContext.Provider
        value={{
          messages,
          setMessages: vi.fn(),
          getMessages: () => messages,
        }}
      >
        <ActivePlanClarificationCard />
      </ChatAnywhereMessagesContext.Provider>
    </ChatAnywhereSessionsContext.Provider>,
  );
}

function renderActivePlanReview(
  messages: IAgentScopeRuntimeWebUIMessage<unknown>[],
) {
  return render(
    <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
      <ChatAnywhereMessagesContext.Provider
        value={{
          messages,
          setMessages: vi.fn(),
          getMessages: () => messages,
        }}
      >
        <ActivePlanReviewCard />
      </ChatAnywhereMessagesContext.Provider>
    </ChatAnywhereSessionsContext.Provider>,
  );
}

function renderActiveComposer(
  messages: IAgentScopeRuntimeWebUIMessage<unknown>[],
  callbacks: Partial<
    React.ComponentProps<typeof ActivePlanInteractionComposer>
  > = {},
) {
  return render(
    <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
      <ChatAnywhereMessagesContext.Provider
        value={{
          messages,
          setMessages: vi.fn(),
          getMessages: () => messages,
        }}
      >
        <ActivePlanInteractionComposer
          defaultComposer={<div data-testid="default-composer">composer</div>}
          {...callbacks}
        />
      </ChatAnywhereMessagesContext.Provider>
    </ChatAnywhereSessionsContext.Provider>,
  );
}

function createClarificationMessage({
  messageId,
  originalId,
  traceId,
  prompt = "Pick scope",
}: {
  messageId: string;
  originalId: string;
  traceId: string;
  prompt?: string;
}): IAgentScopeRuntimeWebUIMessage<unknown> {
  return {
    id: messageId,
    role: "assistant",
    cards: [
      {
        code: "AgentScopeRuntimeResponseCard",
        data: {
          id: `response-${messageId}`,
          output: [
            {
              role: "assistant",
              id: messageId,
              metadata: {
                original_id: originalId,
                trace_id: traceId,
              },
            },
          ],
        },
      },
      {
        code: "PlanInteraction",
        data: {
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt,
          options: [{ id: "small", label: "Small" }],
        },
      },
    ],
  };
}

function createReviewData(
  overrides: Partial<React.ComponentProps<typeof PlanReviewCard>["data"]> = {},
): React.ComponentProps<typeof PlanReviewCard>["data"] {
  return {
    card_type: "plan_review",
    plan_id: "plan-123",
    title: "Fix bug",
    summary: "Investigate and patch",
    steps: ["Read code", "Patch code"],
    risks: ["Regression"],
    verification: ["Focused tests"],
    ...overrides,
  };
}

function createReviewMessage({
  messageId,
  cardId,
  title,
  status,
  submittedDecision,
}: {
  messageId: string;
  cardId: string;
  title: string;
  status?: "pending" | "submitted";
  submittedDecision?: "revise" | "execute" | "exit_plan";
}): IAgentScopeRuntimeWebUIMessage<unknown> {
  return {
    id: messageId,
    role: "assistant",
    cards: [
      {
        id: cardId,
        code: "PlanInteraction",
        data: createReviewData({
          plan_id: cardId,
          title,
          status,
          submitted_decision: submittedDecision,
        }),
      },
    ],
  };
}

describe("Plan interaction cards", () => {
  afterEach(() => {
    cleanup();
    (window as Window & { currentSessionId?: string }).currentSessionId =
      undefined;
  });

  it("hides a dismissed clarification only for the current render", () => {
    const data = {
      card_type: "plan_clarification" as const,
      kind: "single_choice" as const,
      prompt: "Pick scope",
      options: [{ id: "small", label: "Small" }],
    };
    const { container, unmount } = render(
      <PlanClarificationCard data={data} />,
    );

    expect(
      container.querySelector('[data-plan-clarification-active="true"]'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    expect(
      container.querySelector('[data-plan-clarification-active="true"]'),
    ).not.toBeInTheDocument();

    unmount();
    render(<PlanClarificationCard data={data} />);
    expect(screen.getByText("Pick scope")).toBeInTheDocument();
  });

  it("replaces the composer with the latest active plan interaction card", () => {
    renderActiveComposer([
      createClarificationMessage({
        messageId: "assistant-clarification",
        originalId: "original-1",
        traceId: "trace-1",
        prompt: "Pick scope",
      }),
      createReviewMessage({
        messageId: "assistant-review",
        cardId: "plan-2",
        title: "Review latest plan",
      }),
    ]);

    expect(screen.queryByTestId("default-composer")).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Review latest plan" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Pick scope" }),
    ).not.toBeInTheDocument();
  });

  it("falls back to the default composer when no active plan interaction exists", () => {
    renderActiveComposer([
      createReviewMessage({
        messageId: "assistant-review",
        cardId: "plan-2",
        title: "Submitted plan",
        status: "submitted",
        submittedDecision: "execute",
      }),
    ]);

    expect(screen.getByTestId("default-composer")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Submitted plan" }),
    ).not.toBeInTheDocument();
  });

  it("restores the default composer after choosing to continue modifying a plan", () => {
    const onContinueModifying = vi.fn();
    renderActiveComposer(
      [
        createReviewMessage({
          messageId: "assistant-review",
          cardId: "plan-2",
          title: "Review latest plan",
        }),
      ],
      { onContinueModifying },
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Continue modifying" }),
    );

    expect(onContinueModifying).toHaveBeenCalledWith(
      expect.objectContaining({ plan_id: "plan-2" }),
    );
    expect(screen.getByTestId("default-composer")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Review latest plan" }),
    ).not.toBeInTheDocument();
  });

  it("uses focus-only initial state and submits the focused single choice with Enter", async () => {
    const submit = captureSubmitEvents();

    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [
            { id: "small", label: "Small" },
            { id: "large", label: "Large" },
          ],
        }}
      />,
    );

    const small = screen.getByRole("button", { name: /Small/ });
    expect(small).toHaveAttribute("aria-current", "true");
    expect(small).toHaveAttribute("aria-pressed", "false");
    fireEvent.keyDown(screen.getByRole("region", { name: "Pick scope" }), {
      key: "Enter",
    });

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Small",
      biz_params: {
        plan_interaction_response: {
          selected_option_ids: ["small"],
        },
      },
    });

    submit.cleanup();
  });

  it("focuses a choice clarification card on render for immediate keyboard use", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [
            { id: "small", label: "Small" },
            { id: "large", label: "Large" },
          ],
        }}
      />,
    );

    expect(screen.getByRole("region", { name: "Pick scope" })).toHaveFocus();
  });

  it("shows keyboard operation guidance in the card footer", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [
            { id: "lint", label: "Lint" },
            { id: "test", label: "Test" },
          ],
        }}
      />,
    );

    expect(screen.getByText("方向键切换选项，Space 选择")).toBeInTheDocument();
  });

  it("separates multi-choice focus from selection and submits selected rows", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [
            { id: "lint", label: "Lint" },
            { id: "test", label: "Test" },
          ],
        }}
      />,
    );
    const card = screen.getByRole("region", { name: "Pick checks" });

    fireEvent.keyDown(card, { key: " " });
    fireEvent.keyDown(card, { key: "ArrowDown" });
    fireEvent.keyDown(card, { key: " " });
    expect(screen.getByRole("button", { name: /Lint/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Test/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.keyDown(card, { key: "Enter" });

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Lint, Test",
      biz_params: {
        plan_interaction_response: {
          selected_option_ids: ["lint", "test"],
        },
      },
    });
    submit.cleanup();
  });

  it("shows a custom text box by default for top-level single choice cards", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "small", label: "Small" }],
        }}
      />,
    );

    expect(
      screen.getByRole("textbox", { name: "Pick scope" }),
    ).toBeInTheDocument();
  });

  it("single choice custom text clears the selected option and submits only text", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "small", label: "Small" }],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Small/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Pick scope" }), {
      target: { value: "Use a narrower module" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "single_choice",
      selected_option_ids: [],
      text: "Use a narrower module",
    });
    submit.cleanup();
  });

  it("single choice selecting an option clears custom text", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "small", label: "Small" }],
        }}
      />,
    );

    const textbox = screen.getByRole("textbox", {
      name: "Pick scope",
    }) as HTMLTextAreaElement;
    fireEvent.change(textbox, { target: { value: "Custom scope" } });
    fireEvent.click(screen.getByRole("button", { name: /Small/ }));

    expect(textbox.value).toBe("");
  });

  it("single choice Enter on the card submits custom text without the focused option", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          options: [{ id: "small", label: "Small" }],
        }}
      />,
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Pick scope" }), {
      target: { value: "Custom scope" },
    });
    fireEvent.keyDown(screen.getByRole("region", { name: "Pick scope" }), {
      key: "Enter",
    });

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "single_choice",
      selected_option_ids: [],
      text: "Custom scope",
    });
    submit.cleanup();
  });

  it("multi choice submits selected options together with custom text", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [
            { id: "unit", label: "Unit tests" },
            { id: "lint", label: "Lint" },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Unit tests/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Pick checks" }), {
      target: { value: "Also run smoke test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "multi_choice",
      selected_option_ids: ["unit"],
      text: "Also run smoke test",
    });
    submit.cleanup();
  });

  it("multi choice allows submitting only custom text", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [{ id: "unit", label: "Unit tests" }],
        }}
      />,
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Pick checks" }), {
      target: { value: "Manual QA only" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "multi_choice",
      selected_option_ids: [],
      text: "Manual QA only",
    });
    submit.cleanup();
  });

  it("multi choice preserves existing custom text when selecting options", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: [{ id: "unit", label: "Unit tests" }],
        }}
      />,
    );

    const textbox = screen.getByRole("textbox", { name: "Pick checks" });
    fireEvent.change(textbox, { target: { value: "Manual QA" } });
    fireEvent.click(screen.getByRole("button", { name: /Unit tests/ }));
    expect(textbox).toHaveValue("Manual QA");
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(
      submit.handler.mock.calls[0][0].detail.biz_params
        .plan_interaction_response,
    ).toMatchObject({
      card_type: "plan_clarification",
      kind: "multi_choice",
      selected_option_ids: ["unit"],
      text: "Manual QA",
    });
    submit.cleanup();
  });

  it("keeps top-level multi-choice custom text additive even when custom response is allowed", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          allow_custom_response: true,
          options: [
            { id: "lint", label: "Lint" },
            { id: "test", label: "Test" },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Lint/ }));
    expect(
      screen.queryByRole("button", { name: /自定义回复/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Lint/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Pick checks" }), {
      target: { value: "Run security checks" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Lint\nRun security checks",
      biz_params: {
        plan_interaction_response: {
          selected_option_ids: ["lint"],
          text: "Run security checks",
        },
      },
    });
    submit.cleanup();
  });

  it("uses Enter to submit text and preserves Shift+Enter for new lines", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "text",
          prompt: "Add detail",
        }}
      />,
    );
    const input = screen.getByPlaceholderText("Add detail");

    fireEvent.change(input, { target: { value: "Line one" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(submit.handler).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Line one",
    });
    submit.cleanup();
  });

  it("ignores Enter while IME composition is active in text clarifications", () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "text",
          prompt: "Add detail",
        }}
      />,
    );
    const input = screen.getByPlaceholderText("Add detail");

    fireEvent.change(input, { target: { value: "正在输入" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });

    expect(submit.handler).not.toHaveBeenCalled();
    expect(input).toHaveValue("正在输入");
    submit.cleanup();
  });

  it("uses Enter to advance form pages and Escape to return", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "plan-context",
          prompt: "Collect context",
          fields: [
            {
              id: "scope",
              label: "Scope",
              type: "single_choice",
              required: true,
              options: [{ id: "small", label: "Small" }],
            },
            {
              id: "detail",
              label: "Detail",
              type: "text",
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Small/ }));
    fireEvent.keyDown(screen.getByRole("region", { name: "Collect context" }), {
      key: "Enter",
    });
    expect(screen.getByPlaceholderText("Detail")).toBeInTheDocument();

    fireEvent.keyDown(screen.getByPlaceholderText("Detail"), {
      key: "Escape",
    });
    expect(screen.getByRole("button", { name: /Small/ })).toBeInTheDocument();
  });

  it("keeps a form text field visible when Space is pressed on the card", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "plan-detail",
          prompt: "Collect detail",
          fields: [
            {
              id: "detail",
              label: "Detail",
              type: "text",
            },
          ],
        }}
      />,
    );

    fireEvent.keyDown(screen.getByRole("region", { name: "Collect detail" }), {
      key: " ",
    });

    expect(screen.getByPlaceholderText("Detail")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("请输入自定义回复"),
    ).not.toBeInTheDocument();
  });

  it("submits paged form values and optional supplemental context", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "customer_plan_clarification",
          prompt: "Collect planning context",
          allow_custom_response: true,
          fields: [
            {
              id: "industry",
              label: "所在行业",
              type: "single_choice",
              required: true,
              options: [{ id: "retail", label: "零售/电商" }],
            },
            {
              id: "challenges",
              label: "当前主要挑战",
              type: "text",
              placeholder: "请补充",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("1 of 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /零售\/电商/ }));
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    fireEvent.change(screen.getByPlaceholderText("请补充"), {
      target: { value: "复购率低" },
    });
    fireEvent.keyDown(screen.getByPlaceholderText("请补充"), { key: "Enter" });
    fireEvent.change(screen.getByPlaceholderText("请输入自定义回复"), {
      target: { value: "希望年度内看到改善" },
    });
    fireEvent.keyDown(screen.getByPlaceholderText("请输入自定义回复"), {
      key: "Enter",
    });

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "所在行业: 零售/电商\n当前主要挑战: 复购率低\n希望年度内看到改善",
      biz_params: {
        plan_interaction_response: {
          kind: "form",
          form_id: "customer_plan_clarification",
          field_values: {
            industry: "retail",
            challenges: "复购率低",
          },
          text: "希望年度内看到改善",
        },
      },
    });
    submit.cleanup();
  });

  it("submits structured multi-choice form values as selected option ids", async () => {
    const submit = captureSubmitEvents();
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "plan_checks",
          prompt: "Choose verification checks",
          fields: [
            {
              id: "checks",
              label: "验证项",
              type: "multi_choice",
              required: true,
              options: [
                { id: "frontend", label: "前端测试" },
                { id: "backend", label: "后端测试" },
              ],
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /前端测试/ }));
    fireEvent.click(screen.getByRole("button", { name: /后端测试/ }));
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "验证项: 前端测试, 后端测试",
      biz_params: {
        plan_interaction_response: {
          field_values: {
            checks: ["frontend", "backend"],
          },
        },
      },
    });
    submit.cleanup();
  });

  it("preserves supplemental context when revisiting form fields", () => {
    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "form",
          form_id: "scope-context",
          prompt: "Collect context",
          allow_custom_response: true,
          fields: [
            {
              id: "scope",
              label: "Scope",
              type: "single_choice",
              required: true,
              options: [{ id: "small", label: "Small" }],
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Small/ }));
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    fireEvent.change(screen.getByPlaceholderText("请输入自定义回复"), {
      target: { value: "Keep this context" },
    });
    fireEvent.click(screen.getByRole("button", { name: "上一项" }));
    fireEvent.click(screen.getByRole("button", { name: /Small/ }));
    fireEvent.click(screen.getByRole("button", { name: "继续" }));

    expect(screen.getByPlaceholderText("请输入自定义回复")).toHaveValue(
      "Keep this context",
    );
  });

  it("keeps long option sets inside the card viewport", () => {
    const { container } = render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          options: Array.from({ length: 6 }, (_, index) => ({
            id: String(index),
            label: `Option ${index + 1}`,
          })),
        }}
      />,
    );

    expect(
      container.querySelector(`.${styles.choiceOptionsViewport}`),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Option/ })).toHaveLength(6);
  });

  it("hides a submitted clarification in the current render", async () => {
    const submit = captureSubmitEvents();
    const data = {
      card_type: "plan_clarification" as const,
      kind: "single_choice" as const,
      prompt: "Pick scope",
      options: [{ id: "small", label: "Small" }],
    };
    render(<PlanClarificationCard data={data} />);

    fireEvent.keyDown(screen.getByRole("region", { name: "Pick scope" }), {
      key: "Enter",
    });
    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));

    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();
    submit.cleanup();
  });

  it("resets stale clarification state when a newer card instance replaces it", () => {
    const firstMessages = [
      {
        id: "message-1",
        role: "assistant" as const,
        cards: [
          {
            id: "clarification-1",
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];
    const { rerender } = renderActiveClarification(firstMessages);

    fireEvent.click(screen.getByRole("button", { name: /Small/ }));
    expect(screen.getByRole("button", { name: "提交" })).toBeEnabled();

    const secondMessages = [
      ...firstMessages,
      {
        id: "message-2",
        role: "assistant" as const,
        cards: [
          {
            id: "clarification-2",
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick size",
              options: [{ id: "large", label: "Large" }],
            },
          },
        ],
      },
    ];

    rerender(
      <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
        <ChatAnywhereMessagesContext.Provider
          value={{
            messages: secondMessages,
            setMessages: vi.fn(),
            getMessages: () => secondMessages,
          }}
        >
          <ActivePlanClarificationCard />
        </ChatAnywhereMessagesContext.Provider>
      </ChatAnywhereSessionsContext.Provider>,
    );

    expect(screen.getByRole("button", { name: /Large/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByRole("button", { name: "提交" })).toBeDisabled();
  });

  it("shows a dismissed clarification after reload when it is not superseded", () => {
    const firstMessages = [
      {
        id: "msg_runtime_1",
        role: "assistant" as const,
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: {
              id: "response_runtime_1",
              output: [
                {
                  role: "assistant" as const,
                  id: "msg_runtime_1",
                  metadata: {
                    original_id: "assistant-stable-1",
                    trace_id: "trace-stable-1",
                  },
                },
              ],
            },
          },
          {
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];
    const { rerender } = renderActiveClarification(firstMessages);

    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();

    const reloadedMessages = [
      {
        id: "msg_runtime_2",
        role: "assistant" as const,
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: {
              id: "response_runtime_2",
              output: [
                {
                  role: "assistant" as const,
                  id: "msg_runtime_2",
                  metadata: {
                    original_id: "assistant-stable-1",
                    trace_id: "trace-stable-1",
                  },
                },
              ],
            },
          },
          {
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];

    rerender(
      <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
        <ChatAnywhereMessagesContext.Provider
          value={{
            messages: reloadedMessages,
            setMessages: vi.fn(),
            getMessages: () => reloadedMessages,
          }}
        >
          <ActivePlanClarificationCard />
        </ChatAnywhereMessagesContext.Provider>
      </ChatAnywhereSessionsContext.Provider>,
    );

    expect(screen.getByText("Pick scope")).toBeInTheDocument();
  });

  it("shows a repeated clarification again when it is a new card instance", () => {
    const firstMessages = [
      {
        id: "message-1",
        role: "assistant" as const,
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: {
              id: "response_runtime_1",
              output: [
                {
                  role: "assistant" as const,
                  id: "msg_runtime_1",
                  metadata: {
                    original_id: "assistant-stable-1",
                    trace_id: "trace-stable-1",
                  },
                },
              ],
            },
          },
          {
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];
    const { rerender } = renderActiveClarification(firstMessages);

    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();

    const secondMessages = [
      ...firstMessages,
      {
        id: "message-2",
        role: "assistant" as const,
        cards: [
          {
            code: "AgentScopeRuntimeResponseCard",
            data: {
              id: "response_runtime_2",
              output: [
                {
                  role: "assistant" as const,
                  id: "msg_runtime_2",
                  metadata: {
                    original_id: "assistant-stable-2",
                    trace_id: "trace-stable-2",
                  },
                },
              ],
            },
          },
          {
            code: "PlanInteraction",
            data: {
              card_type: "plan_clarification" as const,
              kind: "single_choice" as const,
              prompt: "Pick scope",
              options: [{ id: "small", label: "Small" }],
            },
          },
        ],
      },
    ];

    rerender(
      <ChatAnywhereSessionsContext.Provider value={createSessionContextValue()}>
        <ChatAnywhereMessagesContext.Provider
          value={{
            messages: secondMessages,
            setMessages: vi.fn(),
            getMessages: () => secondMessages,
          }}
        >
          <ActivePlanClarificationCard />
        </ChatAnywhereMessagesContext.Provider>
      </ChatAnywhereSessionsContext.Provider>,
    );

    expect(screen.getByText("Pick scope")).toBeInTheDocument();
  });

  it("hides a clarification superseded by a later user message", async () => {
    const messages = [
      createClarificationMessage({
        messageId: "message-1",
        originalId: "assistant-stable-1",
        traceId: "trace-stable-1",
      }),
    ];
    const { unmount } = renderActiveClarification(messages);

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Pick scope" })).toBeVisible(),
    );
    unmount();
    renderActiveClarification(messages);

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Pick scope" })).toBeVisible(),
    );

    cleanup();
    renderActiveClarification([
      ...messages,
      {
        id: "user-1",
        role: "user" as const,
        cards: [
          {
            code: "AgentScopeRuntimeRequestCard",
            data: {
              input: [
                {
                  role: "user",
                  type: "message",
                  content: [
                    {
                      type: "text",
                      text: "Continue without answering",
                    },
                  ],
                },
              ],
            },
          },
        ],
      },
    ]);

    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();
  });

  it("renders a repeated clarification from a later assistant message", async () => {
    const firstMessage = createClarificationMessage({
      messageId: "message-1",
      originalId: "assistant-stable-1",
      traceId: "trace-stable-1",
    });
    const { unmount } = renderActiveClarification([firstMessage]);

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Pick scope" })).toBeVisible(),
    );
    unmount();

    renderActiveClarification([
      firstMessage,
      createClarificationMessage({
        messageId: "message-2",
        originalId: "assistant-stable-2",
        traceId: "trace-stable-2",
      }),
    ]);

    expect(screen.getByText("Pick scope")).toBeInTheDocument();
  });

  it("does not suppress a later repeated clarification after submitting the first instance", async () => {
    const submit = captureSubmitEvents();
    const firstMessage = createClarificationMessage({
      messageId: "message-1",
      originalId: "assistant-stable-1",
      traceId: "trace-stable-1",
    });
    const { unmount } = renderActiveClarification([firstMessage]);

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Pick scope" })).toBeVisible(),
    );
    fireEvent.keyDown(screen.getByRole("region", { name: "Pick scope" }), {
      key: "Enter",
    });
    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    unmount();

    renderActiveClarification([
      firstMessage,
      createClarificationMessage({
        messageId: "message-2",
        originalId: "assistant-stable-2",
        traceId: "trace-stable-2",
      }),
    ]);

    expect(screen.getByText("Pick scope")).toBeInTheDocument();
    submit.cleanup();
  });

  it("renders only the latest unhandled plan review as the active card", () => {
    renderActivePlanReview([
      createReviewMessage({
        messageId: "message-1",
        cardId: "review-1",
        title: "Older review",
      }),
      createReviewMessage({
        messageId: "message-2",
        cardId: "review-2",
        title: "Submitted review",
        status: "submitted",
        submittedDecision: "execute",
      }),
      createReviewMessage({
        messageId: "message-3",
        cardId: "review-3",
        title: "Latest review",
      }),
    ]);

    expect(
      screen.getByRole("region", { name: "Latest review" }),
    ).toHaveAttribute("data-active-plan-review-card", "true");
    expect(screen.queryByText("Older review")).not.toBeInTheDocument();
    expect(screen.queryByText("Submitted review")).not.toBeInTheDocument();
  });

  it("renders no active plan review if a later user message supersedes it", () => {
    renderActivePlanReview([
      createReviewMessage({
        messageId: "message-1",
        cardId: "review-1",
        title: "Plan to confirm",
      }),
      {
        id: "user-1",
        role: "user" as const,
        cards: [],
      },
    ]);

    expect(screen.queryByText("Plan to confirm")).not.toBeInTheDocument();
  });

  it("renders a read-only plan review snapshot with submitted execute status", () => {
    render(
      <PlanReviewSnapshot
        data={createReviewData({
          status: "submitted",
          submitted_decision: "execute",
        })}
      />,
    );

    expect(screen.getByRole("region", { name: "Fix bug" })).toHaveAttribute(
      "data-plan-review-snapshot",
      "true",
    );
    expect(screen.getByText("已接受并开始执行")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Continue modifying" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Execute" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Exit Plan Mode" }),
    ).not.toBeInTheDocument();
  });

  it("keeps action buttons in active plan review mode", () => {
    const { container } = render(
      <PlanReviewCard active data={createReviewData()} />,
    );

    expect(
      container.querySelector(`.${styles.planReviewActiveCard}`),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Continue modifying" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Execute" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Exit Plan Mode" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "反馈意见" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Feedback")).not.toBeInTheDocument();
  });

  it("renders long plan review summary in the body summary area", () => {
    const longSummary =
      "This summary is intentionally long so it should wrap inside the review body instead of being placed in a single-line header paragraph.";
    const { container } = render(
      <PlanReviewCard
        active
        data={createReviewData({ summary: longSummary })}
      />,
    );

    expect(
      container.querySelector(`.${styles.reviewSummary}`),
    ).toHaveTextContent(longSummary);
  });

  it("calls continue modifying without submitting a plan review response", () => {
    const submit = captureSubmitEvents();
    const onContinueModifying = vi.fn();

    render(
      <PlanReviewCard
        active
        onContinueModifying={onContinueModifying}
        data={{
          card_type: "plan_review",
          plan_id: "plan-123",
          title: "Fix bug",
          summary: "Investigate and patch",
          steps: ["Read code", "Patch code"],
          risks: ["Regression"],
          verification: ["Focused tests"],
        }}
      />,
    );
    expect(
      screen.queryByTestId("generic-operate-card"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Fix bug" })).toHaveAttribute(
      "data-plan-review-card",
      "true",
    );
    expect(screen.getByText("执行步骤")).toBeInTheDocument();
    expect(screen.getByText("风险提示")).toBeInTheDocument();
    expect(screen.getByText("验证方式")).toBeInTheDocument();
    expect(screen.queryByText("Open questions")).not.toBeInTheDocument();
    expect(screen.queryByText(/Confidence:/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continue modifying" }));

    expect(onContinueModifying).toHaveBeenCalledWith(
      expect.objectContaining({ plan_id: "plan-123" }),
    );
    expect(submit.handler).not.toHaveBeenCalled();

    submit.cleanup();
  });

  it("executes review cards in normal mode and disables duplicates", async () => {
    const submit = captureSubmitEvents();

    render(
      <PlanReviewCard
        active
        data={{
          card_type: "plan_review",
          plan_id: "plan-456",
          title: "Ship plan",
          summary: "Ready",
          steps: [],
          risks: [],
          verification: [],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Execute" }));

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      biz_params: {
        mode: "normal",
        plan_interaction_response: {
          card_type: "plan_review",
          plan_id: "plan-456",
          decision: "execute",
        },
      },
    });
    expect(screen.getByRole("button", { name: "Execute" })).toBeDisabled();

    submit.cleanup();
  });

  it("exits plan mode locally without submitting a chat message", async () => {
    const submit = captureSubmitEvents();
    const onPlanModeDecision = vi.fn();

    render(
      <PlanReviewCard
        active
        onPlanModeDecision={onPlanModeDecision}
        data={createReviewData({
          plan_id: "plan-exit",
          title: "Exit without message",
        })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Exit Plan Mode" }));

    expect(onPlanModeDecision).toHaveBeenCalledWith(false);
    await Promise.resolve();
    expect(submit.handler).not.toHaveBeenCalled();

    submit.cleanup();
  });
});
