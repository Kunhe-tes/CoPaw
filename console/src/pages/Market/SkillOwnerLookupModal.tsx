import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { marketApi, type MarketSkill } from "../../api/modules/market";
import {
  fetchTenantsBySource,
  type TenantSourceInfo,
} from "../../api/modules/userInfo";
import {
  buildSkillOwnerRows,
  type SkillOwnerRow,
} from "./skillOwnerLookup";
import type { MySkill } from "../../api/modules/mySkills";

const { Text } = Typography;
const DEFAULT_OWNER_LOOKUP_PAGE_SIZE = 8;
const OWNER_LOOKUP_PAGE_SIZE_OPTIONS = [8, 20, 50, 100];

function normalizeSearchKeyword(value: string): string {
  return value.trim().toLowerCase();
}

function matchesOwnerSearch(row: SkillOwnerRow, keyword: string): boolean {
  if (!keyword) return true;
  return [row.tenant_name, row.tenant_id].some((value) =>
    String(value || "").toLowerCase().includes(keyword),
  );
}

interface SkillOwnerLookupModalProps {
  open: boolean;
  skill: MarketSkill | null;
  sourceId: string;
  onClose: () => void;
}

async function loadTenantSkills(
  sourceId: string,
  tenants: TenantSourceInfo[],
): Promise<{
  skillsByTenant: Record<string, MySkill[]>;
  failedCount: number;
}> {
  const settled = await Promise.allSettled(
    tenants.map(async (tenant) => ({
      tenantId: tenant.tenant_id,
      skills: await marketApi.listUserMarketSkills(sourceId, tenant.tenant_id),
    })),
  );

  const skillsByTenant: Record<string, MySkill[]> = {};
  let failedCount = 0;
  for (const result of settled) {
    if (result.status === "fulfilled") {
      skillsByTenant[result.value.tenantId] = result.value.skills;
    } else {
      failedCount += 1;
    }
  }
  return { skillsByTenant, failedCount };
}

export function SkillOwnerLookupModal({
  open,
  skill,
  sourceId,
  onClose,
}: SkillOwnerLookupModalProps) {
  const [loading, setLoading] = useState(false);
  const [tenantCount, setTenantCount] = useState(0);
  const [failedCount, setFailedCount] = useState(0);
  const [rows, setRows] = useState<SkillOwnerRow[]>([]);
  const [tablePage, setTablePage] = useState(1);
  const [tablePageSize, setTablePageSize] = useState(
    DEFAULT_OWNER_LOOKUP_PAGE_SIZE,
  );
  const [searchInputText, setSearchInputText] = useState("");
  const [appliedSearchText, setAppliedSearchText] = useState("");
  const filteredRows = useMemo(() => {
    const keyword = normalizeSearchKeyword(appliedSearchText);
    return rows.filter((row) => matchesOwnerSearch(row, keyword));
  }, [rows, appliedSearchText]);

  const loadOwners = useCallback(async () => {
    if (!open || !skill || !sourceId) {
      return;
    }

    setLoading(true);
    setFailedCount(0);
    try {
      const tenants = await fetchTenantsBySource(sourceId);
      setTenantCount(tenants.length);
      const result = await loadTenantSkills(sourceId, tenants);
      setFailedCount(result.failedCount);
      setRows(
        buildSkillOwnerRows({
          marketSkill: skill,
          tenants,
          skillsByTenant: result.skillsByTenant,
        }),
      );
    } finally {
      setLoading(false);
    }
  }, [open, skill, sourceId]);

  useEffect(() => {
    if (!open) {
      setRows([]);
      setTenantCount(0);
      setFailedCount(0);
      setTablePage(1);
      setTablePageSize(DEFAULT_OWNER_LOOKUP_PAGE_SIZE);
      setSearchInputText("");
      setAppliedSearchText("");
      return;
    }
    setTablePage(1);
    setSearchInputText("");
    setAppliedSearchText("");
    void loadOwners();
  }, [open, loadOwners]);

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(filteredRows.length / tablePageSize));
    setTablePage((current) => Math.min(current, maxPage));
  }, [filteredRows.length, tablePageSize]);

  return (
    <Modal
      open={open}
      title={`拥有用户 - ${skill?.name || ""}`}
      width={920}
      onCancel={loading ? undefined : onClose}
      footer={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={loadOwners}>
          刷新
        </Button>,
        <Button key="close" type="primary" onClick={onClose}>
          关闭
        </Button>,
      ]}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <Text type="secondary">扫描用户：{tenantCount}</Text>
          <Text type="secondary">拥有用户：{rows.length}</Text>
          {failedCount > 0 && (
            <Text type="warning">读取失败：{failedCount}</Text>
          )}
        </div>
        <Input.Search
          allowClear
          enterButton="搜索"
          placeholder="搜索用户姓名或 ID"
          value={searchInputText}
          onChange={(event) => {
            setSearchInputText(event.target.value);
          }}
          onSearch={(value) => {
            setAppliedSearchText(value);
            setTablePage(1);
          }}
          style={{ maxWidth: 320 }}
        />
        <Table
          rowKey="tenant_id"
          loading={loading}
          size="small"
          dataSource={filteredRows}
          pagination={{
            current: tablePage,
            pageSize: tablePageSize,
            hideOnSinglePage: true,
            showSizeChanger: true,
            pageSizeOptions: OWNER_LOOKUP_PAGE_SIZE_OPTIONS,
            showTotal: (total) => `共 ${total} 个用户`,
            onChange: (nextPage, nextPageSize) => {
              setTablePage(nextPage);
              setTablePageSize(
                nextPageSize || DEFAULT_OWNER_LOOKUP_PAGE_SIZE,
              );
            },
          }}
          locale={{ emptyText: "当前没有用户拥有同名技能" }}
          columns={[
            {
              title: "用户",
              dataIndex: "tenant_name",
              key: "tenant_name",
              render: (_value, record) => (
                <div style={{ display: "grid", gap: 2 }}>
                  <Text strong>{record.tenant_name || record.tenant_id}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {record.tenant_id}
                  </Text>
                </div>
              ),
            },
            {
              title: "机构",
              dataIndex: "bbk_id",
              key: "bbk_id",
              render: (value) => value || "-",
            },
            {
              title: "技能目录",
              dataIndex: "skill_name",
              key: "skill_name",
            },
            {
              title: "市场版本",
              dataIndex: "market_version",
              key: "market_version",
              render: (value) => value || "-",
            },
            {
              title: "用户版本",
              dataIndex: "installed_version",
              key: "installed_version",
              render: (value) => value || "-",
            },
            {
              title: "状态",
              dataIndex: "enabled",
              key: "enabled",
              render: (enabled) => (
                <Tag color={enabled ? "green" : "default"}>
                  {enabled ? "已启用" : "已停用"}
                </Tag>
              ),
            },
            {
              title: "版本",
              dataIndex: "has_update",
              key: "has_update",
              render: (hasUpdate) => (
                <Tag color={hasUpdate ? "orange" : "blue"}>
                  {hasUpdate ? "可更新" : "已同步"}
                </Tag>
              ),
            },
          ]}
        />
      </Space>
    </Modal>
  );
}
