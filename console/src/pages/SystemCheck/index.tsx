import { useMemo, useState } from "react";
import { Alert, Button, Card, Form, Input, Result, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { SearchCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import api from "@/api";
import { PageHeader } from "@/components/PageHeader";
import { useAppMessage } from "@/hooks/useAppMessage";
import { useIframeStore } from "@/stores/iframeStore";
import type {
  CronAuthExpiryRequest,
  CronAuthExpiryResult,
  CronAuthExpiryStatus,
} from "@/api/types/systemCheck";
import styles from "./index.module.less";

const DEFAULT_AUTH_EXPIRY_SOURCE_ID = "RMASSIST";
const TENANT_ID_SPLIT_PATTERN = /[\n\r,，;\s]+/;

const STATUS_COLORS: Record<CronAuthExpiryStatus, string> = {
  valid: "green",
  expired: "red",
  missing_file: "gold",
  invalid_content: "volcano",
  unknown: "default",
};

export function parseTenantIds(input: string): string[] {
  const seen = new Set<string>();
  const tenantIds: string[] = [];
  for (const item of input.split(TENANT_ID_SPLIT_PATTERN)) {
    const tenantId = item.trim();
    if (!tenantId || seen.has(tenantId)) {
      continue;
    }
    seen.add(tenantId);
    tenantIds.push(tenantId);
  }
  return tenantIds;
}

export default function SystemCheckPage() {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const manager = useIframeStore((state) => state.manager);
  const isSuperManager = useIframeStore((state) => state.isSuperManager);
  const canManage = manager || isSuperManager;
  const [sourceId, setSourceId] = useState(DEFAULT_AUTH_EXPIRY_SOURCE_ID);
  const [tenantInput, setTenantInput] = useState("");
  const [results, setResults] = useState<CronAuthExpiryResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const columns = useMemo<ColumnsType<CronAuthExpiryResult>>(
    () => [
      {
        title: t("systemCheck.authExpiry.columns.tenantId", {
          defaultValue: "租户 ID",
        }),
        dataIndex: "tenant_id",
        key: "tenant_id",
      },
      {
        title: "Source ID",
        dataIndex: "source_id",
        key: "source_id",
      },
      {
        title: t("systemCheck.authExpiry.columns.status", {
          defaultValue: "状态",
        }),
        dataIndex: "status",
        key: "status",
        render: (status: CronAuthExpiryStatus) => (
          <Tag color={STATUS_COLORS[status]}>{status}</Tag>
        ),
      },
      {
        title: t("systemCheck.authExpiry.columns.expiry", {
          defaultValue: "过期时间",
        }),
        dataIndex: "user_info_expires_at",
        key: "user_info_expires_at",
        render: (value: string | null) => value || "-",
      },
      {
        title: t("systemCheck.authExpiry.columns.expired", {
          defaultValue: "已过期",
        }),
        dataIndex: "is_expired",
        key: "is_expired",
        render: (value: boolean | null) => {
          if (value === null) {
            return "-";
          }
          return value ? "是" : "否";
        },
      },
      {
        title: t("systemCheck.authExpiry.columns.message", {
          defaultValue: "消息",
        }),
        dataIndex: "message",
        key: "message",
      },
    ],
    [t],
  );

  if (!canManage) {
    return (
      <div className={styles.systemCheckPage}>
        <PageHeader
          parent={t("nav.systemSettings")}
          current={t("nav.systemCheck", { defaultValue: "系统自检" })}
        />
        <div className={styles.centerState}>
          <Result
            status="403"
            title="403"
            subTitle={t("systemCheck.forbidden", {
              defaultValue: "仅管理员可访问系统自检页面。",
            })}
          />
        </div>
      </div>
    );
  }

  const handleSubmit = async () => {
    const normalizedSourceId = sourceId.trim();
    const tenantIds = parseTenantIds(tenantInput);
    setValidationError(null);
    setRequestError(null);

    if (!normalizedSourceId) {
      setValidationError(
        t("systemCheck.authExpiry.sourceRequired", {
          defaultValue: "请输入 Source ID。",
        }),
      );
      return;
    }
    if (tenantIds.length === 0) {
      setValidationError(
        t("systemCheck.authExpiry.tenantRequired", {
          defaultValue: "请输入至少一个租户 ID。",
        }),
      );
      return;
    }

    const payload: CronAuthExpiryRequest = {
      source_id: normalizedSourceId,
      tenant_ids: tenantIds,
    };
    setLoading(true);
    try {
      const response = await api.checkCronAuthExpiry(payload);
      setResults(response.results);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      setRequestError(errorMessage);
      message.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.systemCheckPage}>
      <PageHeader
        parent={t("nav.systemSettings")}
        current={t("nav.systemCheck", { defaultValue: "系统自检" })}
      />
      <div className={styles.pageBody}>
        <Card
          className={styles.checkCard}
          title={t("systemCheck.authExpiry.title", {
            defaultValue: "鉴权过期查询",
          })}
          extra={<SearchCheck size={18} />}
        >
          <Form layout="vertical">
            <div className={styles.formGrid}>
              <Form.Item label="Source ID" htmlFor="system-check-source-id">
                <Input
                  id="system-check-source-id"
                  aria-label="Source ID"
                  value={sourceId}
                  onChange={(event) => setSourceId(event.target.value)}
                />
              </Form.Item>
              <Form.Item
                className={styles.tenantInput}
                htmlFor="system-check-tenant-ids"
                label={t("systemCheck.authExpiry.tenantIds", {
                  defaultValue: "租户 ID",
                })}
              >
                <Input.TextArea
                  id="system-check-tenant-ids"
                  aria-label={t("systemCheck.authExpiry.tenantIds", {
                    defaultValue: "租户 ID",
                  })}
                  value={tenantInput}
                  onChange={(event) => setTenantInput(event.target.value)}
                />
              </Form.Item>
            </div>
            {validationError ? (
              <Alert
                showIcon
                type="warning"
                message={validationError}
                style={{ marginBottom: 16 }}
              />
            ) : null}
            {requestError ? (
              <Alert
                showIcon
                type="error"
                message={requestError}
                style={{ marginBottom: 16 }}
              />
            ) : null}
            <div className={styles.actionRow}>
              <Button
                type="primary"
                htmlType="button"
                loading={loading}
                aria-label={t("common.search", { defaultValue: "查询" })}
                onClick={handleSubmit}
              >
                {t("common.search", { defaultValue: "查询" })}
              </Button>
            </div>
          </Form>
        </Card>
        <Table
          className={styles.resultTable}
          rowKey={(record) => `${record.source_id}:${record.tenant_id}`}
          columns={columns}
          dataSource={results}
          loading={loading}
          pagination={false}
        />
      </div>
    </div>
  );
}
