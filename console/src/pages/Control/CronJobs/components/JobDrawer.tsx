import { Drawer, Form, Button } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import type { FormInstance } from "antd";
import type { CronJobSpecOutput } from "../../../../api/types";
import type { ExecutionModelOption } from "@/hooks/useExecutionModelOptions";
import { DEFAULT_FORM_VALUES } from "./constants";
import { CronJobFormBody } from "./CronJobFormBody";
import type { CronJobFormValues } from "../helpers";
import styles from "../index.module.less";

type CronJob = CronJobSpecOutput;
type SelectOption = { value: string; label: string };

interface JobDrawerProps {
  open: boolean;
  editingJob: CronJob | null;
  form: FormInstance<CronJobFormValues>;
  saving: boolean;
  executionModelOptions: ExecutionModelOption[];
  executionModelLoading: boolean;
  tenantDefaultModelLabel: string;
  skillOptions: SelectOption[];
  skillOptionsLoading: boolean;
  onClose: () => void;
  onSubmit: (values: CronJobFormValues) => void;
}

export function JobDrawer({
  open,
  editingJob,
  form,
  saving,
  executionModelOptions,
  executionModelLoading,
  tenantDefaultModelLabel,
  skillOptions,
  skillOptionsLoading,
  onClose,
  onSubmit,
}: JobDrawerProps) {
  const { t } = useTranslation();

  return (
    <Drawer
      width={600}
      placement="right"
      title={editingJob ? t("cronJobs.editJob") : t("cronJobs.createJob")}
      open={open}
      onClose={onClose}
      destroyOnClose
      footer={
        <div className={styles.formActions}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="primary" loading={saving} onClick={() => form.submit()}>
            {t("common.save")}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onSubmit}
        initialValues={DEFAULT_FORM_VALUES}
      >
        <CronJobFormBody
          form={form}
          executionModelOptions={executionModelOptions}
          executionModelLoading={executionModelLoading}
          tenantDefaultModelLabel={tenantDefaultModelLabel}
          skillOptions={skillOptions}
          skillOptionsLoading={skillOptionsLoading}
          idDisabled={Boolean(editingJob)}
        />
      </Form>
    </Drawer>
  );
}
