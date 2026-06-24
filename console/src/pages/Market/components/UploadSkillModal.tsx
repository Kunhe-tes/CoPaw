import { useState, useEffect } from "react";
import { Modal, Upload, Select, Input, message, Spin, Button, Form, Tooltip, Alert } from "antd";
import { InboxOutlined, ExclamationCircleOutlined, PlusOutlined, InfoCircleOutlined } from "@ant-design/icons";
import type { UploadProps } from "antd";
import { marketApi, type Category } from "../../../api/modules/market";

interface UploadSkillModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  onCategoryAdded?: () => void;
  sourceId: string;
}

const { Dragger } = Upload;

export default function UploadSkillModal({
  open,
  onClose,
  onSuccess,
  onCategoryAdded,
  sourceId,
}: UploadSkillModalProps) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [cnName, setCnName] = useState("");
  const [skillId, setSkillId] = useState("");
  const [skillName, setSkillName] = useState("");
  const [skillIdReused, setSkillIdReused] = useState(false);
  const [parsingZip, setParsingZip] = useState(false);
  const [skillIdUsedCount, setSkillIdUsedCount] = useState(0);
  const [skillIdUsedBy, setSkillIdUsedBy] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [loadingCategories, setLoadingCategories] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [conflictNames, setConflictNames] = useState<string[]>([]);
  const [skillExists, setSkillExists] = useState(false);  // 同名技能已存在（允许覆盖）
  const [addCategoryModalOpen, setAddCategoryModalOpen] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [addingCategory, setAddingCategory] = useState(false);

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
      setCnName("");
      setSkillId("");
      setSkillName("");
      setSkillIdReused(false);
      setSkillIdUsedCount(0);
      setSkillIdUsedBy([]);
      setSelectedCategory(null);
      setShowConfirm(false);
      setConflictNames([]);
      setSkillExists(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // 解析 zip 文件
  const parseZipFile = async (selectedFile: File) => {
    setParsingZip(true);
    try {
      const result = await marketApi.parseSkillZip(sourceId, selectedFile, true);
      if (result.error) {
        message.error(result.error);
        setParsingZip(false);
        return;
      }

      // 设置预解析结果
      setCnName(result.cn_name || result.skill_name || "");
      setSkillId(result.skill_id || "");
      setSkillName(result.skill_name || "");
      setSkillIdReused(result.skill_id_reused || false);
      setSkillIdUsedCount(result.skill_id_used_count || 0);
      setSkillIdUsedBy(result.skill_id_used_by || []);
      setSkillExists(result.exists || false);

      // 同名技能存在时，直接显示确认弹窗
      if (result.exists && result.skill_id_used_count === 0) {
        setConflictNames([result.skill_name || ""]);
        setShowConfirm(true);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "解析失败";
      message.error(errorMsg);
    } finally {
      setParsingZip(false);
    }
  };

  const handleAddCategory = async () => {
    const trimmed = newCategoryName.trim();
    if (!trimmed) {
      message.error("请输入分类名称");
      return;
    }
    setAddingCategory(true);
    try {
      const newCat = await marketApi.createCategory(sourceId, trimmed);
      message.success(`分类 "${newCat.name}" 创建成功`);
      setAddCategoryModalOpen(false);
      setNewCategoryName("");
      await loadCategories();
      setSelectedCategory(newCat.id);
      onCategoryAdded?.();
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "创建失败";
      message.error(errorMsg);
    } finally {
      setAddingCategory(false);
    }
  };

  const handleUpload = async (overwrite: boolean = false) => {
    if (!file) {
      message.error("请选择 zip 文件");
      return;
    }
    if (selectedCategory === null) {
      message.error("请选择技能分类");
      return;
    }
    if (!cnName.trim()) {
      message.error("请输入中文名称");
      return;
    }

    // 同名技能存在时，显示确认弹窗（和我的技能一样）
    if (skillExists && !overwrite) {
      setConflictNames([skillName]);
      setShowConfirm(true);
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
          cn_name: cnName.trim(),
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
      if (result.version_unchanged) {
        message.info({ content: "当前内容已是最新，无需重复上传", key: "upload" });
      } else if (result.count > 0) {
        const actionText = overwrite ? "更新" : "导入";
        message.success({ content: `上传成功，${actionText} ${result.count} 个技能`, key: "upload" });
        onSuccess();
      } else {
        message.info({ content: "未导入新技能，可能已存在", key: "upload" });
      }
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
      // 调用预解析
      parseZipFile(file);
      return false;
    },
    onRemove: () => {
      setFile(null);
      setShowConfirm(false);
      setConflictNames([]);
      setCnName("");
      setSkillId("");
      setSkillName("");
      setSkillIdReused(false);
      setSkillIdUsedCount(0);
      setSkillIdUsedBy([]);
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
        loading: uploading || parsingZip,
        disabled: !file || selectedCategory === null || skillIdUsedCount > 0,
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
            {skillIdReused && (
              <span style={{ color: "#52c41a" }}> 同时复用已有 skill_id。</span>
            )}
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
            {parsingZip && (
              <div style={{ textAlign: "center", marginTop: 8 }}>
                <Spin size="small" />
                <span style={{ marginLeft: 8, color: "#8c8c8c" }}>正在解析...</span>
              </div>
            )}
            {file && !parsingZip && (
              <p style={{ color: "#52c41a", marginTop: 8 }}>
                已选择: {file.name}
                {skillName && <span style={{ color: "#8c8c8c" }}> ({skillName})</span>}
              </p>
            )}
          </div>

          {/* skill_id 冲突提示（禁止上传） */}
          {skillIdUsedCount > 0 && !parsingZip && (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 16 }}
              message={`skill_id '${skillId}' 已被占用`}
              description={
                skillIdUsedCount <= 3
                  ? `已被其他技能占用：${skillIdUsedBy.join("、")}`
                  : `已被 ${skillIdUsedCount} 个其他技能占用`
              }
            />
          )}

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", marginBottom: 8 }}>
              技能分类 <span style={{ color: "#ff4d4f" }}>*</span>
            </label>
            {loadingCategories ? (
              <Spin size="small" />
            ) : (
              <div style={{ display: "flex", gap: 8 }}>
                <Select
                  style={{ flex: 1 }}
                  value={selectedCategory}
                  onChange={setSelectedCategory}
                  placeholder="选择分类"
                  options={categories.map((c) => ({ label: c.name, value: c.id }))}
                />
                <Button
                  icon={<PlusOutlined />}
                  onClick={() => setAddCategoryModalOpen(true)}
                  title="新增分类"
                />
              </div>
            )}
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", marginBottom: 8 }}>
              中文名称 <span style={{ color: "#ff4d4f" }}>*</span>
            </label>
            <Input
              placeholder="请输入技能中文展示名"
              value={cnName}
              onChange={(e) => setCnName(e.target.value)}
              maxLength={50}
              showCount
            />
          </div>

          {skillId && !parsingZip && (
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", marginBottom: 8 }}>
                技能唯一标识
                <Tooltip title={
                  skillIdReused
                    ? "同名技能已存在，复用其 skill_id"
                    : "优先从 SKILL.md metadata.skill_id 提取，若无则自动生成"
                }>
                  <InfoCircleOutlined style={{ marginLeft: 4, color: "#8c8c8c" }} />
                </Tooltip>
              </label>
              <Input value={skillId} disabled />
              {skillIdReused && (
                <p style={{ color: "#52c41a", fontSize: 12, marginTop: 4 }}>
                  同名技能已存在，将复用此标识
                </p>
              )}
            </div>
          )}

          {/* 新增分类弹窗 */}
          <Modal
            title="新增分类"
            open={addCategoryModalOpen}
            onOk={handleAddCategory}
            onCancel={() => {
              setAddCategoryModalOpen(false);
              setNewCategoryName("");
            }}
            confirmLoading={addingCategory}
            okText="创建"
            cancelText="取消"
            destroyOnClose
          >
            <Input
              placeholder="请输入分类名称"
              value={newCategoryName}
              onChange={(e) => setNewCategoryName(e.target.value)}
              onPressEnter={handleAddCategory}
              maxLength={128}
              autoFocus
            />
          </Modal>
          <p style={{ color: "#8c8c8c", fontSize: 12 }}>
            提示：技能名称、描述和技能唯一标识将从 zip 包中的 SKILL.md frontmatter 自动解析，同名技能将复用已有标识
          </p>
        </>
      )}
    </Modal>
  );
}