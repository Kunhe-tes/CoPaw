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
import { ChatAnywhereSessionsContext } from "@/components/agentscope-chat";
import {
  ActivePlanClarificationCard,
  PlanClarificationCard,
  PlanReviewCard,
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
      <section>
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

function renderActiveClarification(messages: any[]) {
  return render(
    <ChatAnywhereSessionsContext.Provider
      value={createSessionContextValue()}
    >
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

describe("Plan interaction cards", () => {
  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    (window as Window & { currentSessionId?: string }).currentSessionId =
      undefined;
  });

  it("marks an active clarification and persists dismissal in the session", () => {
    const data = {
      card_type: "plan_clarification" as const,
      kind: "single_choice" as const,
      prompt: "Pick scope",
      options: [{ id: "small", label: "Small" }],
    };
    const { container, rerender } = render(
      <PlanClarificationCard data={data} />,
    );

    expect(
      container.querySelector('[data-plan-clarification-active="true"]'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    expect(
      container.querySelector('[data-plan-clarification-active="true"]'),
    ).not.toBeInTheDocument();

    rerender(<PlanClarificationCard data={data} />);
    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();
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

  it("makes a multi-choice custom response exclusive with predefined choices", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: /自定义回复/ }));
    expect(
      screen.queryByRole("button", { name: /Lint/ }),
    ).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByPlaceholderText("请输入自定义回复"), {
      key: "Escape",
    });
    expect(screen.getByRole("button", { name: /Lint/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    fireEvent.click(screen.getByRole("button", { name: /自定义回复/ }));
    fireEvent.change(screen.getByPlaceholderText("请输入自定义回复"), {
      target: { value: "Run security checks" },
    });
    fireEvent.keyDown(screen.getByPlaceholderText("请输入自定义回复"), {
      key: "Enter",
    });

    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Run security checks",
      biz_params: {
        plan_interaction_response: {
          selected_option_ids: [],
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
          kind: "text_input",
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
          kind: "text_input",
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
              type: "select",
              required: true,
              options: [{ id: "small", label: "Small" }],
            },
            {
              id: "detail",
              label: "Detail",
              type: "textarea",
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
              type: "select",
              required: true,
              options: [{ id: "retail", label: "零售/电商" }],
            },
            {
              id: "challenges",
              label: "当前主要挑战",
              type: "textarea",
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

  it("submits structured multiselect form values as selected option ids", async () => {
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
              type: "multiselect",
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
              type: "select",
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

  it("does not render an already submitted clarification in the same session", async () => {
    const submit = captureSubmitEvents();
    const data = {
      card_type: "plan_clarification" as const,
      kind: "single_choice" as const,
      prompt: "Pick scope",
      options: [{ id: "small", label: "Small" }],
    };
    const { unmount } = render(<PlanClarificationCard data={data} />);

    fireEvent.keyDown(screen.getByRole("region", { name: "Pick scope" }), {
      key: "Enter",
    });
    await waitFor(() => expect(submit.handler).toHaveBeenCalledTimes(1));

    unmount();
    render(<PlanClarificationCard data={data} />);
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
      <ChatAnywhereSessionsContext.Provider
        value={createSessionContextValue()}
      >
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

  it("keeps a dismissed clarification hidden after reload when runtime ids change", () => {
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
      <ChatAnywhereSessionsContext.Provider
        value={createSessionContextValue()}
      >
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

    expect(screen.queryByText("Pick scope")).not.toBeInTheDocument();
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
      <ChatAnywhereSessionsContext.Provider
        value={createSessionContextValue()}
      >
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

  it("submits review decisions with distinct Plan Review payloads", async () => {
    const submit = captureSubmitEvents();

    render(
      <PlanReviewCard
        data={{
          card_type: "plan_review",
          plan_id: "plan-123",
          title: "Fix bug",
          summary: "Investigate and patch",
          steps: ["Read code", "Patch code"],
          risks: ["Regression"],
          verification: ["Focused tests"],
          open_questions: [],
          confidence: 0.82,
        }}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("Feedback"), {
      target: { value: "Narrow the scope" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue modifying" }));

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Narrow the scope",
      biz_params: {
        mode: "plan",
        plan_interaction_response: {
          card_type: "plan_review",
          plan_id: "plan-123",
          decision: "revise",
          feedback: "Narrow the scope",
        },
      },
    });

    submit.cleanup();
  });

  it("executes review cards in normal mode and disables duplicates", async () => {
    const submit = captureSubmitEvents();

    render(
      <PlanReviewCard
        data={{
          card_type: "plan_review",
          plan_id: "plan-456",
          title: "Ship plan",
          summary: "Ready",
          steps: [],
          risks: [],
          verification: [],
          open_questions: [],
          confidence: 0.95,
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
});
