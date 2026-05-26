import { Modal, Form, Input, Select, Button, Spin } from "antd";
import { useState, useEffect } from "react";
import { marketApi, PublishSkillRequest, type Category } from "../../api/modules/market";
import { BBK_ID_MAP } from "../../constants/bbk";
import { useIframeStore } from "../../stores/iframeStore";

const { TextArea } = Input;

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

  const handleSubmit = async () => {
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
      };
      await marketApi.publishSkill(sourceId, payload);
      form.resetFields();
      onSuccess();
      onClose();
    } catch (err) {
      console.error("Publish failed:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={initialData ? "同步到市场" : "上架技能"}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          上架
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
