import { useEffect, useState } from "react";
import { Button, Flex } from "antd";
import { approvalApi } from "@/api/modules/approval";
import type { ApprovalStatusResponse } from "@/api/types/approval";
import { OperateCard } from "@/components/agentscope-chat";
import { emit } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/useChatAnywhereEventEmitter";
import type { ChatApprovalActionCardData } from "../messageMeta";

const APPROVAL_ACTION_STORAGE_KEY = "copaw_submitted_approval_requests";
const APPROVAL_ACTION_CLOSED_STORAGE_KEY = "copaw_closed_approval_requests";

function loadSubmittedApprovalIds(): Set<string> {
  try {
    const raw = sessionStorage.getItem(APPROVAL_ACTION_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed.filter((item): item is string => typeof item === "string"),
    );
  } catch {
    return new Set();
  }
}

function storeSubmittedApprovalId(requestId: string): void {
  if (!requestId) return;
  const submittedIds = loadSubmittedApprovalIds();
  submittedIds.add(requestId);
  try {
    sessionStorage.setItem(
      APPROVAL_ACTION_STORAGE_KEY,
      JSON.stringify(Array.from(submittedIds)),
    );
  } catch {
    // Ignore storage write failures and keep the in-memory disabled state.
  }
}

function loadClosedApprovalIds(): Set<string> {
  try {
    const raw = sessionStorage.getItem(APPROVAL_ACTION_CLOSED_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed.filter((item): item is string => typeof item === "string"),
    );
  } catch {
    return new Set();
  }
}

function storeClosedApprovalId(requestId: string): void {
  if (!requestId) return;
  const closedIds = loadClosedApprovalIds();
  closedIds.add(requestId);
  try {
    sessionStorage.setItem(
      APPROVAL_ACTION_CLOSED_STORAGE_KEY,
      JSON.stringify(Array.from(closedIds)),
    );
  } catch {
    // Ignore storage write failures and keep the in-memory hidden state.
  }
}

function shouldCloseForStatus(status: ApprovalStatusResponse): boolean {
  const sourceChannel = status.source_channel?.trim();
  if (sourceChannel && sourceChannel !== "console") {
    return true;
  }
  return status.status !== "pending";
}

export default function ApprovalActionCard(props: {
  data: ChatApprovalActionCardData;
  onExternalApprovalResolved?: () => Promise<unknown> | unknown;
}) {
  const { data, onExternalApprovalResolved } = props;
  const [submitted, setSubmitted] = useState(false);
  const [checking, setChecking] = useState(false);
  const [hidden, setHidden] = useState(false);
  const resolvedByBackend = !!data.status && data.status !== "pending";

  useEffect(() => {
    setSubmitted(
      resolvedByBackend || loadSubmittedApprovalIds().has(data.requestId),
    );
    setHidden(loadClosedApprovalIds().has(data.requestId));
  }, [data.requestId, resolvedByBackend]);

  const submitAction = (query: string) => {
    storeSubmittedApprovalId(data.requestId);
    setSubmitted(true);
    emit({
      type: "handleSubmit",
      data: { query, fileList: [] },
    });
  };

  const closeCardAndRefresh = async () => {
    storeSubmittedApprovalId(data.requestId);
    storeClosedApprovalId(data.requestId);
    setSubmitted(true);
    setHidden(true);
    await onExternalApprovalResolved?.();
  };

  const handleAction = async (query: string) => {
    if (submitted || checking || hidden) return;

    setChecking(true);
    try {
      const status = await approvalApi.getApprovalStatus(data.requestId);
      if (shouldCloseForStatus(status)) {
        await closeCardAndRefresh();
        return;
      }
      submitAction(query);
    } catch (error) {
      console.warn("Approval status check failed before submit", error);
      submitAction(query);
    } finally {
      setChecking(false);
    }
  };

  if (hidden) {
    return null;
  }

  return (
    <OperateCard
      header={{
        icon: <span>⏳</span>,
        title: "等待审批",
        description: data.toolName,
      }}
      body={{
        defaultOpen: true,
        children: (
          <OperateCard.LineBody>
            <Flex gap={8} style={{ marginTop: 12 }}>
              <Button
                data-testid="approval-approve"
                type="primary"
                disabled={submitted || checking}
                loading={checking}
                onClick={() => handleAction(data.approveCommand)}
              >
                同意
              </Button>
              <Button
                data-testid="approval-deny"
                disabled={submitted || checking}
                loading={checking}
                onClick={() => handleAction(data.denyCommand)}
              >
                拒绝
              </Button>
            </Flex>
          </OperateCard.LineBody>
        ),
      }}
    />
  );
}
