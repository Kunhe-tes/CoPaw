/**
 * MCP 详情面板，布局对齐 CmbCoworkAgent-main 的 MCPConnectorDetail。
 */
import { useMemo } from "react";
import { Button, Popconfirm, Tag } from "antd";
import { RocketOutlined } from "@ant-design/icons";
import { Database, Plug, Power, Trash2, Pencil } from "lucide-react";
import type { MyMCPDetail, MCPTestResult } from "../../api/types";

function getConnectorSummary(mcp: MyMCPDetail): string {
  if (mcp.transport === "stdio") {
    return [mcp.command ?? "", ...(mcp.args ?? [])].filter(Boolean).join(" ");
  }
  return mcp.url ?? "";
}

function formatDateTime(value?: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const pad = (num: number) => String(num).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate()
  )} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(
    date.getSeconds()
  )}`;
}

interface MCPDetailPanelProps {
  mcp: MyMCPDetail | null;
  testing: boolean;
  testResult: MCPTestResult | null;
  isManager: boolean;
  togglingClientKey?: string | null;
  onEdit: (clientKey: string) => void;
  onDelete: (mcp: MyMCPDetail) => void;
  onToggle: (clientKey: string, enabled: boolean) => void;
  onTest: () => void;
  onPublish: (clientKey: string) => void;
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "92px 1fr",
        gap: 12,
        alignItems: "start",
      }}
    >
      <span style={{ fontSize: 12, color: "#8b94a3" }}>{label}</span>
      <span
        style={{
          fontSize: 12,
          color: "#434a57",
          wordBreak: "break-all",
          lineHeight: 1.6,
        }}
      >
        {value || "-"}
      </span>
    </div>
  );
}

export function MCPDetailPanel({
  mcp,
  testing,
  testResult,
  isManager,
  togglingClientKey,
  onEdit,
  onDelete,
  onToggle,
  onTest,
  onPublish,
}: MCPDetailPanelProps) {
  const isDistributed = useMemo(
    () => !!mcp?.source && mcp.source.startsWith("marketplace:"),
    [mcp]
  );

  if (!mcp) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflowY: "auto",
          padding: 32,
          backgroundColor: "#ffffff",
        }}
      >
        <div style={{ maxWidth: 460 }}>
          <div style={{ textAlign: "center", marginBottom: 24 }}>
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: 18,
                backgroundColor: "#eef6ff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto",
              }}
            >
              <Plug style={{ width: 28, height: 28, color: "#1677ff" }} />
            </div>
            <h3
              style={{
                fontSize: 18,
                fontWeight: 600,
                color: "#243040",
                marginTop: 12,
                marginBottom: 0,
              }}
            >
              MCP 连接器
            </h3>
            <p
              style={{
                fontSize: 14,
                color: "#8b94a3",
                lineHeight: 1.7,
                marginTop: 8,
                marginBottom: 0,
              }}
            >
              MCP（Model Context Protocol）是一种开放协议，让 AI 能够连接远程工具服务器。通过
              MCP 连接器，AI 可以调用服务器提供的各种工具（Tools），从而获取外部数据、执行远程操作，大幅扩展能力边界。
            </p>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div
              style={{
                borderRadius: 14,
                border: "1px solid #edf1f5",
                backgroundColor: "#f8fafc",
                padding: 16,
              }}
            >
              <p
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: "#243040",
                  margin: 0,
                }}
              >
                什么是 MCP？
              </p>
              <p
                style={{
                  fontSize: 13,
                  color: "#8b94a3",
                  lineHeight: 1.7,
                  marginTop: 8,
                  marginBottom: 0,
                }}
              >
                MCP 服务器是一个远程服务，它向 AI 暴露一组工具（Tools）。AI 在对话过程中会根据需要自动调用这些工具来获取信息或执行操作。例如，一个搜索类 MCP 可以让 AI 直接查询网络信息并返回结果。当前支持本地 stdio 和远程 HTTP/SSE 两类连接方式。
              </p>
            </div>

            <div
              style={{
                borderRadius: 14,
                border: "1px solid #edf1f5",
                backgroundColor: "#f8fafc",
                padding: 16,
              }}
            >
              <p
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: "#243040",
                  margin: 0,
                }}
              >
                如何添加？
              </p>
              <ul
                style={{
                  fontSize: 13,
                  color: "#8b94a3",
                  lineHeight: 1.7,
                  marginTop: 8,
                  marginBottom: 0,
                  paddingLeft: 18,
                }}
              >
                <li>
                  点击右上角加号按钮，填写名称并选择连接方式，系统会根据名称自动生成连接器标识。
                </li>
                <li>本地 stdio 填写命令与参数，远程连接填写 URL。</li>
                <li>根据需要展开高级设置，配置请求头。</li>
                <li>保存后点击“测试连接”确认工具可用。</li>
              </ul>
            </div>

            <div
              style={{
                borderRadius: 14,
                border: "1px solid #edf1f5",
                backgroundColor: "#f8fafc",
                padding: 16,
              }}
            >
              <p
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: "#243040",
                  margin: 0,
                }}
              >
                适用场景
              </p>
              <p
                style={{
                  fontSize: 13,
                  color: "#8b94a3",
                  lineHeight: 1.7,
                  marginTop: 8,
                  marginBottom: 0,
                }}
              >
                网络搜索、知识库检索、代码仓库操作、项目管理工具集成、消息通知推送……几乎任何提供 MCP 协议接口的远程服务都可以接入。连接器支持随时启用 / 禁用，不影响其他功能。
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        overflow: "hidden",
        backgroundColor: "#ffffff",
      }}
    >
      <div
        style={{
          padding: 16,
          borderBottom: "1px solid #eef1f5",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <h2
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: "#243040",
              margin: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {mcp.name}
          </h2>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            flexShrink: 0,
            flexWrap: "wrap",
            justifyContent: "flex-end",
          }}
        >
          <Popconfirm
            title={`确定要删除连接器「${mcp.name}」吗？`}
            onConfirm={() => onDelete(mcp)}
          >
            <Button
              size="small"
              danger
              icon={<Trash2 style={{ width: 12, height: 12 }} />}
              style={{ height: 28, fontSize: 12, borderRadius: 8 }}
            >
              删除
            </Button>
          </Popconfirm>
          {!isDistributed && (
            <Button
              size="small"
              icon={<Pencil style={{ width: 12, height: 12 }} />}
              style={{ height: 28, fontSize: 12, borderRadius: 8 }}
              onClick={() => onEdit(mcp.client_key)}
            >
              编辑
            </Button>
          )}
          <Button
            size="small"
            type={mcp.enabled ? "primary" : "default"}
            icon={<Power style={{ width: 12, height: 12 }} />}
            style={{ height: 28, fontSize: 12, borderRadius: 8 }}
            onClick={() => onToggle(mcp.client_key, !mcp.enabled)}
            loading={togglingClientKey === mcp.client_key}
          >
            {mcp.enabled ? "已启用" : "已禁用"}
          </Button>
          {isManager && !isDistributed && (
            <Button
              size="small"
              icon={<RocketOutlined style={{ fontSize: 12 }} />}
              style={{
                height: 28,
                fontSize: 12,
                borderRadius: 8,
                background: "linear-gradient(135deg, #c4956a 0%, #b85a3a 100%)",
                border: "none",
                color: "#fff",
              }}
              onClick={() => onPublish(mcp.client_key)}
            >
              同步到市场
            </Button>
          )}
        </div>
      </div>

      <div style={{ padding: "12px 16px", borderBottom: "1px solid #eef1f5" }}>
        <Button
          size="small"
          style={{ height: 28, fontSize: 12, borderRadius: 8 }}
          loading={testing}
          onClick={onTest}
        >
          {testing ? "测试中..." : "测试连接"}
        </Button>
        {testResult && (
          <div
            style={{
              marginTop: 8,
              fontSize: 12,
              color: testResult.success ? "#8b94a3" : "#ff4d4f",
              lineHeight: 1.7,
            }}
          >
            {testResult.success ? (
              <div>
                <p style={{ margin: 0 }}>
                  连接成功，共 {testResult.tools?.length ?? 0} 个工具：
                </p>
                {testResult.tools && testResult.tools.length > 0 && (
                  <div
                    style={{
                      marginTop: 8,
                      maxHeight: 200,
                      overflow: "auto",
                      display: "grid",
                      gap: 6,
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
                              color: "#8b94a3",
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
                )}
              </div>
            ) : (
              <p style={{ margin: 0 }}>{testResult.error}</p>
            )}
          </div>
        )}
      </div>

      <div style={{ padding: "12px 16px", borderBottom: "1px solid #eef1f5" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <div>
            <p
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: "#243040",
                margin: 0,
              }}
            >
              懒加载
            </p>
            <p
              style={{
                fontSize: 12,
                color: "#8b94a3",
                marginTop: 2,
                marginBottom: 0,
              }}
            >
              {mcp.lazy_load
                ? "工具通过 search_tool 搜索后按需加载"
                : "所有工具直接加载到上下文中"}
            </p>
          </div>
          <Button
            size="small"
            type={mcp.lazy_load ? "primary" : "default"}
            icon={<Database style={{ width: 12, height: 12 }} />}
            style={{ height: 28, fontSize: 12, borderRadius: 8 }}
            disabled
          >
            {mcp.lazy_load ? "已开启" : "已关闭"}
          </Button>
        </div>
      </div>

      <div style={{ padding: "12px 16px", borderBottom: "1px solid #eef1f5" }}>
        <p style={{ fontSize: 12, color: "#8b94a3", margin: 0, lineHeight: 1.7 }}>
          MCP 连接器可访问你配置的数据与工具。请仅添加你信任的服务器。
        </p>
      </div>

      <div style={{ padding: 16, overflowY: "auto", flex: 1 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
          <Tag color={mcp.enabled ? "blue" : "default"}>
            {mcp.enabled ? "启用中" : "已禁用"}
          </Tag>
          <Tag>{mcp.transport}</Tag>
          {isDistributed && <Tag color="purple">市场分发</Tag>}
        </div>

        <div style={{ display: "grid", gap: 16 }}>
          <section
            style={{
              border: "1px solid #edf1f5",
              borderRadius: 14,
              backgroundColor: "#ffffff",
              padding: 16,
            }}
          >
            <p
              style={{
                fontSize: 13,
                fontWeight: 500,
                color: "#243040",
                marginTop: 0,
                marginBottom: 12,
              }}
            >
              基本信息
            </p>
            <div style={{ display: "grid", gap: 10 }}>
              <InfoRow label="名称" value={mcp.name} />
              <InfoRow
                label="创建时间"
                value={formatDateTime(mcp.created_at)}
              />
              <InfoRow
                label="更新时间"
                value={formatDateTime(mcp.updated_at)}
              />
              {isDistributed && <InfoRow label="来源" value={mcp.source} />}
              {isDistributed && (
                <InfoRow label="分发者" value={mcp.distributed_by || "-"} />
              )}
            </div>
          </section>

          <section
            style={{
              border: "1px solid #edf1f5",
              borderRadius: 14,
              backgroundColor: "#ffffff",
              padding: 16,
            }}
          >
            <p
              style={{
                fontSize: 13,
                fontWeight: 500,
                color: "#243040",
                marginTop: 0,
                marginBottom: 12,
              }}
            >
              连接配置
            </p>
            <div style={{ display: "grid", gap: 10 }}>
              {mcp.transport === "stdio" ? (
                <>
                  <InfoRow label="命令" value={mcp.command || "-"} />
                  <InfoRow
                    label="参数"
                    value={mcp.args?.length ? mcp.args.join(" ") : "-"}
                  />
                  <InfoRow label="工作目录" value={mcp.cwd || "-"} />
                  <InfoRow
                    label="环境变量"
                    value={
                      Object.keys(mcp.env || {}).length > 0
                        ? Object.entries(mcp.env)
                            .map(([key, value]) => `${key}: ${value}`)
                            .join("\n")
                        : "-"
                    }
                  />
                </>
              ) : (
                <>
                  <InfoRow label="URL" value={mcp.url || "-"} />
                  <InfoRow
                    label="Headers"
                    value={
                      Object.keys(mcp.headers || {}).length > 0
                        ? Object.entries(mcp.headers)
                            .map(([key, value]) => `${key}: ${value}`)
                            .join("\n")
                        : "-"
                    }
                  />
                </>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
