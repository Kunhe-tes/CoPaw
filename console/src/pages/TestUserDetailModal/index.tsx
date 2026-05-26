import { useMemo, useState } from "react";
import { Button, Modal, Tag } from "antd";
import { User } from "lucide-react";
import type { Message } from "../../api/types";
import type {
  SessionListItem,
  SessionStats,
  UserStats,
} from "../../api/modules/tracing";
import UserStatsHeader from "../Analytics/BusinessOverview/components/UserDetailModal/UserStatsHeader";
import SessionCardList from "../Analytics/BusinessOverview/components/UserDetailModal/SessionCardList";
import ReadOnlySessionChat from "../Analytics/BusinessOverview/components/UserDetailModal/ReadOnlySessionChat";
import modalStyles from "../Analytics/BusinessOverview/components/UserDetailModal/index.module.less";
import styles from "./index.module.less";

const MOCK_USER_ID = "mock-user-001";

const mockUserStats: UserStats = {
  user_id: MOCK_USER_ID,
  total_tokens: 68320,
  input_tokens: 24180,
  output_tokens: 44140,
  total_sessions: 2,
  total_conversations: 7,
  avg_duration_ms: 4680,
  model_usage: [
    {
      model_name: "gpt-5.4",
      count: 5,
      total_tokens: 52300,
      input_tokens: 18400,
      output_tokens: 33900,
    },
    {
      model_name: "gpt-5.3-codex",
      count: 2,
      total_tokens: 16020,
      input_tokens: 5780,
      output_tokens: 10240,
    },
  ],
  tools_used: [],
  skills_used: [
    { skill_name: "knowledge-search", count: 3, avg_duration_ms: 860 },
    { skill_name: "report-summary", count: 2, avg_duration_ms: 1240 },
  ],
  mcp_tools_used: [
    {
      tool_name: "query_customer_profile",
      mcp_server: "crm",
      count: 2,
      avg_duration_ms: 520,
      error_count: 0,
    },
  ],
};

const mockSessions: SessionListItem[] = [
  {
    session_id: "mock-session-risk-review",
    session_name: "授信风险复核",
    user_id: MOCK_USER_ID,
    user_name: "张晓晨",
    bbk_id: "755",
    channel: "console",
    total_traces: 4,
    total_tokens: 42120,
    total_skills: 3,
    first_active: "2026-05-15T09:12:00+08:00",
    last_active: "2026-05-15T09:36:00+08:00",
  },
  {
    session_id: "mock-session-weekly-ops",
    session_name: "周经营简报",
    user_id: MOCK_USER_ID,
    user_name: "张晓晨",
    bbk_id: "755",
    channel: "console",
    total_traces: 3,
    total_tokens: 26200,
    total_skills: 2,
    first_active: "2026-05-14T17:20:00+08:00",
    last_active: "2026-05-14T17:48:00+08:00",
  },
];

const mockSessionStats: Record<string, SessionStats> = {
  "mock-session-risk-review": {
    session_id: "mock-session-risk-review",
    user_id: MOCK_USER_ID,
    channel: "console",
    total_tokens: 42120,
    input_tokens: 14800,
    output_tokens: 27320,
    total_traces: 4,
    avg_duration_ms: 5120,
    first_active: "2026-05-15T09:12:00+08:00",
    last_active: "2026-05-15T09:36:00+08:00",
    model_usage: [
      {
        model_name: "gpt-5.4",
        count: 4,
        total_tokens: 42120,
        input_tokens: 14800,
        output_tokens: 27320,
      },
    ],
    tools_used: [],
    skills_used: [
      { skill_name: "risk-policy-check", count: 2, avg_duration_ms: 980 },
      { skill_name: "customer-profile", count: 1, avg_duration_ms: 640 },
    ],
    mcp_tools_used: [
      {
        tool_name: "query_customer_profile",
        mcp_server: "crm",
        count: 1,
        avg_duration_ms: 510,
        error_count: 0,
      },
    ],
  },
  "mock-session-weekly-ops": {
    session_id: "mock-session-weekly-ops",
    user_id: MOCK_USER_ID,
    channel: "console",
    total_tokens: 26200,
    input_tokens: 9380,
    output_tokens: 16820,
    total_traces: 3,
    avg_duration_ms: 3820,
    first_active: "2026-05-14T17:20:00+08:00",
    last_active: "2026-05-14T17:48:00+08:00",
    model_usage: [
      {
        model_name: "gpt-5.3-codex",
        count: 3,
        total_tokens: 26200,
        input_tokens: 9380,
        output_tokens: 16820,
      },
    ],
    tools_used: [],
    skills_used: [
      { skill_name: "report-summary", count: 2, avg_duration_ms: 1180 },
    ],
    mcp_tools_used: [],
  },
};

function text(text: string) {
  return [{ type: "text", text, status: "completed" }];
}

