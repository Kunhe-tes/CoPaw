import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChatPage from "./index";

const mocks = vi.hoisted(() => {
  const setSessionLoading = vi.fn();
  const setSessions = vi.fn();
  const getLoading = vi.fn(() => false);
  const setLoading = vi.fn();

  return {
    capturedOptions: null as Record<string, any> | null,
    currentSessionId: "chat-1",
    inputDisabled: true,
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
    updateChat: vi.fn(async (_chatId: string, payload: Record<string, any>) => ({
      meta: payload.meta,
    })),
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
      selector: (
        value: {
          disabled: boolean;
          loading: boolean;
          setLoading: typeof mocks.setLoading;
          getLoading: typeof mocks.getLoading;
        },
      ) => unknown,
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
  useLocation: () => ({ pathname: "/chat/chat-1" }),
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
    sessionId: null,
    taskId: null,
    clearNavigationParams: mocks.clearNavigationParams,
  });

  return { useIframeStore };
});

vi.mock("../../api/modules/chat", () => ({
  chatApi: {
    createChat: vi.fn(),
    filePreviewUrl: vi.fn((filename: string) => `/preview/${filename}`),
    stopChat: vi.fn(async () => undefined),
    updateChat: mocks.updateChat,
    uploadFile: vi.fn(),
  },
}));

vi.mock("../../api/modules/cronjob", () => ({
  cronJobApi: {
    listCronJobs: vi.fn(async () => []),
    pauseCronJob: vi.fn(async () => undefined),
    resumeCronJob: vi.fn(async () => undefined),
    runCronJob: vi.fn(async () => undefined),
    deleteCronJob: vi.fn(async () => undefined),
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
    getChatIdForSession: (sessionId: string) => sessionId,
    getLogicalSessionId: (sessionId: string) => sessionId,
    getRealIdForSession: (sessionId: string) => sessionId,
    getSessionList: vi.fn(async () => []),
    setLastUserMessage: vi.fn(),
    updateSession: mocks.updateSession,
  },
}));

vi.mock("./components/ChatSidebar", () => ({
  __esModule: true,
  default: () => null,
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
  PlanClarificationCard: () => null,
  PlanReviewCard: () => null,
}));

vi.mock("./components/TaskRunGroupCard", () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock("@/components/agentscope-chat/AgentScopeRuntimeWebUI/customToolRenders/CopyFileToStatic", () => ({
  __esModule: true,
  default: () => null,
}));

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
    mocks.navigate.mockReset();
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
});
