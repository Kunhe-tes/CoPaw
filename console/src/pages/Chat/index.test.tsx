import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChatPage from "./index";

const mocks = vi.hoisted(() => {
  const setSessionLoading = vi.fn();
  const setSessions = vi.fn();
  const getLoading = vi.fn(() => false);
  const setLoading = vi.fn();

  return {
    capturedOptions: null as Record<string, any> | null,
    createChat: vi.fn(async () => ({
      id: "chat-real-created",
      meta: { plan_mode_enabled: true },
    })),
    listCronJobs: vi.fn(async () => []),
    currentSessionId: "chat-1",
    inputDisabled: true,
    pathname: "/chat/chat-1",
    getChatIdForSession: vi.fn((sessionId: string) => sessionId),
    getLogicalSessionId: vi.fn((sessionId: string) => sessionId),
    getRealIdForSession: vi.fn((sessionId: string) => sessionId),
    navigationSessionId: null as string | null,
    navigationTaskId: null as string | null,
    navigate: vi.fn(),
    sessions: [
      {
        id: "chat-1",
        realId: "chat-1",
        sessionId: "chat-1",
        name: "会话 1",
        messages: [],
        meta: { plan_mode_enabled: true },
      },
    ],
    setLoading,
    getLoading,
    setSessionLoading,
    setSessions,
    updateChat: vi.fn(
      async (_chatId: string, payload: Record<string, any>) => ({
        meta: payload.meta,
      }),
    ),
    updateSession: vi.fn(async () => undefined),
    clearNavigationParams: vi.fn(),
  };
});

vi.mock("@/components/agentscope-chat", () => {
  const React = require("react");

  return {
    AgentScopeRuntimeWebUIComposedProvider: ({
      options,
      children,
    }: {
      options: Record<string, any>;
      children: React.ReactNode;
    }) => {
      mocks.capturedOptions = options;
      return <>{children}</>;
    },
    AgentScopeRuntimeWebUILayout: React.forwardRef(() => (
      <div>
        <div data-testid="chat-welcome">
          {mocks.capturedOptions?.welcome?.render?.({
            greeting: "你好",
            onSubmit: vi.fn(),
          })}
        </div>
        <div data-testid="chat-sender-before-ui">
          {mocks.capturedOptions?.sender?.beforeUI}
        </div>
        <div data-testid="chat-sender-prefix">
          {mocks.capturedOptions?.sender?.prefix}
        </div>
      </div>
    )),
    AgentScopeRuntimeRequestCard: () => null,
    AgentScopeRuntimeResponseCard: () => null,
    Attachments: ({ items }: { items: Array<{ name?: string }> }) => (
      <div>
        {items.map((item) => (
          <span key={item.name}>{item.name}</span>
        ))}
      </div>
    ),
    useChatAnywhereSessionsState: () => ({
      sessions: mocks.sessions,
      setSessionLoading: mocks.setSessionLoading,
      setSessions: mocks.setSessions,
      currentSessionId: mocks.currentSessionId,
    }),
    useChatAnywhereInput: (
      selector: (value: {
        disabled: boolean;
        loading: boolean;
        setLoading: typeof mocks.setLoading;
        getLoading: typeof mocks.getLoading;
      }) => unknown,
    ) =>
      selector({
        disabled: mocks.inputDisabled,
        loading: false,
        setLoading: mocks.setLoading,
        getLoading: mocks.getLoading,
      }),
  };
});

vi.mock("@/components/agentscope-chat/ComposerQuickMenu", () => {
  function ComposerQuickMenu(props: {
    children?: React.ReactNode;
    disabled?: boolean;
    triggerLabel: string;
  }) {
    return (
      <div>
        <button
          type="button"
          aria-label={props.triggerLabel}
          disabled={props.disabled}
        >
          menu
        </button>
        <div>{props.children}</div>
      </div>
    );
  }

  function ComposerQuickMenuItem(props: {
    icon?: React.ReactNode;
    label: React.ReactNode;
    extra?: React.ReactNode;
  }) {
    return (
      <div>
        {props.icon}
        <span>{props.label}</span>
        {props.extra}
      </div>
    );
  }

  return {
    __esModule: true,
    default: ComposerQuickMenu,
    ComposerQuickMenuItem,
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback || _key,
  }),
}));

