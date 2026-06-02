import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  InputNumber,
  Result,
  Space,
  Spin,
  Switch,
  Tag,
} from "antd";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/PageHeader";
import { useAppMessage } from "@/hooks/useAppMessage";
import { sourceSystemConfigApi } from "@/api/modules/sourceSystemConfig";
import type {
  CurrentSourceSystemConfigResponse,
  SourceSystemConfig,
} from "@/api/types/sourceSystemConfig";
import { useIframeStore } from "@/stores/iframeStore";
import { useSourceSystemConfigStore } from "@/stores/sourceSystemConfigStore";
import { DEFAULT_SOURCE_ID } from "@/constants/identity";

import {
  CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES,
  TOOL_RESULT_COMPACT_NUMBER_FIELDS,
  clearImmediateTruncationConfig,
  enableImmediateTruncationConfig,
  readRegisteredSwitchValue,
  readImmediateTruncationConfig,
  readToolResultCompactConfig,
  validateToolOutputConfigs,
  writeRegisteredSwitchValue,
  writeImmediateTruncationValue,
  writeToolResultCompactValue,
} from "./registry";
import type { ImmediateTruncationConfigKey } from "./registry";
import styles from "./index.module.less";

function formatUpdatedAt(value?: string | null): string {
  if (!value) {
    return "未保存";
  }
  return value;
}

