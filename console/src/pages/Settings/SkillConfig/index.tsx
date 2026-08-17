import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Empty,
  Form,
  Input,
  InputNumber,
  Result,
  Select,
  Skeleton,
  Switch,
  Tooltip,
} from "antd";
import { CircleX, Plus, Settings2, SquarePen } from "lucide-react";
import { cronJobApi } from "@/api/modules/cronjob";
import {
  buildSkillConfigCreatePayload,
  buildSkillConfigUpdatePayload,
  skillConfigApi,
  type SkillConfigFormValues,
  type SkillConfigItem,
} from "@/api/modules/skillConfig";
import type { CronJobSpecOutput } from "@/api/types";
import { getBbkDisplayName } from "@/constants/bbk";
import { DEFAULT_BBK_ID } from "@/constants/identity";
import { useAppMessage } from "@/hooks/useAppMessage";
import { useIframeStore } from "@/stores/iframeStore";
import {
  getSkillInspectionMock,
  type SkillInspectionPlaceholder,
} from "./inspectionMock";
import styles from "./index.module.less";

type EditorMode = "view" | "create" | "edit";

interface SkillConfigEditorValues extends SkillConfigFormValues {
  cronJobId: string;
}

const DEFAULT_FORM_VALUES: SkillConfigEditorValues = {
  cronJobId: "",
  skillId: "",
  name: "",
  sort: 0,
  groupId: undefined,
  businessCenterEnabled: false,
  customerInsightEnabled: false,
  outboundCallEnabled: false,
};

function getErrorStatus(error: unknown): number | undefined {
  return error instanceof Error
    ? (error as Error & { status?: number }).status
    : undefined;
}

function toEditorValues(item: SkillConfigItem): SkillConfigEditorValues {
  return {
    cronJobId: item.skillId,
    skillId: item.skillId,
    name: item.name,
    sort: item.sort,
    groupId: item.groupId,
    businessCenterEnabled: item.businessCenterEnabled,
    customerInsightEnabled: item.customerInsightEnabled,
    outboundCallEnabled: item.outboundCallEnabled,
  };
}

