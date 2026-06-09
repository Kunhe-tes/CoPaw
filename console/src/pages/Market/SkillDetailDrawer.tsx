import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  BarChartOutlined,
  CalendarOutlined,
  HistoryOutlined,
  ProfileOutlined,
  TagOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Button, Popconfirm, Spin, Table, Tag, Typography } from "antd";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, Undo2, Trash2, Archive } from "lucide-react";
import { marketApi, MarketSkillDetail } from "../../api/modules/market";
import type { FileContentResponse } from "../../api/modules/mySkills";
import { VersionHistoryModal } from "./Skills/VersionHistoryModal";
import styles from "./SkillDetailDrawer.module.less";

const { Paragraph, Text, Title } = Typography;

interface SkillDetailDrawerProps {
  open: boolean;
  skill: MarketSkillDetail | null;
  onClose: () => void;
  isManager?: boolean;
  onDistribute?: () => void;
  onRecall?: () => void;
  onUnpublish?: () => void;
  onDelete?: () => void;
  sourceId?: string;
  onRefresh?: () => void;
  categoryName?: string;
}

const FRONTMATTER_PATTERN = /^---\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/;

const FOOTER_BUTTON_STYLE = {
  height: 28,
  padding: "0 12px",
  borderRadius: 8,
  fontSize: 12,
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
} as const;

const BASE_META_TAG_STYLE = {
  margin: 0,
  backgroundColor: "#f5f5f5",
  color: "#5e5d59",
  borderRadius: 999,
  border: "1px solid #e8e8e8",
  paddingInline: 10,
  paddingBlock: 1,
  fontSize: 12,
} as const;

const BASE_STAT_TAG_STYLE = {
  ...BASE_META_TAG_STYLE,
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  fontSize: 12,
  lineHeight: "20px",
} as const;

function formatDate(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString("zh-CN");
}

function splitMarkdownFrontmatter(
  fileType: string | null,
  fileContent: string | null,
): string | null {
  if (fileType !== "markdown" || typeof fileContent !== "string") {
    return fileContent;
  }
  const match = fileContent.match(FRONTMATTER_PATTERN);
  if (!match) {
    return fileContent;
  }
  return fileContent.slice(match[0].length).trim();
}

function renderPreviewContent(
  fileType: string | null,
  fileContent: string | null,
): ReactNode {
  if (fileContent === null) {
    return (
      <Text type="secondary" style={{ fontSize: 13 }}>
        选择左侧文件查看内容
      </Text>
    );
  }

  if (fileType === "binary") {
    return (
      <div
        style={{
          width: "100%",
          boxSizing: "border-box",
          border: "1px dashed #d9d9d9",
          borderRadius: 12,
          padding: 24,
          backgroundColor: "#fafafa",
          textAlign: "center",
        }}
      >
        <Text type="secondary">该文件为二进制内容，当前仅支持只读占位预览。</Text>
      </div>
    );
  }

  if (fileType === "markdown") {
    const previewContent = splitMarkdownFrontmatter(fileType, fileContent) ?? "";
    return (
      <div
        style={{
          width: "100%",
          maxWidth: "100%",
          boxSizing: "border-box",
          backgroundColor: "#fff",
          borderRadius: 10,
          padding: 12,
          border: "1px solid #f0f0f0",
          lineHeight: 1.7,
          overflow: "hidden",
          wordBreak: "break-word",
          overflowWrap: "anywhere",
        }}
      >
        <div
          className={styles.streamingMarkdown}
          data-testid="skill-markdown-preview"
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {previewContent}
          </ReactMarkdown>
        </div>
      </div>
    );
  }

  if (fileType === "json") {
    let formatted = fileContent;
    try {
      formatted = JSON.stringify(JSON.parse(fileContent), null, 2);
    } catch {
      // 解析失败时回退原始内容，避免预览中断
    }
    return (
      <pre
        style={{
          margin: 0,
          width: "100%",
          boxSizing: "border-box",
          backgroundColor: "#1f2430",
          color: "#f5f5f5",
          borderRadius: 10,
          padding: 10,
          overflow: "auto",
          fontSize: 12,
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          overflowWrap: "anywhere",
        }}
      >
        {formatted}
      </pre>
    );
  }

  return (
    <pre
      style={{
        margin: 0,
        width: "100%",
        boxSizing: "border-box",
        backgroundColor: "#fafafa",
        borderRadius: 10,
        padding: 10,
        border: "1px solid #f0f0f0",
        overflow: "auto",
        fontSize: 12,
        lineHeight: 1.6,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        overflowWrap: "anywhere",
      }}
    >
      {fileContent}
    </pre>
  );
}

