import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ApprovalActionCard from "./ApprovalActionCard";
import type { ChatApprovalActionCardData } from "../messageMeta";

const mocks = vi.hoisted(() => ({
  emit: vi.fn(),
  getApprovalStatus: vi.fn(),
}));

vi.mock("@/api/modules/approval", () => ({
  approvalApi: {
    getApprovalStatus: mocks.getApprovalStatus,
  },
}));

vi.mock(
  "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/useChatAnywhereEventEmitter",
  () => ({
    emit: mocks.emit,
  }),
);

vi.mock("@/components/agentscope-chat", () => {
  type MockOperateCard = ((props: {
    body: { children: ReactNode };
  }) => ReactNode) & {
    LineBody: (props: { children: ReactNode }) => ReactNode;
  };
  const OperateCard = (({ body }: { body: { children: ReactNode } }) => (
    <div data-testid="operate-card">{body.children}</div>
  )) as MockOperateCard;
  OperateCard.LineBody = ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  );
  return { OperateCard };
});

const data: ChatApprovalActionCardData = {
  requestId: "approval-1",
  toolName: "execute_shell_command",
  toolInput: {},
  triggerLabel: "Tool approval",
  approveCommand: "/approve approval-1",
  denyCommand: "/deny approval-1",
  status: "pending",
};

describe("ApprovalActionCard", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("closes and refreshes when zhaohu has already submitted the approval", async () => {
    const onExternalApprovalResolved = vi.fn();
    mocks.getApprovalStatus.mockResolvedValue({
      request_id: "approval-1",
      status: "submitted",
      source_channel: "zhaohu",
    });

    render(
      <ApprovalActionCard
        data={data}
        onExternalApprovalResolved={onExternalApprovalResolved}
      />,
    );

    fireEvent.click(screen.getByTestId("approval-approve"));

    await waitFor(() => {
      expect(onExternalApprovalResolved).toHaveBeenCalledTimes(1);
    });
    expect(mocks.emit).not.toHaveBeenCalled();
    expect(screen.queryByTestId("approval-approve")).not.toBeInTheDocument();
  });

  it("submits the console command when the approval is still pending", async () => {
    mocks.getApprovalStatus.mockResolvedValue({
      request_id: "approval-1",
      status: "pending",
    });

    render(<ApprovalActionCard data={data} />);

    fireEvent.click(screen.getByTestId("approval-approve"));

    await waitFor(() => {
      expect(mocks.emit).toHaveBeenCalledWith({
        type: "handleSubmit",
        data: { query: "/approve approval-1", fileList: [] },
      });
    });
  });
});