const mockMessagesBySession: Record<string, Message[]> = {
  "mock-session-risk-review": [
    {
      id: "risk-user-1",
      role: "user",
      object: "message",
      type: "message",
      timestamp: "2026-05-15T09:12:00+08:00",
      content: text("帮我看一下客户 A 的授信申请，重点关注最近三个月流水和历史逾期。"),
    },
    {
      id: "risk-assistant-1",
      role: "assistant",
      object: "message",
      type: "message",
      status: "completed",
      timestamp: "2026-05-15T09:12:08+08:00",
      content: text(
        "已读取客户资料。初步结论：\n\n- 最近三个月流水稳定，月均入账约 **48.6 万**。\n- 历史逾期有 1 次，发生在 2025 年 11 月，已结清。\n- 当前负债率约 **38%**，低于预警阈值。\n\n建议进入人工复核，并补充经营场地租赁合同。",
      ),
    },
    {
      id: "risk-user-2",
      role: "user",
      object: "message",
      type: "message",
      timestamp: "2026-05-15T09:18:30+08:00",
      content: text("把风险点和需要补充的材料整理成给客户经理看的话术。"),
    },
    {
      id: "risk-assistant-2",
      role: "assistant",
      object: "message",
      type: "message",
      status: "completed",
      timestamp: "2026-05-15T09:18:39+08:00",
      content: text(
        "可以这样说明：\n\n> 客户整体经营流水较稳定，现有负债水平可控。本次授信主要需要确认两项信息：一是历史逾期的实际原因，二是经营场地稳定性。\n\n补充材料：\n1. 经营场地租赁合同或产权证明\n2. 近 6 个月主要上下游合同\n3. 历史逾期结清证明",
      ),
    },
  ],
  "mock-session-weekly-ops": [
    {
      id: "ops-user-1",
      role: "user",
      object: "message",
      type: "message",
      timestamp: "2026-05-14T17:20:00+08:00",
      content: text("生成本周经营简报，突出调用量、活跃用户和高频技能。"),
    },
    {
      id: "ops-assistant-1",
      role: "assistant",
      object: "message",
      type: "message",
      status: "completed",
      timestamp: "2026-05-14T17:20:11+08:00",
      content: text(
        "本周经营简报：\n\n| 指标 | 数值 | 环比 |\n| --- | ---: | ---: |\n| 调用量 | 12,840 | +18.6% |\n| 活跃用户 | 426 | +9.3% |\n| 总 Token | 8.7M | +21.4% |\n\n高频技能集中在资料摘要、客户画像查询和风险政策校验。",
      ),
    },
    {
      id: "ops-user-2",
      role: "user",
      object: "message",
      type: "message",
      timestamp: "2026-05-14T17:43:00+08:00",
      content: text("再压缩成三句话，适合放在运营看板顶部。"),
    },
    {
      id: "ops-assistant-2",
      role: "assistant",
      object: "message",
      type: "message",
      status: "completed",
      timestamp: "2026-05-14T17:43:07+08:00",
      content: text(
        "本周调用量继续走高，活跃用户和 Token 消耗同步增长。高频需求主要集中在经营分析、客户画像和风险复核。建议下周重点观察高频技能耗时，优先优化客户画像查询链路。",
      ),
    },
  ],
};

export default function TestUserDetailModalPage() {
  const [open, setOpen] = useState(true);
  const [statsCollapsed, setStatsCollapsed] = useState(false);
  const [sessionsCollapsed, setSessionsCollapsed] = useState(false);
  const [selectedSessionId, setSelectedSessionId] = useState(
    mockSessions[0].session_id,
  );

  const selectedSessionStats = mockSessionStats[selectedSessionId] || null;
  const selectedMessages = useMemo(
    () => mockMessagesBySession[selectedSessionId] || [],
    [selectedSessionId],
  );

  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <div className={styles.toolbar}>
          <div>
            <h1 className={styles.title}>用户详情弹窗 Mock 预览</h1>
            <p className={styles.subtitle}>
              这里用静态数据模拟“调用数排行榜”点击后的用户详情，右侧是只读聊天组件效果。
            </p>
          </div>
          <Button type="primary" onClick={() => setOpen(true)}>
            打开用户详情
          </Button>
        </div>

        <div className={styles.rankingCard}>
          <div className={styles.rankingTitle}>调用数排行榜</div>
          <div className={styles.rankingRow} onClick={() => setOpen(true)}>
            <span className={styles.rank}>1</span>
            <span className={styles.name}>深圳分行/张晓晨({MOCK_USER_ID})</span>
            <span className={styles.value}>7 次调用</span>
          </div>
        </div>
      </div>

      <Modal
        title={
          <div className={modalStyles.modalTitleBlock}>
            <span className={modalStyles.modalTitleIcon}>
              <User size={18} />
            </span>
            <div className={modalStyles.modalTitleText}>
              <div className={modalStyles.modalTitle}>
                用户详情 <Tag color="purple">Mock</Tag>
              </div>
              <div className={modalStyles.modalSubtitle}>
                调用排行 · 运营看板 · 只读审计视图
              </div>
            </div>
          </div>
        }
        open={open}
        onCancel={() => setOpen(false)}
        width="100vw"
        footer={null}
        destroyOnClose={false}
        className={modalStyles.userDetailModal}
        classNames={{ body: modalStyles.userDetailModalBody }}
        style={{ top: 0, paddingBottom: 0 }}
      >
        <div className={modalStyles.modalContent}>
          <div className={modalStyles.topSection}>
            <UserStatsHeader
              userStats={mockUserStats}
              sessionStats={selectedSessionStats}
              collapsed={statsCollapsed}
              onToggleCollapsed={() => setStatsCollapsed((value) => !value)}
            />
          </div>

          <div className={modalStyles.bottomSection}>
            <div
              className={`${modalStyles.leftPanel} ${
                sessionsCollapsed ? modalStyles.leftPanelCollapsed : ""
              }`}
            >
              <SessionCardList
                sessions={mockSessions}
                total={mockSessions.length}
                page={1}
                pageSize={10}
                loading={false}
                selectedSessionId={selectedSessionId}
                collapsed={sessionsCollapsed}
                onSelect={(sessionId) => setSelectedSessionId(sessionId)}
                onPageChange={() => undefined}
                onToggleCollapsed={() =>
                  setSessionsCollapsed((value) => !value)
                }
              />
            </div>
            <div className={modalStyles.rightPanel}>
              <ReadOnlySessionChat
                selectedSessionId={selectedSessionId}
                chatIdBySessionId={{}}
                mockMessages={selectedMessages}
              />
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
