import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";

import type { WPlusSopSession } from "@/api/types/wplusSop";
import WPlusSopWorkspace from "./index";

const apiMock = vi.hoisted(() => ({
  getSession: vi.fn(),
  sendCommand: vi.fn(),
  downloadArtifact: vi.fn(),
  subscribeSessionEvents: vi.fn(),
}));

interface SubscriptionCallbacks {
  afterStateVersion: number;
  onEvent: (event: unknown) => void;
  onError: (error: unknown) => void;
}

let subscriptionCallbacks: SubscriptionCallbacks[] = [];

vi.mock("@/api/modules/wplusSop", () => ({
  wplusSopApi: apiMock,
}));

function makeSession(
  overrides: Partial<WPlusSopSession> = {},
): WPlusSopSession {
  return {
    session_id: "sop-1",
    chat_id: "chat-1",
    title: "客户经营 SOP",
    state: "AwaitingQueueConfirmation",
    state_version: 4,
    revision: 1,
    round: 1,
    runtime_status: {
      status: "ready",
      runtime_ready: true,
      blocking_run_id: null,
    },
    current_stage_id: "stage-1",
    stages: [
      {
        stage_id: "stage-1",
        title: "确认名单范围",
        description: "确定产品和时间窗口",
        status: "current",
      },
      {
        stage_id: "stage-2",
        title: "创建后续任务",
        description: "确认任务字段",
        status: "pending",
      },
    ],
    updated_at: "2026-07-28T08:00:00Z",
    ...overrides,
  };
}

function SessionSwitchControl() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate("/wplus-sop/sop-2?from=chat")}
    >
      切换测试 Session
    </button>
  );
}

