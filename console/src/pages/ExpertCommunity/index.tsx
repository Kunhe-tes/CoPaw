import { Empty, Typography } from "antd";

export default function ExpertCommunityPage() {
  return (
    <section style={{ padding: 24 }}>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        专家社区
      </Typography.Title>
      <Typography.Text type="secondary">
        浏览、接收和管理当前来源下的专家包。
      </Typography.Text>
      <Empty description="专家社区正在加载" style={{ marginTop: 72 }} />
    </section>
  );
}
