import { memo } from "react";
import { Typography, Button, Spin, Tag, Popconfirm, Tooltip } from "antd";
import { StarOutlined, RocketOutlined } from "@ant-design/icons";
import { Power, Trash2, Pencil, PencilLine } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
dayjs.extend(relativeTime);
import { MySkill } from "../../api/modules/mySkills";
import styles from "./index.module.less";

const { Title, Text } = Typography;

/**
 * 将 Markdown 文件内容分割为 frontmatter 和正文。
 */
function splitMarkdownFrontmatter(
  filePath: string | null,
  content: string | null
): { protectedPrefix: string; editableContent: string; hasFrontmatter: boolean } {
  const isMarkdown = !!filePath && /\.md$/i.test(filePath);
  if (!isMarkdown || typeof content !== "string") {
    return { protectedPrefix: "", editableContent: content ?? "", hasFrontmatter: false };
  }

  const match = content.match(/^---\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/);
  if (!match) {
    return { protectedPrefix: "", editableContent: content, hasFrontmatter: false };
  }

  return {
    protectedPrefix: match[0],
    editableContent: content.slice(match[0].length),
    hasFrontmatter: true,
  };
}

/**
 * 将 protectedPrefix (frontmatter) 和 editableContent 合并为完整文件内容。
 */
function mergeMarkdownFrontmatter(protectedPrefix: string, editableContent: string): string {
  if (!protectedPrefix) return editableContent;
  if (!editableContent || protectedPrefix.endsWith("\n") || protectedPrefix.endsWith("\r\n")) {
    return `${protectedPrefix}${editableContent}`;
  }
  return `${protectedPrefix}\n${editableContent}`;
}

interface SkillDetailPanelProps {
  skill: MySkill | null;
  selectedFile: string | null;
  fileContent: string | null;
  fileType: string | null;
  isEditing: boolean;
  draftContent: string;
  isSaving: boolean;
  togglingSkill: string | null;
  isManager: boolean;
  onEditStart: () => void;
  onEditCancel: () => void;
  onSave: () => void;
  onDraftChange: (content: string) => void;
  onToggleEnabled: (skill: MySkill) => void;
  onDelete: (skill: MySkill) => void;
  onSyncToMarket: (skill: MySkill) => void;
}

