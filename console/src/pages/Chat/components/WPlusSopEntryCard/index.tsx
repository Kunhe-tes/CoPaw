import { Alert, Button, Space, Tag } from "antd";
import { ArrowRight, ListChecks, MessagesSquare } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { wplusSopApi } from "@/api/modules/wplusSop";
import type { WPlusSopEntryProposal } from "@/api/types/wplusSop";
import { createCommandRequestId } from "@/pages/WPlusSopWorkspace/sessionView";
import { WPLUS_SOP_REPLAY_EVENT } from "../../wplusSopEntryEvents";
import styles from "./index.module.less";

export default function WPlusSopEntryCard({
  data,
}: {
  data: WPlusSopEntryProposal;
}) {
  const navigate = useNavigate();
  const [busyAction, setBusyAction] = useState<"confirm" | "reject" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [rejected, setRejected] = useState(false);
  const requestIdsRef = useRef<Partial<Record<"confirm" | "reject", string>>>(
    {},
  );

  const requestIdFor = (action: "confirm" | "reject") => {
    const existing = requestIdsRef.current[action];
    if (existing) return existing;
    const created = createCommandRequestId();
    requestIdsRef.current[action] = created;
    return created;
  };

  const confirm = async () => {
    setBusyAction("confirm");
    setError(null);
    try {
      const receipt = await wplusSopApi.confirmEntry(
        data.proposal_id,
        requestIdFor("confirm"),
      );
      navigate(`/wplus-sop/${receipt.session.session_id}?from=chat`);
    } catch {
      setError("工作台没有成功创建，请稍后重试。");
    } finally {
      setBusyAction(null);
    }
  };

  const reject = async () => {
    setBusyAction("reject");
    setError(null);
    try {
      const receipt = await wplusSopApi.rejectEntry(
        data.proposal_id,
        requestIdFor("reject"),
      );
      setRejected(true);
      document.dispatchEvent(
        new CustomEvent(WPLUS_SOP_REPLAY_EVENT, {
          detail: {
            query: receipt.original_request.text || "",
            proposal_id: receipt.proposal_id,
            suppression_token: receipt.suppression_token,
          },
        }),
      );
    } catch {
      setError("无法继续原 Chat 请求，请重新发送一次。");
    } finally {
      setBusyAction(null);
    }
  };

  if (rejected) {
    return (
      <article className={styles.card} data-status="rejected">
        <div className={styles.icon}>
          <MessagesSquare size={20} />
        </div>
        <div>
          <strong>已留在当前 Chat</strong>
          <p>原请求已继续处理，本次不会再次触发 W+ 入口。</p>
        </div>
      </article>
    );
  }

  return (
    <article className={styles.card}>
      <div className={styles.cardHeader}>
        <div className={styles.icon}>
          <ListChecks size={20} />
        </div>
        <div>
          <div className={styles.titleLine}>
            <strong>{data.title}</strong>
            <Tag color={data.mode === "explicit" ? "cyan" : "default"}>
              {data.mode === "explicit" ? "已选择 W+" : "智能识别"}
            </Tag>
          </div>
          <p>{data.message}</p>
        </div>
      </div>
      <div className={styles.flow}>
        <span>确认 2–4 个环节</span>
        <ArrowRight size={14} />
        <span>逐环节澄清</span>
        <ArrowRight size={14} />
        <span>系统预跑与反馈</span>
      </div>
      {error && (
        <Alert className={styles.alert} type="error" showIcon message={error} />
      )}
      <Space className={styles.actions}>
        <Button
          loading={busyAction === "reject"}
          disabled={busyAction === "confirm"}
          onClick={() => void reject()}
        >
          留在 Chat
        </Button>
        <Button
          type="primary"
          loading={busyAction === "confirm"}
          disabled={busyAction === "reject"}
          onClick={() => void confirm()}
        >
          进入工作台
        </Button>
      </Space>
    </article>
  );
}
