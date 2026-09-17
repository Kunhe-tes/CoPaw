import { Button, List, Modal, Popconfirm, Space, Tag } from "antd";
import type { ExpertVersion } from "../../api/modules/market";

interface ExpertVersionHistoryModalProps {
  open: boolean;
  expertName?: string;
  versions: ExpertVersion[];
  loading: boolean;
  isManager: boolean;
  restoringId?: string | null;
  onClose: () => void;
  onRestore: (versionId: string) => void;
}

export function ExpertVersionHistoryModal({
  open,
  expertName,
  versions,
  loading,
  isManager,
  restoringId,
  onClose,
  onRestore,
}: ExpertVersionHistoryModalProps) {
  return (
    <Modal
      title={expertName ? `${expertName} · 版本历史` : "版本历史"}
      open={open}
      footer={null}
      onCancel={onClose}
      width={620}
    >
      <List
        loading={loading}
        dataSource={versions}
        locale={{ emptyText: "暂无版本历史" }}
        renderItem={(version) => (
          <List.Item
            actions={
              isManager && !version.is_current
                ? [
                    <Popconfirm
                      key="restore"
                      title={`恢复到 v${version.version_id}？`}
                      description="恢复后会成为当前发布版本，并保留现有历史记录。"
                      onConfirm={() => onRestore(version.version_id)}
                      okText="恢复"
                      cancelText="取消"
                    >
                      <Button
                        type="link"
                        loading={restoringId === version.version_id}
                      >
                        恢复
                      </Button>
                    </Popconfirm>,
                  ]
                : undefined
            }
          >
            <List.Item.Meta
              title={
                <Space>
                  <span>v{version.version_id}</span>
                  {version.is_current ? <Tag color="green">当前</Tag> : null}
                  {version.is_initial ? <Tag>初始版本</Tag> : null}
                </Space>
              }
              description={
                <Space direction="vertical" size={2}>
                  <span>
                    {version.created_by_name || version.created_by} ·{" "}
                    {version.created_at}
                  </span>
                  {version.description ? (
                    <span>{version.description}</span>
                  ) : null}
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </Modal>
  );
}