function renderPage(options: { withSessionSwitcher?: boolean } = {}) {
  return render(
    <MemoryRouter initialEntries={["/wplus-sop/sop-1?from=chat"]}>
      {options.withSessionSwitcher ? <SessionSwitchControl /> : null}
      <Routes>
        <Route path="/wplus-sop/:sessionId" element={<WPlusSopWorkspace />} />
        <Route path="/chat/:chatId" element={<p>所属 Chat</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function emitSafeStreamTrace({
  runId,
  sequence,
  summaryText,
  stateVersion = 5,
  truncated = false,
  subscriptionIndex = 0,
}: {
  runId: string;
  sequence: number;
  summaryText: string;
  stateVersion?: number;
  truncated?: boolean;
  subscriptionIndex?: number;
}) {
  act(() => {
    subscriptionCallbacks[subscriptionIndex].onEvent({
      event_id: `trace:sop-1:${runId}:${sequence}`,
      session_id: "sop-1",
      state_version: stateVersion,
      kind: "safe_stream_trace",
      run_id: runId,
      safe_stream_trace: {
        sequence,
        summary_text: summaryText,
        truncated,
      },
    });
  });
}

describe("WPlusSopWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    subscriptionCallbacks = [];
    apiMock.subscribeSessionEvents.mockImplementation(
      (_sessionId, afterStateVersion, onEvent, onError) => {
        subscriptionCallbacks.push({
          afterStateVersion,
          onEvent,
          onError,
        });
        return {
          close: vi.fn(),
          done: Promise.resolve(),
        };
      },
    );
    apiMock.getSession.mockResolvedValue(makeSession());
    apiMock.downloadArtifact.mockResolvedValue(
      new Blob(["artifact"], { type: "text/plain" }),
    );
    apiMock.sendCommand.mockImplementation(async (_sessionId, command) => ({
      command_request_id: command.command_request_id,
      accepted: true,
      session: makeSession({
        state: "GeneratingQuestions",
        state_version: 5,
      }),
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("names the loading state and explains what is loading", () => {
    apiMock.getSession.mockReturnValue(new Promise(() => {}));
    renderPage();

    expect(
      screen.getByRole("status", { name: "正在加载 W+ SOP 工作台" }),
    ).toHaveAttribute("aria-live", "polite");
    expect(
      screen.getByText("正在同步环节、回答和预跑状态，请稍候。"),
    ).toBeInTheDocument();
  });

  it("announces generation and labels both progress indicators", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "GeneratingQuestions",
        state_version: 5,
      }),
    );
    renderPage();

    expect(
      await screen.findByRole("status", { name: "正在生成问题" }),
    ).toHaveAttribute("aria-live", "polite");
    expect(
      screen.getByRole("progressbar", { name: "SOP 总体进度" }),
    ).toHaveAttribute("aria-valuenow", "12");
    expect(
      screen.getByRole("progressbar", { name: "当前运行进度" }),
    ).toHaveAttribute("aria-valuenow", "12");
  });

  it("gives the pre-run result table a caption and scoped headers", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "AwaitingTrialFeedback",
        state_version: 10,
        trial: {
          run_id: "run-1",
          status: "completed",
          steps: [],
          result_columns: [
            { field: "product", label: "产品" },
            { field: "due_at", label: "到期日" },
          ],
          result_rows: [{ product: "稳健理财", due_at: "2026-08-01" }],
        },
      }),
    );
    renderPage();

    const table = await screen.findByRole("table", {
      name: "系统预跑结果明细",
    });
    const caption = table.querySelector("caption");
    const headers = table.querySelectorAll("th");

    expect(caption).toHaveTextContent("系统预跑结果明细");
    expect(headers).toHaveLength(2);
    expect(Array.from(headers)).toEqual([
      expect.objectContaining({ scope: "col" }),
      expect.objectContaining({ scope: "col" }),
    ]);
  });

  it("exposes the complete value of a long stage title", async () => {
    const longStageTitle =
      "核验跨区域重点客户近十二个月到期资产与当前持仓的完整覆盖范围";
    apiMock.getSession.mockResolvedValue(
      makeSession({
        stages: [
          {
            stage_id: "stage-1",
            title: longStageTitle,
            description: "确定产品和时间窗口",
            status: "current",
          },
        ],
      }),
    );
    renderPage();

    expect(
      await screen.findByText(longStageTitle, { selector: "strong" }),
    ).toHaveAttribute("title", longStageTitle);
  });

  it("opens and closes the named evidence drawer from the narrow-shell entry", async () => {
    renderPage();

    const trigger = await screen.findByRole("button", {
      name: "查看本次 SOP 证据",
      hidden: true,
    });
    fireEvent.click(trigger);

    expect(
      await screen.findByRole("dialog", { name: "本次 SOP 证据" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "关闭本次 SOP 证据" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "本次 SOP 证据" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("closes the evidence drawer when navigating to another SOP session", async () => {
    renderPage({ withSessionSwitcher: true });

    fireEvent.click(
      await screen.findByRole("button", {
        name: "查看本次 SOP 证据",
        hidden: true,
      }),
    );
    expect(
      await screen.findByRole("dialog", { name: "本次 SOP 证据" }),
    ).toBeInTheDocument();

    apiMock.getSession.mockResolvedValue(
      makeSession({ session_id: "sop-2", state_version: 1 }),
    );
    fireEvent.click(screen.getByRole("button", { name: "切换测试 Session" }));

    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "本次 SOP 证据" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("edits and atomically confirms a valid stage queue", async () => {
    renderPage();

    const firstStage = await screen.findByDisplayValue("确认名单范围");
    fireEvent.change(firstStage, { target: { value: "确认目标名单" } });
    fireEvent.click(screen.getByLabelText("将“创建后续任务”上移"));
    fireEvent.click(screen.getByRole("button", { name: "确认这 2 个环节" }));

    await waitFor(() => expect(apiMock.sendCommand).toHaveBeenCalledTimes(1));
    const [, command] = apiMock.sendCommand.mock.calls[0];
    expect(command.command).toBe("confirm_stage_queue");
    expect(command.payload.stages).toEqual([
      expect.objectContaining({ stage_id: "stage-2" }),
      expect.objectContaining({
        stage_id: "stage-1",
        title: "确认目标名单",
      }),
    ]);
  });

  it("adds and confirms a fifth stage without imposing a manual upper limit", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        stages: [
          ...makeSession().stages,
          {
            stage_id: "stage-3",
            title: "核验客户资料",
            description: "确认资料是否完整",
            status: "pending",
          },
          {
            stage_id: "stage-4",
            title: "安排跟进计划",
            description: "确认后续负责人",
            status: "pending",
          },
        ],
      }),
    );
    renderPage();

    const addButton = await screen.findByRole("button", { name: "增加环节" });
    expect(
      screen.getByText("自动候选 2–4 个 · 手动新增不限"),
    ).toBeInTheDocument();
    expect(addButton).toBeEnabled();
    fireEvent.click(addButton);
    fireEvent.click(screen.getByRole("button", { name: "确认这 5 个环节" }));

    await waitFor(() => expect(apiMock.sendCommand).toHaveBeenCalledTimes(1));
    expect(apiMock.sendCommand.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        command: "confirm_stage_queue",
        payload: {
          stages: expect.arrayContaining([
            expect.objectContaining({ title: "新环节 5" }),
          ]),
        },
      }),
    );
    expect(apiMock.sendCommand.mock.calls[0][1].payload.stages).toHaveLength(5);
  }, 15_000);

  it("uses native radio semantics and submits the whole question batch once", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "AwaitingAnswer",
        state_version: 7,
        question_batch: {
          batch_id: "batch-1",
          stage_id: "stage-1",
          questions: [
            {
              question_id: "q-1",
              kind: "single_select",
              prompt: "到期窗口多长？",
              required: true,
              options: [
                { option_id: "30d", label: "未来 30 天" },
                { option_id: "60d", label: "未来 60 天" },
              ],
            },
            {
              question_id: "q-2",
              kind: "free_text",
              prompt: "名单状态是什么？",
              required: true,
            },
          ],
        },
      }),
    );
    renderPage();

    const radio = await screen.findByRole("radio", { name: "未来 30 天" });
    fireEvent.click(radio);
    expect(radio).toBeChecked();
    fireEvent.change(screen.getByLabelText("名单状态是什么？"), {
      target: { value: "待处理" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交本轮 2 个回答" }));

    await waitFor(() => expect(apiMock.sendCommand).toHaveBeenCalledTimes(1));
    expect(apiMock.sendCommand.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        command: "submit_answers",
        expected_state_version: 7,
        payload: {
          batch_id: "batch-1",
          answers: {
            "q-1": "30d",
            "q-2": "待处理",
          },
        },
      }),
    );
  });

  it("keeps answers editable but blocks submission while the owning Chat is finalizing", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "AwaitingAnswer",
        state_version: 7,
        runtime_status: {
          status: "finalizing",
          runtime_ready: false,
          blocking_run_id: "run-question-batch",
        },
        question_batch: {
          batch_id: "batch-waiting",
          stage_id: "stage-1",
          questions: [
            {
              question_id: "q-waiting",
              kind: "free_text",
              prompt: "补充客户范围",
              required: true,
            },
          ],
        },
      } as Partial<WPlusSopSession>),
    );
    renderPage();

    const answer = await screen.findByLabelText("补充客户范围");
    fireEvent.change(answer, { target: { value: "重点客户" } });

    expect(answer).toHaveValue("重点客户");
    expect(
      screen.getByRole("button", { name: "正在完成上一轮处理" }),
    ).toBeDisabled();
    expect(screen.getAllByText("正在完成上一轮处理")).toHaveLength(2);
    expect(apiMock.sendCommand).not.toHaveBeenCalled();
  });

  it("fails closed when an AwaitingAnswer snapshot has no runtime readiness", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "AwaitingAnswer",
        state_version: 7,
        runtime_status: undefined,
        question_batch: {
          batch_id: "batch-legacy",
          stage_id: "stage-1",
          questions: [
            {
              question_id: "q-legacy",
              kind: "free_text",
              prompt: "补充名单",
              required: true,
            },
          ],
        },
      } as Partial<WPlusSopSession>),
    );
    renderPage();

    fireEvent.change(await screen.findByLabelText("补充名单"), {
      target: { value: "已补充" },
    });
    expect(
      screen.getByRole("button", { name: "正在完成上一轮处理" }),
    ).toBeDisabled();
  });

  it("enables answer submission from a same-version runtime_status SSE event", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "AwaitingAnswer",
        state_version: 7,
        runtime_status: {
          status: "finalizing",
          runtime_ready: false,
          blocking_run_id: "run-question-batch",
        },
        question_batch: {
          batch_id: "batch-runtime-ready",
          stage_id: "stage-1",
          questions: [
            {
              question_id: "q-runtime-ready",
              kind: "free_text",
              prompt: "补充触达规则",
              required: true,
            },
          ],
        },
      } as Partial<WPlusSopSession>),
    );
    renderPage();

    fireEvent.change(await screen.findByLabelText("补充触达规则"), {
      target: { value: "仅工作日" },
    });
    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));
    expect(
      screen.getByRole("button", { name: "正在完成上一轮处理" }),
    ).toBeDisabled();

    act(() => {
      subscriptionCallbacks[0].onEvent({
        event_id: "runtime-ready:sop-1",
        session_id: "sop-1",
        state_version: 7,
        kind: "runtime_status",
        runtime_status: {
          status: "ready",
          runtime_ready: true,
          blocking_run_id: null,
        },
      });
    });

    const submit = screen.getByRole("button", {
      name: "提交本轮 1 个回答",
    });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    await waitFor(() => expect(apiMock.sendCommand).toHaveBeenCalledTimes(1));
  });

  it("preserves answer drafts and explains an owning_chat_finalizing 409", async () => {
    const session = makeSession({
      state: "AwaitingAnswer",
      state_version: 7,
      runtime_status: {
        status: "ready",
        runtime_ready: true,
        blocking_run_id: null,
      },
      question_batch: {
        batch_id: "batch-race",
        stage_id: "stage-1",
        questions: [
          {
            question_id: "q-race",
            kind: "free_text",
            prompt: "填写执行范围",
            required: true,
          },
        ],
      },
    } as Partial<WPlusSopSession>);
    apiMock.getSession.mockResolvedValue(session);
    let rejectCommand: ((reason?: unknown) => void) | undefined;
    apiMock.sendCommand.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectCommand = reject;
        }),
    );
    const finalizingError = Object.assign(
      new Error("owning Chat is finalizing"),
      {
        status: 409,
        data: {
          detail: {
            code: "owning_chat_finalizing",
            message: "上一轮 Agent 正在收尾",
            retry_after_ms: 1000,
          },
        },
      },
    );
    renderPage();

    const answer = await screen.findByLabelText("填写执行范围");
    fireEvent.change(answer, { target: { value: "保留这份回答" } });
    fireEvent.click(screen.getByRole("button", { name: "提交本轮 1 个回答" }));
    await waitFor(() => expect(rejectCommand).toBeDefined());
    await act(async () => rejectCommand?.(finalizingError));

    expect(
      await screen.findByText(
        "上一轮处理仍在结束中，回答已保留，请稍候再提交。",
      ),
    ).toBeInTheDocument();
    expect(answer).toHaveValue("保留这份回答");
    expect(apiMock.getSession).toHaveBeenCalledTimes(2);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /提交本轮 1 个回答/ }),
      ).toBeEnabled(),
    );
    expect(screen.queryByText(/页面状态已变化/)).not.toBeInTheDocument();
  });

  it("ignores a late command 409 after navigating to another SOP session", async () => {
    const questionBatch = {
      batch_id: "batch-route-race",
      stage_id: "stage-1",
      questions: [
        {
          question_id: "q-route-race",
          kind: "free_text" as const,
          prompt: "填写范围",
          required: true,
        },
      ],
    };
    apiMock.getSession
      .mockResolvedValueOnce(
        makeSession({
          state: "AwaitingAnswer",
          state_version: 7,
          question_batch: questionBatch,
        }),
      )
      .mockResolvedValueOnce(
        makeSession({
          session_id: "sop-2",
          title: "新会话",
          state: "AwaitingAnswer",
          state_version: 3,
          question_batch: questionBatch,
        }),
      );
    let rejectCommand: ((reason?: unknown) => void) | undefined;
    apiMock.sendCommand.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectCommand = reject;
        }),
    );
    renderPage({ withSessionSwitcher: true });

    fireEvent.change(await screen.findByLabelText("填写范围"), {
      target: { value: "旧会话回答" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交本轮 1 个回答" }));
    await waitFor(() => expect(rejectCommand).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: "切换测试 Session" }));
    expect(
      await screen.findByRole("heading", { name: "新会话" }),
    ).toBeInTheDocument();

    await act(async () => {
      rejectCommand?.(
        Object.assign(new Error("owning Chat is finalizing"), {
          status: 409,
          data: { detail: { code: "owning_chat_finalizing" } },
        }),
      );
    });
    expect(screen.getByRole("heading", { name: "新会话" })).toBeInTheDocument();
    expect(screen.queryByText(/上一轮处理仍在结束中/)).not.toBeInTheDocument();
    expect(apiMock.getSession).toHaveBeenCalledTimes(2);
  });

  it("submits single- and multi-select custom answers as structured values", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "AwaitingAnswer",
        state_version: 7,
        question_batch: {
          batch_id: "batch-custom",
          stage_id: "stage-1",
          questions: [
            {
              question_id: "q-single",
              kind: "single_select",
              prompt: "选择触达渠道",
              required: true,
              options: [
                { option_id: "phone", label: "电话" },
                {
                  option_id: "single-other",
                  label: "其他渠道",
                  requires_custom_input: true,
                },
              ],
            },
            {
              question_id: "q-multi",
              kind: "multi_select",
              prompt: "选择跟进动作",
              required: true,
              options: [
                { option_id: "call", label: "致电" },
                {
                  option_id: "multi-other-1",
                  label: "其他动作一",
                  requires_custom_input: true,
                },
                {
                  option_id: "multi-other-2",
                  label: "其他动作二",
                  requires_custom_input: true,
                },
              ],
            },
          ],
        },
      }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("radio", { name: "其他渠道" }));
    const singleCustomInput = screen.getByLabelText("选择触达渠道 自定义补充");
    expect(singleCustomInput).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "提交本轮 2 个回答" }),
    ).toBeDisabled();
    fireEvent.change(singleCustomInput, { target: { value: "企业微信" } });

    fireEvent.click(screen.getByRole("checkbox", { name: "致电" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "其他动作一" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "其他动作二" }));
    const multiCustomInput = screen.getByLabelText("选择跟进动作 自定义补充");
    expect(multiCustomInput).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "提交本轮 2 个回答" }),
    ).toBeDisabled();
    fireEvent.change(multiCustomInput, { target: { value: "寄送纸质资料" } });

    fireEvent.click(screen.getByRole("button", { name: "提交本轮 2 个回答" }));

    await waitFor(() => expect(apiMock.sendCommand).toHaveBeenCalledTimes(1));
    expect(apiMock.sendCommand.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        command: "submit_answers",
        payload: {
          batch_id: "batch-custom",
          answers: {
            "q-single": {
              selected_option_ids: ["single-other"],
              text: "企业微信",
            },
            "q-multi": {
              selected_option_ids: ["call", "multi-other-1", "multi-other-2"],
              text: "寄送纸质资料",
            },
          },
        },
      }),
    );
  }, 15_000);

  it("hides a custom input after switching to a normal option", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "AwaitingAnswer",
        state_version: 7,
        question_batch: {
          batch_id: "batch-custom-toggle",
          stage_id: "stage-1",
          questions: [
            {
              question_id: "q-single",
              kind: "single_select",
              prompt: "选择触达渠道",
              required: true,
              options: [
                { option_id: "phone", label: "电话" },
                {
                  option_id: "other",
                  label: "其他渠道",
                  requires_custom_input: true,
                },
              ],
            },
          ],
        },
      }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("radio", { name: "其他渠道" }));
    expect(
      screen.getByLabelText("选择触达渠道 自定义补充"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "电话" }));
    expect(
      screen.queryByLabelText("选择触达渠道 自定义补充"),
    ).not.toBeInTheDocument();
  });

  it("navigates back to the receipt Chat after saving and exiting", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "AwaitingAnswer",
        state_version: 7,
        question_batch: {
          batch_id: "batch-1",
          stage_id: "stage-1",
          questions: [],
        },
      }),
    );
    apiMock.sendCommand.mockResolvedValue({
      command_request_id: "save-1",
      accepted: true,
      session: makeSession({
        chat_id: "chat-from-receipt",
        state: "Paused",
        state_version: 8,
      }),
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "保存并退出" }));

    expect(await screen.findByText("所属 Chat")).toBeInTheDocument();
    expect(apiMock.sendCommand).toHaveBeenCalledWith(
      "sop-1",
      expect.objectContaining({ command: "save_and_exit" }),
    );
  });

  it("isolates answer drafts by session and question batch", async () => {
    const firstBatch = makeSession({
      state: "AwaitingAnswer",
      state_version: 7,
      question_batch: {
        batch_id: "batch-1",
        stage_id: "stage-1",
        questions: [
          {
            question_id: "q-shared",
            kind: "free_text",
            prompt: "第一批说明",
            required: true,
          },
        ],
      },
    });
    apiMock.getSession.mockResolvedValue(firstBatch);
    renderPage();

    const firstAnswer = await screen.findByLabelText("第一批说明");
    fireEvent.change(firstAnswer, { target: { value: "只属于第一批" } });
    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));

    const secondBatch = makeSession({
      state: "AwaitingAnswer",
      state_version: 8,
      question_batch: {
        batch_id: "batch-2",
        stage_id: "stage-1",
        questions: [
          {
            question_id: "q-shared",
            kind: "free_text",
            prompt: "第二批说明",
            required: true,
          },
        ],
      },
    });
    act(() => {
      subscriptionCallbacks[0].onEvent({
        event_id: "evt-8",
        session_id: "sop-1",
        state_version: 8,
        kind: "question_batch_presented",
        snapshot: secondBatch,
      });
    });

    expect(await screen.findByLabelText("第二批说明")).toHaveValue("");
    expect(
      screen.getByRole("button", { name: "提交本轮 1 个回答" }),
    ).toBeDisabled();
  });

  it("always exposes feedback after a completed pre-run and starts a real rerun", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "AwaitingTrialFeedback",
        state_version: 10,
        trial: {
          run_id: "run-1",
          status: "completed",
          steps: [
            {
              step_id: "step-1",
              title: "查询到期产品",
              status: "completed",
            },
          ],
          summary: "已完成查询并脱敏。",
          result_rows: [{ product: "稳健理财", due_at: "2026-08-01" }],
        },
      }),
    );
    renderPage();

    const feedback = await screen.findByLabelText("预跑反馈");
    fireEvent.change(feedback, {
      target: { value: "排除缺少任务日期的记录" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交反馈并重新预跑" }));

    await waitFor(() => expect(apiMock.sendCommand).toHaveBeenCalledTimes(1));
    expect(apiMock.sendCommand.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        command: "submit_trial_feedback",
        payload: {
          feedback: "排除缺少任务日期的记录",
          rerun_of_run_id: "run-1",
        },
      }),
    );
  });

  it("preserves a draft and explains a 409 after reloading the snapshot", async () => {
    const feedbackSession = makeSession({
      state: "AwaitingTrialFeedback",
      state_version: 10,
      trial: { run_id: "run-1", status: "completed", steps: [] },
    });
    apiMock.getSession.mockResolvedValue(feedbackSession);
    apiMock.sendCommand.mockRejectedValue(
      Object.assign(new Error("state version conflict"), { status: 409 }),
    );
    renderPage();

    const feedback = await screen.findByLabelText("预跑反馈");
    fireEvent.change(feedback, { target: { value: "保留我的草稿" } });
    fireEvent.click(screen.getByRole("button", { name: "提交反馈并重新预跑" }));

    expect(
      await screen.findByText(/页面状态已变化，已重新同步/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("预跑反馈")).toHaveValue("保留我的草稿");
    expect(apiMock.getSession).toHaveBeenCalledTimes(2);
  });

  it("does not overwrite an edited stage queue when a 409 refreshes it", async () => {
    apiMock.getSession
      .mockResolvedValueOnce(makeSession())
      .mockResolvedValueOnce(
        makeSession({
          state_version: 5,
          stages: [
            {
              stage_id: "stage-1",
              title: "服务端环节名称",
              description: "服务端新投影",
              status: "current",
            },
            {
              stage_id: "stage-2",
              title: "创建后续任务",
              description: "确认任务字段",
              status: "pending",
            },
          ],
        }),
      );
    apiMock.sendCommand.mockRejectedValue(
      Object.assign(new Error("state version conflict"), { status: 409 }),
    );
    renderPage();

    const firstStage = await screen.findByDisplayValue("确认名单范围");
    fireEvent.change(firstStage, { target: { value: "保留本地环节草稿" } });
    fireEvent.click(screen.getByRole("button", { name: "确认这 2 个环节" }));

    expect(
      await screen.findByText(/页面状态已变化，已重新同步/),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("保留本地环节草稿")).toBeInTheDocument();
    expect(
      screen.queryByDisplayValue("服务端环节名称"),
    ).not.toBeInTheDocument();
  });

  it("refreshes the projection and reconnects SSE from the latest version", async () => {
    apiMock.getSession
      .mockResolvedValueOnce(makeSession({ state_version: 4 }))
      .mockResolvedValue(
        makeSession({
          state: "GeneratingQuestions",
          state_version: 5,
        }),
      );
    renderPage();

    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));
    expect(subscriptionCallbacks[0].afterStateVersion).toBe(4);
    await act(async () => {
      subscriptionCallbacks[0].onError(new Error("stream ended"));
    });

    await waitFor(() => expect(apiMock.getSession).toHaveBeenCalledTimes(2));
    await waitFor(
      () => {
        expect(subscriptionCallbacks).toHaveLength(2);
      },
      { timeout: 1_000 },
    );
    expect(subscriptionCallbacks[1].afterStateVersion).toBe(5);
    expect(
      screen.getByText(/已刷新最新状态，正在尝试重新连接/),
    ).toBeInTheDocument();
  });

  it("never lets an older async snapshot roll state_version backward", async () => {
    let resolveRefresh: ((session: WPlusSopSession) => void) | undefined;
    apiMock.getSession
      .mockResolvedValueOnce(makeSession({ state_version: 4 }))
      .mockImplementationOnce(
        () =>
          new Promise<WPlusSopSession>((resolve) => {
            resolveRefresh = resolve;
          }),
      );
    renderPage();
    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));

    act(() => {
      subscriptionCallbacks[0].onEvent({
        event_id: "evt-5",
        session_id: "sop-1",
        state_version: 5,
        kind: "lifecycle_progress",
        snapshot: makeSession({
          state: "GeneratingQuestions",
          state_version: 5,
        }),
      });
    });
    expect(
      await screen.findByRole("heading", { name: "正在生成问题" }),
    ).toBeInTheDocument();

    await act(async () => {
      subscriptionCallbacks[0].onError(new Error("stream ended"));
      resolveRefresh?.(makeSession({ state_version: 4 }));
    });
    expect(
      screen.getByRole("heading", { name: "正在生成问题" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "确认这 2 个环节" }),
    ).not.toBeInTheDocument();
  });

  it("ignores a recovery snapshot after navigating to another SOP session", async () => {
    let resolveOldRecovery: ((session: WPlusSopSession) => void) | undefined;
    apiMock.getSession
      .mockResolvedValueOnce(makeSession({ title: "旧会话" }))
      .mockImplementationOnce(
        () =>
          new Promise<WPlusSopSession>((resolve) => {
            resolveOldRecovery = resolve;
          }),
      )
      .mockResolvedValueOnce(
        makeSession({ session_id: "sop-2", title: "新会话" }),
      );
    renderPage({ withSessionSwitcher: true });

    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));
    act(() => subscriptionCallbacks[0].onError(new Error("stream ended")));
    await waitFor(() => expect(apiMock.getSession).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "切换测试 Session" }));
    expect(
      await screen.findByRole("heading", { name: "新会话" }),
    ).toBeInTheDocument();

    await act(async () => {
      resolveOldRecovery?.(makeSession({ title: "旧会话覆盖" }));
    });
    expect(screen.getByRole("heading", { name: "新会话" })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "旧会话覆盖" }),
    ).not.toBeInTheDocument();
  });

  it("removes old-session controls while the destination session loads", async () => {
    apiMock.getSession
      .mockResolvedValueOnce(
        makeSession({
          state: "AwaitingAnswer",
          state_version: 7,
          question_batch: {
            batch_id: "batch-old-controls",
            stage_id: "stage-1",
            questions: [
              {
                question_id: "q-old-controls",
                kind: "free_text",
                prompt: "旧会话输入",
                required: true,
              },
            ],
          },
        }),
      )
      .mockImplementationOnce(() => new Promise<WPlusSopSession>(() => {}));
    renderPage({ withSessionSwitcher: true });

    fireEvent.change(await screen.findByLabelText("旧会话输入"), {
      target: { value: "完整回答" },
    });
    const oldSubmit = screen.getByRole("button", {
      name: "提交本轮 1 个回答",
    });
    fireEvent.click(screen.getByRole("button", { name: "切换测试 Session" }));

    await waitFor(() =>
      expect(screen.queryByLabelText("旧会话输入")).not.toBeInTheDocument(),
    );
    fireEvent.click(oldSubmit);
    expect(apiMock.sendCommand).not.toHaveBeenCalled();
  });

  it("shows the active run trace without applying it as Session state", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "GeneratingQuestions",
        state_version: 5,
        trial: { run_id: "run-1", status: "planning", steps: [] },
      }),
    );
    renderPage();

    const trigger = await screen.findByRole("button", {
      name: "查看实时返回内容（调试）",
    });
    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));

    emitSafeStreamTrace({
      runId: "run-1",
      sequence: 1,
      summaryText:
        "message role=assistant type=message status=in_progress content_types=text content_chars=8 hidden=true",
      stateVersion: 99,
      truncated: true,
    });
    fireEvent.click(trigger);

    expect(
      await screen.findByText(/content_chars=8 hidden=true/),
    ).toBeInTheDocument();
    expect(apiMock.getSession).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("heading", { name: "正在生成问题" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("较早内容已截断，仅显示最近片段。"),
    ).toBeInTheDocument();

    act(() => {
      subscriptionCallbacks[0].onEvent({
        event_id: "evt-6",
        session_id: "sop-1",
        state_version: 6,
        kind: "question_batch_presented",
        run_id: "run-2",
        snapshot: makeSession({
          state: "GeneratingQuestions",
          state_version: 6,
          trial: { run_id: "run-2", status: "planning", steps: [] },
        }),
      });
    });

    expect(
      screen.queryByText(/content_chars=8 hidden=true/),
    ).not.toBeInTheDocument();
    expect(await screen.findByText("等待返回内容…")).toBeInTheDocument();

    act(() => {
      subscriptionCallbacks[0].onEvent({
        event_id: "evt-7",
        session_id: "sop-1",
        state_version: 7,
        kind: "stage_proposal",
        run_id: "run-2",
        snapshot: makeSession({
          state: "AwaitingQueueConfirmation",
          state_version: 7,
          trial: { run_id: "run-2", status: "completed", steps: [] },
        }),
      });
    });

    expect(
      screen.queryByRole("button", { name: "查看实时返回内容（调试）" }),
    ).not.toBeInTheDocument();
  });

  async function renderGeneratingTracePage() {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "GeneratingTrial",
        state_version: 8,
        trial: { run_id: "run-1", status: "planning", steps: [] },
      }),
    );
    renderPage();
    return screen.findByRole("button", {
      name: "查看实时返回内容（调试）",
    });
  }

  it("opens the safe trace on hover while generating", async () => {
    const trigger = await renderGeneratingTracePage();
    fireEvent.mouseEnter(trigger);

    await waitFor(() =>
      expect(trigger).toHaveAttribute("aria-expanded", "true"),
    );
    const popover = await screen.findByTestId("wplus-debug-stream-popover");
    const title = screen.getByTestId("wplus-debug-stream-title");

    vi.useFakeTimers();
    try {
      fireEvent.mouseLeave(trigger);
      fireEvent.mouseEnter(title);
      act(() => vi.advanceTimersByTime(200));
      expect(trigger).toHaveAttribute("aria-expanded", "true");

      fireEvent.mouseLeave(popover);
      act(() => vi.advanceTimersByTime(200));
      expect(trigger).toHaveAttribute("aria-expanded", "false");
    } finally {
      vi.useRealTimers();
    }
  });

  it("opens the safe trace on keyboard focus while generating", async () => {
    const trigger = await renderGeneratingTracePage();
    fireEvent.focus(trigger);

    await waitFor(() =>
      expect(trigger).toHaveAttribute("aria-expanded", "true"),
    );
    expect(await screen.findByText("等待返回内容…")).toBeInTheDocument();

    vi.useFakeTimers();
    try {
      fireEvent.blur(trigger);
      act(() => vi.advanceTimersByTime(200));
      expect(trigger).toHaveAttribute("aria-expanded", "false");
    } finally {
      vi.useRealTimers();
    }
  });

  it("closes the clicked safe trace with Escape and reopens it", async () => {
    const trigger = await renderGeneratingTracePage();
    fireEvent.click(trigger);
    await waitFor(() =>
      expect(trigger).toHaveAttribute("aria-expanded", "true"),
    );
    expect(
      await screen.findByText(
        /仅展示普通回复文本；思考过程、工具调用、参数、工具输出和非文本内容均已隐藏/,
      ),
    ).toBeInTheDocument();

    vi.useFakeTimers();
    try {
      fireEvent.mouseLeave(trigger);
      fireEvent.blur(trigger);
      act(() => vi.advanceTimersByTime(200));
      expect(trigger).toHaveAttribute("aria-expanded", "true");
    } finally {
      vi.useRealTimers();
    }

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(trigger).toHaveAttribute("aria-expanded", "false"),
    );
    fireEvent.click(trigger);
    await waitFor(() =>
      expect(trigger).toHaveAttribute("aria-expanded", "true"),
    );
  });

  it("ignores descending sequences and late events from an old run", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "GeneratingQuestions",
        state_version: 5,
        trial: { run_id: "run-1", status: "planning", steps: [] },
      }),
    );
    renderPage();

    const trigger = await screen.findByRole("button", {
      name: "查看实时返回内容（调试）",
    });
    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));
    fireEvent.focus(trigger);

    emitSafeStreamTrace({
      runId: "run-1",
      sequence: 2,
      summaryText: "sequence=2",
    });
    expect(await screen.findByText("sequence=2")).toBeInTheDocument();

    emitSafeStreamTrace({
      runId: "run-1",
      sequence: 1,
      summaryText: "sequence=1",
    });
    expect(screen.queryByText("sequence=1")).not.toBeInTheDocument();

    act(() => {
      subscriptionCallbacks[0].onEvent({
        event_id: "evt-6",
        session_id: "sop-1",
        state_version: 6,
        kind: "question_batch_presented",
        run_id: "run-2",
        snapshot: makeSession({
          state: "GeneratingQuestions",
          state_version: 6,
          trial: { run_id: "run-2", status: "planning", steps: [] },
        }),
      });
    });

    expect(screen.queryByText("sequence=2")).not.toBeInTheDocument();
    expect(await screen.findByText("等待返回内容…")).toBeInTheDocument();
    emitSafeStreamTrace({
      runId: "run-1",
      sequence: 3,
      summaryText: "late-old-run",
    });
    expect(screen.queryByText("late-old-run")).not.toBeInTheDocument();
    expect(screen.getByText("等待返回内容…")).toBeInTheDocument();
  });

  it("follows new trace lines only while the viewer stays near the bottom", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "GeneratingTrial",
        state_version: 8,
        trial: { run_id: "run-1", status: "planning", steps: [] },
      }),
    );
    renderPage();
    const trigger = await screen.findByRole("button", {
      name: "查看实时返回内容（调试）",
    });
    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));

    emitSafeStreamTrace({
      runId: "run-1",
      sequence: 1,
      summaryText: "sequence=1",
      stateVersion: 8,
    });
    fireEvent.focus(trigger);
    const trace = await screen.findByTestId("wplus-debug-stream-trace");
    Object.defineProperties(trace, {
      scrollHeight: { configurable: true, value: 500 },
      clientHeight: { configurable: true, value: 100 },
      scrollTop: { configurable: true, writable: true, value: 400 },
    });
    fireEvent.scroll(trace);
    expect(trace.scrollTop).toBe(400);

    trace.scrollTop = 100;
    fireEvent.scroll(trace);
    fireEvent.mouseEnter(trigger);
    emitSafeStreamTrace({
      runId: "run-1",
      sequence: 2,
      summaryText: "sequence=2",
      stateVersion: 8,
    });
    expect(await screen.findByText("sequence=2")).toBeInTheDocument();
    expect(trace.scrollTop).toBe(100);

    trace.scrollTop = 400;
    fireEvent.scroll(trace);
    emitSafeStreamTrace({
      runId: "run-1",
      sequence: 3,
      summaryText: "sequence=3",
      stateVersion: 8,
    });
    await waitFor(() => expect(trace.scrollTop).toBe(500));
  });

  it("clears pinned trace state when the owning Session changes", async () => {
    apiMock.getSession.mockImplementation(async (requestedSessionId) =>
      makeSession({
        session_id: requestedSessionId,
        state: "GeneratingTrial",
        state_version: 8,
        trial: { run_id: "shared-run-id", status: "planning", steps: [] },
      }),
    );
    renderPage({ withSessionSwitcher: true });

    const trigger = await screen.findByRole("button", {
      name: "查看实时返回内容（调试）",
    });
    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));
    emitSafeStreamTrace({
      runId: "shared-run-id",
      sequence: 1,
      summaryText: "old-session-trace",
      stateVersion: 8,
    });
    fireEvent.click(trigger);
    expect(await screen.findByText("old-session-trace")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "切换测试 Session" }));
    await waitFor(() =>
      expect(apiMock.getSession).toHaveBeenLastCalledWith(
        "sop-2",
        expect.any(AbortSignal),
      ),
    );
    const currentTrigger = screen.getByRole("button", {
      name: "查看实时返回内容（调试）",
    });
    await waitFor(() =>
      expect(currentTrigger).toHaveAttribute("aria-expanded", "false"),
    );

    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(2));
    emitSafeStreamTrace({
      runId: "shared-run-id",
      sequence: 2,
      summaryText: "late-old-session-trace",
      stateVersion: 8,
      subscriptionIndex: 0,
    });
    fireEvent.click(currentTrigger);
    await waitFor(() =>
      expect(currentTrigger).toHaveAttribute("aria-expanded", "true"),
    );
    expect(
      screen.queryByText("late-old-session-trace"),
    ).not.toBeInTheDocument();
  });

  it("preserves an edited queue when an SSE version gap reloads the snapshot", async () => {
    apiMock.getSession
      .mockResolvedValueOnce(makeSession({ state_version: 4 }))
      .mockResolvedValueOnce(
        makeSession({
          state_version: 6,
          stages: [
            {
              stage_id: "stage-1",
              title: "服务端覆盖名称",
              description: "新投影",
              status: "current",
            },
            {
              stage_id: "stage-2",
              title: "创建后续任务",
              description: "确认任务字段",
              status: "pending",
            },
          ],
        }),
      );
    renderPage();
    const firstStage = await screen.findByDisplayValue("确认名单范围");
    fireEvent.change(firstStage, { target: { value: "保留 gap 前的草稿" } });
    await waitFor(() => expect(subscriptionCallbacks).toHaveLength(1));

    act(() => {
      subscriptionCallbacks[0].onEvent({
        event_id: "evt-6",
        session_id: "sop-1",
        state_version: 6,
        kind: "stage_queue_confirmed",
        snapshot: null,
      });
    });

    await waitFor(() => expect(apiMock.getSession).toHaveBeenCalledTimes(2));
    expect(screen.getByDisplayValue("保留 gap 前的草稿")).toBeInTheDocument();
    expect(
      screen.queryByDisplayValue("服务端覆盖名称"),
    ).not.toBeInTheDocument();
  });

  it("downloads a completed artifact through the authenticated API", async () => {
    const createObjectURL = vi.fn(() => "blob:wplus-artifact");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "Completed",
        state_version: 20,
        artifacts: [
          {
            artifact_id: "sop_render_md",
            name: "sop_render.md",
            format: "markdown",
            status: "validated",
            download_url: "/wplus-sop/sessions/sop-1/artifacts/sop_render_md",
          },
        ],
      }),
    );
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "sop_render.md" }),
    );
    await waitFor(() =>
      expect(apiMock.downloadArtifact).toHaveBeenCalledWith(
        "sop-1",
        "sop_render_md",
      ),
    );
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:wplus-artifact");
  });

  it("offers explicit controls while a safe exit is pending", async () => {
    apiMock.getSession.mockResolvedValue(
      makeSession({
        state: "PendingExit",
        state_version: 12,
        pending_exit: {
          requested_action: "pause",
          requested_at: "2026-07-29T00:00:00Z",
        },
      }),
    );
    renderPage();

    expect(
      await screen.findByRole("heading", {
        name: "等待当前完整响应落盘",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "保存并退出" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "取消本轮并暂停" }));

    await waitFor(() =>
      expect(apiMock.sendCommand).toHaveBeenCalledWith(
        "sop-1",
        expect.objectContaining({
          command: "cancel_run_and_pause",
          expected_state_version: 12,
        }),
      ),
    );
  });

  it("renders a non-leaking unavailable state for 404", async () => {
    apiMock.getSession.mockRejectedValue(
      Object.assign(new Error("not found"), { status: 404 }),
    );
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "无法访问这个工作台" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("not found")).not.toBeInTheDocument();
  });
});
