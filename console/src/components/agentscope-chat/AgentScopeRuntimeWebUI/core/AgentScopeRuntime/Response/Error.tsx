import { useId, useState } from "react";
import { Link } from "react-router-dom";
import {
  SparkCopyLine,
  SparkDownLine,
  SparkErrorCircleLine,
  SparkRightArrowLine,
  SparkUpLine,
} from "@agentscope-ai/icons";
import { Bubble, useProviderContext } from "@/components/agentscope-chat";
import { copy } from "@/components/agentscope-chat/Util/copy";
import {
  type MessageKey,
  useTranslation,
} from "../../Context/ChatAnywhereI18nContext";
import { IAgentScopeRuntimeError, IAgentScopeRuntimeMessage } from "../types";
import { ModelCallFailedStyle } from "./Error.style";

const MODEL_CALL_FAILED_CODE = "model_call_failed";

type ModelCallDiagnostic = {
  errorType: string;
  rawMessage: string;
  requestId?: string;
  status?: number;
};

function parseJsonDetail(message: string): Record<string, unknown> | undefined {
  const start = message.indexOf("{");
  const end = message.lastIndexOf("}");
  if (start < 0 || end <= start) return undefined;

  try {
    return JSON.parse(message.slice(start, end + 1)) as Record<string, unknown>;
  } catch {
    return undefined;
  }
}

function readString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function parseModelCallDiagnostic(message: string): ModelCallDiagnostic {
  const payload = parseJsonDetail(message);
  const nestedError =
    payload?.error && typeof payload.error === "object"
      ? (payload.error as Record<string, unknown>)
      : undefined;
  const statusMatch = message.match(/error status\s*\((\d{3})\)/i);
  const rawMessage =
    readString(nestedError?.message) ||
    message.replace(/^The model provider[^\n]*\n*/i, "").trim() ||
    message;

  const summaryErrorType = /timed out/i.test(message)
    ? "timeout"
    : /rate-limited/i.test(message)
    ? "rate_limit"
    : /connection failed/i.test(message)
    ? "connection"
    : MODEL_CALL_FAILED_CODE;

  return {
    errorType: readString(nestedError?.code) || summaryErrorType,
    rawMessage,
    requestId: readString(payload?.request_id),
    status: statusMatch ? Number(statusMatch[1]) : undefined,
  };
}

type Translate = (key: MessageKey) => string;

function getUserFacingCopy(diagnostic: ModelCallDiagnostic, t: Translate) {
  if (diagnostic.status === 401 || diagnostic.errorType === "invalid_api_key") {
    return {
      message: t("modelCallFailed.invalidCredential.message"),
      guidance: t("modelCallFailed.invalidCredential.guidance"),
    };
  }

  if (diagnostic.status === 429 || diagnostic.errorType === "rate_limit") {
    return {
      message: t("modelCallFailed.rateLimit.message"),
      guidance: t("modelCallFailed.rateLimit.guidance"),
    };
  }

  if (diagnostic.errorType === "timeout") {
    return {
      message: t("modelCallFailed.timeout.message"),
      guidance: t("modelCallFailed.timeout.guidance"),
    };
  }

  return {
    message: t("modelCallFailed.generic.message"),
    guidance: t("modelCallFailed.generic.guidance"),
  };
}

function buildCopyText(diagnostic: ModelCallDiagnostic, t: Translate) {
  return [
    diagnostic.status
      ? `${t("modelCallFailed.detail.httpStatus")}: ${diagnostic.status}`
      : null,
    `${t("modelCallFailed.detail.errorType")}: ${diagnostic.errorType}`,
    `${t("modelCallFailed.detail.rawMessage")}: ${diagnostic.rawMessage}`,
    diagnostic.requestId
      ? `${t("modelCallFailed.detail.requestId")}: ${diagnostic.requestId}`
      : null,
  ]
    .filter(Boolean)
    .join("\n");
}

function ModelCallFailedCard({
  data,
}: {
  data: IAgentScopeRuntimeError | IAgentScopeRuntimeMessage;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">(
    "idle",
  );
  const detailsId = useId();
  const titleId = useId();
  const { t } = useTranslation();
  const { getPrefixCls } = useProviderContext();
  const prefixCls = getPrefixCls("model-call-failed");
  const diagnostic = parseModelCallDiagnostic(data.message || "");
  const userFacingCopy = getUserFacingCopy(diagnostic, t);
  const detailRows = [
    [t("modelCallFailed.detail.errorType"), diagnostic.errorType],
    [t("modelCallFailed.detail.rawMessage"), diagnostic.rawMessage],
    ...(diagnostic.requestId
      ? [[t("modelCallFailed.detail.requestId"), diagnostic.requestId]]
      : []),
  ];

  const handleCopy = async () => {
    try {
      await copy(buildCopyText(diagnostic, t));
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  };

  const copyLabel =
    copyStatus === "copied"
      ? t("modelCallFailed.copied")
      : copyStatus === "failed"
      ? t("modelCallFailed.copyFailed")
      : t("modelCallFailed.copyError");

  return (
    <>
      <ModelCallFailedStyle />
      <section className={prefixCls} role="alert" aria-labelledby={titleId}>
        <div className={`${prefixCls}-main`}>
          <div className={`${prefixCls}-header`}>
            <div className={`${prefixCls}-header-copy`}>
              <span className={`${prefixCls}-icon`} aria-hidden="true">
                <SparkErrorCircleLine />
              </span>
              <h3 id={titleId} className={`${prefixCls}-title`}>
                {t("modelCallFailed.title")}
              </h3>
              {diagnostic.status ? (
                <span className={`${prefixCls}-status`}>
                  HTTP {diagnostic.status}
                </span>
              ) : null}
            </div>
          </div>
          <p className={`${prefixCls}-message`}>{userFacingCopy.message}</p>
          <p className={`${prefixCls}-guidance`}>{userFacingCopy.guidance}</p>
          <Link className={`${prefixCls}-settings-link`} to="/models">
            {t("modelCallFailed.openSettings")}
            <SparkRightArrowLine aria-hidden="true" />
          </Link>
        </div>
        <div className={`${prefixCls}-detail`}>
          <div className={`${prefixCls}-detail-header`}>
            <button
              type="button"
              className={`${prefixCls}-detail-trigger`}
              aria-expanded={detailsOpen}
              aria-controls={detailsId}
              onClick={() => setDetailsOpen((current) => !current)}
            >
              {detailsOpen ? (
                <SparkUpLine aria-hidden="true" />
              ) : (
                <SparkDownLine aria-hidden="true" />
              )}
              {t("modelCallFailed.details")}
            </button>
            {detailsOpen ? (
              <button
                type="button"
                className={`${prefixCls}-detail-copy`}
                onClick={() => void handleCopy()}
              >
                <SparkCopyLine aria-hidden="true" />
                <span aria-live="polite">{copyLabel}</span>
              </button>
            ) : null}
          </div>
          <dl
            id={detailsId}
            className={`${prefixCls}-details`}
            hidden={!detailsOpen}
          >
            {detailRows.map(([label, value]) => (
              <div className={`${prefixCls}-detail-row`} key={label}>
                <dt className={`${prefixCls}-detail-label`}>{label}</dt>
                <dd className={`${prefixCls}-detail-value`}>{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </>
  );
}

export default function Error({
  data,
}: {
  data: IAgentScopeRuntimeError | IAgentScopeRuntimeMessage;
}) {
  if (data.code === MODEL_CALL_FAILED_CODE) {
    return <ModelCallFailedCard data={data} />;
  }

  return (
    <Bubble.Interrupted type="error" title={data.code} desc={data.message} />
  );
}
