import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { ReloadOutlined, StopOutlined } from "@ant-design/icons";
import {
  marketApi,
  type Category,
  type MarketExpert,
} from "../../api/modules/market";
import { useAppMessage } from "../../hooks/useAppMessage";
import { useIframeStore } from "../../stores/iframeStore";
import { DEFAULT_SOURCE_ID } from "../../constants/identity";
import { useAgentStore } from "../../stores/agentStore";

const { Title, Text } = Typography;

export default function ExpertCommunityPage() {
  const sourceId = useIframeStore((state) => state.source) || DEFAULT_SOURCE_ID;
  const manager = useIframeStore((state) => state.manager);
  const userId = useIframeStore((state) => state.userId) || "default";
  const selectedAgent = useAgentStore((state) => state.selectedAgent);
  const [items, setItems] = useState<MarketExpert[]>([]);
  const [query, setQuery] = useState("");
  const [categoryId, setCategoryId] = useState<number>();
  const [bbkIds, setBbkIds] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [receivedIds, setReceivedIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [versionItem, setVersionItem] = useState<MarketExpert | null>(null);
  const [versions, setVersions] = useState<Awaited<
    ReturnType<typeof marketApi.listExpertVersions>
  > | null>(null);
  const { message } = useAppMessage();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(
        await marketApi.listMarketExperts(sourceId, {
          categoryId,
          bbkIds: bbkIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载专家社区失败");
    } finally {
      setLoading(false);
    }
  }, [bbkIds, categoryId, sourceId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void marketApi.listCategories(sourceId).then(setCategories).catch(() => {});
  }, [sourceId]);

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) =>
      [item.name, item.description, item.creator_name].some((value) =>
        value.toLowerCase().includes(normalized),
      ),
    );
  }, [items, query]);

  const unpublish = async (item: MarketExpert) => {
    setBusyId(item.item_id);
    try {
      await marketApi.unpublishExpert(sourceId, item.item_id);
      message.success("专家已下架");
      await load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "下架失败");
    } finally {
      setBusyId(null);
    }
  };

  const receive = async (item: MarketExpert) => {
    setBusyId(item.item_id);
    try {
      const result = await marketApi.installExpert(
        sourceId,
        item.item_id,
        userId,
        selectedAgent,
      );
      if (!result.success) {
        message.error(result.reason || "专家已接收，不能重复安装");
        return;
      }
      setReceivedIds((current) => new Set(current).add(item.item_id));
      message.success("专家已接收");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "接收失败");
    } finally {
      setBusyId(null);
    }
  };

  const showVersions = async (item: MarketExpert) => {
    try {
      const versions = await marketApi.listExpertVersions(
        sourceId,
        item.item_id,
      );
      setVersions(versions);
      setVersionItem(item);
    } catch (err) {
      message.error(err instanceof Error ? err.message : "加载版本历史失败");
    }
  };

  const distribute = async (item: MarketExpert) => {
    setBusyId(item.item_id);
    try {
      const result = await marketApi.distributeExpert(sourceId, item.item_id, {
        target_type: "all",
        target_values: [],
      });
      message.success(`已分发 ${result.distributed_count} 个用户`);
      await load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "分发失败");
    } finally {
      setBusyId(null);
    }
  };

  const recall = async (item: MarketExpert) => {
    setBusyId(item.item_id);
    try {
      const result = await marketApi.recallExpert(sourceId, item.item_id);
      message.success(`已撤回 ${result.recalled_count} 个用户的专家`);
      await load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "撤回失败");
    } finally {
      setBusyId(null);
    }
  };

  const restoreVersion = async (versionId: string) => {
    if (!versionItem) return;
    setBusyId(versionItem.item_id);
    try {
      await marketApi.restoreExpertVersion(
        sourceId,
        versionItem.item_id,
        versionId,
      );
      message.success(`已恢复到 v${versionId}`);
      await Promise.all([load(), showVersions(versionItem)]);
    } catch (err) {
      message.error(err instanceof Error ? err.message : "恢复版本失败");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section style={{ padding: 24 }}>
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Space
          align="center"
          style={{ justifyContent: "space-between", width: "100%" }}
        >
          <div>
            <Title level={3} style={{ margin: 0 }}>
              专家社区
            </Title>
            <Text type="secondary">
              来源：{sourceId} · 浏览当前来源发布的专家包和冻结版本。
            </Text>
          </div>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => void load()}
            disabled={loading}
          >
            刷新
          </Button>
        </Space>
        <Input.Search
          allowClear
          placeholder="搜索专家名称、描述或发布者"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Space wrap>
          <Select
            allowClear
            placeholder="全部分类"
            style={{ minWidth: 160 }}
            value={categoryId}
            options={categories.map((category) => ({
              label: category.name,
              value: category.id,
            }))}
            onChange={setCategoryId}
          />
          <Input
            allowClear
            placeholder="按 BBK 筛选，逗号分隔"
            style={{ width: 220 }}
            value={bbkIds}
            onChange={(event) => setBbkIds(event.target.value)}
          />
        </Space>
        {error ? <Alert type="error" showIcon message={error} /> : null}
        {loading ? (
          <Spin />
        ) : visibleItems.length === 0 ? (
          <Empty description="暂无专家" />
        ) : (
          <List
            bordered
            dataSource={visibleItems}
            renderItem={(item) => (
              <List.Item
                actions={
                  manager
                    ? [
                        <Button
                          key="versions"
                          type="text"
                          onClick={() => void showVersions(item)}
                        >
                          版本历史
                        </Button>,
                        <Popconfirm
                          key="distribute"
                          title="确认分发此专家？"
                          description="管理员分发会静默覆盖同一社区来源的本地变体。"
                          onConfirm={() => void distribute(item)}
                        >
                          <Button
                            type="text"
                            loading={busyId === item.item_id}
                            disabled={
                              busyId !== null && busyId !== item.item_id
                            }
                          >
                            分发
                          </Button>
                        </Popconfirm>,
                        <Popconfirm
                          key="recall"
                          title="确认撤回此专家？"
                          description="将删除用户已接收副本，并立即释放会话依赖视图。"
                          onConfirm={() => void recall(item)}
                        >
                          <Button
                            danger
                            type="text"
                            loading={busyId === item.item_id}
                            disabled={
                              busyId !== null && busyId !== item.item_id
                            }
                          >
                            撤回
                          </Button>
                        </Popconfirm>,
                        <Popconfirm
                          key="unpublish"
                          title="确认下架此专家？"
                          description="下架只会停止新的浏览、接收和分发，已接收副本仍可使用。"
                          onConfirm={() => void unpublish(item)}
                        >
                          <Button
                            danger
                            type="text"
                            icon={<StopOutlined />}
                            loading={busyId === item.item_id}
                            disabled={
                              busyId !== null && busyId !== item.item_id
                            }
                          >
                            下架
                          </Button>
                        </Popconfirm>,
                      ]
                    : [
                        <Button
                          key="receive"
                          type="primary"
                          loading={busyId === item.item_id}
                          disabled={
                            item.status !== "active" ||
                            receivedIds.has(item.item_id)
                          }
                          onClick={() => void receive(item)}
                        >
                          {receivedIds.has(item.item_id) ? "已接收" : "接收"}
                        </Button>,
                        <Button
                          key="versions"
                          type="link"
                          onClick={() => void showVersions(item)}
                        >
                          版本历史
                        </Button>,
                      ]
                }
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <span>{item.name}</span>
                      <Tag
                        color={item.status === "active" ? "green" : "default"}
                      >
                        {item.status === "active" ? "已发布" : "已下架"}
                      </Tag>
                      <Tag>v{item.version}</Tag>
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size={2}>
                      <span>{item.description || "暂无描述"}</span>
                      <Text type="secondary">
                        发布者：{item.creator_name || item.creator_id}
                      </Text>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Space>
      <Modal
        title={versionItem ? `${versionItem.name} · 版本历史` : "版本历史"}
        open={versionItem !== null}
        footer={null}
        onCancel={() => {
          setVersionItem(null);
          setVersions(null);
        }}
      >
        <List
          dataSource={versions?.versions || []}
          locale={{ emptyText: "暂无版本历史" }}
          renderItem={(version) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <span>v{version.version_id}</span>
                    {version.is_current ? <Tag color="green">当前</Tag> : null}
                  </Space>
                }
                description={`${
                  version.created_by_name || version.created_by
                } · ${version.created_at}`}
              />
              {manager && !version.is_current ? (
                <Popconfirm
                  title={`恢复到 v${version.version_id}？`}
                  description="恢复后会成为当前发布版本。"
                  onConfirm={() => void restoreVersion(version.version_id)}
                >
                  <Button
                    type="link"
                    loading={busyId === versionItem?.item_id}
                  >
                    恢复
                  </Button>
                </Popconfirm>
              ) : null}
            </List.Item>
          )}
        />
      </Modal>
    </section>
  );
}
