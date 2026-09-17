import { Button, Popconfirm, Tag, Tooltip, Typography } from "antd";
import {
  CalendarOutlined,
  EyeOutlined,
  HistoryOutlined,
  SendOutlined,
  StopOutlined,
  UndoOutlined,
  UserOutlined,
} from "@ant-design/icons";
import type { MarketExpert } from "../../api/modules/market";
import { BBK_ID_TO_NAME_MAP } from "../../constants/bbk";

const { Text } = Typography;

interface ExpertCardProps {
  expert: MarketExpert;
  isManager: boolean;
  isReceived: boolean;
  busy: boolean;
  onOpen: () => void;
  onReceive?: () => void;
  onVersions: () => void;
  onDistribute?: () => void;
  onRecall?: () => void;
  onUnpublish?: () => void;
  categoryName?: string;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("zh-CN");
}

export function ExpertCard({
  expert,
  isManager,
  isReceived,
  busy,
  onOpen,
  onReceive,
  onVersions,
  onDistribute,
  onRecall,
  onUnpublish,
  categoryName,
}: ExpertCardProps) {
  return (
    <article
      role="button"
      tabIndex={0}
      aria-label={`查看专家 ${expert.name}`}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      style={{
        padding: 20,
        borderRadius: 16,
        border: "1px solid #f0eee6",
        backgroundColor: "#fff",
        cursor: "pointer",
        transition:
          "border-color 160ms ease, background-color 160ms ease, box-shadow 160ms ease",
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
      }}
      onMouseEnter={(event) => {
        event.currentTarget.style.backgroundColor = "#faf9f5";
        event.currentTarget.style.borderColor = "#e8e6dc";
        event.currentTarget.style.boxShadow = "rgba(0,0,0,0.06) 0px 4px 20px";
      }}
      onMouseLeave={(event) => {
        event.currentTarget.style.backgroundColor = "#fff";
        event.currentTarget.style.borderColor = "#f0eee6";
        event.currentTarget.style.boxShadow = "none";
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              <Tooltip title={expert.name}>
                <Text
                  strong
                  ellipsis
                  style={{ maxWidth: "100%", fontSize: 15 }}
                >
                  {expert.name}
                </Text>
              </Tooltip>
              <Tag color={expert.status === "active" ? "green" : "default"}>
                {expert.status === "active" ? "已发布" : "已下架"}
              </Tag>
              <Tag>v{expert.version}</Tag>
            </div>
            <p
              style={{
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                fontSize: 14,
                color: "#87867f",
                margin: "8px 0 0",
                lineHeight: "22px",
                wordBreak: "break-word",
              }}
            >
              {expert.description || "暂无描述"}
            </p>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: 6,
            marginTop: 14,
          }}
        >
          {expert.category_id !== null ? (
            <Tag>分类 {categoryName || expert.category_id}</Tag>
          ) : null}
          {expert.bbk_ids.map((bbkId) => (
            <Tag key={bbkId}>{BBK_ID_TO_NAME_MAP[bbkId] || bbkId}</Tag>
          ))}
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 8,
          paddingTop: 12,
          marginTop: 16,
          borderTop: "1px solid #f0eee6",
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: 12,
            fontSize: 12,
            color: "#87867f",
          }}
        >
          <span
            style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
          >
            <CalendarOutlined />
            {formatDate(expert.updated_at || expert.created_at)}
          </span>
          <span
            style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
          >
            <UserOutlined />
            <span
              style={{ maxWidth: 120 }}
              title={expert.creator_name || expert.creator_id}
            >
              {expert.creator_name || expert.creator_id}
            </span>
          </span>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            flexWrap: "wrap",
          }}
        >
          <Button size="small" icon={<EyeOutlined />} onClick={onOpen}>
            详情
          </Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={onVersions}>
            版本历史
          </Button>
          {isManager ? (
            <>
              {onDistribute ? (
                <Popconfirm
                  title="确认分发此专家？"
                  description="管理员分发会静默覆盖同一社区来源的本地变体。"
                  onConfirm={onDistribute}
                  okText="分发"
                  cancelText="取消"
                >
                  <Button
                    type="primary"
                    size="small"
                    icon={<SendOutlined />}
                    loading={busy}
                  >
                    分发
                  </Button>
                </Popconfirm>
              ) : null}
              {onRecall ? (
                <Popconfirm
                  title="确认撤回此专家？"
                  description="将删除用户已接收副本，并释放会话依赖视图。"
                  onConfirm={onRecall}
                  okText="撤回"
                  cancelText="取消"
                >
                  <Button
                    danger
                    size="small"
                    icon={<UndoOutlined />}
                    loading={busy}
                  >
                    撤回
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
                  <Button
                    danger
                    size="small"
                    icon={<StopOutlined />}
                    loading={busy}
                  >
                    下架
                  </Button>
                </Popconfirm>
              ) : null}
            </>
          ) : onReceive ? (
            <Button
              type="primary"
              size="small"
              disabled={expert.status !== "active" || isReceived}
              loading={busy}
              onClick={onReceive}
            >
              {isReceived ? "已接收" : "接收"}
            </Button>
          ) : null}
        </div>
      </div>
    </article>
  );
}
