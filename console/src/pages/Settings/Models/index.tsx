import { useCallback, useMemo, useState } from "react";
import { Button, Input, Modal } from "@agentscope-ai/design";
import { PlusOutlined, SearchOutlined, SendOutlined } from "@ant-design/icons";
import { useProviders } from "./useProviders";
import {
  LoadingState,
  ProviderCard,
  CustomProviderModal,
  ModelsSection,
} from "./components";
import { PageHeader } from "@/components/PageHeader";
import { useTranslation } from "react-i18next";
import { useAppMessage } from "@/hooks/useAppMessage";
import { useIframeStore } from "@/stores/iframeStore";
import { TenantTargetPicker } from "@/components/TenantTargetPicker";
import api from "@/api";
import type { ProviderInfo } from "../../../api/types/provider";
import styles from "./index.module.less";

/* ------------------------------------------------------------------ */
/* Main Page                                                           */
/* ------------------------------------------------------------------ */

function ModelsPage() {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const manager = useIframeStore((state) => state.manager);
  const { providers, activeModels, loading, error, fetchAll } = useProviders();
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);
  const [addProviderOpen, setAddProviderOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // 供应商全量分发状态
  const [providersDistOpen, setProvidersDistOpen] = useState(false);
  const [providersDistLoading, setProvidersDistLoading] = useState(false);
  const [providersDistSubmitting, setProvidersDistSubmitting] = useState(false);
  const [providersDistTenantIds, setProvidersDistTenantIds] = useState<string[]>([]);
  const [selectedProvidersDistTenantIds, setSelectedProvidersDistTenantIds] =
    useState<string[]>([]);

  const refreshProvidersSilently = useCallback(() => {
    void fetchAll(false);
  }, [fetchAll]);

  const { regularProviders, localProviders } = useMemo(() => {
    const regular: ProviderInfo[] = [];
    const local: ProviderInfo[] = [];
    for (const p of providers) {
      if (p.is_local) local.push(p);
      else regular.push(p);
    }
    // Fuzzy search filter: match provider name (case-insensitive)
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return { regularProviders: regular, localProviders: local };
    }
    return {
      regularProviders: regular.filter((p) =>
        p.name.toLowerCase().includes(query),
      ),
      localProviders: local.filter((p) => p.name.toLowerCase().includes(query)),
    };
  }, [providers, searchQuery]);

  const handleMouseEnter = (providerId: string) => {
    setHoveredCard(providerId);
  };

  const handleMouseLeave = () => {
    setHoveredCard(null);
  };

  // ===== 供应商全量分发 =====

  const openProvidersDistModal = async () => {
    setProvidersDistOpen(true);
    setSelectedProvidersDistTenantIds([]);
    setProvidersDistLoading(true);
    try {
      const result = await api.listActiveModelDistributionTenants();
      setProvidersDistTenantIds(result.tenant_ids || []);
    } catch (error) {
      const errMsg =
        error instanceof Error ? error.message : t("models.distributeFailed");
      message.error(errMsg);
    } finally {
      setProvidersDistLoading(false);
    }
  };

  const closeProvidersDistModal = () => {
    if (providersDistSubmitting) return;
    setProvidersDistOpen(false);
    setSelectedProvidersDistTenantIds([]);
  };

  const handleDistributeProviders = async () => {
    if (!selectedProvidersDistTenantIds.length) return;

    setProvidersDistSubmitting(true);
    try {
      const result = await api.distributeProviders({
        target_tenant_ids: selectedProvidersDistTenantIds,
        overwrite: true,
      });
      const items = Array.isArray(result.results) ? result.results : [];
      const succeeded = items.filter((item) => item.success);
      const failed = items.filter((item) => !item.success);

      if (succeeded.length > 0) {
        const lines = succeeded.map((item) => {
          const suffix = item.bootstrapped
            ? ` (${t("models.distributeBootstrapped")})`
            : "";
          return `• ${item.tenant_id}${suffix}`;
        });
        message.success(
          t("models.distributeProvidersSuccess", { count: succeeded.length }),
        );
        Modal.confirm({
          title: t("models.distributeResultTitle"),
          content: (
            <div style={{ display: "grid", gap: 8 }}>
              <div>{t("models.distributeSuccessList")}</div>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {lines.join("\n")}
              </pre>
              {failed.length > 0 ? (
                <div>{t("models.distributeFailureInlineHint")}</div>
              ) : null}
            </div>
          ),
          okText: t("common.close"),
          cancelButtonProps: { style: { display: "none" } },
        });
      }

      if (failed.length > 0) {
        const failureLines = failed.map(
          (item) => `• ${item.tenant_id}: ${item.error || t("models.distributeFailed")}`,
        );
        Modal.confirm({
          title: t("models.distributePartialFailureTitle"),
          content: (
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
              {failureLines.join("\n")}
            </pre>
          ),
          okText: t("common.close"),
          cancelButtonProps: { style: { display: "none" } },
        });
      }

      setProvidersDistOpen(false);
      setSelectedProvidersDistTenantIds([]);
    } catch (error) {
      const errMsg =
        error instanceof Error ? error.message : t("models.distributeFailed");
      message.error(errMsg);
    } finally {
      setProvidersDistSubmitting(false);
    }
  };

  const renderProviderCards = (list: ProviderInfo[]) =>
    list.map((provider) => (
      <ProviderCard
        key={provider.id}
        provider={provider}
        activeModels={activeModels}
        onSaved={refreshProvidersSilently}
        isHover={hoveredCard === provider.id}
        onMouseEnter={() => handleMouseEnter(provider.id)}
        onMouseLeave={handleMouseLeave}
      />
    ));

  return (
    <div className={styles.settingsPage}>
      {loading ? (
        <LoadingState message={t("models.loading")} />
      ) : error ? (
        <LoadingState message={error} error onRetry={fetchAll} />
      ) : (
        <>
          {/* ---- LLM Section (top) ---- */}
          <PageHeader
            parent={t("nav.systemSettings")}
            current={t("models.llmTitle")}
          />
          {/* ---- Scrollable Content ---- */}
          <div className={styles.content}>
            <ModelsSection
              providers={providers}
              activeModels={activeModels}
              onSaved={fetchAll}
            />
            {/* ---- Providers Section ---- */}
            <div className={styles.providersBlock}>
              <div className={styles.sectionHeaderRow}>
                <PageHeader
                  current={t("models.providersTitle")}
                  className={styles.providersPageHeader}
                />
                <div className={styles.headerRight}>
                  {/* ---- Search ---- */}
                  <div className={styles.searchRow}>
                    <Input
                      placeholder={t("models.searchPlaceholder")}
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onPressEnter={() => {}}
                      className={styles.searchInput}
                      prefix={<SearchOutlined />}
                      allowClear
                    />
                    <Button
                      type="primary"
                      icon={<SearchOutlined />}
                      onClick={() => fetchAll()}
                      className={styles.searchBtn}
                    >
                      {t("models.search")}
                    </Button>
                  </div>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => setAddProviderOpen(true)}
                    className={styles.addProviderBtn}
                  >
                    {t("models.addProvider")}
                  </Button>
                  <Button
                    icon={<SendOutlined />}
                    onClick={openProvidersDistModal}
                    className={styles.addProviderBtn}
                    disabled={!manager}
                  >
                    {t("models.distributeProviders")}
                  </Button>
                </div>
              </div>

              {localProviders.length > 0 && (
                <div className={styles.providerGroup}>
                  {/* <h4 className={styles.providerGroupTitle}>
                  {t("models.localEmbedded")}
                </h4> */}
                  <div className={styles.providerCards}>
                    {renderProviderCards(localProviders)}
                  </div>
                </div>
              )}

              {regularProviders.length > 0 && (
                <div className={styles.providerGroup}>
                  <div className={styles.providerCards}>
                    {renderProviderCards(regularProviders)}
                  </div>
                </div>
              )}
            </div>

            <CustomProviderModal
              open={addProviderOpen}
              onClose={() => setAddProviderOpen(false)}
              onSaved={fetchAll}
            />

            {/* 供应商全量分发 Modal */}
            <Modal
              open={providersDistOpen}
              title={t("models.distributeProvidersTitle")}
              onCancel={closeProvidersDistModal}
              onOk={handleDistributeProviders}
              okButtonProps={{
                disabled: !selectedProvidersDistTenantIds.length,
                loading: providersDistSubmitting,
              }}
            >
              <div style={{ display: "grid", gap: 12 }}>
                <div style={{ color: "#666", fontSize: 12 }}>
                  {t("models.distributeProvidersHint")}
                </div>
                <div
                  style={{
                    padding: 12,
                    borderRadius: 8,
                    background: "#fff2f0",
                    border: "1px solid #ffccc7",
                    color: "#cf1322",
                  }}
                >
                  {t("models.distributeProvidersWarning")}
                </div>
                {providersDistLoading ? (
                  <div>{t("models.loading")}</div>
                ) : (
                  <TenantTargetPicker
                    tenantIds={providersDistTenantIds}
                    selectedTenantIds={selectedProvidersDistTenantIds}
                    onChange={setSelectedProvidersDistTenantIds}
                  />
                )}
              </div>
            </Modal>
          </div>
        </>
      )}
    </div>
  );
}

export default ModelsPage;