export default function SystemConfigPage() {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const isSuperManager = useIframeStore((state) => state.isSuperManager);
  const manager = useIframeStore((state) => state.manager);
  const activeSourceId =
    useIframeStore((state) => state.source) || DEFAULT_SOURCE_ID;
  const loadEffectiveConfig = useSourceSystemConfigStore(
    (state) => state.loadEffectiveConfig,
  );
  const canManage = isSuperManager || manager;
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [record, setRecord] =
    useState<CurrentSourceSystemConfigResponse | null>(null);
  const [draftConfig, setDraftConfig] = useState<SourceSystemConfig>({});
  const requestSeqRef = useRef(0);
  const activeSourceRef = useRef(activeSourceId);

  useEffect(() => {
    activeSourceRef.current = activeSourceId;
  }, [activeSourceId]);

  const beginRequest = (sourceId: string) => {
    requestSeqRef.current += 1;
    return {
      sourceId,
      requestId: requestSeqRef.current,
    };
  };

  const isCurrentRequest = (request: {
    sourceId: string;
    requestId: number;
  }) => {
    return (
      activeSourceRef.current === request.sourceId &&
      requestSeqRef.current === request.requestId
    );
  };

  const isLoadedSourceCurrent =
    record !== null && record.source_id === activeSourceId;
  const formDisabled = loading || saving || !isLoadedSourceCurrent;

  useEffect(() => {
    if (!canManage) {
      requestSeqRef.current += 1;
      setLoading(false);
      setSaving(false);
      setRequestError(null);
      setValidationError(null);
      setRecord(null);
      setDraftConfig({});
      return;
    }

    const request = beginRequest(activeSourceId);
    setLoading(true);
    setSaving(false);
    setRequestError(null);
    setValidationError(null);
    setRecord(null);
    setDraftConfig({});

    sourceSystemConfigApi
      .getCurrent()
      .then((response) => {
        if (
          !isCurrentRequest(request) ||
          response.source_id !== request.sourceId
        ) {
          return;
        }
        setRecord(response);
        setDraftConfig(response.config);
      })
      .catch((requestError) => {
        if (!isCurrentRequest(request)) {
          return;
        }
        setRequestError(
          requestError instanceof Error
            ? requestError.message
            : String(requestError),
        );
      })
      .finally(() => {
        if (isCurrentRequest(request)) {
          setLoading(false);
        }
      });
  }, [activeSourceId, canManage]);

  if (!canManage) {
    return (
      <div className={styles.systemConfigPage}>
        <PageHeader
          parent={t("nav.systemSettings")}
          current={t("nav.currentSourceConfig", {
            defaultValue: "当前系统配置",
          })}
        />
        <div className={styles.centerState}>
          <Result
            status="403"
            title="403"
            subTitle={t("sourceSystemConfigPage.forbidden", {
              defaultValue: "仅管理员可访问当前系统配置页面。",
            })}
          />
        </div>
      </div>
    );
  }

  const handleSwitchChange = (key: string, checked: boolean) => {
    if (formDisabled) {
      return;
    }
    const definition = CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES.find(
      (item) => item.key === key,
    );
    if (!definition) {
      return;
    }
    setValidationError(null);
    setDraftConfig((previous) =>
      writeRegisteredSwitchValue(previous, definition, checked),
    );
  };

  const handleToolResultEnabledChange = (checked: boolean) => {
    if (formDisabled) {
      return;
    }
    setValidationError(null);
    setDraftConfig((previous) =>
      writeToolResultCompactValue(previous, "enabled", checked),
    );
  };

  const handleToolResultNumberChange = (
    key: (typeof TOOL_RESULT_COMPACT_NUMBER_FIELDS)[number]["key"],
    value: number | null,
  ) => {
    if (formDisabled || typeof value !== "number") {
      return;
    }
    setValidationError(null);
    setDraftConfig((previous) =>
      writeToolResultCompactValue(previous, key, value),
    );
  };

  const handleEnableImmediateTruncation = (
    configKey: ImmediateTruncationConfigKey,
  ) => {
    if (formDisabled) {
      return;
    }
    setValidationError(null);
    setDraftConfig((previous) =>
      enableImmediateTruncationConfig(previous, configKey),
    );
  };

  const handleImmediateTruncationEnabledChange = (
    configKey: ImmediateTruncationConfigKey,
    checked: boolean,
  ) => {
    if (formDisabled) {
      return;
    }
    setValidationError(null);
    setDraftConfig((previous) =>
      writeImmediateTruncationValue(previous, configKey, "enabled", checked),
    );
  };

  const handleImmediateTruncationMaxBytesChange = (
    configKey: ImmediateTruncationConfigKey,
    value: number | null,
  ) => {
    if (formDisabled || typeof value !== "number") {
      return;
    }
    setValidationError(null);
    setDraftConfig((previous) =>
      writeImmediateTruncationValue(previous, configKey, "max_bytes", value),
    );
  };

  const handleRestoreImmediateTruncationInheritance = (
    configKey: ImmediateTruncationConfigKey,
  ) => {
    if (formDisabled) {
      return;
    }
    setValidationError(null);
    setDraftConfig((previous) =>
      clearImmediateTruncationConfig(previous, configKey),
    );
  };

  const handleSave = async () => {
    if (formDisabled) {
      return;
    }
    const validationError = validateToolOutputConfigs(draftConfig);
    if (validationError) {
      setValidationError(validationError);
      message.error(validationError);
      return;
    }
    const request = beginRequest(activeSourceId);
    setSaving(true);
    setRequestError(null);
    setValidationError(null);
    try {
      const nextRecord = await sourceSystemConfigApi.updateCurrent({
        config: draftConfig,
      });
      if (
        !isCurrentRequest(request) ||
        nextRecord.source_id !== request.sourceId
      ) {
        return;
      }
      setRecord(nextRecord);
      setDraftConfig(nextRecord.config);
      await loadEffectiveConfig(request.sourceId);
      if (!isCurrentRequest(request)) {
        return;
      }
      message.success(
        t("sourceSystemConfigPage.saveSuccess", {
          defaultValue: "当前系统配置已保存",
        }),
      );
    } catch (requestError) {
      const nextError =
        requestError instanceof Error
          ? requestError.message
          : String(requestError);
      if (!isCurrentRequest(request)) {
        return;
      }
      setRequestError(nextError);
      message.error(nextError);
    } finally {
      if (isCurrentRequest(request)) {
        setSaving(false);
      }
    }
  };

  const toolResultCompactConfig = readToolResultCompactConfig(draftConfig);
  const fileReadTruncationState = readImmediateTruncationConfig(
    draftConfig,
    "file_read_truncation",
  );

  const handleDelete = async () => {
    if (formDisabled) {
      return;
    }
    const request = beginRequest(activeSourceId);
    setSaving(true);
    setRequestError(null);
    setValidationError(null);
    try {
      await sourceSystemConfigApi.deleteCurrent();
      if (!isCurrentRequest(request)) {
        return;
      }
      const nextRecord = await sourceSystemConfigApi.getCurrent();
      if (
        !isCurrentRequest(request) ||
        nextRecord.source_id !== request.sourceId
      ) {
        return;
      }
      setRecord(nextRecord);
      setDraftConfig(nextRecord.config);
      await loadEffectiveConfig(request.sourceId);
      if (!isCurrentRequest(request)) {
        return;
      }
      message.success(
        t("sourceSystemConfigPage.deleteSuccess", {
          defaultValue: "当前系统配置已恢复默认态",
        }),
      );
    } catch (requestError) {
      const nextError =
        requestError instanceof Error
          ? requestError.message
          : String(requestError);
      if (!isCurrentRequest(request)) {
        return;
      }
      setRequestError(nextError);
      message.error(nextError);
    } finally {
      if (isCurrentRequest(request)) {
        setSaving(false);
      }
    }
  };

  return (
    <div className={styles.systemConfigPage}>
      <PageHeader
        parent={t("nav.systemSettings")}
        current={t("nav.currentSourceConfig", {
          defaultValue: "系统特性配置",
        })}
        subRow={
          <Space size={8}>
            <Tag color="blue">{activeSourceId}</Tag>
            {record ? (
              <Tag color={record.is_default ? "default" : "gold"}>
                {record.is_default
                  ? t("sourceSystemConfigPage.defaultState", {
                      defaultValue: "继承默认值",
                    })
                  : t("sourceSystemConfigPage.overrideState", {
                      defaultValue: "存在显式覆盖",
                    })}
              </Tag>
            ) : null}
          </Space>
        }
      />
      <div className={styles.pageBody}>
        {requestError ? (
          <Alert
            type="error"
            showIcon
            message={t("sourceSystemConfigPage.requestFailed", {
              defaultValue: "当前系统配置请求失败",
            })}
            description={requestError}
          />
        ) : null}

        {validationError ? (
          <Alert
            type="error"
            showIcon
            message={t("sourceSystemConfigPage.validationFailed", {
              defaultValue: "当前系统配置校验失败",
            })}
            description={validationError}
          />
        ) : null}

        {loading ? (
          <div className={styles.centerState}>
            <Spin size="large" />
          </div>
        ) : (
          <>
            <Card className={styles.metaCard}>
              <div className={styles.metaGrid}>
                <div>
                  <span className={styles.metaLabel}>
                    {t("sourceSystemConfigPage.sourceLabel", {
                      defaultValue: "当前系统",
                    })}
                  </span>
                  <span className={styles.metaValue}>{activeSourceId}</span>
                </div>
                <div>
                  <span className={styles.metaLabel}>
                    {t("sourceSystemConfigPage.versionLabel", {
                      defaultValue: "原始配置版本",
                    })}
                  </span>
                  <span className={styles.metaValue}>
                    {record?.version ?? 0}
                  </span>
                </div>
                <div>
                  <span className={styles.metaLabel}>
                    {t("sourceSystemConfigPage.updatedByLabel", {
                      defaultValue: "最近修改人",
                    })}
                  </span>
                  <span className={styles.metaValue}>
                    {record?.updated_by || "未保存"}
                  </span>
                </div>
                <div>
                  <span className={styles.metaLabel}>
                    {t("sourceSystemConfigPage.updatedAtLabel", {
                      defaultValue: "最近修改时间",
                    })}
                  </span>
                  <span className={styles.metaValue}>
                    {formatUpdatedAt(record?.updated_at)}
                  </span>
                </div>
              </div>
            </Card>

            <Card
              className={styles.switchCard}
              title={t("sourceSystemConfigPage.switchesTitle", {
                defaultValue: "受控功能开关",
              })}
            >
              <div className={styles.switchList}>
                {CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES.map((definition) => (
                  <div key={definition.key} className={styles.switchRow}>
                    <div className={styles.switchCopy}>
                      <span className={styles.switchTitle}>
                        {definition.title}
                      </span>
                      <span className={styles.switchDescription}>
                        {definition.description}
                      </span>
                    </div>
                    <Switch
                      checked={readRegisteredSwitchValue(
                        draftConfig,
                        definition,
                      )}
                      disabled={formDisabled}
                      onChange={(checked) =>
                        handleSwitchChange(definition.key, checked)
                      }
                    />
                  </div>
                ))}
              </div>
            </Card>

            <Card
              className={styles.switchCard}
              title={t("sourceSystemConfigPage.toolResultCompactTitle", {
                defaultValue: "工具输出控制",
              })}
            >
              <div className={styles.toolResultIntro}>
                {t("sourceSystemConfigPage.toolResultCompactIntro", {
                  defaultValue:
                    "当前系统下工具历史压缩和文件读取即时截断的解析配置。",
                })}
              </div>
              <section className={styles.toolOutputSection}>
                <div className={styles.toolOutputSectionHeader}>
                  <div className={styles.switchCopy}>
                    <span className={styles.switchTitle}>
                      {t("sourceSystemConfigPage.historyToolResultTitle", {
                        defaultValue: "历史工具结果压缩",
                      })}
                    </span>
                    <span className={styles.switchDescription}>
                      {t(
                        "sourceSystemConfigPage.historyToolResultDescription",
                        {
                          defaultValue:
                            "未保存系统覆盖时继承 Agent 配置；保存后当前系统下请求使用这些历史压缩阈值。",
                        },
                      )}
                    </span>
                  </div>
                </div>
                <div className={styles.switchRow}>
                  <div className={styles.switchCopy}>
                    <span className={styles.switchTitle}>
                      {t("sourceSystemConfigPage.toolResultEnabled", {
                        defaultValue: "启用工具结果压缩",
                      })}
                    </span>
                    <span className={styles.switchDescription}>
                      {t(
                        "sourceSystemConfigPage.toolResultEnabledDescription",
                        {
                          defaultValue:
                            "关闭后当前系统的历史工具结果不再压缩为 toolresult 文件。",
                        },
                      )}
                    </span>
                  </div>
                  <Switch
                    checked={toolResultCompactConfig.enabled}
                    disabled={formDisabled}
                    onChange={handleToolResultEnabledChange}
                  />
                </div>
                <div className={styles.numberGrid}>
                  {TOOL_RESULT_COMPACT_NUMBER_FIELDS.map((definition) => (
                    <label key={definition.key} className={styles.numberField}>
                      <span className={styles.numberLabel}>
                        {definition.title}
                      </span>
                      <InputNumber
                        min={definition.min}
                        max={definition.max}
                        step={definition.step}
                        value={toolResultCompactConfig[definition.key]}
                        disabled={formDisabled}
                        onChange={(value) =>
                          handleToolResultNumberChange(definition.key, value)
                        }
                      />
                    </label>
                  ))}
                </div>
              </section>

              <section className={styles.toolOutputSection}>
                <div className={styles.toolOutputSectionHeader}>
                  <div className={styles.switchCopy}>
                    <span className={styles.switchTitle}>
                      {t("sourceSystemConfigPage.fileReadTruncationTitle", {
                        defaultValue: "文件读取截断",
                      })}
                    </span>
                    <span className={styles.switchDescription}>
                      {t(
                        "sourceSystemConfigPage.fileReadTruncationDescription",
                        {
                          defaultValue:
                            "缺少独立配置时继续使用历史工具结果的近期阈值；显式配置后由本段接管。",
                        },
                      )}
                    </span>
                  </div>
                  <Tag
                    color={fileReadTruncationState.explicit ? "green" : "blue"}
                  >
                    {fileReadTruncationState.explicit
                      ? fileReadTruncationState.config.enabled
                        ? t(
                            "sourceSystemConfigPage.fileReadIndependentEnabledState",
                            {
                              defaultValue: "独立配置已启用",
                            },
                          )
                        : t(
                            "sourceSystemConfigPage.fileReadIndependentDisabledState",
                            {
                              defaultValue: "独立配置已关闭",
                            },
                          )
                      : t("sourceSystemConfigPage.fileReadInheritedState", {
                          defaultValue: "继承旧工具结果近期阈值",
                        })}
                  </Tag>
                </div>
                {fileReadTruncationState.explicit ? (
                  <>
                    <div className={styles.switchRow}>
                      <div className={styles.switchCopy}>
                        <span className={styles.switchTitle}>
                          {t("sourceSystemConfigPage.fileReadEnabledTitle", {
                            defaultValue: "启用文件读取截断",
                          })}
                        </span>
                        <span className={styles.switchDescription}>
                          {t(
                            "sourceSystemConfigPage.fileReadEnabledDescription",
                            {
                              defaultValue:
                                "关闭后当前系统的文件读取即时输出不再由 SWE 截断。",
                            },
                          )}
                        </span>
                      </div>
                      <Switch
                        checked={fileReadTruncationState.config.enabled}
                        disabled={formDisabled}
                        onChange={(checked) =>
                          handleImmediateTruncationEnabledChange(
                            "file_read_truncation",
                            checked,
                          )
                        }
                      />
                    </div>
                    <div className={styles.numberGrid}>
                      <label className={styles.numberField}>
                        <span className={styles.numberLabel}>
                          {t("sourceSystemConfigPage.fileReadMaxBytesLabel", {
                            defaultValue: "输出片段字节数",
                          })}
                        </span>
                        <InputNumber
                          min={1000}
                          step={1000}
                          value={fileReadTruncationState.config.max_bytes}
                          disabled={
                            formDisabled ||
                            !fileReadTruncationState.config.enabled
                          }
                          onChange={(value) =>
                            handleImmediateTruncationMaxBytesChange(
                              "file_read_truncation",
                              value,
                            )
                          }
                        />
                      </label>
                    </div>
                    <Button
                      disabled={formDisabled}
                      onClick={() =>
                        handleRestoreImmediateTruncationInheritance(
                          "file_read_truncation",
                        )
                      }
                    >
                      {t("sourceSystemConfigPage.restoreInheritance", {
                        defaultValue: "恢复继承",
                      })}
                    </Button>
                  </>
                ) : (
                  <Button
                    disabled={formDisabled}
                    onClick={() =>
                      handleEnableImmediateTruncation("file_read_truncation")
                    }
                  >
                    {t("sourceSystemConfigPage.enableFileReadTruncation", {
                      defaultValue: "启用独立配置",
                    })}
                  </Button>
                )}
              </section>

            </Card>

            <div className={styles.actionRow}>
              <Button
                danger
                onClick={handleDelete}
                disabled={formDisabled || record?.is_default}
              >
                {t("common.delete")}
              </Button>
              <Button
                type="primary"
                loading={saving}
                disabled={formDisabled}
                onClick={handleSave}
              >
                {t("common.save")}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
