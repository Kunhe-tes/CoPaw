import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Input, InputNumber, Select, Switch, Tabs } from "antd";
import { Button, Drawer, Form, Modal } from "@agentscope-ai/design";
import api from "@/api";
import {
  schedulerCronApi,
  targetManagedContext,
} from "@/api/modules/schedulerCron";
import type {
  ManagedCronContext,
  ManagedCronSpec,
  ManagedJob,
  ManagedOperation,
} from "@/api/types/schedulerCron";
import { useExecutionModelOptions } from "@/hooks/useExecutionModelOptions";
import { CronJobFormBody } from "../CronJobs/components/CronJobFormBody";
import { DEFAULT_FORM_VALUES } from "../CronJobs/components/constants";
import {
  buildSkillSelectOptions,
  type SkillSelectOption,
} from "../CronJobs/helpers";
import {
  buildManagedCronFormValues,
  buildManagedCronSubmitPayload,
  type ManagedCronFormValues,
} from "./scheduleForm";
import { detailToJob, failureMessage, RequestIdentity } from "./helpers";
import styles from "../CronJobs/index.module.less";
import { ManagedDateRangeField } from "./ManagedDateRangeField";
import { isBroadcastChildJob } from "../CronJobs/components/columns";
import { ManagedModeSettings } from "./ManagedModeModal";
import { MODE_LABELS } from "./helpers";

interface Props {
  context: ManagedCronContext;
  job: ManagedJob | null;
  saving: boolean;
  onSave: (
    job: ManagedJob | null,
    spec: ManagedCronSpec,
    requestId: string,
    syncChildren?: boolean,
  ) => Promise<ManagedOperation | null>;
  onClose: () => void;
  onLoaded?: (job: ManagedJob) => void;
  onChanged?: () => void;
  onSyncStarted?: (job: ManagedJob, taskId: string) => void;
}

