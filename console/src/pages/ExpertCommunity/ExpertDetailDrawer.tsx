import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Popconfirm,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  CalendarOutlined,
  HistoryOutlined,
  SendOutlined,
  StopOutlined,
  UndoOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  marketApi,
  type MarketExpert,
  type MarketExpertDetail,
} from "../../api/modules/market";
import { BBK_ID_TO_NAME_MAP } from "../../constants/bbk";

const { Text, Title } = Typography;

interface ExpertDetailDrawerProps {
  sourceId: string;
  expert: MarketExpert | null;
  open: boolean;
  isManager: boolean;
  busy: boolean;
  onClose: () => void;
  onVersions: () => void;
  onDistribute?: () => void;
  onRecall?: () => void;
  onUnpublish?: () => void;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

export function ExpertDetailDrawer({
  sourceId,
  expert,
  open,
  isManager,
  busy,
  onClose,
  onVersions,
  onDistribute,
  onRecall,
  onUnpublish,
}: ExpertDetailDrawerProps) {
  const [detail, setDetail] = useState<MarketExpertDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !expert) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void marketApi
      .getMarketExpert(sourceId, expert.item_id)
      .then((result) => {
        if (!cancelled) setDetail(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(
            reason instanceof Error ? reason.message : "加载专家详情失败",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [expert, open, sourceId]);

  const current = detail || expert;

  return (
    <Drawer
      title={current ? `专家详情 · ${current.name}` : "专家详情"}
      width={560}
      open={open}
      onClose={onClose}
      extra={
        current ? (
          <div style={{ display: "flex", gap: 8 }}>
            <Button icon={<HistoryOutlined />} onClick={onVersions}>
              版本历史
            </Button>
            {isManager && onDistribute ? (
              <Popconfirm
                title="确认分发此专家？"
                description="管理员分发会静默覆盖同一社区来源的本地变体。"
                onConfirm={onDistribute}
                okText="分发"
                cancelText="取消"
              >
                <Button type="primary" icon={<SendOutlined />} loading={busy}>
                  分发
                </Button>
              </Popconfirm>
            ) : null}
          </div>
        ) : null
      }
    >
      {loading ? (
        <div style={{ minHeight: 180, display: "grid", placeItems: "center" }}>
          <Spin />
        </div>
      ) : error ? (
        <Alert type="error" showIcon message={error} />
      ) : current ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <Title level={4} style={{ margin: 0, wordBreak: "break-word" }}>
                {current.name}
              </Title>
              <Tag color={current.status === "active" ? "green" : "default"}>
                {current.status === "active" ? "已发布" : "已下架"}
              </Tag>
              <Tag>v{current.version}</Tag>
            </div>
            <Text type="secondary">{current.description || "暂无描述"}</Text>
          </div>

          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="发布者">
              <span
                style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
              >
                <UserOutlined />
                {current.creator_name || current.creator_id}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              <span
                style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
              >
                <CalendarOutlined />
                {formatDate(current.created_at)}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label="更新时间">
              {formatDate(current.updated_at)}
            </Descriptions.Item>
            <Descriptions.Item label="分类">
              {current.category_id === null ? "未分类" : current.category_id}
            </Descriptions.Item>
            <Descriptions.Item label="所属分行">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {current.bbk_ids.length
                  ? current.bbk_ids.map((bbkId) => (
                      <Tag key={bbkId}>
                        {BBK_ID_TO_NAME_MAP[bbkId] || bbkId}
                      </Tag>
                    ))
                  : "未指定"}
              </div>
            </Descriptions.Item>
          </Descriptions>

          {detail?.definition && Object.keys(detail.definition).length > 0 ? (
            <section>
              <Title level={5}>专家配置摘要</Title>
              <pre
                style={{
                  margin: 0,
                  padding: 12,
                  border: "1px solid #f0f0f0",
                  borderRadius: 8,
                  background: "#fafafa",
                  whiteSpace: "pre-wrap",
                  overflowWrap: "anywhere",
                  fontSize: 12,
                  lineHeight: 1.6,
                }}
              >
                {JSON.stringify(detail.definition, null, 2)}
              </pre>
            </section>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无配置摘要"
            />
          )}

          {isManager ? (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {onRecall ? (
                <Popconfirm
                  title="确认撤回此专家？"
                  description="将删除用户已接收副本，并释放会话依赖视图。"
                  onConfirm={onRecall}
                  okText="撤回"
                  cancelText="取消"
                >
                  <Button danger icon={<UndoOutlined />} loading={busy}>
                    撤回已接收副本
                  </Button>
                </Popconfirm>
              ) : null}
              {onUnpublish ? (
                <Popconfirm
                  title="确认下架此专家？"
                  description="下架后将停止新的浏览、接收和分发。"
                  onConfirm={onUnpublish}
                  okText="下架"
                  cancelText="取消"
                >
                  <Button danger icon={<StopOutlined />} loading={busy}>
                    下架专家
                  </Button>
                </Popconfirm>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  );
}
