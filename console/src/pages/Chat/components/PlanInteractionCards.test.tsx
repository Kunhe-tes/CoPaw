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
import { PlanClarificationCard, PlanReviewCard } from "./PlanInteractionCards";

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

describe("Plan interaction cards", () => {
  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    (window as Window & { currentSessionId?: string }).currentSessionId =
      undefined;
  });

  it("renders and submits a single-choice clarification", async () => {
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

    expect(screen.queryByText("Plan clarification")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Small"));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalled();
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Small",
      biz_params: {
        plan_interaction_response: {
          card_type: "plan_clarification",
          kind: "single_choice",
          selected_option_ids: ["small"],
        },
      },
    });
    expect(screen.queryByLabelText("Small")).not.toBeInTheDocument();

    submit.cleanup();
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

    fireEvent.click(screen.getByLabelText("Small"));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });

    unmount();
    render(<PlanClarificationCard data={data} />);

    await waitFor(() => {
      expect(screen.queryByLabelText("Small")).not.toBeInTheDocument();
    });

    submit.cleanup();
  });

  it("renders multiple-choice and text clarification inputs", () => {
    const { rerender } = render(
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

    expect(screen.getByLabelText("Lint")).toBeInTheDocument();
    expect(screen.getByLabelText("Test")).toBeInTheDocument();

    rerender(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "text_input",
          prompt: "Add detail",
        }}
      />,
    );

    expect(screen.getByPlaceholderText("Add detail")).toBeInTheDocument();
  });

  it("submits custom text for choice clarification when allowed", async () => {
    const submit = captureSubmitEvents();

    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "single_choice",
          prompt: "Pick scope",
          allow_custom_response: true,
          options: [{ id: "small", label: "Small" }],
        }}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("Custom response"), {
      target: { value: "Use a narrower scope" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Use a narrower scope",
      biz_params: {
        plan_interaction_response: {
          card_type: "plan_clarification",
          kind: "single_choice",
          selected_option_ids: [],
          text: "Use a narrower scope",
        },
      },
    });

    submit.cleanup();
  });

  it("submits selected choices plus custom text when both are present", async () => {
    const submit = captureSubmitEvents();

    render(
      <PlanClarificationCard
        data={{
          card_type: "plan_clarification",
          kind: "multi_choice",
          prompt: "Pick checks",
          allow_custom_response: true,
          options: [{ id: "lint", label: "Lint" }],
        }}
      />,
    );

    fireEvent.click(screen.getByLabelText("Lint"));
    fireEvent.change(screen.getByPlaceholderText("Custom response"), {
      target: { value: "Also run focused backend tests" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "Lint\nAlso run focused backend tests",
      biz_params: {
        plan_interaction_response: {
          kind: "multi_choice",
          selected_option_ids: ["lint"],
          text: "Also run focused backend tests",
        },
      },
    });

    submit.cleanup();
  });

  it("renders structured clarification forms and submits field values", async () => {
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
              id: "current_challenges",
              label: "当前主要挑战",
              type: "textarea",
              placeholder: "请补充",
            },
          ],
        }}
      />,
    );

    expect(screen.queryByPlaceholderText("请补充")).not.toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("零售/电商"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByPlaceholderText("请补充")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(screen.getByPlaceholderText("请补充"), {
      target: { value: "复购率低" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(screen.getByPlaceholderText("Custom response"), {
      target: { value: "希望年度内看到改善" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "所在行业: 零售/电商\n当前主要挑战: 复购率低\n希望年度内看到改善",
      biz_params: {
        plan_interaction_response: {
          card_type: "plan_clarification",
          kind: "form",
          form_id: "customer_plan_clarification",
          field_values: {
            industry: "retail",
            current_challenges: "复购率低",
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

    fireEvent.mouseDown(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("前端测试"));
    fireEvent.click(screen.getByText("后端测试"));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(submit.handler).toHaveBeenCalledTimes(1);
    });
    expect(submit.handler.mock.calls[0][0].detail).toMatchObject({
      query: "验证项: 前端测试, 后端测试",
      biz_params: {
        plan_interaction_response: {
          card_type: "plan_clarification",
          kind: "form",
          form_id: "plan_checks",
          field_values: {
            checks: ["frontend", "backend"],
          },
        },
      },
    });

    submit.cleanup();
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

  it("executes or exits review cards in normal mode and disables duplicates", async () => {
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