/** 原表单只负责编辑展示；服务端 ID、版本和启停走新版协议。 */
export function ManagedJobEditor({
  context,
  job,
  saving,
  onSave,
  onClose,
  onLoaded,
  onChanged,
  onSyncStarted,
}: Props) {
  const [form] = Form.useForm<ManagedCronFormValues>();

  const models = useExecutionModelOptions(true);
  const [skills, setSkills] = useState<SkillSelectOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState(job);
  const [hasChildren, setHasChildren] = useState(false);
  const [activeTab, setActiveTab] = useState("basic");
  const [basicDirty, setBasicDirty] = useState(false);
  const [modeDirty, setModeDirty] = useState(false);
  const [modeBusy, setModeBusy] = useState(false);
  const [localSaving, setLocalSaving] = useState<"save" | "sync" | null>(null);
  const [scheduleConfirmation, setScheduleConfirmation] = useState<
    string | null
  >(null);
  const [revision, setRevision] = useState(0);
  const contentDirty = useRef(false);
  const lock = useRef(false);
  const confirmation = useRef<ReturnType<typeof Modal.confirm> | null>(null);
  const scheduleAnswer = useRef<((confirmed: boolean) => void) | null>(null);
  const inherited = Boolean(snapshot && isBroadcastChildJob(snapshot));
  const modeContext = useMemo(
    () => (snapshot ? targetManagedContext(context, snapshot) : context),
    [context, snapshot],
  );
  const refresh = () => {
    onChanged?.();
    setRevision((value) => value + 1);
  };
  const guard = (next: () => void) => {
    if (lock.current || saving || modeBusy) return;
    if (!basicDirty && !modeDirty) {
      next();
      return;
    }
    confirmation.current = Modal.confirm({
      title: "有尚未保存的修改",
      content: "离开后将丢弃当前页签的修改，是否继续？",
      okText: "丢弃修改",
      cancelText: "继续编辑",
      onOk: () => {
        if (!mounted.current) return;
        if (snapshot) form.setFieldsValue(buildManagedCronFormValues(snapshot));
        setBasicDirty(false);
        contentDirty.current = false;
        setModeDirty(false);
        next();
      },
    });
  };
  const request = useRef(new RequestIdentity());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    let alive = true;
    const load = async () => {
      setLoading(true);
      setScheduleConfirmation(null);
      setReady(false);
      setError(null);
      try {
        const [detail, options, timezone] = await Promise.all([
          job
            ? schedulerCronApi.detail(
                targetManagedContext(context, job),
                job.id,
              )
            : Promise.resolve(null),
          api.listSweSkills(context.source_id),
          api.getUserTimezone(),
        ]);
        if (!alive) return;
        const current = detail ? detailToJob(detail) : null;
        if (
          current &&
          job &&
          current.definition_version < job.definition_version
        )
          throw new Error("任务详情版本落后于列表，请刷新后重新编辑。");
        let children = false;
        if (current && !isBroadcastChildJob(current)) {
          const page = await schedulerCronApi.childrenPreview(
            targetManagedContext(context, current),
            current.id,
          );
          if (!Array.isArray(page.items))
            throw new Error("子任务信息不可用，请刷新后重试");
          children = page.items.length > 0;
        }
        if (!alive) return;
        setHasChildren(children);
        if (current) onLoaded?.(current);
        setSnapshot(current);
        setSkills(buildSkillSelectOptions(options.skills ?? []));
        form.setFieldsValue(
          current
            ? buildManagedCronFormValues(current)
            : {
                ...DEFAULT_FORM_VALUES,
                recheckEnabled: false,
                recheckDelay: 10,
                recheckUnit: "minutes",
                recheckInstruction: "",
                id: "由系统自动分配",
                schedule: {
                  ...DEFAULT_FORM_VALUES.schedule,
                  run_on_non_workday: false,
                  timezone: timezone.timezone || "UTC",
                },
                dispatch: {
                  ...DEFAULT_FORM_VALUES.dispatch,
                  target: { user_id: context.tenant_id, session_id: "" },
                },
              },
        );
        contentDirty.current = false;
        setBasicDirty(false);
        setReady(true);
      } catch (failure) {
        if (alive) setError(failureMessage(failure));
      } finally {
        if (alive) setLoading(false);
      }
    };
    void load();
    return () => {
      alive = false;
      mounted.current = false;
      confirmation.current?.destroy();
      scheduleAnswer.current?.(false);
      scheduleAnswer.current = null;
    };
  }, [context, job, form, onLoaded, revision]);
  const answerScheduleConfirmation = (confirmed: boolean) => {
    setScheduleConfirmation(null);
    scheduleAnswer.current?.(confirmed);
    scheduleAnswer.current = null;
  };
  const submit = async (
    values: ManagedCronFormValues,
    syncChildren = false,
  ) => {
    if (!ready || loading || saving || lock.current) return;
    lock.current = true;
    setLocalSaving(syncChildren ? "sync" : "save");
    setError(null);

    try {
      const spec = buildManagedCronSubmitPayload(values, snapshot);
      const dates = spec.run_date_range;
      const previousDates = snapshot?.run_date_range;
      const dateChanged =
        dates?.start_date !== previousDates?.start_date ||
        dates?.end_date !== previousDates?.end_date;
      const scheduleChanges = snapshot
        ? [
            spec.schedule.cron !== snapshot.schedule.cron && "Cron 表达式",
            spec.schedule.timezone !== snapshot.schedule.timezone && "时区",
          ].filter(Boolean)
        : [];
      const scheduleChanged = scheduleChanges.length > 0;
      // 只认用户对正文字段的编辑，不把隐藏字段的注册/卸载当成修改。
      const definitionChanged = contentDirty.current;
      if (hasChildren && !syncChildren && (scheduleChanged || dateChanged)) {
        const fields = [
          ...scheduleChanges,
          ...(dateChanged ? ["可执行日期"] : []),
        ].join("、");
        const confirmed = await new Promise<boolean>((resolve) => {
          scheduleAnswer.current = resolve;
          setScheduleConfirmation(`修改后的${fields}将同步到所有分发子任务。`);
        });
        if (!confirmed || !mounted.current) return;
      }
      let operation: ManagedOperation | null;
      if (snapshot && dateChanged && !definitionChanged && !scheduleChanged) {
        if (!snapshot.management_version || inherited)
          throw new Error("当前任务不能单独修改日期，请刷新或在父任务操作");
        const body = { dates, version: snapshot.management_version };
        const result = await schedulerCronApi.setDateRange(
          targetManagedContext(context, snapshot),
          snapshot.id,
          dates ?? null,
          snapshot.management_version,
          request.current.for(body),
        );
        operation = result.operation;
        if (mounted.current) onChanged?.();
      } else {
        const groupSync = snapshot && !inherited ? syncChildren : undefined;
        operation = await onSave(
          snapshot,
          spec,
          request.current.for({ spec, groupSync }),
          groupSync,
        );
      }
      const waitsForSync = syncChildren || (hasChildren && scheduleChanged);
      if (
        mounted.current &&
        operation &&
        operation.status !== "failed" &&
        (!waitsForSync || operation.status === "completed")
      ) {
        if (snapshot && operation.broadcast_task_id && onSyncStarted)
          onSyncStarted(snapshot, operation.broadcast_task_id);
        else onClose();
      } else if (mounted.current)
        setError(
          "保存结果尚未确认，请保持原内容重试，并核对列表和操作进度；不要重复新建任务。",
        );
    } catch (failure) {
      if (mounted.current) setError(failureMessage(failure));
    } finally {
      lock.current = false;
      if (mounted.current) setLocalSaving(null);
    }
  };
  return (
    <Drawer
      open
      width={720}
      placement="right"
      title={job ? "任务设置" : "创建定时任务"}
      onClose={() => guard(onClose)}
      destroyOnClose
      footer={
        <div className={styles.formActions}>
          <Button
            disabled={Boolean(localSaving) || saving || modeBusy}
            onClick={() => guard(onClose)}
          >
            取消
          </Button>
          {activeTab === "basic" && (
            <>
              <Button
                type="primary"
                disabled={loading || !ready || saving || localSaving === "sync"}
                loading={localSaving === "save"}
                onClick={() => form.submit()}
              >
                保存
              </Button>
              {hasChildren && (
                <Button
                  disabled={
                    loading || !ready || saving || localSaving === "save"
                  }
                  loading={localSaving === "sync"}
                  onClick={() => {
                    void form.validateFields().then(
                      (values) => submit(values, true),
                      () => undefined,
                    );
                  }}
                >
                  保存并同步子任务
                </Button>
              )}
            </>
          )}
        </div>
      }
    >
      {scheduleConfirmation && (
        <Modal
          open
          title="确认同步调度变更"
          okText="确认保存"
          cancelText="继续编辑"
          onOk={() => answerScheduleConfirmation(true)}
          onCancel={() => answerScheduleConfirmation(false)}
        >
          {scheduleConfirmation}
        </Modal>
      )}
      {error && <Alert type="error" showIcon message={error} />}
      {job && (
        <Alert
          type="info"
          message={
            hasChildren
              ? "两种保存方式都会同步修改后的 Cron 表达式、时区和可执行日期。其他字段只有选择保存并同步子任务时才会覆盖子任务的对应配置。"
              : "启停请使用列表中的独立操作。"
          }
        />
      )}
      <Tabs
        activeKey={activeTab}
        onChange={(key) => guard(() => setActiveTab(key))}
        destroyOnHidden
        items={[
          {
            key: "basic",
            label: "基本配置",
            children: (
              <Form
                form={form}
                layout="vertical"
                disabled={loading || saving || Boolean(localSaving)}
                onValuesChange={(changed) => {
                  if (Object.keys(changed).some((name) => name !== "runDates"))
                    contentDirty.current = true;
                  setBasicDirty(true);
                }}
                onFinish={(values) => void submit(values)}
              >
                <CronJobFormBody
                  form={form}
                  executionModelOptions={models.options}
                  executionModelLoading={models.loading}
                  tenantDefaultModelLabel={models.tenantDefaultLabel}
                  skillOptions={skills}
                  skillOptionsLoading={loading}
                  managedCalendar
                  idDisabled
                  enabledDisabled={Boolean(job)}
                />
                <Form.Item
                  noStyle
                  shouldUpdate={(previous, current) =>
                    previous.task_type !== current.task_type ||
                    previous.recheckEnabled !== current.recheckEnabled
                  }
                >
                  {({ getFieldValue }) =>
                    getFieldValue("task_type") === "agent" && (
                      <>
                        <Form.Item
                          name="recheckEnabled"
                          label="启用回检"
                          valuePropName="checked"
                        >
                          <Switch />
                        </Form.Item>
                        {getFieldValue("recheckEnabled") && (
                          <>
                            <Form.Item
                              name="recheckDelay"
                              label="回检延迟"
                              rules={[{ required: true }]}
                            >
                              <InputNumber min={0} />
                            </Form.Item>
                            <Form.Item
                              name="recheckUnit"
                              label="延迟单位"
                              rules={[{ required: true }]}
                            >
                              <Select
                                options={[
                                  { value: "minutes", label: "分钟" },
                                  { value: "hours", label: "小时" },
                                ]}
                              />
                            </Form.Item>
                            <Form.Item
                              name="recheckInstruction"
                              label="回检指令"
                              rules={[{ required: true, whitespace: true }]}
                            >
                              <Input.TextArea rows={3} />
                            </Form.Item>
                          </>
                        )}
                      </>
                    )
                  }
                </Form.Item>
                <ManagedDateRangeField
                  inherited={inherited}
                  disabled={loading || saving || Boolean(localSaving)}
                />
              </Form>
            ),
          },
          ...(snapshot
            ? [
                {
                  key: "scheduling",
                  label: "调度设置",
                  disabled: loading || !ready,
                  children: inherited ? (
                    <Alert
                      type="info"
                      message={`继承父任务的调度配置：${
                        MODE_LABELS[snapshot.dispatch_state]
                      }。请在父任务修改。`}
                    />
                  ) : (
                    <ManagedModeSettings
                      context={modeContext}
                      job={snapshot}
                      onChanged={refresh}
                      onDirtyChange={setModeDirty}
                      onBusyChange={setModeBusy}
                    />
                  ),
                },
              ]
            : []),
        ]}
      />
    </Drawer>
  );
}