vi.mock("@agentscope-ai/icons", () => ({
  SparkAttachmentLine: () => <span data-testid="attachment-icon" />,
  SparkCopyLine: () => <span data-testid="copy-icon" />,
}));

vi.mock("react-router-dom", () => ({
  useLocation: () => ({ pathname: mocks.pathname }),
  useNavigate: () => mocks.navigate,
}));

vi.mock("../../hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    },
  }),
}));

vi.mock("../../contexts/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));

vi.mock("../../contexts/BrandThemeContext", () => ({
  useBrandTheme: () => ({
    theme: {
      brandName: "Swe",
      avatar: "",
    },
  }),
}));

vi.mock("../../stores/agentStore", () => ({
  useAgentStore: () => ({
    selectedAgent: null,
  }),
}));

vi.mock("../../stores/sourceSystemConfigStore", () => ({
  useSourceSystemConfigStore: (
    selector: (value: { config: Record<string, unknown> }) => unknown,
  ) => selector({ config: {} }),
}));

vi.mock("../../stores/iframeStore", () => {
  const useIframeStore = (selector?: (value: { userId: string }) => unknown) =>
    selector ? selector({ userId: "test-user" }) : { userId: "test-user" };

  useIframeStore.getState = () => ({
    sessionId: mocks.navigationSessionId,
    taskId: mocks.navigationTaskId,
    clearNavigationParams: mocks.clearNavigationParams,
  });

  return {
    getIframeContext: () => ({ userId: "test-user" }),
    useIframeStore,
  };
});

vi.mock("../../api/modules/chat", () => ({
  chatApi: {
    createChat: mocks.createChat,
    filePreviewUrl: vi.fn((filename: string) => `/preview/${filename}`),
    stopChat: vi.fn(async () => undefined),
    updateChat: mocks.updateChat,
    uploadFile: vi.fn(),
  },
  sessionApi: {},
}));

vi.mock("../../api/modules/cronjob", () => ({
  cronJobApi: {
    listCronJobs: mocks.listCronJobs,
    pauseCronJob: vi.fn(async () => undefined),
    resumeCronJob: vi.fn(async () => undefined),
    runCronJob: vi.fn(async () => undefined),
    deleteCronJob: vi.fn(async () => undefined),
    markTaskRead: vi.fn(async () => undefined),
  },
}));

vi.mock("../../api/modules/feedback", () => ({
  feedbackApi: {
    getSessionFeedbacks: vi.fn(async () => ({ items: [] })),
  },
}));

vi.mock("../../api/modules/provider", () => ({
  providerApi: {
    listProviders: vi.fn(async () => []),
    getActiveModels: vi.fn(async () => []),
  },
}));

vi.mock("../../api/config", () => ({
  getApiUrl: (path: string) => path,
}));

vi.mock("../../api/authHeaders", () => ({
  buildAuthHeaders: () => ({}),
}));

vi.mock("./OptionsPanel/defaultConfig", () => ({
  __esModule: true,
  default: {
    theme: {
      leftHeader: {},
    },
    api: {},
  },
  getDefaultConfig: () => ({
    sender: {},
    welcome: {},
    api: {},
    cards: {},
  }),
}));

vi.mock("./sessionApi", () => ({
  __esModule: true,
  default: {
    preferredChatId: "",
    onSessionCreated: null,
    onSessionIdResolved: null,
    onSessionRemoved: null,
    onSessionSelected: null,
    getChatIdForSession: (sessionId: string) =>
      mocks.getChatIdForSession(sessionId),
    getLogicalSessionId: (sessionId: string) =>
      mocks.getLogicalSessionId(sessionId),
    getRealIdForSession: (sessionId: string) =>
      mocks.getRealIdForSession(sessionId),
    getSessionList: vi.fn(async () => []),
    setLastUserMessage: vi.fn(),
    updateSession: mocks.updateSession,
  },
}));

vi.mock("./components/ChatSidebar", () => {
  function ChatSidebar(props: {
    tasks: Array<{ id: string; name?: string }>;
    selectedTaskId?: string;
    onTaskClick?: (task: { id: string; name?: string }) => void;
  }) {
    return (
      <div
        data-testid="chat-sidebar"
        data-selected-task-id={props.selectedTaskId || ""}
      >
        {props.tasks.map((task) => (
          <button
            key={task.id}
            type="button"
            onClick={() => props.onTaskClick?.(task)}
          >
            {`Open ${task.name || task.id}`}
          </button>
        ))}
      </div>
    );
  }

  return {
    __esModule: true,
    default: ChatSidebar,
  };
});

vi.mock("@/components/agentscope-chat/AutoPreviewHtmlContext", () => ({
  AutoPreviewHtmlProvider: ({
    children,
    triggerKey,
  }: {
    children: React.ReactNode;
    triggerKey: number;
    onConsumed: () => void;
  }) => (
    <div data-testid="auto-preview-provider" data-trigger-key={triggerKey}>
      {children}
    </div>
  ),
  useAutoPreviewHtml: () => ({
    enabled: false,
    register: () => () => undefined,
  }),
}));

vi.mock("@/components/agentscope-chat/HtmlPreviewTrackingContext", () => ({
  HtmlPreviewTrackingProvider: ({
    children,
    value,
  }: {
    children: React.ReactNode;
    value: { cronTaskId?: string | null; cronTaskName?: string | null };
  }) => (
    <div
      data-testid="html-preview-tracking-provider"
      data-cron-task-id={value.cronTaskId || ""}
      data-cron-task-name={value.cronTaskName || ""}
    >
      {children}
    </div>
  ),
  useHtmlPreviewTracking: () => ({}),
}));

vi.mock("./components/ChatHeaderTitle", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("./components/ChatSessionInitializer", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("./ModelSelector", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("@/components/ConversationQuickNav", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("@/components/agentscope-chat/DragUploadOverlay", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("./components/GeneratedFilesDrawer", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("./components/TaskProgressFloatingCard", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("./components/RuntimeRequestCard", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("./components/RuntimeResponseCard", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("./components/ApprovalActionCard", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("./components/PlanInteractionCards", () => ({
  ActivePlanReviewCard: (props: {
    onContinueModifying?: (data: Record<string, any>) => void;
    onPlanModeDecision?: (enabled: boolean) => void;
  }) => (
    <div data-testid="active-plan-review-card">
      <button
        type="button"
        onClick={() =>
          props.onContinueModifying?.({
            card_type: "plan_review",
            plan_id: "plan-123",
            title: "Implementation plan",
            summary: "Plan summary",
            steps: [],
            risks: [],
            verification: [],
          })
        }
      >
        Continue modifying
      </button>
      <button type="button" onClick={() => props.onPlanModeDecision?.(false)}>
        Exit Plan Mode
      </button>
    </div>
  ),
  ActivePlanClarificationCard: () => null,
  PlanClarificationCard: () => null,
  PlanReviewCard: () => null,
}));

vi.mock("./components/TaskRunGroupCard", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock(
  "@/components/agentscope-chat/AgentScopeRuntimeWebUI/customToolRenders/CopyFileToStatic",
  () => ({
    __esModule: true,
    default: () => null,
  }),
);

vi.mock("./components/ResponseFeedbackCard/whitelist", () => ({
  isResponseFeedbackUserAllowed: () => false,
}));

vi.mock("@/components/agentscope-chat/FeaturedCases", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("@/components/agentscope-chat/CaseDetailDrawer", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("@/api/modules/featuredCases", () => ({
  featuredCasesApi: {
    getCaseDetail: vi.fn(),
  },
}));

describe("ChatPage plan mode wiring", () => {
  beforeEach(() => {
    mocks.capturedOptions = null;
    mocks.inputDisabled = true;
    mocks.pathname = "/chat/chat-1";
    mocks.currentSessionId = "chat-1";
    mocks.getChatIdForSession.mockImplementation(
      (sessionId: string) => sessionId,
    );
    mocks.getLogicalSessionId.mockImplementation(
      (sessionId: string) => sessionId,
    );
    mocks.getRealIdForSession.mockImplementation(
      (sessionId: string) => sessionId,
    );
    mocks.sessions = [
      {
        id: "chat-1",
        realId: "chat-1",
        sessionId: "chat-1",
        name: "会话 1",
        messages: [],
        meta: { plan_mode_enabled: true },
      },
    ];
    mocks.navigationSessionId = null;
    mocks.navigationTaskId = null;
    mocks.navigate.mockReset();
    mocks.createChat.mockClear();
    mocks.listCronJobs.mockReset();
    mocks.listCronJobs.mockResolvedValue([]);
    mocks.setLoading.mockReset();
    mocks.getLoading.mockReset();
    mocks.getLoading.mockReturnValue(false);
    mocks.setSessionLoading.mockReset();
    mocks.setSessions.mockReset();
    mocks.updateChat.mockClear();
    mocks.updateSession.mockClear();
    mocks.clearNavigationParams.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("disables active Plan Mode buttons when the composer is disabled", async () => {
    render(<ChatPage />);

    const buttons = screen.getAllByRole("button", { name: "计划模式" });

    expect(buttons).toHaveLength(2);
    buttons.forEach((button) => {
      expect(button).toBeDisabled();
    });

    fireEvent.click(buttons[0]);
    await Promise.resolve();

    expect(mocks.updateChat).not.toHaveBeenCalled();
  });

  it("disables the quick menu Plan Mode switch when the composer is disabled", () => {
    render(<ChatPage />);

    expect(screen.getByRole("switch", { name: "计划模式" })).toBeDisabled();
  });

  it("creates a backend chat before persisting Plan Mode for a pending local session", async () => {
    mocks.inputDisabled = false;
    mocks.pathname = "/chat/1780458341751000";
    mocks.currentSessionId = "1780458341751000";
    mocks.getChatIdForSession.mockImplementation(() => null);
    mocks.getRealIdForSession.mockImplementation(() => null);
    mocks.sessions = [
      {
        id: "1780458341751000",
        realId: "",
        sessionId: "1780458341751000",
        name: "新会话",
        messages: [],
        meta: { plan_mode_enabled: false },
      },
    ];
    mocks.updateChat.mockResolvedValueOnce({
      meta: { plan_mode_enabled: true },
    });

    render(<ChatPage />);

    fireEvent.click(screen.getByRole("switch", { name: "计划模式" }));

    await waitFor(() => {
      expect(mocks.createChat).toHaveBeenCalledTimes(1);
    });

    expect(mocks.createChat).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: "1780458341751000",
        name: "新会话",
      }),
    );
    expect(mocks.updateChat).toHaveBeenCalledWith("chat-real-created", {
      meta: { plan_mode_enabled: true },
    });
  });

  it("renders the active plan review card in the sender before UI", () => {
    render(<ChatPage />);

    expect(screen.getByTestId("active-plan-review-card")).toBeInTheDocument();
  });

  it("defers Continue modifying and sends the next submission as plan revision feedback", async () => {
    render(<ChatPage />);

    fireEvent.click(screen.getByRole("button", { name: "Continue modifying" }));

    await waitFor(() => {
      expect(mocks.capturedOptions?.sender?.beforeSubmit).toBeDefined();
    });

    const result = await mocks.capturedOptions?.sender?.beforeSubmit({
      query: "Narrow the implementation scope",
      fileList: [],
      biz_params: {},
    });

    expect(result).toMatchObject({
      query: "Narrow the implementation scope",
      biz_params: {
        mode: "plan",
        plan_interaction_response: {
          card_type: "plan_review",
          plan_id: "plan-123",
          decision: "revise",
          feedback: "Narrow the implementation scope",
        },
      },
    });
  });

  it("preserves an explicit plan interaction response after Continue modifying and clears the pending revision", async () => {
    render(<ChatPage />);

    fireEvent.click(screen.getByRole("button", { name: "Continue modifying" }));

    await waitFor(() => {
      expect(mocks.capturedOptions?.sender?.beforeSubmit).toBeDefined();
    });

    const explicitResponse = {
      card_type: "plan_review",
      plan_id: "plan-123",
      decision: "execute",
    };
    const explicitResult = await mocks.capturedOptions?.sender?.beforeSubmit({
      query: "Execute plan plan-123",
      fileList: [],
      biz_params: {
        mode: "normal",
        plan_interaction_response: explicitResponse,
      },
    });

    expect(explicitResult).toMatchObject({
      query: "Execute plan plan-123",
      biz_params: {
        mode: "normal",
        plan_interaction_response: explicitResponse,
      },
    });

    const ordinaryResult = await mocks.capturedOptions?.sender?.beforeSubmit({
      query: "Ordinary follow up",
      fileList: [],
      biz_params: {},
    });

    expect(ordinaryResult).toMatchObject({
      query: "Ordinary follow up",
      biz_params: {
        mode: "plan",
      },
    });
    expect(
      ordinaryResult?.biz_params?.plan_interaction_response,
    ).toBeUndefined();
  });

  it("clears pending revision when Exit Plan Mode is clicked after Continue modifying", async () => {
    render(<ChatPage />);

    fireEvent.click(screen.getByRole("button", { name: "Continue modifying" }));
    fireEvent.click(screen.getByRole("button", { name: "Exit Plan Mode" }));

    await waitFor(() => {
      expect(mocks.updateChat).toHaveBeenCalledWith("chat-1", {
        meta: { plan_mode_enabled: false },
      });
    });

    const result = await mocks.capturedOptions?.sender?.beforeSubmit({
      query: "Ordinary follow up",
      fileList: [],
      biz_params: {},
    });

    expect(result).toMatchObject({
      query: "Ordinary follow up",
    });
    expect(result?.biz_params?.plan_interaction_response).toBeUndefined();
  });

  it("clears pending revision when the active Plan Mode control is disabled after Continue modifying", async () => {
    mocks.inputDisabled = false;
    render(<ChatPage />);

    fireEvent.click(screen.getByRole("button", { name: "Continue modifying" }));
    fireEvent.click(screen.getAllByRole("button", { name: "计划模式" })[0]);

    await waitFor(() => {
      expect(mocks.updateChat).toHaveBeenCalledWith("chat-1", {
        meta: { plan_mode_enabled: false },
      });
    });

    const result = await mocks.capturedOptions?.sender?.beforeSubmit({
      query: "Ordinary follow up",
      fileList: [],
      biz_params: {},
    });

    expect(result).toMatchObject({
      query: "Ordinary follow up",
    });
    expect(result?.biz_params?.plan_interaction_response).toBeUndefined();
  });

  it("does not clear or replace composer input when Continue modifying is clicked", () => {
    const setContentHandler = vi.fn();
    document.addEventListener(
      "agentscope-runtime:set-input-content",
      setContentHandler,
    );

    try {
      render(<ChatPage />);

      fireEvent.click(
        screen.getByRole("button", { name: "Continue modifying" }),
      );

      expect(setContentHandler).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener(
        "agentscope-runtime:set-input-content",
        setContentHandler,
      );
    }
  });

  it("blocks an empty submission after Continue modifying", async () => {
    render(<ChatPage />);

    fireEvent.click(screen.getByRole("button", { name: "Continue modifying" }));

    const result = await mocks.capturedOptions?.sender?.beforeSubmit({
      query: "   ",
      fileList: [],
      biz_params: {},
    });

    expect(result).toBe(false);
  });

  it("passes a Plan Mode decision callback that can close local Plan Mode state", async () => {
    render(<ChatPage />);

    fireEvent.click(screen.getByRole("button", { name: "Exit Plan Mode" }));

    await waitFor(() => {
      expect(mocks.updateChat).toHaveBeenCalledWith("chat-1", {
        meta: { plan_mode_enabled: false },
      });
    });
  });

  it("triggers HTML auto preview when taskId navigation resolves to a chat", async () => {
    mocks.navigationTaskId = "task-from-url";
    mocks.listCronJobs.mockResolvedValue([
      {
        id: "task-from-url",
        name: "URL Task",
        enabled: true,
        schedule: { type: "cron", cron: "* * * * *" },
        dispatch: {
          type: "channel",
          target: { user_id: "test-user", session_id: "chat-2" },
        },
        task: {
          visible_in_my_tasks: true,
          chat_id: "chat-2",
          has_scheduled_result: true,
          latest_scheduled_preview: "",
          unread_execution_count: 0,
          is_running: false,
        },
      },
    ]);

    render(<ChatPage />);

    await screen.findByRole("button", { name: "Open URL Task" });

    expect(mocks.clearNavigationParams).toHaveBeenCalled();
    await waitFor(() => {
      expect(mocks.navigate).toHaveBeenCalledWith("/chat/chat-2", {
        replace: true,
      });
    });
    expect(screen.getByTestId("auto-preview-provider")).toHaveAttribute(
      "data-trigger-key",
      "1",
    );
  });

  it("wires task tracking context and triggers auto preview from sidebar task open", async () => {
    mocks.listCronJobs.mockResolvedValue([
      {
        id: "task-current",
        name: "Current Task",
        enabled: true,
        schedule: { type: "cron", cron: "* * * * *" },
        dispatch: {
          type: "channel",
          target: { user_id: "test-user", session_id: "chat-1" },
        },
        task: {
          visible_in_my_tasks: true,
          chat_id: "chat-1",
          has_scheduled_result: true,
          latest_scheduled_preview: "",
          unread_execution_count: 0,
          is_running: false,
        },
      },
      {
        id: "task-other",
        name: "Other Task",
        enabled: true,
        schedule: { type: "cron", cron: "* * * * *" },
        dispatch: {
          type: "channel",
          target: { user_id: "test-user", session_id: "chat-2" },
        },
        task: {
          visible_in_my_tasks: true,
          chat_id: "chat-2",
          has_scheduled_result: true,
          latest_scheduled_preview: "",
          unread_execution_count: 0,
          is_running: false,
        },
      },
    ]);

    render(<ChatPage />);

    await waitFor(() => {
      expect(
        screen.getByTestId("html-preview-tracking-provider"),
      ).toHaveAttribute("data-cron-task-id", "task-current");
    });
    expect(
      screen.getByTestId("html-preview-tracking-provider"),
    ).toHaveAttribute("data-cron-task-name", "Current Task");

    fireEvent.click(screen.getByRole("button", { name: "Open Other Task" }));

    expect(mocks.setSessionLoading).toHaveBeenCalledWith(true);
    expect(mocks.navigate).toHaveBeenCalledWith("/chat/chat-2", {
      replace: true,
    });
    expect(screen.getByTestId("auto-preview-provider")).toHaveAttribute(
      "data-trigger-key",
      "1",
    );
  });
});