export function SkillDetailDrawer(
  props: SkillDetailDrawerProps,
) {
  const {
    open,
    skill,
    isManager,
    onDistribute,
    onRecall,
    onUnpublish,
    onDelete,
    sourceId,
    categoryName,
    onRefresh,
  } = props;
  const [fileDetail, setFileDetail] = useState<FileContentResponse | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [versionHistoryOpen, setVersionHistoryOpen] = useState(false);
  const displayTitle = skill?.chinese_name?.trim() || skill?.name || "";
  const displayDescription = skill?.description || "暂无描述";
  const normalizedCategoryName = categoryName?.trim();

  useEffect(() => {
    if (!open || !skill || !sourceId) {
      return;
    }

    let cancelled = false;
    setFileLoading(true);
    setPreviewError(null);
    setFileDetail(null);

    marketApi.readSkillFile(sourceId, skill.item_id, "SKILL.md")
      .then((data) => {
        if (!cancelled) {
          setFileDetail(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPreviewError("暂未获取到 Skill 文档预览");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setFileLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open, skill, sourceId]);

  const userStatsColumns = useMemo(
    () => [
      { title: "用户ID", dataIndex: "user_id", key: "user_id" },
      { title: "用户名称", dataIndex: "user_name", key: "user_name" },
      {
        title: "调用次数",
        dataIndex: "call_count",
        key: "call_count",
        sorter: (
          a: { call_count: number },
          b: { call_count: number },
        ) => a.call_count - b.call_count,
      },
    ],
    [],
  );

  if (!open || !skill) {
    return null;
  }

  return (
    <>
      <div style={{ height: "100%", overflow: "auto", padding: 12 }}>
        <div
          style={{
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
            alignItems: "flex-start",
          }}
        >
        <div
          style={{
            flex: "1 1 720px",
            minWidth: 0,
            backgroundColor: "#fff",
            border: "1px solid #f0f0f0",
            borderRadius: 16,
            overflow: "hidden",
            boxShadow: "rgba(0, 0, 0, 0.04) 0px 4px 16px",
          }}
        >
          <div
            style={{
              padding: "10px 14px",
              borderBottom: "1px solid #f0f0f0",
              backgroundColor: "#fff",
            }}
          >
            <Title
              level={4}
              style={{
                margin: 0,
                fontSize: 15,
                fontWeight: 600,
                color: "#141413",
              }}
            >
              {displayTitle}
            </Title>
          </div>

          <div
            style={{
              padding: "8px 14px",
              borderBottom: "1px solid #f0f0f0",
              backgroundColor: "#fff",
            }}
          >
            <Text
              type="secondary"
              style={{
                fontSize: 13,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {displayDescription}
            </Text>
          </div>

          <div
            style={{
              display: "flex",
              minHeight: 480,
            }}
          >
            <div
              style={{
                flex: "1 1 auto",
                width: "100%",
                minWidth: 0,
                padding: 12,
                backgroundColor: "#fafafa",
                height: "100%",
              }}
            >
              {previewError ? (
                <div
                  style={{
                    padding: 24,
                    borderRadius: 12,
                    backgroundColor: "#fff2f0",
                    border: "1px solid #ffccc7",
                  }}
                >
                  <Text type="danger">{previewError}</Text>
                </div>
              ) : fileLoading ? (
                <div
                  style={{
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    minHeight: 360,
                  }}
                >
                  <Spin />
                </div>
              ) : (
                renderPreviewContent(
                  fileDetail?.file_type ?? null,
                  fileDetail?.content ?? null,
                )
              )}
            </div>
          </div>
        </div>

        <div
          style={{
            flex: "0 1 360px",
            width: "100%",
            maxWidth: 360,
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div
            style={{
              borderRadius: 16,
              border: "1px solid #f0f0f0",
              backgroundColor: "#fff",
              padding: 12,
              boxShadow: "rgba(0, 0, 0, 0.04) 0px 4px 16px",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <Title
                level={4}
                style={{ margin: 0, color: "#141413", fontSize: 15, fontWeight: 500, lineHeight: 1.35 }}
              >
                {skill.chinese_name?.trim() ? (
                  <>
                    {skill.chinese_name}
                    <Text style={{ marginLeft: 8, fontSize: 14, fontWeight: 400, color: "#87867f" }}>
                      ({skill.name})
                    </Text>
                  </>
                ) : (
                  displayTitle
                )}
              </Title>
            </div>
            <Paragraph
              style={{
                marginTop: 6,
                marginBottom: 10,
                color: "#87867f",
                fontSize: 13,
                lineHeight: 1.6,
              }}
            >
              {displayDescription}
            </Paragraph>

            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
              {normalizedCategoryName && (
                <Tag
                  icon={<TagOutlined />}
                  bordered={false}
                  style={BASE_META_TAG_STYLE}
                >
                  {normalizedCategoryName}
                </Tag>
              )}
              <Tag
                icon={<ProfileOutlined />}
                bordered={false}
                style={BASE_META_TAG_STYLE}
              >
                v{skill.version}
              </Tag>
              <Tag
                icon={<CalendarOutlined />}
                bordered={false}
                style={BASE_META_TAG_STYLE}
              >
                {formatDate(skill.created_at)}
              </Tag>
              <Tag
                icon={<UserOutlined />}
                bordered={false}
                style={BASE_META_TAG_STYLE}
              >
                {skill.creator_name || "未知创建人"}
              </Tag>
              <Tag
                bordered={false}
                style={{
                  margin: 0,
                  backgroundColor:
                    skill.status === "active" ? "#edf7f0" : "#fff1f0",
                  color:
                    skill.status === "active" ? "#2e7d4f" : "#cf1322",
                  borderRadius: 999,
                  paddingInline: 12,
                }}
              >
                {skill.status === "active" ? "已发布" : "已删除"}
              </Tag>
              <Tag
                bordered={false}
                style={{
                  ...BASE_STAT_TAG_STYLE,
                  backgroundColor: "#eef4ff",
                  color: "#365d97",
                  border: "1px solid #d7e2f5",
                  paddingInline: 12,
                }}
              >
                <BarChartOutlined />
                <Text style={{ fontSize: 11, color: "#6a7fa5" }}>调用次数</Text>
                <Text style={{ fontSize: 12, color: "inherit", fontWeight: 600 }}>
                  {skill.call_count}
                </Text>
              </Tag>
              <Tag
                bordered={false}
                style={{
                  ...BASE_STAT_TAG_STYLE,
                  backgroundColor: "#eef8f2",
                  color: "#2f7a55",
                  border: "1px solid #cfe4d9",
                  paddingInline: 12,
                }}
              >
                <UserOutlined />
                <Text style={{ fontSize: 11, color: "#4c8669" }}>使用用户数</Text>
                <Text style={{ fontSize: 12, color: "inherit", fontWeight: 600 }}>
                  {skill.user_count}
                </Text>
              </Tag>
            </div>

            {isManager && (onDistribute || onRecall || onUnpublish || onDelete) && (
              <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Button
                  onClick={() => setVersionHistoryOpen(true)}
                  style={{
                    ...FOOTER_BUTTON_STYLE,
                    color: "#5e5d59",
                    border: "1px solid #d9d9d9",
                    backgroundColor: "#fff",
                  }}
                >
                  <HistoryOutlined style={{ fontSize: 12 }} />
                  版本历史
                </Button>
                {onDistribute && (
                  <Button
                    type="primary"
                    onClick={onDistribute}
                    style={{ ...FOOTER_BUTTON_STYLE }}
                  >
                    <Send size={12} />
                    分发
                  </Button>
                )}
                {onRecall && (
                  <Button
                    onClick={onRecall}
                    style={{
                      ...FOOTER_BUTTON_STYLE,
                      color: "#5e5d59",
                      border: "1px solid #d9d9d9",
                      backgroundColor: "#fff",
                    }}
                  >
                    <Undo2 size={12} />
                    撤回
                  </Button>
                )}
                {onUnpublish && (
                  <Popconfirm
                    title="确认下架此技能？"
                    description="下架后用户将无法查看此技能，但数据仍保留"
                    onConfirm={onUnpublish}
                    okText="下架"
                    cancelText="取消"
                  >
                    <Button
                      style={{
                        ...FOOTER_BUTTON_STYLE,
                        color: "#5e5d59",
                        border: "1px solid #d9d9d9",
                        backgroundColor: "#fff",
                      }}
                    >
                      <Archive size={12} />
                      下架
                    </Button>
                  </Popconfirm>
                )}
                {onDelete && (
                  <Popconfirm
                    title="彻底删除此技能？"
                    description="删除后技能文件和版本历史将全部清除，无法恢复"
                    onConfirm={onDelete}
                    okText="删除"
                    okButtonProps={{ danger: true }}
                    cancelText="取消"
                  >
                    <Button
                      danger
                      style={{ ...FOOTER_BUTTON_STYLE }}
                    >
                      <Trash2 size={12} />
                      删除
                    </Button>
                  </Popconfirm>
                )}
              </div>
            )}
            {!isManager && (
              <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                <Button
                  onClick={() => setVersionHistoryOpen(true)}
                  style={{
                    ...FOOTER_BUTTON_STYLE,
                    color: "#5e5d59",
                    border: "1px solid #d9d9d9",
                    backgroundColor: "#fff",
                  }}
                >
                  <HistoryOutlined style={{ fontSize: 12 }} />
                  版本历史
                </Button>
              </div>
            )}
          </div>

          <div
            style={{
              borderRadius: 16,
              border: "1px solid #f0f0f0",
              backgroundColor: "#fff",
              padding: 12,
              boxShadow: "rgba(0, 0, 0, 0.03) 0px 2px 10px",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 10,
              }}
            >
              <Title level={5} style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>
                使用用户明细
              </Title>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Tag
                  bordered={false}
                  style={{
                    ...BASE_STAT_TAG_STYLE,
                    backgroundColor: "#eef4ff",
                    color: "#365d97",
                    border: "1px solid #d7e2f5",
                    paddingInline: 8,
                    paddingBlock: 0,
                  }}
                >
                  <BarChartOutlined />
                  <Text style={{ fontSize: 11, color: "inherit", fontWeight: 600 }}>
                    {skill.call_count}
                  </Text>
                </Tag>
                <Tag
                  bordered={false}
                  style={{
                    ...BASE_STAT_TAG_STYLE,
                    backgroundColor: "#edf8f2",
                    color: "#2f7a55",
                    border: "1px solid #cfe4d9",
                    paddingInline: 8,
                    paddingBlock: 0,
                  }}
                >
                  <UserOutlined />
                  <Text style={{ fontSize: 11, color: "inherit", fontWeight: 600 }}>
                    {skill.user_count}
                  </Text>
                </Tag>
              </div>
            </div>

            <div className={styles.usageTable}>
              <Table
                dataSource={skill.user_stats}
                columns={userStatsColumns}
                rowKey="user_id"
                pagination={{ pageSize: 5, hideOnSinglePage: true, size: "small" }}
                size="small"
                scroll={{ y: 260 }}
              />
            </div>
          </div>
        </div>
      </div>
      </div>

      <VersionHistoryModal
        open={versionHistoryOpen}
        itemId={skill.item_id}
        skillName={displayTitle}
        currentVersion={skill.version}
        sourceId={sourceId || ""}
        isManager={isManager}
        onClose={() => setVersionHistoryOpen(false)}
        onVersionSwitched={onRefresh}
      />
    </>
  );
}
