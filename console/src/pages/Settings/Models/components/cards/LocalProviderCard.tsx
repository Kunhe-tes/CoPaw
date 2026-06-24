import { useState } from "react";
import { Card, Button } from "@agentscope-ai/design";
import type { ProviderInfo } from "../../../../../api/types";
import { ModelManageModal } from "../modals/ModelManageModal";
import { useTranslation } from "react-i18next";
import { AppstoreOutlined } from "@ant-design/icons";
import styles from "../../index.module.less";
import { providerIcon } from "../providerIcon";

interface LocalProviderCardProps {
  provider: ProviderInfo;
  onSaved: () => void;
}

export function LocalProviderCard({
  provider,
  onSaved,
}: LocalProviderCardProps) {
  const { t } = useTranslation();
  const [modelManageOpen, setModelManageOpen] = useState(false);

  const totalCount = provider.models.length + provider.extra_models.length;
  const statusReady = totalCount > 0;
  const statusLabel = statusReady
    ? t("models.available")
    : t("models.unavailable");

  return (
    <Card
      className={`${styles.providerCard} ${
        statusReady ? styles.enabledCard : ""
      }`}
    >
      <div className={styles.cardIdentity}>
        <div className={styles.providerBrand}>
          <div className={styles.providerIconFrame}>
            <img
              src={providerIcon(provider.id)}
              alt={provider.name}
              className={styles.providerIcon}
            />
          </div>
          <div className={styles.providerTitleText}>
            <div className={styles.providerNameLine} title={provider.name}>
              <span className={styles.cardName}>{provider.name}</span>
              <span className={styles.localTag}>{t("models.local")}</span>
            </div>
            <div className={styles.providerIdLine} title={provider.id}>
              <span className={styles.providerFieldLabel}>ID</span>
              <span className={styles.providerIdText}>{provider.id}</span>
            </div>
          </div>
        </div>
        <div className={styles.cardStatusHeader}>
          <span
            className={styles.statusDot}
            style={{
              backgroundColor: statusReady ? "#52c41a" : "#d9d9d9",
              boxShadow: statusReady
                ? "0 0 0 2px rgba(82, 196, 26, 0.2)"
                : "none",
            }}
          />
          <span
            className={`${styles.statusText} ${
              statusReady ? styles.enabled : styles.disabled
            }`}
          >
            {statusLabel}
          </span>
        </div>
      </div>

      <div className={styles.cardInfo}>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t("models.localType")}:</span>
          <span className={styles.infoValue}>{t("models.localEmbedded")}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t("models.model")}:</span>
          <span className={styles.infoValue}>
            {totalCount > 0
              ? t("models.modelsCount", { count: totalCount })
              : t("models.localDownloadFirst")}
          </span>
        </div>
      </div>

      <div className={styles.cardActions}>
        <Button
          type="text"
          size="small"
          icon={<AppstoreOutlined />}
          onClick={() => setModelManageOpen(true)}
          className={styles.actionBtn}
        >
          {t("models.models")}
        </Button>
      </div>

      <ModelManageModal
        provider={provider}
        open={modelManageOpen}
        onClose={() => setModelManageOpen(false)}
        onSaved={onSaved}
      />
    </Card>
  );
}
