import { Modal, Form, Input, Select, Button, Spin, message, Typography, Alert } from "antd";
import { ExclamationCircleOutlined } from "@ant-design/icons";
import { useState, useEffect } from "react";
import { marketApi, PublishSkillRequest, type Category } from "../../api/modules/market";
import { BBK_ID_MAP } from "../../constants/bbk";
import { useIframeStore } from "../../stores/iframeStore";

const { TextArea } = Input;
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

/**
 * 从 HTTP 409 响应中提取冲突详情。
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
  isOwnSkill: boolean,
  creatorLabel?: string,
): string {
  const existingName = conflict.existing_name;
  const existingVersion = conflict.existing_version;
  const fallbackMsg = conflict.message;

  if (existingName) {
    const versionSuffix = existingVersion ? `（当前市场版本 v${existingVersion}）` : "";
    return isOwnSkill
      ? `您之前已发布过「${existingName}」${versionSuffix}`
      : `「${existingName}」已由 ${creatorLabel || "其他用户"} 发布${versionSuffix}`;
  }
  return fallbackMsg || "市场中已存在同名技能";
}

interface PublishModalProps {
  open: boolean;
  sourceId: string;
  userId: string;
  onClose: () => void;
  onSuccess: () => void;
  // 同步模式：预填技能数据
  initialData?: {
    skillName: string;
    description: string;
    skillJson: Record<string, unknown>;
    skillMd: string;
    skillDirName?: string; // 技能目录名，用于同步整个目录
  };
}

export function PublishModal({ open, sourceId, userId, onClose, onSuccess, initialData }: PublishModalProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loadingCategories, setLoadingCategories] = useState(false);
  const resolvedUserName = useIframeStore((state) => state.userName);
  const resolvedClawName = useIframeStore((state) => state.clawName);
  const userName = resolvedUserName || resolvedClawName || userId;

  // 加载分类列表
  useEffect(() => {
    if (open) {
      setLoadingCategories(true);
      marketApi.listCategories(sourceId)
        .then(setCategories)
        .catch(console.error)
        .finally(() => setLoadingCategories(false));
    }
  }, [open, sourceId]);

  // 当 initialData 变化时预填表单
  useEffect(() => {
    if (open && initialData) {
      form.setFieldsValue({
        name: initialData.skillName,
        description: initialData.description,
        skill_md: initialData.skillMd,
      });
    } else if (open) {
      form.resetFields();
    }
  }, [open, initialData, form]);

  const doPublish = async (overwrite: boolean) => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      const payload: PublishSkillRequest = {
        name: values.name,
        description: values.description,
        creator_id: userId,
        creator_name: userName,
        category_id: values.category_id,
        bbk_ids: values.bbk_ids,
        skill_json: initialData?.skillJson || {},
        skill_md: values.skill_md,
        skill_name: initialData?.skillDirName,
        agent_id: "default",
        overwrite,
      };
      await marketApi.publishSkill(sourceId, payload);
      message.success(initialData ? "同步成功" : "上架成功");
      form.resetFields();
      onClose();
      onSuccess();
    } catch (err) {
      // Ant Design 表单校验失败时直接返回，不进入冲突/错误逻辑
      if (err && typeof err === "object" && "errorFields" in err) {
        return;
      }

      // 尝试提取 409 冲突详情
      const conflict = extractConflictDetail(err);

      // 兜底：检查错误消息是否包含冲突关键词
      if (!conflict) {
        const errMsg =
          (err instanceof Error ? err.message : String(err)) || "发布失败";
        if (errMsg.includes("already exists") || errMsg.includes("同名")) {
          handleConflict({ existing_name: undefined } as ConflictDetail, errMsg);
          return;
        }
        console.error("发布失败:", err);
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

    const isOwnSkill =
      userId && conflict.existing_creator_id
        ? conflict.existing_creator_id === userId
        : false;

    const creatorName = conflict.existing_creator_name?.trim();
    const creatorId = conflict.existing_creator_id?.trim();
    const existingCreator =
      creatorName && creatorId
        ? `${creatorName}/${creatorId}`
        : creatorName || creatorId || undefined;

    const conflictMsg = buildConflictMessage(conflict, isOwnSkill, existingCreator) || fallbackMsg || "市场中已存在同名技能";

    Modal.confirm({
      title: isOwnSkill ? "确认更新" : "确认覆盖",
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>{conflictMsg}</p>
          <p>
            {isOwnSkill
              ? "是否使用当前版本替换市场中的已有内容？"
              : "是否用当前版本替换已有的同名技能？此操作不可撤销。"}
          </p>
        </div>
      ),
      okText: isOwnSkill ? "确认更新" : "确认覆盖",
      okType: isOwnSkill ? "primary" : "danger",
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
      title={initialData ? "同步到市场" : "上架技能"}
      footer={[
        <Button key="cancel" onClick={onClose}>
          关闭
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          {initialData ? "同步" : "上架"}
        </Button>,
      ]}
    >
      <Form form={form} layout="vertical">
        <Form.Item name="name" label="技能名称" rules={[{ required: true }]}>
          <Input disabled={!!initialData} />
        </Form.Item>
        <Form.Item name="description" label="描述">
          <TextArea rows={2} />
        </Form.Item>
        <Form.Item name="category_id" label="分类" rules={[{ required: true, message: "请选择分类" }]}>
          {loadingCategories ? (
            <Spin size="small" />
          ) : (
            <Select
              placeholder="选择分类"
              options={categories.map((c) => ({ label: c.name, value: c.id }))}
            />
          )}
        </Form.Item>
        <Form.Item name="bbk_ids" label="可见机构">
          <Select
            mode="multiple"
            allowClear
            placeholder="不选择则全员可见"
            options={BBK_ID_MAP}
          />
        </Form.Item>
        <Form.Item name="skill_md" label="技能说明">
          <TextArea rows={6} placeholder="Markdown 格式" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
