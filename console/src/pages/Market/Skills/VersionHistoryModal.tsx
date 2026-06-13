import { useEffect, useState } from "react";
import {
  Button,
  Modal,
  Spin,
  Tag,
  Typography,
  message,
  Popconfirm,
  Empty,
} from "antd";
import {
  UserOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
} from "@ant-design/icons";
import { skillVersionApi, SkillVersion, VersionsManifest } from "../../../api/modules/skillVersion";
import { VersionCompareDrawer } from "./VersionCompareDrawer";

const { Text, Title } = Typography;

interface VersionHistoryModalProps {
  open: boolean;
  itemId: string;
  skillName: string;
  currentVersion: string;
  sourceId: string;
  isManager?: boolean;
  onClose: () => void;
  onVersionSwitched?: () => void;
}

function formatDateTime(value: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function VersionHistoryModal(props: VersionHistoryModalProps) {
  const {
    open,
    itemId,
    skillName,
    currentVersion,
    sourceId,
    isManager,
    onClose,
    onVersionSwitched,
  } = props;

  const [loading, setLoading] = useState(false);
  const [versions, setVersions] = useState<SkillVersion[]>([]);
  const [skillNameFromManifest, setSkillNameFromManifest] = useState("");
  const [switching, setSwitching] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [compareDrawerOpen, setCompareDrawerOpen] = useState(false);
  const [compareTargetVersion, setCompareTargetVersion] = useState<string>("");

  useEffect(() => {
    if (!open || !itemId || !sourceId) {
      return;
    }

    setLoading(true);
    skillVersionApi
      .listVersions(sourceId, itemId)
      .then((data: VersionsManifest) => {
        setVersions(data.versions || []);
        setSkillNameFromManifest(data.skill_name || skillName);
      })
      .catch((err) => {
        console.error("Failed to load versions:", err);
        message.error("加载版本历史失败");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [open, itemId, sourceId, skillName]);

  // 获取当前版本（is_current=true 的版本）
  const currentVersionInfo = versions.find((v) => v.is_current);

  const handleSwitchVersion = async (versionId: string) => {
    if (!isManager) {
      message.warning("需要管理员权限才能切换版本");
      return;
    }

    setSwitching(true);
    try {
      const result = await skillVersionApi.switchVersion(sourceId, itemId, versionId);
      if (result.success) {
        message.success(`已切换到版本 ${versionId}`);
        onVersionSwitched?.();
        // 刷新版本列表
        const data = await skillVersionApi.listVersions(sourceId, itemId);
        setVersions(data.versions || []);
        // 关闭比对抽屉
        setCompareDrawerOpen(false);
      } else {
        message.error(result.message || "切换版本失败");
      }
    } catch (err) {
      console.error("Failed to switch version:", err);
      message.error("切换版本失败");
    } finally {
      setSwitching(false);
    }
  };

  const handleDeleteVersion = async (versionId: string) => {
    if (!isManager) {
      message.warning("需要管理员权限才能删除版本");
      return;
    }

    setDeleting(true);
    try {
      const result = await skillVersionApi.deleteVersion(sourceId, itemId, versionId);
      if (result.success) {
        message.success(`已删除版本 ${versionId}`);
        // 刷新版本列表
        const data = await skillVersionApi.listVersions(sourceId, itemId);
        setVersions(data.versions || []);
      } else {
        message.error(result.message || "删除版本失败");
      }
    } catch (err) {
      console.error("Failed to delete version:", err);
      message.error("删除版本失败");
    } finally {
      setDeleting(false);
    }
  };

  // 点击比对时，打开比对抽屉
  const handleCompare = (versionId: string) => {
    if (!currentVersionInfo) {
      message.warning("未找到当前版本");
      return;
    }
    setCompareTargetVersion(versionId);
    setCompareDrawerOpen(true);
  };

  // 关闭比对抽屉
  const handleCloseCompare = () => {
    setCompareDrawerOpen(false);
    setCompareTargetVersion("");
  };

  return (
    <>
      <Modal
        open={open}
        onCancel={onClose}
        footer={null}
        width={720}
        title={
          <Title level={4} style={{ margin: 0 }}>
            版本历史 - {skillNameFromManifest || skillName}
          </Title>
        }
        styles={{
          body: { maxHeight: 480, overflow: "auto" },
        }}
      >
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 200 }}>
            <Spin />
          </div>
        ) : versions.length === 0 ? (
          <Empty description="暂无版本历史" />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {versions.map((version) => {
              const isCurrent = version.is_current;
              const isInitial = version.is_initial;
              const canSwitch = !isCurrent && isManager;
              // 只有当前版本不能删除，初始版本也可以删除（删除后会有警告提示）
              const canDelete = !isCurrent && isManager;

              return (
                <div
                  key={version.version_id}
                  style={{
                    padding: 14,
                    border: "1px solid #e1e4e8",
                    borderRadius: 8,
                    backgroundColor: isCurrent ? "#f6f8fa" : "#fff",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {isCurrent && (
                        <Tag
                          style={{
                            backgroundColor: "#28a745",
                            color: "#fff",
                            borderRadius: 3,
                            fontSize: 12,
                          }}
                        >
                          当前
                        </Tag>
                      )}
                      {isInitial && (
                        <Tag
                          style={{
                            backgroundColor: "#0366d6",
                            color: "#fff",
                            borderRadius: 3,
                            fontSize: 12,
                          }}
                        >
                          初始
                        </Tag>
                      )}
                      <Text strong style={{ fontSize: 14 }}>
                        {version.version_id}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <ClockCircleOutlined style={{ marginRight: 4 }} />
                        {formatDateTime(version.created_at)}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <UserOutlined style={{ marginRight: 4 }} />
                        {version.created_by || "-"}
                      </Text>
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                      {canSwitch && (
                        <Popconfirm
                          title="确定切换到此版本？"
                          description={`将技能从 ${currentVersionInfo?.version_id || '当前版本'} 切换到 ${version.version_id}`}
                          onConfirm={() => handleSwitchVersion(version.version_id)}
                          okText="切换"
                          cancelText="取消"
                          icon={<ExclamationCircleOutlined style={{ color: "#faad14" }} />}
                        >
                          <Button
                            size="small"
                            type="primary"
                            ghost
                            loading={switching}
                            style={{ fontSize: 11 }}
                          >
                            切换到此版本
                          </Button>
                        </Popconfirm>
                      )}
                      {!isCurrent && (
                        <Button
                          size="small"
                          onClick={() => handleCompare(version.version_id)}
                          style={{ fontSize: 11 }}
                        >
                          比对
                        </Button>
                      )}
                      {canDelete && (
                        <Popconfirm
                          title={isInitial ? "确定删除初始版本？" : "确定删除此版本？"}
                          description={isInitial ? "删除初始版本后，最早的剩余版本将成为新初始版本" : "删除后无法恢复"}
                          onConfirm={() => handleDeleteVersion(version.version_id)}
                          okText="删除"
                          okButtonProps={{ danger: true }}
                          cancelText="取消"
                        >
                          <Button
                            size="small"
                            danger
                            loading={deleting}
                            style={{ fontSize: 11 }}
                          >
                            删除
                          </Button>
                        </Popconfirm>
                      )}
                    </div>
                  </div>
                  {version.description && (
                    <Text type="secondary" style={{ fontSize: 13, marginTop: 6, display: "block" }}>
                      {version.description}
                    </Text>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div style={{ marginTop: 12, color: "#87867f", fontSize: 13 }}>
          <Text type="secondary">
            共 {versions.length} 个版本
          </Text>
        </div>
      </Modal>

      {/* 版本比对 Drawer */}
      <VersionCompareDrawer
        open={compareDrawerOpen}
        sourceId={sourceId}
        itemId={itemId}
        baseVersion={compareTargetVersion}
        targetVersion={currentVersionInfo?.version_id || ""}
        onClose={handleCloseCompare}
      />
    </>
  );
}