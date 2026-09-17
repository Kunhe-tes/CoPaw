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
  existing_version?: string;
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

interface ParsedConflict {
  isConflict: boolean;
  message: string;
  existingCreatorName?: string;
  existingCreatorId?: string;
}

interface PublishMCPModalProps {
  open: boolean;
  clientKey: string;
  clientName: string;
  userId?: string;
  onClose: () => void;
  onSuccess: () => void;
}

/**
 * 从 HTTP 409 响应中提取冲突详情。
 *
 * FastAPI 把 `HTTPException(detail=...)` 序列化为 `{detail: ...}`，
 * 所以优先从 `data.detail` 取结构化字段；同时兼容上游已扁平化的情况。
 */
function extractConflictDetail(err: unknown): ConflictDetail | null {
  const httpErr = err as HttpError;
  if (httpErr?.status !== 409 || !httpErr?.data) {
    return null;
  }

  const raw = httpErr.data as { detail?: ConflictDetail | string } & ConflictDetail;
  const detailField = raw.detail;
  if (detailField && typeof detailField === "object") {
    return detailField;
  }
  // 兼容已扁平化的响应体
  if (raw.existing_name) {
    return raw;
  }
  return null;
}

/**
 * 将冲突详情转换为用户可见文案。
 */
function buildConflictMessage(
  conflict: ConflictDetail,
  isOwnMcp: boolean,
  creatorLabel?: string,
): string {
  const existingName = conflict.existing_name;
  const existingVersion = conflict.existing_version;
  const fallbackMsg = conflict.message;

  if (existingName) {
    const versionSuffix = existingVersion ? `（当前市场版本 v${existingVersion}）` : "";
    return isOwnMcp
      ? `您之前已发布过「${existingName}」${versionSuffix}`
      : `「${existingName}」已由 ${creatorLabel || "其他用户"} 发布${versionSuffix}`;
  }
  return fallbackMsg || "市场中已存在同名 MCP";
}

export function PublishMCPModal({
  open,
  clientKey,
  clientName,
  userId,
  onClose,
  onSuccess,
}: PublishMCPModalProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  const doPublish = async (overwrite: boolean) => {
    if (!clientKey) {
      message.warning("未找到可同步的 MCP");
      return;
    }

    try {
      const values = await form.validateFields();
      setLoading(true);

      const result = await myMcpApi.publishSingleToMarket(clientKey, {
        bbk_ids: values.bbk_ids,
        overwrite,
      });
      if (result.version_unchanged) {
        message.info("当前内容已是最新，无需重复同步");
      } else {
        message.success("同步成功");
        onSuccess();
      }
    } catch (err) {
      // 尝试提取 409 冲突详情
      const conflict = extractConflictDetail(err);

      // 兜底：检查错误消息是否包含冲突关键词
      if (!conflict) {
        const errMsg =
          (err instanceof Error ? err.message : String(err)) || "同步失败";
        if (errMsg.includes("already exists") || errMsg.includes("同名")) {
          handleConflict({ existing_name: undefined } as ConflictDetail, errMsg);
          return;
        }
        console.error("同步失败:", err);
        message.error(errMsg);
        return;
      }

      // 有结构化冲突信息，走冲突弹窗
      handleConflict(conflict);
    } finally {
      setLoading(false);
    }
  };

  /**
   * 显示同名冲突确认弹窗。
   */
  const handleConflict = (
    conflict: ConflictDetail,
    fallbackMsg?: string,
  ) => {
    setLoading(false);

    const isOwnMcp =
      userId && conflict.existing_creator_id
        ? conflict.existing_creator_id === userId
        : false;

    // 拼装创建者显示名：优先 "name/id"，缺一项就只显示另一项。
    const creatorName = conflict.existing_creator_name?.trim();
    const creatorId = conflict.existing_creator_id?.trim();
    const existingCreator =
      creatorName && creatorId
        ? `${creatorName}/${creatorId}`
        : creatorName || creatorId || undefined;

    const conflictMsg = buildConflictMessage(conflict, isOwnMcp, existingCreator) || fallbackMsg || "市场中已存在同名 MCP";

    Modal.confirm({
      title: isOwnMcp ? "确认更新" : "确认覆盖",
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>{conflictMsg}</p>
          <p>
            {isOwnMcp
              ? "是否使用当前版本替换市场中的已有内容？"
              : "是否用当前版本替换已有的同名 MCP？此操作不可撤销。"}
          </p>
        </div>
      ),
      okText: isOwnMcp ? "确认更新" : "确认覆盖",
      okType: isOwnMcp ? "primary" : "danger",
      cancelText: "取消",
      onOk: () => {
        void doPublish(true);
      },
    });
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