const SkillDetailPanel = memo(function SkillDetailPanel({
  skill,
  selectedFile,
  fileContent,
  fileType,
  isEditing,
  draftContent,
  isSaving,
  togglingSkill,
  isManager,
  onEditStart,
  onEditCancel,
  onSave,
  onDraftChange,
  onToggleEnabled,
  onDelete,
  onSyncToMarket,
}: SkillDetailPanelProps) {
  if (!skill) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", padding: 32, textAlign: "center" }}>
        <StarOutlined style={{ fontSize: 48, color: "#faad14", marginBottom: 16 }} />
        <Title level={5} style={{ margin: "0 0 8px 0", color: "#262626" }}>
          技能详情
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          选择左侧技能查看详情
        </Text>
      </div>
    );
  }

  const isDisabled = !skill.enabled;
  const canEdit = !skill.is_received;
  const isLoading = selectedFile && fileContent === null;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div
        style={{
          padding: 16,
          borderBottom: "1px solid #f0f0f0",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <Text strong style={{ fontSize: 16, color: "#262626" }}>
              {skill.display_name || skill.skill_name}
            </Text>
            {skill.source === "customized" && (
              <Tag color="green" style={{ fontSize: 11, borderRadius: 4 }}>自定义</Tag>
            )}
            {skill.is_received && (
              <Tag color="orange" style={{ fontSize: 11, borderRadius: 4 }}>接收的</Tag>
            )}
            {isDisabled && (
              <Tag color="red" style={{ fontSize: 11, borderRadius: 4 }}>已禁用</Tag>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            {skill.category && (
              <Tag style={{ fontSize: 11, borderRadius: 4, backgroundColor: "#f5f5f5", border: "1px solid #d9d9d9" }}>
                {skill.category}
              </Tag>
            )}
            {skill.creator_name && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                创建者: {skill.creator_name}
              </Text>
            )}
            {skill.created_at && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                创建: {dayjs(skill.created_at).format("YYYY-MM-DD")}
              </Text>
            )}
            {skill.updated_at && (
              <Tooltip title={dayjs(skill.updated_at).format("YYYY-MM-DD HH:mm:ss")}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  更新: {dayjs(skill.updated_at).fromNow()}
                </Text>
              </Tooltip>
            )}
            {skill.version && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                版本: v{skill.version}
              </Text>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          <Popconfirm
            title="删除技能"
            description={`确定删除技能「${skill.display_name || skill.skill_name}」？删除后不可恢复。`}
            onConfirm={() => onDelete(skill)}
            okText="确定"
            cancelText="取消"
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
          {canEdit && fileContent !== null && !isEditing && (
            <Button
              size="small"
              icon={<Pencil style={{ width: 12, height: 12 }} />}
              style={{ height: 28, fontSize: 12, borderRadius: 8 }}
              onClick={onEditStart}
            >
              编辑
            </Button>
          )}
          <Button
            size="small"
            type={skill.enabled ? "primary" : "default"}
            icon={<Power style={{ width: 12, height: 12 }} />}
            style={{ height: 28, fontSize: 12, borderRadius: 8 }}
            onClick={() => onToggleEnabled(skill)}
            loading={togglingSkill === skill.skill_name}
          >
            {skill.enabled ? "已启用" : "已禁用"}
          </Button>
          {isManager && canEdit && (
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
              onClick={() => onSyncToMarket(skill)}
            >
              同步到市场
            </Button>
          )}
          {isEditing && (
            <>
              <Button
                size="small"
                style={{ height: 28, fontSize: 12, borderRadius: 8 }}
                onClick={onEditCancel}
                disabled={isSaving}
              >
                取消
              </Button>
              <Button
                size="small"
                type="primary"
                style={{ height: 28, fontSize: 12, borderRadius: 8 }}
                onClick={onSave}
                loading={isSaving}
              >
                保存
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Description */}
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #f0f0f0" }}>
        <Text type="secondary" style={{ fontSize: 14, whiteSpace: "pre-wrap" }}>
          {skill.description || "暂无描述"}
        </Text>
      </div>

      {/* Content */}
      <div style={{ flex: "1 1 0", padding: 16, overflow: "auto", minHeight: 0 }}>
        {isLoading ? (
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: 100 }}>
            <Spin />
          </div>
        ) : isEditing ? (
          <div className={styles.editModeContainer}>
            {/* 编辑模式标签 */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <div className={styles.editModeTag}>
                <PencilLine style={{ width: 12, height: 12 }} />
                编辑模式
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                可使用 Ctrl/Cmd + S 快速保存
              </Text>
            </div>
            {/* Frontmatter 保护提示 */}
            {selectedFile && /\.md$/i.test(selectedFile) && splitMarkdownFrontmatter(selectedFile, fileContent).hasFrontmatter && (
              <p className={styles.frontmatterNote}>
                Markdown 顶部元信息受保护，此处只编辑正文内容。
              </p>
            )}
            {/* 编辑区域 */}
            <textarea
              value={draftContent}
              onChange={(e) => onDraftChange(e.target.value)}
              onKeyDown={(e) => {
                // Ctrl/Cmd + S 快捷保存
                if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
                  e.preventDefault();
                  onSave();
                }
              }}
              className={styles.editModeTextarea}
              placeholder="输入内容..."
              spellCheck={false}
            />
          </div>
        ) : fileContent === null ? (
          <div className={styles.detailPanelEmpty}>
            <Text type="secondary">选择文件查看内容</Text>
          </div>
        ) : fileType === "markdown" ? (
          <div className={styles.previewContainerMarkdown}>
            {/* Frontmatter 提示 */}
            {splitMarkdownFrontmatter(selectedFile, fileContent).hasFrontmatter && (
              <p className={styles.frontmatterPreviewNote}>
                文件顶部包含受保护的元信息，此处只显示正文内容。
              </p>
            )}
            <div className={styles.streamingMarkdown}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {splitMarkdownFrontmatter(selectedFile, fileContent).editableContent.trim()}
              </ReactMarkdown>
            </div>
          </div>
        ) : fileType === "json" ? (
          <pre className={styles.previewContainerJson}>
            {(() => {
              try {
                return JSON.stringify(JSON.parse(fileContent), null, 2);
              } catch {
                return fileContent;
              }
            })()}
          </pre>
        ) : (
          <pre className={styles.previewContainer}>
            {fileContent}
          </pre>
        )}
      </div>
    </div>
  );
});

export { SkillDetailPanel, splitMarkdownFrontmatter, mergeMarkdownFrontmatter };