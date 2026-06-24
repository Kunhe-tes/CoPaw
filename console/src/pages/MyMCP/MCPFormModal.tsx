/**
 * MCP 创建/编辑弹窗，布局对齐 CmbCoworkAgent-main 的 AddMcpConnectorDialog。
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Input, Modal, message } from "antd";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useMyMCP } from "./useMyMCP";
import { buildClientKey } from "./clientKey";
import { myMcpApi } from "../../api/modules/myMcp";
import type {
  MyMCPCreateRequest,
  MCPTestResult,
  MyMCPDetail,
  MyMCPUpdateRequest,
} from "../../api/types";

const { TextArea } = Input;

type ConnectorMode = "remote" | "stdio";

interface MCPFormModalProps {
  open: boolean;
  clientKey: string | null;
  initialData: MyMCPDetail | null;
  onClose: () => void;
  onSuccess: () => void | Promise<void>;
}

function pairsToObject(pairs: Array<[string, string]>): Record<string, string> {
  const result: Record<string, string> = {};
  pairs.forEach(([key, value]) => {
    const trimmedKey = key.trim();
    if (trimmedKey) {
      result[trimmedKey] = value.trim();
    }
  });
  return result;
}

function isDuplicateMcpError(err: unknown): boolean {
  if (!(err instanceof Error) || !err.message) {
    return false;
  }
  return /MCP client '.*' already exists/i.test(err.message);
}

function sectionLabelStyle() {
  return {
    fontSize: 13,
    fontWeight: 500,
    color: "#243040",
  } as const;
}

export function MCPFormModal({
  open,
  clientKey,
  initialData,
  onClose,
  onSuccess,
}: MCPFormModalProps) {
  const { createMCP, updateMCP } = useMyMCP();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const isEdit = !!clientKey;
  const initialMode = useMemo<ConnectorMode>(
    () => (initialData?.transport === "stdio" ? "stdio" : "remote"),
    [initialData]
  );

  const [name, setName] = useState("");
  const [mode, setMode] = useState<ConnectorMode>("remote");
  const [remoteTransport, setRemoteTransport] = useState<
    "streamable_http" | "sse"
  >("streamable_http");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [headers, setHeaders] = useState<Array<[string, string]>>([]);
  const [envVars, setEnvVars] = useState<Array<[string, string]>>([]);
  const [lazyLoad, setLazyLoad] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<MCPTestResult | null>(null);

  useEffect(() => {
    if (!open) return;

    if (initialData) {
      setName(initialData.name || "");
      setMode(initialMode);
      setRemoteTransport(
        initialData.transport === "sse" ? "sse" : "streamable_http"
      );
      setUrl(initialData.url || "");
      setCommand(initialData.command || "");
      setArgsText((initialData.args || []).join("\n"));
      setHeaders(
        initialData.headers ? Object.entries(initialData.headers) : []
      );
      setEnvVars(initialData.env ? Object.entries(initialData.env) : []);
      setLazyLoad(!!initialData.lazy_load);
    } else {
      setName("");
      setMode("remote");
      setRemoteTransport("streamable_http");
      setUrl("");
      setCommand("");
      setArgsText("");
      setHeaders([]);
      setEnvVars([]);
      setLazyLoad(false);
    }

    setAdvancedOpen(false);
    setError(null);
    setTestResult(null);
  }, [open, initialData, initialMode]);

  useEffect(() => {
    if (!open) return;
    setTestResult(null);
  }, [
    open,
    name,
    mode,
    remoteTransport,
    url,
    command,
    argsText,
    headers,
    envVars,
    lazyLoad,
  ]);

  const addHeader = useCallback(() => {
    setHeaders((prev) => [...prev, ["", ""]]);
  }, []);

  const updateHeader = useCallback(
    (idx: number, key: string, value: string) => {
      setHeaders((prev) => {
        const next = [...prev];
        next[idx] = [key, value];
        return next;
      });
    },
    []
  );

  const removeHeader = useCallback((idx: number) => {
    setHeaders((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const addEnvVar = useCallback(() => {
    setEnvVars((prev) => [...prev, ["", ""]]);
  }, []);

  const updateEnvVar = useCallback(
    (idx: number, key: string, value: string) => {
      setEnvVars((prev) => {
        const next = [...prev];
        next[idx] = [key, value];
        return next;
      });
    },
    []
  );

  const removeEnvVar = useCallback((idx: number) => {
    setEnvVars((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const handleSubmit = useCallback(async () => {
    const trimmedName = name.trim();
    const trimmedClientKey = buildClientKey(trimmedName);

    if (!trimmedName) {
      setError("请输入名称");
      return;
    }

    if (mode === "remote") {
      const trimmedUrl = url.trim();
      if (!trimmedUrl) {
        setError("请输入 MCP 服务器 URL");
        return;
      }
      try {
        new URL(trimmedUrl);
      } catch {
        setError("URL 格式无效");
        return;
      }
    } else if (!command.trim()) {
      setError("请输入启动命令");
      return;
    }

    setLoading(true);
    setError(null);

    const args = argsText
      .split(/\r?\n/)
      .map((arg) => arg.trim())
      .filter(Boolean);

    const payload = {
      name: trimmedName,
      description: "",
      transport: mode === "stdio" ? "stdio" : remoteTransport,
      url: mode === "remote" ? url.trim() : "",
      command: mode === "stdio" ? command.trim() : "",
      args,
      headers: mode === "remote" ? pairsToObject(headers) : {},
      env: mode === "stdio" ? pairsToObject(envVars) : {},
      cwd: initialData?.cwd || "",
      lazy_load: lazyLoad,
    } satisfies MyMCPUpdateRequest;

    try {
      if (isEdit && clientKey) {
        await updateMCP(clientKey, payload);
        message.success("更新成功");
      } else {
        const createPayload: MyMCPCreateRequest = {
          client_key: trimmedClientKey,
          ...payload,
        };
        await createMCP(createPayload);
        message.success("创建成功");
      }
      await onSuccess();
    } catch (err) {
      console.error("保存 MCP 失败:", err);
      if (!isEdit && isDuplicateMcpError(err)) {
        setError(null);
        message.warning("MCP 连接器已存在，请勿重复添加");
      } else {
        setError("操作失败");
      }
    } finally {
      setLoading(false);
    }
  }, [
    name,
    isEdit,
    mode,
    url,
    command,
    argsText,
    remoteTransport,
    headers,
    envVars,
    clientKey,
    updateMCP,
    createMCP,
    onSuccess,
    initialData?.cwd,
    lazyLoad,
  ]);

  const handleTest = useCallback(async () => {
    const trimmedName = name.trim();

    if (!trimmedName) {
      setError("请输入名称");
      return;
    }

    if (mode === "remote") {
      const trimmedUrl = url.trim();
      if (!trimmedUrl) {
        setError("请输入 MCP 服务器 URL");
        return;
      }
      try {
        new URL(trimmedUrl);
      } catch {
        setError("URL 格式无效");
        return;
      }
    } else if (!command.trim()) {
      setError("请输入启动命令");
      return;
    }

    setError(null);
    setTestLoading(true);
    setTestResult(null);

    const args = argsText
      .split(/\r?\n/)
      .map((arg) => arg.trim())
      .filter(Boolean);

    try {
      const result = await myMcpApi.testMyMCPDraftConnection({
        baseline_client_key: isEdit ? clientKey ?? undefined : undefined,
        name: trimmedName,
        transport: mode === "stdio" ? "stdio" : remoteTransport,
        url: mode === "remote" ? url.trim() : "",
        command: mode === "stdio" ? command.trim() : "",
        args,
        headers: mode === "remote" ? pairsToObject(headers) : {},
        env: mode === "stdio" ? pairsToObject(envVars) : {},
        cwd: initialData?.cwd || "",
      });
      setTestResult(result);
    } catch (err) {
      console.error("测试 MCP 草稿失败:", err);
      setTestResult({
        success: false,
        tools: [],
        error: "测试失败",
      });
    } finally {
      setTestLoading(false);
    }
  }, [
    name,
    mode,
    url,
    command,
    argsText,
    remoteTransport,
    headers,
    envVars,
    initialData?.cwd,
    isEdit,
    clientKey,
  ]);

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title={null}
      width={580}
      destroyOnClose
    >
      <div style={{ display: "grid", gap: 18 }}>
        <div style={{ display: "grid", gap: 6 }}>
          <h3
            style={{
              fontSize: 18,
              fontWeight: 600,
              color: "#243040",
              margin: 0,
            }}
          >
            {isEdit ? "编辑 MCP 连接器" : "添加 MCP 连接器"}
          </h3>
          <p style={{ fontSize: 13, color: "#8b94a3", margin: 0 }}>
            连接到外部 MCP 服务器，为 Agent 提供额外工具。
          </p>
        </div>

        <div style={{ display: "grid", gap: 14 }}>
          <div style={{ display: "grid", gap: 8 }}>
            <label style={sectionLabelStyle()}>名称</label>
            <Input
              placeholder="例如：我的 MCP 服务"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ height: 36, borderRadius: 8 }}
            />
          </div>

          <div style={{ display: "grid", gap: 8 }}>
            <label style={sectionLabelStyle()}>连接方式</label>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as ConnectorMode)}
              style={{
                height: 36,
                width: "100%",
                borderRadius: 8,
                border: "1px solid #d9dde5",
                backgroundColor: "#fff",
                padding: "0 12px",
                fontSize: 13,
                color: "#243040",
              }}
            >
              <option value="remote">Remote MCP server</option>
              <option value="stdio">Local stdio command</option>
            </select>
          </div>

          {mode === "remote" ? (
            <>
              <div style={{ display: "grid", gap: 8 }}>
                <label style={sectionLabelStyle()}>Remote MCP server URL</label>
                <Input
                  placeholder="https://..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  style={{ height: 36, borderRadius: 8 }}
                />
              </div>

              <button
                type="button"
                onClick={() => setAdvancedOpen((prev) => !prev)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  width: "100%",
                  padding: "2px 0",
                  border: "none",
                  background: "none",
                  color: "#8b94a3",
                  cursor: "pointer",
                  fontSize: 13,
                }}
              >
                {advancedOpen ? (
                  <ChevronDown style={{ width: 16, height: 16 }} />
                ) : (
                  <ChevronRight style={{ width: 16, height: 16 }} />
                )}
                高级设置
              </button>

              {advancedOpen && (
                <div
                  style={{
                    display: "grid",
                    gap: 14,
                    paddingLeft: 16,
                    borderLeft: "1px solid #eef1f5",
                  }}
                >
                  <div style={{ display: "grid", gap: 8 }}>
                    <label
                      style={{
                        fontSize: 12,
                        fontWeight: 500,
                        color: "#243040",
                      }}
                    >
                      自定义请求头
                    </label>
                    {headers.map(([key, value], idx) => (
                      <div
                        key={idx}
                        style={{ display: "flex", gap: 8, alignItems: "center" }}
                      >
                        <Input
                          placeholder="Key"
                          value={key}
                          onChange={(e) =>
                            updateHeader(idx, e.target.value, value)
                          }
                          style={{ borderRadius: 8 }}
                        />
                        <Input
                          placeholder="Value"
                          value={value}
                          onChange={(e) =>
                            updateHeader(idx, key, e.target.value)
                          }
                          style={{ borderRadius: 8 }}
                        />
                        <Button
                          onClick={() => removeHeader(idx)}
                          style={{ borderRadius: 8 }}
                        >
                          ×
                        </Button>
                      </div>
                    ))}
                    <Button onClick={addHeader} style={{ borderRadius: 8 }}>
                      添加请求头
                    </Button>
                  </div>

                  <div style={{ display: "grid", gap: 8 }}>
                    <label
                      style={{
                        fontSize: 12,
                        fontWeight: 500,
                        color: "#243040",
                      }}
                    >
                      传输类型
                    </label>
                    <select
                      value={remoteTransport}
                      onChange={(e) =>
                        setRemoteTransport(
                          e.target.value as "streamable_http" | "sse"
                        )
                      }
                      style={{
                        height: 34,
                        width: "100%",
                        borderRadius: 8,
                        border: "1px solid #d9dde5",
                        backgroundColor: "#fff",
                        padding: "0 12px",
                        fontSize: 12,
                        color: "#243040",
                      }}
                    >
                      <option value="streamable_http">Streamable HTTP</option>
                      <option value="sse">SSE</option>
                    </select>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <div style={{ display: "grid", gap: 8 }}>
                <label style={sectionLabelStyle()}>启动命令</label>
                <Input
                  placeholder="例如：npx"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  style={{ height: 36, borderRadius: 8 }}
                />
              </div>

              <div style={{ display: "grid", gap: 8 }}>
                <label style={sectionLabelStyle()}>命令参数</label>
                <TextArea
                  placeholder={"每行一个参数\n例如：--yes\n@example/mcp-server"}
                  value={argsText}
                  onChange={(e) => setArgsText(e.target.value)}
                  rows={4}
                  style={{ borderRadius: 8 }}
                />
                <p style={{ fontSize: 12, color: "#8b94a3", margin: 0 }}>
                  按行拆分为 args 数组。
                </p>
              </div>

              <div style={{ display: "grid", gap: 8 }}>
                <label
                  style={{
                    fontSize: 12,
                    fontWeight: 500,
                    color: "#243040",
                  }}
                >
                  环境变量
                </label>
                {envVars.map(([key, value], idx) => (
                  <div
                    key={idx}
                    style={{ display: "flex", gap: 8, alignItems: "center" }}
                  >
                    <Input
                      placeholder="Key"
                      value={key}
                      onChange={(e) => updateEnvVar(idx, e.target.value, value)}
                      style={{ borderRadius: 8 }}
                    />
                    <Input
                      placeholder="Value"
                      value={value}
                      onChange={(e) => updateEnvVar(idx, key, e.target.value)}
                      style={{ borderRadius: 8 }}
                    />
                    <Button
                      onClick={() => removeEnvVar(idx)}
                      style={{ borderRadius: 8 }}
                    >
                      ×
                    </Button>
                  </div>
                ))}
                <Button onClick={addEnvVar} style={{ borderRadius: 8 }}>
                  添加环境变量
                </Button>
              </div>
            </>
          )}

          <div
            style={{
              borderRadius: 12,
              border: "1px solid #eef1f5",
              backgroundColor: "#f8fafc",
              padding: 12,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                id="mcp-lazy-load"
                checked={lazyLoad}
                onChange={(e) => setLazyLoad(e.target.checked)}
              />
              <label
                htmlFor="mcp-lazy-load"
                style={{
                  fontSize: 12,
                  fontWeight: 500,
                  color: "#243040",
                }}
              >
                懒加载
              </label>
            </div>
            <p style={{ fontSize: 12, color: "#8b94a3", margin: "8px 0 0" }}>
              启用后，工具不会立即加载到上下文中，而是通过 search_tool 搜索后按需加载。
            </p>
          </div>

          <p style={{ fontSize: 12, color: "#8b94a3", margin: 0, lineHeight: 1.7 }}>
            MCP 连接器可访问你配置的数据与工具。请仅添加你信任的服务器。
          </p>
        </div>

        {error && (
          <p style={{ fontSize: 13, color: "#ff4d4f", margin: 0 }}>{error}</p>
        )}

        {testResult && (
          <div
            style={{
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

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 8,
            paddingTop: 4,
          }}
        >
          <Button
            onClick={() => void handleTest()}
            loading={testLoading}
            disabled={loading}
            style={{ borderRadius: 8 }}
          >
            {testLoading ? "测试中..." : "测试连接"}
          </Button>
          <div style={{ display: "flex", gap: 8 }}>
            <Button
              onClick={onClose}
              disabled={loading || testLoading}
              style={{ borderRadius: 8 }}
            >
              取消
            </Button>
            <Button
              type="primary"
              onClick={handleSubmit}
              loading={loading}
              style={{ borderRadius: 8 }}
            >
              {isEdit ? "保存" : "添加"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
