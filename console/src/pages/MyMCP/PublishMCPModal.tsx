/**
 * 同步 MCP 到市场弹窗
 */
import { useState } from "react";
import { Modal, Form, Select, Button, message, Typography, Alert } from "antd";
import { RocketOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import { myMcpApi } from "../../api/modules/myMcp";
import { BBK_ID_MAP } from "../../constants/bbk";

const { Text } = Typography;

/** 带有 HTTP 元数据的错误类型 */
interface ConflictDetail {
  message?: string;
  existing_item_id?: string;
  existing_name?: string;
  existing_creator_id?: string;
  existing_creator_name?: string;
}

interface HttpError extends Error {
  status?: number;
  /**
   * FastAPI HTTPException 序列化后的响应体形如 `{ detail: {...} }`，
   * 这里允许 data 同时承载嵌套结构与扁平结构以便兼容上游差异。
   */
  data?:
    | ConflictDetail
    | { detail?: ConflictDetail | string };
}

interface PublishMCPModalProps {
  open: boolean;
  clientKey: string;
  clientName: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function PublishMCPModal({
  open,
  clientKey,
  clientName,
  onClose,
  onSuccess,
}: PublishMCPModalProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  /**
   * 从 HttpError 中提取同名冲突信息。
   *
   * FastAPI 把 `HTTPException(detail=...)` 序列化为 `{detail: ...}`，
   * 所以优先从 `data.detail` 取结构化字段；同时兼容上游已扁平化的情况。
   *
   * 注意：用户可见文案统一在前端拼接（中文），后端 message 仅作为兜底，
   * 避免把后端的英文 exception 字符串直接展示给用户。
   */
  const parseConflictError = (err: unknown) => {
    const httpErr = err as HttpError;

    // HTTP 409 表示同名冲突
    if (httpErr?.status === 409 && httpErr?.data) {
      // 先尝试 data.detail（FastAPI 原生格式），再回退到 data 自身
      const raw = httpErr.data as {
        detail?: ConflictDetail | string;
      } & ConflictDetail;
      const detailField = raw.detail;
      const conflict: ConflictDetail =
        detailField && typeof detailField === "object"
          ? detailField
          : raw;

      const existingName = conflict.existing_name;
      // 拼装显示名：优先 "name/id"，缺一项就只显示另一项。
      // 例如：张三/zhangsan001、只有名字则显示 张三、只有 id 则显示 zhangsan001
      const creatorName = conflict.existing_creator_name?.trim();
      const creatorId = conflict.existing_creator_id?.trim();
      const existingCreator =
        creatorName && creatorId
          ? `${creatorName}/${creatorId}`
          : creatorName || creatorId || undefined;

      // 优先用结构化字段拼中文文案；都拿不到再退回后端/纯字符串 detail
      const fallbackMsg =
        conflict.message ||
        (typeof detailField === "string" ? detailField : undefined);
      const message = existingName
        ? `同名 MCP "${existingName}" 已存在`
        : fallbackMsg || "同名 MCP 已存在";

      return {
        isConflict: true,
        message,
        existingCreatorName: existingCreator,
      };
    }

    // 兜底：检查错误消息
    const errMsg =
      (err instanceof Error ? err.message : String(err)) || "同步失败";
    if (errMsg.includes("already exists") || errMsg.includes("同名")) {
      return {
        isConflict: true,
        message: "同名 MCP 已存在",
        existingCreatorName: undefined,
      };
    }

    return {
      isConflict: false,
      message: errMsg,
      existingCreatorName: undefined,
    };
  };

  const doPublish = async (overwrite: boolean) => {
    if (!clientKey) {
      message.warning("未找到可同步的 MCP");
      return;
    }

    try {
      const values = await form.validateFields();
      setLoading(true);

      await myMcpApi.publishSingleToMarket(clientKey, {
        bbk_ids: values.bbk_ids,
        overwrite,
      });
      message.success("同步成功");
      onSuccess();
    } catch (err) {
      const { isConflict, message: conflictMsg, existingCreatorName } =
        parseConflictError(err);

      if (isConflict) {
        setLoading(false);
        // 弹窗确认是否覆盖
        Modal.confirm({
          title: "同名 MCP 已存在",
          icon: <ExclamationCircleOutlined />,
          content: (
            <div>
              <p>{conflictMsg}</p>
              {existingCreatorName && (
                <p>
                  原始创建者：
                  <Text strong>{existingCreatorName}</Text>
                </p>
              )}
              <p>是否覆盖已有的同名 MCP？覆盖后原配置将被替换。</p>
            </div>
          ),
          okText: "覆盖",
          okType: "primary",
          cancelText: "取消",
          onOk: () => {
            void doPublish(true);
          },
        });
      } else {
        console.error("同步失败:", err);
        message.error(conflictMsg);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    await doPublish(false);
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={<><RocketOutlined /> 同步到市场</>}
      width={500}
      footer={[
        <Button key="cancel" onClick={onClose}>
          关闭
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          同步
        </Button>,
      ]}
    >
      <Alert
        type="info"
        message="将当前 MCP 同步到应用市场"
        style={{ marginBottom: 16 }}
        showIcon
      />

      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">当前 MCP</Text>
        <div style={{ marginTop: 6, fontWeight: 500 }}>
          {clientName || clientKey}
        </div>
      </div>

      <Form form={form} layout="vertical">
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
