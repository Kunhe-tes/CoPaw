/**
 * MCP 上传弹窗
 */
import { useState } from "react";
import {
  Modal,
  Form,
  Input,
  Select,
  Button,
  Upload,
  message,
  Alert,
  Segmented,
  Tooltip,
} from "antd";
import {
  InboxOutlined,
  CheckOutlined,
  CopyOutlined,
  InfoCircleOutlined,
} from "@ant-design/icons";
import { marketMcpApi } from "../../api/modules/marketMcp";
import { BBK_ID_MAP } from "../../constants/bbk";
import { copyToClipboard } from "../../utils/clipboard";

const { Dragger } = Upload;

const MCP_JSON_TEMPLATE = `{
  "mcpServers": {
    "demo-mcp": {
      "type": "sse",
      "name": "测试MCP服务",
      "url": "http://test.com",
      "advanced": {
        "headers": {
          "Token": "xxx"
        },
        "transport": "sse"
      }
    }
  }
}`;

type ParsedUploadConfig = {
  suggestedName: string;
  hasRawName: boolean;
  /** 文件上传时为原 File；粘贴模式下为 null */
  file: File | null;
  /** 粘贴模式下为原始 JSON 文本；文件上传时为 null */
  rawJson: string | null;
};

function baseNameFromFile(fileName: string): string {
  return fileName.replace(/\.(json|mcp\.json)$/i, "");
}

function inferTransport(config: Record<string, unknown>): "stdio" | "streamable_http" | "sse" | null {
  const rawTransport =
    (config.transport as string | undefined) ||
    (config.type as string | undefined) ||
    ((config.advanced as Record<string, unknown> | undefined)?.transport as string | undefined);

  const normalized = rawTransport?.toLowerCase();
  if (normalized === "stdio") return "stdio";
  if (normalized === "sse") return "sse";
  if (normalized === "streamable_http" || normalized === "streamable-http") {
    return "streamable_http";
  }
  if (typeof config.command === "string" && config.command.trim()) return "stdio";
  if (typeof config.url === "string" && config.url.trim()) return "streamable_http";
  return null;
}

/**
 * 解析 MCP JSON 内容，校验格式并提取建议的 name。
 * 文件上传走 parseMcpUploadFile，粘贴上传走 parseMcpUploadRaw —— 两者复用同一段校验逻辑。
 */
function extractMcpNameAndConfig(
  raw: string,
  fallbackName: string,
): { suggestedName: string; hasRawName: boolean } {
  const parsed = JSON.parse(raw) as Record<string, unknown>;

  let candidateName = "";
  let candidateConfig: Record<string, unknown> | null = null;

  const mcpServers = parsed.mcpServers;
  if (
    mcpServers &&
    typeof mcpServers === "object" &&
    !Array.isArray(mcpServers)
  ) {
    const entries = Object.entries(mcpServers as Record<string, unknown>);
    const [, firstValue] = entries[0] || [];
    if (firstValue && typeof firstValue === "object" && !Array.isArray(firstValue)) {
      candidateConfig = firstValue as Record<string, unknown>;
      candidateName =
        typeof candidateConfig.name === "string" ? candidateConfig.name : "";
    }
  }

  if (!candidateConfig) {
    const config =
      parsed.config && typeof parsed.config === "object" && !Array.isArray(parsed.config)
        ? (parsed.config as Record<string, unknown>)
        : parsed;
    candidateConfig = config;
    candidateName =
      typeof config.name === "string"
        ? config.name
        : typeof parsed.name === "string"
          ? parsed.name
          : "";
  }

  if (!candidateConfig) {
    throw new Error("文件格式不正确");
  }

  const transport = inferTransport(candidateConfig);
  if (!transport) {
    throw new Error("文件格式不正确：无法识别连接方式");
  }

  const finalName = candidateName?.trim() || fallbackName;
  return {
    suggestedName: finalName,
    hasRawName: !!candidateName?.trim(),
  };
}

function parseMcpUploadFile(file: File, raw: string): ParsedUploadConfig {
  const fallbackName = baseNameFromFile(file.name);
  const { suggestedName, hasRawName } = extractMcpNameAndConfig(raw, fallbackName);
  return {
    suggestedName,
    hasRawName,
    file,
    rawJson: null,
  };
}

