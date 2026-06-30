/**
 * 市场 MCP 卡片。
 *
 * 说明：
 * - 列表卡片布局尽量贴近 CmbCoworkAgent-main 的应用市场卡片
 * - 只保留 MCP 市场自己的动作：详情 / 分发 / 删除
 */
import { Button, Tag, Popover } from "antd";
import { Calendar, GitBranch, Eye, Send, Trash2, Pencil, Users, Building2 } from "lucide-react";
import { BBK_ID_TO_NAME_MAP } from "../../constants/bbk";
import type { MarketMCPItem } from "../../api/types";

interface MCPCardProps {
  mcp: MarketMCPItem;
  onOpenDetail: () => void;
  onDistribute?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  canEdit?: boolean;
  isManager?: boolean;
}

const footerButtonStyle = {
  height: 28,
  padding: "0 12px",
  borderRadius: 8,
  fontSize: 12,
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
};

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("zh-CN");
}

export function MCPCard({
  mcp,
  onOpenDetail,
  onDistribute,
  onEdit,
  onDelete,
  canEdit = false,
  isManager = false,
}: MCPCardProps) {
  return (
    <div
      onClick={onOpenDetail}
      style={{
        padding: 20,
        borderRadius: 20,
        border: "1px solid #f0eee6",
        background: "#fff",
        cursor: "pointer",
        transition: "all 0.2s ease",
        boxShadow: "rgba(0, 0, 0, 0) 0px 0px 0px",
      }}
      onMouseEnter={(event) => {
        event.currentTarget.style.background = "#faf9f5";
        event.currentTarget.style.borderColor = "#e8e6dc";
        event.currentTarget.style.boxShadow =
          "rgba(0, 0, 0, 0.06) 0px 4px 20px";
      }}
      onMouseLeave={(event) => {
        event.currentTarget.style.background = "#fff";
        event.currentTarget.style.borderColor = "#f0eee6";
        event.currentTarget.style.boxShadow =
          "rgba(0, 0, 0, 0) 0px 0px 0px";
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: 12,
          gap: 12,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <div
              style={{
                fontWeight: 500,
                fontSize: 15,
                lineHeight: "22px",
                color: "#141413",
              }}
            >
              {mcp.chinese_name ? (
                <>
                  {mcp.chinese_name}
                  <span style={{ marginLeft: 6, color: "#87867f", fontWeight: 400, fontSize: 14 }}>
                    ({mcp.name})
                  </span>
                </>
              ) : (
                mcp.name
              )}
            </div>
            {mcp.bbk_ids?.length > 0 && (
              <>
                {/* 分行 Tag：单个分行直接显示，多个分行显示首个+N，hover展开全部 */}
                {mcp.bbk_ids.length === 1 ? (
                  <Tag
                    style={{
                      fontSize: 11,
                      color: "#5e5d59",
                      backgroundColor: "#f5f4ed",
                      border: "1px solid #e8e6dc",
                      borderRadius: 999,
                      padding: "0 8px",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    <Building2 size={12} style={{ color: "#87867f" }} />
                    {BBK_ID_TO_NAME_MAP[mcp.bbk_ids[0]] || mcp.bbk_ids[0]}
                  </Tag>
                ) : (
                  <Popover
                    trigger="hover"
                    placement="bottom"
                    content={
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {mcp.bbk_ids.map((bbkId) => (
                          <span key={bbkId} style={{ fontSize: 12 }}>
                            {BBK_ID_TO_NAME_MAP[bbkId] || bbkId}
                          </span>
                        ))}
                      </div>
                    }
                  >
                    <Tag
                      style={{
                        fontSize: 11,
                        color: "#5e5d59",
                        backgroundColor: "#f5f4ed",
                        border: "1px solid #e8e6dc",
                        borderRadius: 999,
                        padding: "0 8px",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 4,
                        cursor: "pointer",
                      }}
                    >
                      <Building2 size={12} style={{ color: "#87867f" }} />
                      {BBK_ID_TO_NAME_MAP[mcp.bbk_ids[0]] || mcp.bbk_ids[0]}
                      <span style={{ color: "#87867f" }}>+{mcp.bbk_ids.length - 1}</span>
                    </Tag>
                  </Popover>
                )}
              </>
            )}
          </div>
          {mcp.description ? (
            <p
              style={{
                margin: "8px 0 0",
                fontSize: 14,
                lineHeight: "22px",
                color: "#87867f",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                wordBreak: "break-word",
              }}
            >
              {mcp.description}
            </p>
          ) : null}
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
          borderTop: "1px solid #f0eee6",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            fontSize: 12,
            color: "#87867f",
          }}
        >
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              whiteSpace: "nowrap",
            }}
          >
            <Calendar size={12} />
            <span>{formatDate(mcp.created_at)}</span>
          </div>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              whiteSpace: "nowrap",
            }}
          >
            <GitBranch size={12} />
            <span>v{mcp.version || "1.0.0"}</span>
          </div>
          {mcp.creator_name && (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                whiteSpace: "nowrap",
              }}
            >
              <Users size={12} />
              <span>{mcp.creator_name}</span>
            </div>
          )}
        </div>

        <div
          style={{ display: "flex", alignItems: "center", gap: 6 }}
          onClick={(event) => event.stopPropagation()}
        >
          <Button
            size="small"
            onClick={onOpenDetail}
            style={{
              ...footerButtonStyle,
              color: "#5e5d59",
              border: "1px solid #e8e6dc",
              backgroundColor: "#f5f4ed",
            }}
          >
            <Eye size={12} />
            详情
          </Button>
          {isManager && onDistribute && (
            <Button
              size="small"
              type="primary"
              onClick={onDistribute}
              style={{
                ...footerButtonStyle,
              }}
            >
              <Send size={12} />
              分发
            </Button>
          )}
          {canEdit && onEdit && (
            <Button
              size="small"
              onClick={onEdit}
              style={{
                ...footerButtonStyle,
                color: "#5e5d59",
                border: "1px solid #e8e6dc",
                backgroundColor: "#f5f4ed",
              }}
            >
              <Pencil size={12} />
              编辑
            </Button>
          )}
          {isManager && onDelete && (
            <Button
              size="small"
              danger
              onClick={onDelete}
              style={{
                ...footerButtonStyle,
              }}
            >
              <Trash2 size={12} />
              删除
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
