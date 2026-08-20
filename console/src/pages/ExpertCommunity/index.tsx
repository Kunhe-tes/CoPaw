import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  Input,
  List,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { ReloadOutlined, StopOutlined } from "@ant-design/icons";
import { marketApi, type MarketExpert } from "../../api/modules/market";
import { useAppMessage } from "../../hooks/useAppMessage";
import { useIframeStore } from "../../stores/iframeStore";
import { DEFAULT_SOURCE_ID } from "../../constants/identity";

const { Title, Text } = Typography;

export default function ExpertCommunityPage() {
  const sourceId = useIframeStore((state) => state.source) || DEFAULT_SOURCE_ID;
  const manager = useIframeStore((state) => state.manager);
  const [items, setItems] = useState<MarketExpert[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { message } = useAppMessage();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await marketApi.listMarketExperts(sourceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载专家社区失败");
    } finally {
      setLoading(false);
    }
  }, [sourceId]);

  useEffect(() => {
    void load();
  }, [load]);

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
    try {
      await marketApi.unpublishExpert(sourceId, item.item_id);
      message.success("专家已下架");
      await load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "下架失败");
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
            <Text type="secondary">浏览当前来源发布的专家包和冻结版本。</Text>
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
                          key="unpublish"
                          danger
                          type="text"
                          icon={<StopOutlined />}
                          onClick={() => void unpublish(item)}
                        >
                          下架
                        </Button>,
                      ]
                    : undefined
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
    </section>
  );
}
