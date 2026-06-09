import { useState, useEffect } from "react";
import { Modal, Upload, Select, message, Spin, Button } from "antd";
import { InboxOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import type { UploadProps } from "antd";
import { marketApi, type Category } from "../../../api/modules/market";

interface UploadSkillModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  sourceId: string;
}

const { Dragger } = Upload;

export default function UploadSkillModal({
  open,
  onClose,
  onSuccess,
  sourceId,
}: UploadSkillModalProps) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loadingCategories, setLoadingCategories] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [conflictNames, setConflictNames] = useState<string[]>([]);

  const loadCategories = async () => {
    setLoadingCategories(true);
    try {
      const data = await marketApi.listCategories(sourceId);
      setCategories(data);
      if (data.length > 0) {
        setSelectedCategory(data[0].id);
      }
    } catch (err) {
      console.error("Failed to load categories:", err);
    } finally {
      setLoadingCategories(false);
    }
  };

  useEffect(() => {
    if (open) {
      loadCategories();
      setFile(null);
      setSelectedCategory(null);
      setShowConfirm(false);
      setConflictNames([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleUpload = async (overwrite: boolean = false) => {
    if (!file) {
      message.error("请选择 zip 文件");
      return;
    }
    if (selectedCategory === null) {
      message.error("请选择技能分类");
      return;
    }

    setUploading(true);

    try {
      message.loading({ content: `正在上传 ${file.name}...`, key: "upload" });
      const result = await marketApi.uploadSkillToMarket(
        sourceId,
        file,
        {
          category_id: selectedCategory,
          overwrite,
        }
      );

      // 检查冲突（仅在 overwrite=false 时可能返回）
      const conflicts = Array.isArray(result.conflicts) ? result.conflicts : [];
      if (conflicts.length > 0) {
        message.destroy("upload");
        const names = conflicts.map((c) => c.skill_name);
        setConflictNames(names);
        setShowConfirm(true);
        return;
      }

      // 成功
      if (result.count > 0) {
        const actionText = overwrite ? "更新" : "导入";
        message.success({ content: `上传成功，${actionText} ${result.count} 个技能`, key: "upload" });
      } else {
        message.info({ content: "未导入新技能，可能已存在", key: "upload" });
      }
      onSuccess();
      onClose();
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "上传失败";
      message.error({ content: errorMsg, key: "upload" });
    } finally {
      setUploading(false);
    }
  };

  const handleConfirmUpload = () => {
    // 用户确认覆盖，执行上传
    setShowConfirm(false);
    handleUpload(true);
  };

  const uploadProps: UploadProps = {
    accept: ".zip",
    showUploadList: false,
    beforeUpload: (file) => {
      const isZip = file.name.toLowerCase().endsWith(".zip");
      if (!isZip) {
        message.error("仅支持 .zip 文件");
        return false;
      }
      setFile(file);
      setShowConfirm(false);
      setConflictNames([]);
      return false;
    },
    onRemove: () => {
      setFile(null);
      setShowConfirm(false);
      setConflictNames([]);
    },
    fileList: file ? [file as any] : [],
  };

  return (
    <Modal
      title="上传技能到市场"
      open={open}
      onCancel={() => {
        setShowConfirm(false);
        onClose();
      }}
      onOk={showConfirm ? undefined : () => handleUpload(false)}
      okText={showConfirm ? undefined : "上传"}
      cancelText={showConfirm ? undefined : "取消"}
      okButtonProps={{
        loading: uploading,
        disabled: !file || selectedCategory === null,
      }}
      footer={showConfirm ? null : undefined}
      destroyOnClose
    >
      {showConfirm ? (
        <div style={{ padding: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <ExclamationCircleOutlined style={{ fontSize: 24, color: "#faad14" }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: 16 }}>发现同名技能</div>
              <div style={{ color: "#8c8c8c", fontSize: 13 }}>
                以下技能已存在：{conflictNames.join(", ")}
              </div>
            </div>
          </div>
          <div style={{ marginBottom: 16, color: "#595959" }}>
            覆盖将更新现有技能版本并创建版本快照，您可以在版本历史中查看和回滚。
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
            <Button onClick={() => setShowConfirm(false)} disabled={uploading}>
              取消
            </Button>
            <Button type="primary" onClick={handleConfirmUpload} loading={uploading}>
              确认覆盖
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div style={{ marginBottom: 16 }}>
            <Dragger {...uploadProps} style={{ marginBottom: 16 }}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">拖拽 .zip 文件到此处</p>
              <p className="ant-upload-hint">或点击选择文件（需包含 SKILL.md）</p>
            </Dragger>
            {file && (
              <p style={{ color: "#52c41a", marginTop: 8 }}>
                已选择: {file.name}
              </p>
            )}
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", marginBottom: 8 }}>
              技能分类 <span style={{ color: "#ff4d4f" }}>*</span>
            </label>
            {loadingCategories ? (
              <Spin size="small" />
            ) : (
              <Select
                style={{ width: "100%" }}
                value={selectedCategory}
                onChange={setSelectedCategory}
                placeholder="选择分类"
                options={categories.map((c) => ({ label: c.name, value: c.id }))}
              />
            )}
          </div>

          <p style={{ color: "#8c8c8c", fontSize: 12 }}>
            提示：技能名称和描述将从 zip 包中的 SKILL.md frontmatter 自动解析
          </p>
        </>
      )}
    </Modal>
  );
}