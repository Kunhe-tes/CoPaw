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

function getUserFacingCopy(diagnostic: ModelCallDiagnostic) {
  if (diagnostic.status === 401 || diagnostic.errorType === "invalid_api_key") {
    return {
      message: "当前模型的访问凭证无效或已过期，暂时无法生成回复。",
      guidance: "请前往「设置 > 模型」检查 API Key，更新后重新发送消息。",
    };
  }

  if (diagnostic.status === 429 || diagnostic.errorType === "rate_limit") {
    return {
      message: "模型服务请求过于频繁，暂时无法生成回复。",
      guidance: "请稍后重新发送消息；如问题持续，请检查模型配额和服务状态。",
    };
  }

  if (diagnostic.errorType === "timeout") {
    return {
      message: "模型响应超时，暂时无法生成回复。",
      guidance: "请稍后重新发送消息；如问题持续，请检查模型服务状态。",
    };
  }

  return {
    message: "模型服务暂时无法完成请求。",
    guidance: "请稍后重新发送消息；如问题持续，请检查模型配置和服务状态。",
  };
}

function buildCopyText(diagnostic: ModelCallDiagnostic) {
  return [
    diagnostic.status ? `HTTP 状态: ${diagnostic.status}` : null,
    `错误类型: ${diagnostic.errorType}`,
    `原始信息: ${diagnostic.rawMessage}`,
    diagnostic.requestId ? `请求 ID: ${diagnostic.requestId}` : null,
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
  const { getPrefixCls } = useProviderContext();
  const prefixCls = getPrefixCls("model-call-failed");
  const diagnostic = parseModelCallDiagnostic(data.message || "");
  const userFacingCopy = getUserFacingCopy(diagnostic);
  const detailRows = [
    ["错误类型", diagnostic.errorType],
    ["原始信息", diagnostic.rawMessage],
    ...(diagnostic.requestId ? [["请求 ID", diagnostic.requestId]] : []),
  ];

  const handleCopy = async () => {
    try {
      await copy(buildCopyText(diagnostic));
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  };

  const copyLabel =
    copyStatus === "copied"
      ? "已复制"
      : copyStatus === "failed"
      ? "复制失败"
      : "复制错误信息";

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
                模型连接失败
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
            打开模型设置
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
              详细报错信息
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