function SkillList({
  items,
  selectedId,
  onSelect,
  onEdit,
  onCreate,
}: {
  items: SkillConfigItem[];
  selectedId: string | null;
  onSelect: (item: SkillConfigItem) => void;
  onEdit: (item: SkillConfigItem) => void;
  onCreate: () => void;
}) {
  return (
    <aside className={styles.skillListPanel} aria-label="SKILL 列表">
      <div className={styles.panelHeader}>
        <h2>SKILL 列表</h2>
        <Button
          type="primary"
          size="small"
          icon={<Plus size={14} />}
          onClick={onCreate}
        >
          新增
        </Button>
      </div>
      <div className={styles.skillList}>
        {items.map((item) => {
          const selected = selectedId === item.skillId;
          return (
            <div
              key={item.skillId}
              className={`${styles.skillRow}${
                selected ? ` ${styles.skillRowSelected}` : ""
              }`}
            >
              <button
                type="button"
                className={styles.skillSelectButton}
                onClick={() => onSelect(item)}
                aria-current={selected ? "page" : undefined}
              >
                <span
                  className={`${styles.statusDot}${
                    item.enabled ? ` ${styles.statusDotEnabled}` : ""
                  }`}
                  aria-hidden="true"
                />
                <span className={styles.skillName} title={item.name}>
                  {item.name || item.skillId}
                </span>
              </button>
              <Tooltip title={`编辑 ${item.name || item.skillId}`}>
                <button
                  type="button"
                  className={styles.editIconButton}
                  onClick={() => onEdit(item)}
                  aria-label={`编辑 ${item.name || item.skillId}`}
                >
                  <SquarePen size={15} />
                </button>
              </Tooltip>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

function InspectionPanel({
  data,
}: {
  data: SkillInspectionPlaceholder | null;
}) {
  return (
    <section
      className={styles.inspectionPanel}
      aria-labelledby="inspection-title"
    >
      <div className={styles.sectionHeading}>
        <span className={styles.sectionMarker} aria-hidden="true" />
        <h2 id="inspection-title">回检</h2>
      </div>
      {data?.sections.map((section, index) => (
        <div className={styles.inspectionSection} key={section.title}>
          <div className={styles.inspectionSectionTitle}>
            <span className={styles.stepBadge}>{index + 1}</span>
            <strong>{section.title}</strong>
            <span>{section.description}</span>
          </div>
          <div className={styles.metricGrid}>
            {section.metrics.map((metric) => (
              <div className={styles.metricCard} key={metric.label}>
                <span className={styles.metricLabel}>{metric.label}</span>
                <div className={styles.metricValue}>
                  {metric.value}
                  {metric.suffix ? <small>{metric.suffix}</small> : null}
                </div>
                <span className={styles.metricDescription}>
                  {metric.description}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className={styles.depthSection}>
        <div className={styles.sectionHeading}>
          <span className={styles.sectionMarker} aria-hidden="true" />
          <h3>L2 客户级方案模块滚动深度</h3>
        </div>
        <div className={styles.depthList}>
          {data?.depthItems.map((item, index) => (
            <div className={styles.depthRow} key={item.label}>
              <span className={styles.depthIndex}>{index + 1}</span>
              <span className={styles.depthLabel}>{item.label}</span>
              <strong>{item.value}</strong>
              <span className={styles.depthTrack} aria-hidden="true" />
            </div>
          ))}
        </div>
        <p className={styles.placeholderHint}>
          回检接口接入后，将在此展示真实触达与转化数据。
        </p>
      </div>
    </section>
  );
}

export default function SkillConfigPage() {
  const { message } = useAppMessage();
  const bbkId = useIframeStore((state) => state.bbk) || DEFAULT_BBK_ID;
  const [form] = Form.useForm<SkillConfigEditorValues>();
  const [configs, setConfigs] = useState<SkillConfigItem[]>([]);
  const [cronJobs, setCronJobs] = useState<CronJobSpecOutput[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedConfig, setSelectedConfig] = useState<SkillConfigItem | null>(
    null,
  );
  const [inspection, setInspection] =
    useState<SkillInspectionPlaceholder | null>(null);
  const [mode, setMode] = useState<EditorMode>("view");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const cronOptions = useMemo(() => {
    const options = cronJobs.map((job) => ({ value: job.id, label: job.name }));
    if (
      selectedConfig &&
      !options.some((option) => option.value === selectedConfig.skillId)
    ) {
      options.unshift({
        value: selectedConfig.skillId,
        label: selectedConfig.name || selectedConfig.skillId,
      });
    }
    return options;
  }, [cronJobs, selectedConfig]);

  const groupOptions = useMemo(() => {
    const groups = configs.flatMap((item) =>
      item.groupId
        ? [
            {
              value: item.groupId,
              label: item.groupName || item.groupId,
            },
          ]
        : [],
    );
    return Array.from(
      new Map(groups.map((group) => [group.value, group])).values(),
    );
  }, [configs]);

  const loadConfigs = async () => {
    const nextConfigs = await skillConfigApi.listSkillConfigs(bbkId);
    setConfigs(nextConfigs);
    return nextConfigs;
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setListError(null);
    Promise.allSettled([
      skillConfigApi.listSkillConfigs(bbkId),
      cronJobApi.listCronJobs(),
    ])
      .then(([configResult, cronResult]) => {
        if (cancelled) return;
        if (configResult.status === "fulfilled") {
          setConfigs(configResult.value);
          if (configResult.value.length) {
            setSelectedId(configResult.value[0].skillId);
          }
        } else if (getErrorStatus(configResult.reason) === 500) {
          setConfigs([]);
          setSelectedId(null);
          setSelectedConfig(null);
          setInspection(null);
          setMode("view");
        } else {
          const errorMessage =
            configResult.reason instanceof Error
              ? configResult.reason.message
              : "请稍后重试";
          setListError(errorMessage);
          message.error(errorMessage);
        }
        if (cronResult.status === "fulfilled") {
          setCronJobs(cronResult.value ?? []);
        } else {
          message.error("定时任务列表加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [bbkId, message, reloadKey]);

  useEffect(() => {
    if (!selectedId || mode === "create") return;
    let cancelled = false;
    setDetailLoading(true);
    Promise.all([
      skillConfigApi.getSkillConfigDetail(selectedId, bbkId),
      getSkillInspectionMock(selectedId),
    ])
      .then(([detail, inspectionData]) => {
        if (cancelled) return;
        setSelectedConfig(detail);
        setInspection(inspectionData);
        form.setFieldsValue(toEditorValues(detail));
      })
      .catch((error) => {
        if (!cancelled) {
          message.error(
            error instanceof Error ? error.message : "SKILL 详情加载失败",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [bbkId, form, message, mode, selectedId]);

  const handleCreate = async () => {
    setMode("create");
    setSelectedId(null);
    setSelectedConfig(null);
    form.setFieldsValue(DEFAULT_FORM_VALUES);
    setInspection(await getSkillInspectionMock("new"));
  };

  const handleSelect = (item: SkillConfigItem) => {
    setMode("view");
    setSelectedId(item.skillId);
  };

  const handleEdit = (item: SkillConfigItem) => {
    setMode("edit");
    setSelectedId(item.skillId);
  };

  const handleCronJobChange = (jobId: string) => {
    const job = cronJobs.find((item) => item.id === jobId);
    form.setFieldsValue({
      skillId: jobId,
      name: job?.name || jobId,
    });
  };

  const handleCancel = () => {
    if (mode === "create") {
      if (!configs.length) {
        setMode("view");
        setInspection(null);
        return;
      }
      setSelectedId(configs[0].skillId);
    } else if (selectedConfig) {
      form.setFieldsValue(toEditorValues(selectedConfig));
    }
    setMode("view");
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const groupName = groupOptions.find(
        (option) => option.value === values.groupId,
      )?.label;
      if (mode === "create") {
        const bbkName =
          configs.find((item) => item.bbkId === bbkId)?.bbkName ||
          getBbkDisplayName(bbkId);
        const createPayload = buildSkillConfigCreatePayload(
          values,
          bbkId,
          bbkName,
          groupName,
        );
        const createdConfig = await skillConfigApi.createSkillConfig(
          createPayload,
        );
        setSelectedConfig(createdConfig);
        form.setFieldsValue(toEditorValues(createdConfig));
        message.success("SKILL 触发规则创建成功");
      } else {
        const updatePayload = buildSkillConfigUpdatePayload(
          values,
          selectedConfig ?? undefined,
          bbkId,
          groupName,
        );
        const updatedConfig = await skillConfigApi.updateSkillConfig(
          updatePayload,
        );
        setSelectedConfig(updatedConfig);
        form.setFieldsValue(toEditorValues(updatedConfig));
        message.success("SKILL 触发规则更新成功");
      }
    } catch (error) {
      if (error instanceof Error) message.error(error.message);
      setSaving(false);
      return;
    }

    setMode("view");
    setSelectedId(values.skillId);
    try {
      const nextConfigs = await loadConfigs();
      setSelectedId(values.skillId || nextConfigs[0]?.skillId || null);
    } catch {
      message.warning("保存成功，但 SKILL 列表刷新失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <Skeleton active />
        </div>
      </div>
    );
  }

  if (listError) {
    return (
      <div className={styles.page}>
        <div className={styles.errorState}>
          <Result
            className={styles.errorResult}
            status="error"
            icon={
              <CircleX
                className={styles.errorIcon}
                size={44}
                strokeWidth={1.75}
                aria-hidden="true"
              />
            }
            title="SKILL 配置加载失败"
            subTitle={listError}
            extra={
              <Button
                type="primary"
                onClick={() => setReloadKey((key) => key + 1)}
              >
                重新加载
              </Button>
            }
          />
        </div>
      </div>
    );
  }

  const showWorkspace =
    configs.length > 0 || mode === "create" || selectedId !== null;

  return (
    <div className={styles.page}>
      {!showWorkspace ? (
        <div className={styles.emptyState}>
          <Empty
            image={<Settings2 size={52} strokeWidth={1.35} />}
            description={
              <div className={styles.emptyCopy}>
                <strong>暂无 SKILL 配置</strong>
                <span>创建第一条触发规则后，可在这里查看和维护回检配置。</span>
              </div>
            }
          >
            <Button
              type="primary"
              size="large"
              icon={<Plus size={17} />}
              onClick={handleCreate}
            >
              新增 SKILL
            </Button>
          </Empty>
        </div>
      ) : (
        <div className={styles.workspace}>
          <SkillList
            items={configs}
            selectedId={selectedId}
            onSelect={handleSelect}
            onEdit={handleEdit}
            onCreate={handleCreate}
          />
          <section className={styles.rulePanel} aria-labelledby="rule-title">
            <div className={styles.rulePanelHeader}>
              <div className={styles.sectionHeading}>
                <span className={styles.sectionMarker} aria-hidden="true" />
                <h2 id="rule-title">SKILL 触发规则</h2>
              </div>
              {mode !== "view" ? (
                <div className={styles.formActions}>
                  <Button size="small" onClick={handleCancel}>
                    取消
                  </Button>
                  <Button
                    type="primary"
                    size="small"
                    loading={saving}
                    onClick={handleSave}
                  >
                    {mode === "create" ? "创建" : "保存"}
                  </Button>
                </div>
              ) : null}
            </div>
            {detailLoading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : (
              <Form
                form={form}
                layout="vertical"
                disabled={mode === "view"}
                requiredMark={false}
                className={styles.ruleForm}
              >
                <Form.Item name="skillId" label="SKILL ID">
                  <Input
                    readOnly
                    className={styles.skillIdInput}
                    placeholder="选择名称后自动生成"
                  />
                </Form.Item>
                <Form.Item
                  name="cronJobId"
                  label="名称"
                  rules={[{ required: true, message: "请选择定时任务" }]}
                >
                  <Select
                    showSearch
                    optionFilterProp="label"
                    options={cronOptions}
                    placeholder="请选择定时任务"
                    onChange={handleCronJobChange}
                  />
                </Form.Item>
                <Form.Item name="name" hidden>
                  <Input />
                </Form.Item>
                <div className={styles.sortRow}>
                  <Form.Item name="sort" label="排序">
                    <InputNumber min={0} precision={0} />
                  </Form.Item>
                  <span>数值越小越优先</span>
                </div>
                <div className={styles.ruleDivider} />
                <Form.Item
                  name="businessCenterEnabled"
                  label="商机中心"
                  valuePropName="checked"
                  className={styles.switchField}
                >
                  <Switch size="small" />
                </Form.Item>
                <div className={styles.groupField}>
                  <Form.Item name="groupId" label="所属分组">
                    <Select
                      allowClear
                      options={groupOptions}
                      placeholder="请选择所属分组"
                    />
                  </Form.Item>
                </div>
                <Form.Item
                  name="customerInsightEnabled"
                  label="客户洞察"
                  valuePropName="checked"
                  className={styles.switchField}
                >
                  <Switch size="small" />
                </Form.Item>
                <Form.Item
                  name="outboundCallEnabled"
                  label="电访"
                  valuePropName="checked"
                  className={styles.switchField}
                >
                  <Switch size="small" />
                </Form.Item>
              </Form>
            )}
          </section>
          <InspectionPanel data={inspection} />
        </div>
      )}
    </div>
  );
}
