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
} from "antd";
import {
  InboxOutlined,
  CheckOutlined,
  CopyOutlined,
} from "@ant-design/icons";
import { ChevronDown, ChevronRight } from "lucide-react";
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
  file: File;
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

function parseMcpUploadFile(file: File, raw: string): ParsedUploadConfig {
  const parsed = JSON.parse(raw) as Record<string, unknown>;
  const fallbackName = baseNameFromFile(file.name);

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
    file,
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
  const [showJsonTemplate, setShowJsonTemplate] = useState(false);

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

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      if (!parsedUpload) {
        message.error("请先上传 MCP 配置文件");
        return;
      }

      setLoading(true);

      await marketMcpApi.uploadMCP({
        name: values.name,
        chinese_name: values.chinese_name,
        description: values.description,
        guidance: values.guidance,
        bbk_ids: values.bbk_ids,
        file: parsedUpload.file,
      });

      message.success("上传成功");
      form.resetFields();
      setParsedUpload(null);
      setFileName("");
      onSuccess();
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
    setShowJsonTemplate(false);
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
        message="上传 .json 格式的 MCP 配置文件，系统将自动解析名称与标识。"
        style={{ marginBottom: 16 }}
        showIcon
      />

      <div
        style={{
          marginBottom: 16,
          padding: "14px 16px",
          borderRadius: 8,
          border: "1px solid #ffe7ba",
          background: "#fffbe6",
        }}
      >
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "#8b6d1f" }}>
          需要帮助？可以复制 JSON 模板，按需修改后上传。
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: showJsonTemplate ? 12 : 0 }}>
          <Button onClick={() => void handleCopyJsonTemplate()} style={{ borderRadius: 8 }}>
            {jsonTemplateCopied ? <CheckOutlined /> : <CopyOutlined />}
            {jsonTemplateCopied ? "模板已复制" : "复制 JSON 模板"}
          </Button>
          <Button
            type="text"
            onClick={() => setShowJsonTemplate((prev) => !prev)}
            style={{ borderRadius: 8, color: "#8b6d1f" }}
          >
            {showJsonTemplate ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {showJsonTemplate ? "隐藏模板" : "查看模板"}
          </Button>
        </div>
        {showJsonTemplate ? (
          <div style={{ maxHeight: 180, overflow: "auto" }}>
            <pre
              style={{
                margin: 0,
                padding: 12,
                borderRadius: 8,
                border: "1px solid #f0ebe1",
                background: "#ffffff",
                fontSize: 12,
                lineHeight: 1.6,
                color: "#434a57",
                overflowX: "auto",
              }}
            >
              <code>{MCP_JSON_TEMPLATE}</code>
            </pre>
          </div>
        ) : null}
      </div>

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

      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="英文名称 *（英文名称 = json 文件名 = 配置里的 name）"
          rules={[{ required: true, message: "请输入英文名称" }]}
        >
          <Input
            placeholder="输入英文名称"
            disabled={!!parsedUpload?.hasRawName}
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

        <Form.Item name="bbk_ids" label="可见机构">
          <Select
            mode="multiple"
            allowClear
            placeholder="不选择则全员可见"
            options={BBK_ID_MAP}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