function parseMcpUploadRaw(raw: string): ParsedUploadConfig {
  const { suggestedName, hasRawName } = extractMcpNameAndConfig(raw, "");
  return {
    suggestedName,
    hasRawName,
    file: null,
    rawJson: raw,
  };
}

interface MCPUploadModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function MCPUploadModal({
  open,
  onClose,
  onSuccess,
}: MCPUploadModalProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [parsedUpload, setParsedUpload] = useState<ParsedUploadConfig | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [jsonTemplateCopied, setJsonTemplateCopied] = useState(false);
  const [uploadMode, setUploadMode] = useState<"file" | "paste">("file");
  const [pasteContent, setPasteContent] = useState<string>("");
  const [pasteError, setPasteError] = useState<string>("");

  const handleCopyJsonTemplate = async () => {
    const success = await copyToClipboard(MCP_JSON_TEMPLATE);
    if (success) {
      setJsonTemplateCopied(true);
      setTimeout(() => setJsonTemplateCopied(false), 2000);
    } else {
      message.error("复制 JSON 模板失败");
    }
  };

  // 解析上传的 JSON 文件
  const parseFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const parsed = parseMcpUploadFile(file, content);
        setParsedUpload(parsed);
        setFileName(file.name);

        form.setFieldsValue({
          name: parsed.suggestedName,
          chinese_name: "",
          description: "",
          guidance: "",
        });

        message.success("文件解析成功");
      } catch (error) {
        setParsedUpload(null);
        setFileName("");
        message.error(error instanceof Error ? error.message : "无法解析 JSON 文件");
      }
    };
    reader.readAsText(file);
    return false; // 阻止自动上传
  };

  // 解析粘贴的 JSON 内容
  const handlePasteChange = (value: string) => {
    setPasteContent(value);
    if (!value.trim()) {
      setParsedUpload(null);
      setPasteError("");
      return;
    }
    try {
      const parsed = parseMcpUploadRaw(value);
      setParsedUpload(parsed);
      setPasteError("");
      // 粘贴模式下 JSON 是权威：只要 JSON 里能解析出 name，就把表单 name 同步过去，
      // 让用户在 JSON 里改 name 时下方输入框跟着变。
      if (parsed.hasRawName) {
        form.setFieldsValue({ name: parsed.suggestedName });
      }
    } catch (error) {
      setParsedUpload(null);
      setPasteError(error instanceof Error ? error.message : "JSON 解析失败");
    }
  };

  // 切换上传模式：清掉对侧已经解析好的状态，避免歧义
  const handleModeChange = (mode: "file" | "paste") => {
    setUploadMode(mode);
    setParsedUpload(null);
    setFileName("");
    setPasteError("");
    if (mode === "paste") {
      // 切到粘贴模式时把模板预填进去，并立刻解析一次同步 name 字段
      setPasteContent(MCP_JSON_TEMPLATE);
      try {
        const parsed = parseMcpUploadRaw(MCP_JSON_TEMPLATE);
        setParsedUpload(parsed);
        if (parsed.hasRawName) {
          form.setFieldsValue({ name: parsed.suggestedName });
        }
      } catch {
        // 模板本身合法，不会走到这里；万一异常也安静失败
      }
    } else {
      setPasteContent("");
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      if (!parsedUpload) {
        message.error(
          uploadMode === "file" ? "请先上传 MCP 配置文件" : "请粘贴 MCP JSON 配置",
        );
        return;
      }

      setLoading(true);

      // 严格按当前 tab 决定上传方式，避免依赖 parsedUpload 内部字段做隐式判断
      const payload =
        uploadMode === "file"
          ? { file: parsedUpload.file as File }
          : { raw_json: parsedUpload.rawJson as string };

      const result = await marketMcpApi.uploadMCP({
        name: values.name,
        chinese_name: values.chinese_name,
        description: values.description,
        guidance: values.guidance,
        bbk_ids: values.bbk_ids,
        ...payload,
      });

      if (result.version_unchanged) {
        message.info("当前内容已是最新，无需重复上传");
      } else {
        message.success("上传成功");
      }
      form.resetFields();
      setParsedUpload(null);
      setFileName("");
      setPasteContent("");
      setPasteError("");
      if (!result.version_unchanged) {
        onSuccess();
      }
      onClose();
    } catch (err) {
      console.error("上传失败:", err);
      message.error("上传失败");
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    form.resetFields();
    setParsedUpload(null);
    setFileName("");
    setJsonTemplateCopied(false);
    setUploadMode("file");
    setPasteContent("");
    setPasteError("");
    onClose();
  };

  return (
    <Modal
      open={open}
      onCancel={handleClose}
      title="上传 MCP 连接器"
      width={600}
      footer={[
        <Button key="cancel" onClick={handleClose}>
          取消
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          上传
        </Button>,
      ]}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={
          <span>
            上传 .json 文件或直接粘贴 JSON 配置，系统将自动解析名称与标识。
            <Button
              type="link"
              size="small"
              onClick={() => void handleCopyJsonTemplate()}
              icon={jsonTemplateCopied ? <CheckOutlined /> : <CopyOutlined />}
              style={{ paddingInline: 4, height: "auto" }}
            >
              {jsonTemplateCopied ? "已复制" : "复制 JSON 模板"}
            </Button>
          </span>
        }
      />

      <Segmented
        block
        value={uploadMode}
        onChange={(value) => handleModeChange(value as "file" | "paste")}
        options={[
          { label: "文件上传", value: "file" },
          { label: "粘贴 JSON", value: "paste" },
        ]}
        style={{ marginBottom: 16 }}
      />

      {uploadMode === "file" ? (
        <>
          <Dragger
            accept=".json"
            beforeUpload={parseFile}
            showUploadList={false}
            style={{ marginBottom: 16 }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此区域</p>
            <p className="ant-upload-hint">支持 .json 格式的 MCP 配置文件</p>
          </Dragger>

          {fileName && (
            <Alert
              type="success"
              message={`已解析文件: ${fileName}`}
              style={{ marginBottom: 16 }}
              showIcon
            />
          )}
        </>
      ) : (
        <>
          <Input.TextArea
            value={pasteContent}
            onChange={(e) => handlePasteChange(e.target.value)}
            placeholder="粘贴 MCP JSON 配置，支持 mcpServers 或顶层 config 结构"
            rows={10}
            style={{
              marginBottom: 12,
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
              fontSize: 12,
            }}
          />
          {pasteError ? (
            <Alert
              type="error"
              message={pasteError}
              style={{ marginBottom: 16 }}
              showIcon
            />
          ) : parsedUpload && parsedUpload.rawJson ? (
            <Alert
              type="success"
              message={`已解析配置: ${parsedUpload.suggestedName || "(未识别名称)"}`}
              style={{ marginBottom: 16 }}
              showIcon
            />
          ) : null}
        </>
      )}

      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label={
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              英文名称
              <Tooltip title="英文名称 = json 文件名 = 配置里的 name">
                <InfoCircleOutlined style={{ color: "#8c8c8c", cursor: "help" }} />
              </Tooltip>
            </span>
          }
          rules={[{ required: true, message: "请输入英文名称" }]}
        >
          <Input
            placeholder="输入英文名称"
            disabled={uploadMode === "paste" || (uploadMode === "file" && !!parsedUpload?.hasRawName)}
          />
        </Form.Item>

        <Form.Item name="chinese_name" label="中文名称（可选）">
          <Input placeholder="输入中文名称（可选）" />
        </Form.Item>

        <Form.Item name="description" label="描述（可选）">
          <Input.TextArea placeholder="输入描述（可选）" rows={3} />
        </Form.Item>

        <Form.Item name="guidance" label="使用指引（可选）">
          <Input.TextArea placeholder="输入使用指引（可选）" rows={4} />
        </Form.Item>

        <Form.Item name="bbk_ids" label="所属分行" rules={[{ required: true, message: "请选择所属分行" }]}>
          <Select
            mode="multiple"
            allowClear
            placeholder="设置 MCP 所属的分行"
            options={BBK_ID_MAP}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
