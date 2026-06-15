import dayjs from "dayjs";
import type {
  CronBroadcastTenantResult,
  CronJobSpecInput,
  CronJobSpecOutput,
} from "@/api/types";
import {
  buildExecutionModelKey,
  parseExecutionModelKey,
} from "@/hooks/useExecutionModelOptions";
import {
  getNotificationDelayFormValue,
  toNotificationDelayMinutes,
  type NotificationDelayUnit,
} from "@/utils/cron";
import type { CronParts } from "./components/parseCron";
import { parseCron, serializeCron } from "./components/parseCron";

export type CronJobFormValues = CronJobSpecOutput & {
  cronType?: string;
  cronTime?: dayjs.Dayjs;
  cronDaysOfWeek?: string[];
  cronCustom?: string;
  execution_model_key?: string;
  notificationDelayValue?: number;
  notificationDelayUnit?: NotificationDelayUnit;
};

export function buildCronJobFormValues(
  job: CronJobSpecOutput,
): CronJobFormValues {
  const cronParts = parseCron(job.schedule?.cron || "0 9 * * *");
  const notificationDelay = getNotificationDelayFormValue(
    job.meta?.notification_delay_minutes,
  );
  const formValues: CronJobFormValues = {
    ...job,
    request: {
      ...job.request,
      input: job.request?.input
        ? JSON.stringify(job.request.input, null, 2)
        : "",
    },
    cronType: cronParts.type,
    execution_model_key: buildExecutionModelKey(job.model_slot),
    notificationDelayValue: notificationDelay.value,
    notificationDelayUnit: notificationDelay.unit,
  };

  if (cronParts.type === "daily" || cronParts.type === "weekly") {
    formValues.cronTime = dayjs()
      .hour(cronParts.hour ?? 9)
      .minute(cronParts.minute ?? 0);
  }
  if (cronParts.type === "weekly" && cronParts.daysOfWeek) {
    formValues.cronDaysOfWeek = cronParts.daysOfWeek;
  }
  if (cronParts.type === "custom" && cronParts.rawCron) {
    formValues.cronCustom = cronParts.rawCron;
  }
  return formValues;
}

export function buildCronJobSubmitPayload(
  values: Record<string, any>,
): CronJobSpecInput {
  const cronParts: CronParts = {
    type: values.cronType || "daily",
  } as CronParts;
  if (values.cronType === "daily" || values.cronType === "weekly") {
    if (values.cronTime) {
      cronParts.hour = values.cronTime.hour();
      cronParts.minute = values.cronTime.minute();
    }
  }
  if (values.cronType === "weekly" && values.cronDaysOfWeek) {
    cronParts.daysOfWeek = values.cronDaysOfWeek;
  }
  if (values.cronType === "custom" && values.cronCustom) {
    cronParts.rawCron = values.cronCustom;
  }

  const cronExpression = serializeCron(cronParts);
  const {
    execution_model_key: executionModelKey,
    notificationDelayValue,
    notificationDelayUnit,
    ...rawValues
  } = values;
  const notificationDelayMinutes = toNotificationDelayMinutes(
    notificationDelayValue,
    notificationDelayUnit || "minutes",
  );
  let processedValues: Record<string, any> = {
    ...rawValues,
    schedule: {
      ...values.schedule,
      cron: cronExpression,
    },
    meta: {
      ...(values.meta || {}),
      notification_delay_minutes: notificationDelayMinutes,
    },
    model_slot:
      values.task_type === "agent"
        ? parseExecutionModelKey(executionModelKey)
        : undefined,
  };

  if (values.request?.input && typeof values.request.input === "string") {
    processedValues = {
      ...processedValues,
      request: {
        ...values.request,
        input: JSON.parse(values.request.input),
      },
    };
  }

  return processedValues as CronJobSpecInput;
}

export function getBroadcastResultMessage(
  results: CronBroadcastTenantResult[],
): { tone: "success" | "warning"; text: string } {
  const successCount = results.filter((item) => item.success).length;
  const failedCount = results.length - successCount;
  const warningCount = results.filter((item) => item.warning).length;

  if (failedCount > 0) {
    return {
      tone: "warning",
      text: `Broadcasted ${successCount}, failed ${failedCount}`,
    };
  }
  if (warningCount > 0) {
    return {
      tone: "warning",
      text: `Broadcasted ${successCount} tenants, ${warningCount} with warnings`,
    };
  }
  return {
    tone: "success",
    text: `Broadcasted ${successCount} tenants`,
  };
}
