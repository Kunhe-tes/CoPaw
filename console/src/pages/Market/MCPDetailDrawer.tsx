/**
 * 市场 MCP 详情面板。
 *
 * 说明：
 * - 文件名沿用历史命名，职责已切换为页面内详情面板
 * - 视觉结构参考 CmbCoworkAgent-main 的 MCP 市场详情区
 */
import { useState } from "react";
import {
  Alert,
  Button,
  Popconfirm,
  Space,
  Typography,
  message,
} from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import {
  Calendar,
  GitBranch,
  Info,
  Link as LinkIcon,
  TerminalSquare,
  Send,
  Pencil,
  Trash2,
  Undo2,
} from "lucide-react";
import { marketMcpApi } from "../../api/modules/marketMcp";
import type { MarketMCPDetail, MCPTestResult } from "../../api/types";

const { Title, Paragraph, Text } = Typography;

interface MCPDetailDrawerProps {
  mcp: MarketMCPDetail | null;
  onDistribute?: () => void;
  onRecall?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  canEdit?: boolean;
  isManager?: boolean;
}

function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (num: number) => String(num).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
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

export function MCPDetailDrawer({
  mcp,
  onDistribute,
  onRecall,
  onEdit,
  onDelete,
  canEdit = false,
  isManager = false,
}: MCPDetailDrawerProps) {
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<MCPTestResult | null>(null);

  if (!mcp) return null;

  const summary =
    mcp.config.transport === "stdio"
      ? [mcp.config.command, ...(mcp.config.args || [])].filter(Boolean).join(" ")
      : mcp.config.url || "暂无摘要";

  const configRows =
    mcp.config.transport === "stdio"
      ? [
          { label: "传输类型", value: "STDIO" },
          { label: "命令", value: mcp.config.command || "-" },
          {
            label: "参数",
            value: mcp.config.args?.length ? mcp.config.args.join(" ") : "-",
          },
          {
            label: "环境变量",
            value:
              Object.keys(mcp.config.env || {}).length > 0
                ? Object.entries(mcp.config.env || {})
                    .map(([key, value]) => `${key}: ${value}`)
                    .join("\n")
                : "-",
          },
        ]
      : [
          { label: "传输类型", value: "HTTP" },
          { label: "URL", value: mcp.config.url || "-" },
          {
            label: "Headers",
            value:
              Object.keys(mcp.config.headers || {}).length > 0
                ? Object.entries(mcp.config.headers || {})
                    .map(([key, value]) => `${key}: ${value}`)
                    .join("\n")
                : "-",
          },
        ];

  const handleTest = async () => {
    setTestLoading(true);
    setTestResult(null);
    try {
      const result = await marketMcpApi.testMarketMCP(mcp.item_id);
      setTestResult(result);
      if (result.success) {
        message.success(`连接成功，共 ${result.tools.length} 个工具`);
      } else {
        message.error(result.error || "测试连接失败");
      }
    } catch (error) {
      console.error("测试市场 MCP 失败:", error);
      message.error(error instanceof Error ? error.message : "测试连接失败");
    } finally {
      setTestLoading(false);
    }
  };

  return (
    <div style={{ padding: 4 }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 380px",
          gap: 20,
          alignItems: "start",
        }}
      >
        <div
          style={{
            border: "1px solid #f0f0f0",
            borderRadius: 18,
            background: "#ffffff",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: 16,
              borderBottom: "1px solid #f0f0f0",
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <div style={{ minWidth: 0, flex: 1 }}>
              <Title level={4} style={{ margin: 0, fontSize: 16, color: "#141413" }}>
                {mcp.name}
              </Title>
              <Paragraph style={{ marginTop: 4, marginBottom: 0, fontSize: 12, color: "#87867f" }}>
                {summary}
              </Paragraph>
            </div>
          </div>

          <div style={{ padding: "12px 16px", borderBottom: "1px solid #f0f0f0" }}>
            <Button
              icon={<ThunderboltOutlined />}
              loading={testLoading}
              onClick={handleTest}
              style={{ borderRadius: 10, height: 28, fontSize: 12 }}
            >
              {testLoading ? "测试中..." : "测试连接"}
            </Button>
            {testResult ? (
              <div style={{ marginTop: 10 }}>
                {testResult.success ? (
                  <div style={{ display: "grid", gap: 8 }}>
                    <Text style={{ fontSize: 12, color: "#5e5d59" }}>
                      连接成功，共 {testResult.tools.length} 个工具：
                    </Text>
                    <div
                      style={{
                        display: "grid",
                        gap: 6,
                        fontSize: 12,
                        maxHeight: 200,
                        overflow: "auto",
                        padding: "4px 0",
                      }}
                    >
                      {testResult.tools.map((tool) => (
                        <div
                          key={tool.name}
                          style={{
                            padding: "6px 8px",
                            borderRadius: 6,
                            backgroundColor: "#f5f5f5",
                          }}
                        >
                          <div style={{ fontWeight: 500, color: "#434a57" }}>
                            {tool.name}
                          </div>
                          {tool.description ? (
                            <div
                              style={{
                                marginTop: 2,
                                color: "#87867f",
                                fontSize: 11,
                                lineHeight: 1.4,
                              }}
                            >
                              {tool.description}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <Text style={{ fontSize: 12, color: "#b53333" }}>
                    {testResult.error || "测试连接失败"}
                  </Text>
                )}
              </div>
            ) : null}
          </div>

          <div style={{ padding: "12px 16px", borderBottom: "1px solid #f0f0f0" }}>
            <p style={{ margin: 0, fontSize: 12, color: "#87867f", lineHeight: 1.7 }}>
              MCP 连接器可访问你配置的数据与工具。请仅添加你信任的服务器。
            </p>
          </div>

          <div style={{ padding: 16, display: "grid", gap: 14 }}>
            <div>
              <p
                style={{
                  marginTop: 0,
                  marginBottom: 12,
                  fontSize: 13,
                  fontWeight: 500,
                  color: "#141413",
                }}
              >
                连接配置
              </p>
              <div style={{ display: "grid", gap: 10 }}>
                {configRows.map((row) => (
                  <div
                    key={row.label}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "96px 1fr",
                      gap: 12,
                      alignItems: "start",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        fontSize: 12,
                        color: "#87867f",
                      }}
                    >
                      {row.label === "URL" ? <LinkIcon size={14} /> : null}
                      {row.label === "命令" ? <TerminalSquare size={14} /> : null}
                      <span>{row.label}</span>
                    </div>
                    <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", fontSize: 12, color: "#434a57" }}>
                      {row.value}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gap: 12 }}>
          <div
            style={{
              border: "1px solid #f0f0f0",
              borderRadius: 18,
              background: "#fff",
              padding: 16,
              boxShadow: "rgba(0,0,0,0.04) 0px 4px 16px",
            }}
          >
            <div style={{ display: "grid", gap: 12 }}>
              <div style={{ display: "grid", gap: 8 }}>
                <Title level={4} style={{ margin: 0, fontSize: 16, color: "#141413" }}>
                  {mcp.chinese_name ? `${mcp.chinese_name} (${mcp.name})` : mcp.name}
                </Title>
                {mcp.description ? (
                  <Paragraph style={{ margin: 0, fontSize: 14, color: "#87867f", lineHeight: 1.6 }}>
                    {mcp.description}
                  </Paragraph>
                ) : null}
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px", borderRadius: 999, border: "1px solid #e8e8e8", background: "#f5f5f5", fontSize: 12, color: "#5e5d59" }}>
                  <GitBranch size={12} />
                  <span>v{mcp.version || "1.0.0"}</span>
                </div>
                <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px", borderRadius: 999, border: "1px solid #e8e8e8", background: "#f5f5f5", fontSize: 12, color: "#5e5d59" }}>
                  <Calendar size={12} />
                  <span>{formatDateTime(mcp.created_at)}</span>
                </div>
              </div>

              <Space wrap size={8}>
                {isManager && onDistribute && (
                  <Button
                    size="small"
                    type="primary"
                    onClick={onDistribute}
                    style={{ ...footerButtonStyle }}
                  >
                    <Send size={12} />
                    分发
                  </Button>
                )}
                {isManager && onRecall && (
                  <Button
                    size="small"
                    onClick={onRecall}
                    style={{
                      ...footerButtonStyle,
                      color: "#5e5d59",
                      border: "1px solid #d9d9d9",
                      backgroundColor: "#fff",
                    }}
                  >
                    <Undo2 size={12} />
                    撤回
                  </Button>
                )}
                {canEdit && onEdit && (
                  <Button
                    size="small"
                    onClick={onEdit}
                    style={{
                      ...footerButtonStyle,
                      color: "#5e5d59",
                      border: "1px solid #e8e8e8",
                      backgroundColor: "#f5f5f5",
                    }}
                  >
                    <Pencil size={12} />
                    编辑
                  </Button>
                )}
                {isManager && onDelete && (
                  <Popconfirm
                    title="确认删除此 MCP？删除后不影响已分发用户"
                    onConfirm={onDelete}
                  >
                    <Button
                      size="small"
                      danger
                      style={{ ...footerButtonStyle }}
                    >
                      <Trash2 size={12} />
                      删除
                    </Button>
                  </Popconfirm>
                )}
              </Space>
            </div>
          </div>

          <Alert
            type="warning"
            showIcon
            message="市场连接器可直接分发给目标租户，请确认配置内容可信。"
          />

          <div
            style={{
              border: "1px solid #f0f0f0",
              borderRadius: 16,
              background: "#ffffff",
              overflow: "hidden",
            }}
          >
            {[
              { label: "中文名称", value: mcp.chinese_name || "-" },
              { label: "创建人", value: mcp.creator_name || "-" },
              { label: "更新时间", value: formatDateTime(mcp.updated_at) },
            ].map((row, index, arr) => (
              <div
                key={row.label}
                style={{
                  display: "grid",
                  gridTemplateColumns: "88px 1fr",
                  gap: 12,
                  padding: "12px 14px",
                  borderBottom: index === arr.length - 1 ? "none" : "1px solid #f0f0f0",
                }}
              >
                <div style={{ fontSize: 12, color: "#87867f" }}>{row.label}</div>
                <div style={{ fontSize: 12, color: "#434a57", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                  {row.value}
                </div>
              </div>
            ))}
          </div>

          <div
            style={{
              border: "1px solid #d9e5f6",
              borderRadius: 16,
              background: "#f7faff",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "12px 14px",
                borderBottom: "1px solid #e6eefb",
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 13,
                fontWeight: 500,
                color: "#365d97",
              }}
            >
              <Info size={14} />
              <span>使用指引</span>
            </div>
            <div
              style={{
                padding: "12px 14px",
                whiteSpace: "pre-wrap",
                fontSize: 12,
                color: mcp.guidance ? "#4b5f7e" : "#7b8da8",
                lineHeight: 1.7,
              }}
            >
              {mcp.guidance || "暂无使用指引"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
