import {
  Alert,
  Button,
  Checkbox,
  Drawer,
  Empty,
  Input,
  Progress,
  Radio,
  Skeleton,
  Space,
  Tag,
  Tooltip,
} from "antd";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Check,
  CircleAlert,
  CircleCheck,
  Clock3,
  ChevronDown,
  FileCheck2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { wplusSopApi } from "@/api/modules/wplusSop";
import type {
  WPlusSopAnswerValue,
  WPlusSopCommandType,
  WPlusSopCustomAnswerValue,
  WPlusSopMemoryCandidate,
  WPlusSopQuestion,
  WPlusSopSafeStreamTrace,
  WPlusSopSession,
  WPlusSopStage,
} from "@/api/types/wplusSop";
import { getToolDisplayName } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/ToolTitle";
import {
  applySessionEvent,
  buildResultTable,
  createCommandRequestId,
  getSessionStateLabel,
  validateStageQueue,
} from "./sessionView";
import styles from "./index.module.less";

type LoadState = "loading" | "ready" | "unavailable" | "error";

const STREAM_MAX_RECONNECTS = 3;
const STREAM_RECONNECT_BASE_DELAY_MS = 250;
const PROGRESS_STROKE_COLOR = "var(--console-conversation-primary, #3769FC)";
const PROGRESS_TRAIL_COLOR = "var(--console-management-border, #E5E7EB)";

interface LoadSessionOptions {
  background?: boolean;
  preserveStageDraft?: boolean;
}

interface AnswerDraft {
  scope: string | null;
  values: Record<string, WPlusSopAnswerValue>;
}

type MemoryDecision = "approve" | "reject";

interface MemoryDecisionDraft {
  scope: string | null;
  values: Record<string, MemoryDecision>;
}

function completedMemoryStatus(candidate: WPlusSopMemoryCandidate): {
  color: string;
  label: string;
} {
  if (candidate.status === "approved") {
    if (candidate.legacy_read_only) {
      return {
        color: "default",
        label: "历史已批准（无可验证写入回执）",
      };
    }
    return candidate.write_receipt
      ? { color: "green", label: "已写入" }
      : { color: "default", label: "已批准（无可验证写入回执）" };
  }
  if (candidate.status === "rejected") {
    return { color: "default", label: "已拒绝" };
  }
  if (candidate.status === "failed") {
    return {
      color: "red",
      label: `写入失败${
        candidate.failure_reason ? `：${candidate.failure_reason}` : ""
      }`,
    };
  }
  if (candidate.status === "writing") {
    return { color: "processing", label: "历史状态：写入中" };
  }
  return { color: "default", label: "历史状态：待处理" };
}

interface ActiveSafeStreamTrace extends WPlusSopSafeStreamTrace {
  session_id: string;
  run_id: string;
}

function ResultPreview({
  preview,
}: {
  preview: WPlusSopSession["result_preview"];
}) {
  const [remoteMarkdown, setRemoteMarkdown] = useState<string | null>(null);
  const [markdownFailed, setMarkdownFailed] = useState(false);
  const [markdownLoading, setMarkdownLoading] = useState(false);
  const [remoteHtml, setRemoteHtml] = useState<string | null>(null);
  const [htmlFailed, setHtmlFailed] = useState(false);
  const [htmlLoading, setHtmlLoading] = useState(false);
  const markdownUrl = preview?.markdown_url || null;
  const htmlUrl = preview?.html_url || null;

  useEffect(() => {
    setRemoteMarkdown(null);
    setMarkdownFailed(false);
    setMarkdownLoading(Boolean(markdownUrl));
    if (!markdownUrl) return;

    const controller = new AbortController();
    let disposed = false;
    void fetch(markdownUrl, { signal: controller.signal, cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("Markdown preview request failed");
        return response.text();
      })
      .then((body) => {
        if (!disposed) {
          setRemoteMarkdown(body);
          setMarkdownLoading(false);
        }
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        if (!disposed) {
          setMarkdownFailed(true);
          setMarkdownLoading(false);
        }
      });
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [markdownUrl, preview?.markdown_sha256]);

  useEffect(() => {
    setRemoteHtml(null);
    setHtmlFailed(false);
    setHtmlLoading(Boolean(htmlUrl));
    if (!htmlUrl) return;

    const controller = new AbortController();
    let disposed = false;
    void fetch(htmlUrl, { signal: controller.signal, cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("HTML preview request failed");
        return response.text();
      })
      .then((body) => {
        if (!disposed) {
          setRemoteHtml(body);
          setHtmlLoading(false);
        }
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        if (!disposed) {
          setHtmlFailed(true);
          setHtmlLoading(false);
        }
      });
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [htmlUrl, preview?.html_sha256]);

  const markdown = preview?.markdown_url
    ? remoteMarkdown
    : preview?.markdown || null;
  const html = preview?.html_url ? remoteHtml : preview?.html || null;

  return (
    <div className={styles.resultPreviewGrid}>
      <article
        aria-busy={markdownLoading}
        aria-live="polite"
        className={styles.resultPreviewCard}
      >
        <h3>Markdown 预览</h3>
        <pre>
          {markdown ||
            (markdownLoading
              ? "Markdown 预览加载中…"
              : markdownFailed
              ? "Markdown 预览加载失败。"
              : "暂无 Markdown 结果。")}
        </pre>
      </article>
      <article
        aria-busy={htmlLoading}
        aria-live="polite"
        className={styles.resultPreviewCard}
      >
        <h3>HTML 预览</h3>
        {html ? (
          <iframe
            className={styles.htmlPreview}
            title="HTML 结果预览"
            sandbox=""
            srcDoc={html}
          />
        ) : (
          <Empty
            description={
              htmlLoading
                ? "HTML 预览加载中…"
                : htmlFailed
                ? "HTML 预览加载失败。"
                : "暂无 HTML 结果"
            }
          />
        )}
      </article>
    </div>
  );
}

function LiveRunTranscript({
  trace,
  running,
  title,
}: {
  trace: ActiveSafeStreamTrace | null;
  running: boolean;
  title: string;
}) {
  const [expanded, setExpanded] = useState(running);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const shouldFollowRef = useRef(true);
  const entries = useMemo(() => trace?.entries || [], [trace?.entries]);

  useEffect(() => {
    setExpanded(running);
    shouldFollowRef.current = true;
  }, [running, trace?.run_id]);

  useEffect(() => {
    if (running && expanded && shouldFollowRef.current && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [entries, expanded, running, trace?.sequence, trace?.summary_text]);

  const stepCount = entries.length || (trace?.summary_text ? 1 : 0);
  const failedCount = entries.filter(
    (entry) => entry.status === "failed",
  ).length;
  const toggleLabel = expanded ? "折叠运行过程" : "展开运行过程";

  return (
    <section
      className={styles.liveRunTranscript}
      role="region"
      aria-label="实时运行过程"
      data-running={running}
    >
      <button
        type="button"
        className={styles.liveRunHeader}
        aria-expanded={expanded}
        aria-controls="wplus-live-run-body"
        onClick={() =>
          setExpanded((current) => {
            if (current) return false;
            shouldFollowRef.current = true;
            return true;
          })
        }
      >
        <span className={styles.liveRunState} aria-hidden="true">
          {running ? <RefreshCw size={17} /> : <CircleCheck size={17} />}
        </span>
        <span className={styles.liveRunHeading}>
          <h2>{running ? title : "本轮运行过程"}</h2>
          <small>
            {running
              ? "正在实时接收回复与工具活动"
              : `${stepCount} 条记录${
                  failedCount ? ` · ${failedCount} 条失败` : ""
                }`}
          </small>
        </span>
        <span className={styles.liveRunToggleText}>{toggleLabel}</span>
        <ChevronDown
          className={styles.liveRunChevron}
          size={16}
          aria-hidden="true"
        />
      </button>

      <div
        id="wplus-live-run-body"
        data-testid="wplus-live-run-body"
        ref={bodyRef}
        className={styles.liveRunBody}
        hidden={!expanded}
        role={running ? "status" : undefined}
        aria-label={running ? title : undefined}
        aria-live={running ? "polite" : "off"}
        onScroll={() => {
          const body = bodyRef.current;
          if (!body) return;
          shouldFollowRef.current =
            body.scrollHeight - body.scrollTop - body.clientHeight <= 24;
        }}
      >
        {entries.length ? (
          entries.map((entry) =>
            entry.kind === "tool" ? (
              <div
                key={entry.entry_id}
                className={styles.liveToolEntry}
                data-status={entry.status}
              >
                <Wrench size={15} aria-hidden="true" />
                <span>
                  {getToolDisplayName(entry.tool_name, entry.server_label)}
                </span>
                <small>
                  {entry.status === "running"
                    ? "执行中"
                    : entry.status === "failed"
                    ? "执行失败"
                    : "已完成"}
                </small>
              </div>
            ) : (
              <div key={entry.entry_id} className={styles.liveAssistantEntry}>
                <p>{entry.text}</p>
              </div>
            ),
          )
        ) : trace?.summary_text ? (
          <div className={styles.liveAssistantEntry}>
            <p>{trace.summary_text}</p>
          </div>
        ) : (
          <div className={styles.liveRunEmpty}>
            <RefreshCw size={16} aria-hidden="true" />
            <span>等待返回内容…</span>
          </div>
        )}
        {trace?.truncated ? (
          <p className={styles.liveRunTruncated}>
            较早内容已截断，仅显示最近片段。
          </p>
        ) : null}
      </div>
    </section>
  );
}

function errorStatus(error: unknown): number | undefined {
  if (typeof error !== "object" || error === null || !("status" in error)) {
    return undefined;
  }
  return Number((error as { status?: unknown }).status);
}

function commandErrorCode(error: unknown): string | undefined {
  if (typeof error !== "object" || error === null || !("data" in error)) {
    return undefined;
  }
  const data = (error as { data?: unknown }).data;
  if (typeof data !== "object" || data === null || !("detail" in data)) {
    return undefined;
  }
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail !== "object" || detail === null || !("code" in detail)) {
    return undefined;
  }
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" ? code : undefined;
}

function isGenerating(session: WPlusSopSession): boolean {
  return [
    "GeneratingStageProposal",
    "GeneratingQuestions",
    "GeneratingTrial",
    "ExecutingTrial",
    "FinalizingOutputs",
    "WritingMemory",
    "PendingExit",
  ].includes(session.state);
}

function stateProgress(session: WPlusSopSession): number {
  const confirmed = session.stages.filter(
    (stage) => stage.status === "confirmed",
  ).length;
  if (!session.stages.length) return 8;
  if (session.state === "Completed") return 100;
  return Math.min(
    94,
    Math.round((confirmed / session.stages.length) * 82) + 12,
  );
}

function conclusionMilestoneProjection(session: WPlusSopSession): {
  status: "confirmed" | "current" | "pending";
  label: string;
} {
  if (session.state === "Completed") {
    return { status: "confirmed", label: "已完成" };
  }
  if (session.state === "FinalizingOutputs") {
    return { status: "current", label: "生成中" };
  }
  if (session.state === "OutputReview") {
    return { status: "current", label: "待确认结果" };
  }
  if (session.state === "MemoryReview") {
    return { status: "current", label: "待确认" };
  }
  if (session.state === "WritingMemory") {
    return { status: "current", label: "写入中" };
  }
  if (session.state === "Terminated") {
    return { status: "pending", label: "未生成" };
  }
  return { status: "pending", label: "等待中" };
}

function StageQueueEditor({
  session,
  stages,
  busy,
  onChange,
  onConfirm,
}: {
  session: WPlusSopSession;
  stages: WPlusSopStage[];
  busy: boolean;
  onChange: (stages: WPlusSopStage[]) => void;
  onConfirm: () => void;
}) {
  const validation = validateStageQueue(stages);
  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= stages.length) return;
    const next = [...stages];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };
  const add = () => {
    const suffix = createCommandRequestId().slice(-6);
    onChange([
      ...stages,
      {
        stage_id: `stage_${suffix}`,
        title: `新环节 ${stages.length + 1}`,
        description: "",
        status: "pending",
      },
    ]);
  };

  return (
    <section className={styles.workSection} aria-labelledby="stage-queue-title">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.eyebrow}>流程 01</span>
          <h2 id="stage-queue-title">确认 SOP 环节</h2>
          <p>可重命名、增删或调整顺序；确认时会一次性保存整个队列。</p>
        </div>
        <Tag color="cyan">自动候选 2–4 个 · 手动新增不限</Tag>
      </div>

      <ol className={styles.stageEditor}>
        {stages.map((stage, index) => (
          <li key={stage.stage_id} className={styles.stageEditorRow}>
            <span className={styles.stageNumber}>
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className={styles.stageFields}>
              <Input
                aria-label={`环节 ${index + 1} 名称`}
                value={stage.title}
                onChange={(event) =>
                  onChange(
                    stages.map((item) =>
                      item.stage_id === stage.stage_id
                        ? { ...item, title: event.target.value }
                        : item,
                    ),
                  )
                }
              />
              <Input
                aria-label={`环节 ${index + 1} 说明`}
                placeholder="这个环节要确认什么"
                value={stage.description || ""}
                onChange={(event) =>
                  onChange(
                    stages.map((item) =>
                      item.stage_id === stage.stage_id
                        ? { ...item, description: event.target.value }
                        : item,
                    ),
                  )
                }
              />
            </div>
            <Space size={2} className={styles.stageActions}>
              <Tooltip title="上移">
                <Button
                  type="text"
                  icon={<ArrowUp size={16} />}
                  aria-label={`将“${stage.title}”上移`}
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                />
              </Tooltip>
              <Tooltip title="下移">
                <Button
                  type="text"
                  icon={<ArrowDown size={16} />}
                  aria-label={`将“${stage.title}”下移`}
                  disabled={index === stages.length - 1}
                  onClick={() => move(index, 1)}
                />
              </Tooltip>
              <Tooltip title="删除">
                <Button
                  danger
                  type="text"
                  icon={<Trash2 size={16} />}
                  aria-label={`删除“${stage.title}”`}
                  disabled={stages.length <= 2}
                  onClick={() =>
                    onChange(
                      stages.filter((item) => item.stage_id !== stage.stage_id),
                    )
                  }
                />
              </Tooltip>
            </Space>
          </li>
        ))}
      </ol>

      {!validation.valid && (
        <Alert
          type="warning"
          showIcon
          message={validation.message}
          className={styles.inlineAlert}
        />
      )}
      <div className={styles.sectionActions}>
        <Button icon={<Plus size={16} />} onClick={add}>
          增加环节
        </Button>
        <Button
          type="primary"
          icon={<Check size={16} />}
          loading={busy}
          disabled={
            !validation.valid || session.state !== "AwaitingQueueConfirmation"
          }
          onClick={onConfirm}
        >
          确认这 {stages.length} 个环节
        </Button>
      </div>
    </section>
  );
}

function QuestionField({
  question,
  value,
  disabled,
  onChange,
}: {
  question: WPlusSopQuestion;
  value: WPlusSopAnswerValue | undefined;
  disabled: boolean;
  onChange: (value: WPlusSopAnswerValue) => void;
}) {
  const structuredValue = isStructuredAnswerValue(value) ? value : null;
  const selectedOptionIds =
    typeof value === "string"
      ? [value]
      : Array.isArray(value)
      ? value
      : structuredValue?.selected_option_ids || [];
  const selectedRequiresCustomInput = selectedOptionIds.some(
    (optionId) =>
      question.options?.some(
        (option) =>
          option.option_id === optionId && option.requires_custom_input,
      ),
  );
  const customInput = selectedRequiresCustomInput ? (
    <Input.TextArea
      className={styles.customAnswerInput}
      aria-label={`${question.prompt} 自定义补充`}
      autoSize={{ minRows: 2, maxRows: 6 }}
      disabled={disabled}
      value={structuredValue?.text || ""}
      onChange={(event) =>
        onChange({
          selected_option_ids: selectedOptionIds,
          text: event.target.value,
        })
      }
      placeholder="输入自定义补充"
    />
  ) : null;

  if (question.kind === "single_select") {
    return (
      <>
        <Radio.Group
          className={styles.optionList}
          disabled={disabled}
          value={selectedOptionIds[0]}
          onChange={(event) => {
            const optionId = String(event.target.value);
            const requiresCustomInput = question.options?.some(
              (option) =>
                option.option_id === optionId && option.requires_custom_input,
            );
            onChange(
              requiresCustomInput
                ? {
                    selected_option_ids: [optionId],
                    text: structuredValue?.text || "",
                  }
                : optionId,
            );
          }}
        >
          {(question.options || []).map((option) => (
            <Radio key={option.option_id} value={option.option_id}>
              <span>{option.label}</span>
              {option.description && (
                <small className={styles.optionDescription}>
                  {option.description}
                </small>
              )}
            </Radio>
          ))}
        </Radio.Group>
        {customInput}
      </>
    );
  }
  if (question.kind === "multi_select") {
    return (
      <>
        <Checkbox.Group
          className={styles.optionList}
          disabled={disabled}
          value={selectedOptionIds}
          onChange={(values) => {
            const optionIds = values.map(String);
            const requiresCustomInput = optionIds.some(
              (optionId) =>
                question.options?.some(
                  (option) =>
                    option.option_id === optionId &&
                    option.requires_custom_input,
                ),
            );
            onChange(
              requiresCustomInput
                ? {
                    selected_option_ids: optionIds,
                    text: structuredValue?.text || "",
                  }
                : optionIds,
            );
          }}
        >
          {(question.options || []).map((option) => (
            <Checkbox key={option.option_id} value={option.option_id}>
              <span>{option.label}</span>
              {option.description && (
                <small className={styles.optionDescription}>
                  {option.description}
                </small>
              )}
            </Checkbox>
          ))}
        </Checkbox.Group>
        {customInput}
      </>
    );
  }
  return (
    <Input.TextArea
      aria-label={question.prompt}
      autoSize={{ minRows: 3, maxRows: 8 }}
      disabled={disabled}
      value={typeof value === "string" ? value : ""}
      onChange={(event) => onChange(event.target.value)}
      placeholder="输入你的补充说明"
    />
  );
}

function isStructuredAnswerValue(
  value: WPlusSopAnswerValue | undefined,
): value is WPlusSopCustomAnswerValue {
  return Boolean(
    value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Array.isArray(value.selected_option_ids),
  );
}

function QuestionBatchPanel({
  session,
  answers,
  busy,
  runtimeReady,
  onAnswer,
  onSubmit,
}: {
  session: WPlusSopSession;
  answers: Record<string, WPlusSopAnswerValue>;
  busy: boolean;
  runtimeReady: boolean;
  onAnswer: (questionId: string, value: WPlusSopAnswerValue) => void;
  onSubmit: () => void;
}) {
  const batch = session.question_batch;
  if (!batch) return null;
  const complete = batch.questions.every((question) => {
    const value = answers[question.question_id];
    if (isStructuredAnswerValue(value)) {
      if (!value.text?.trim()) return false;
      return !question.required || value.selected_option_ids.length > 0;
    }
    if (!question.required) return true;
    return Array.isArray(value)
      ? value.length > 0
      : Boolean(typeof value === "string" && value.trim());
  });

  return (
    <section className={styles.workSection} aria-labelledby="question-title">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.eyebrow}>流程 02</span>
          <h2 id="question-title">补齐本环节信息</h2>
          <p>一次提交整批回答；必填项齐全后才会开始系统预跑。</p>
        </div>
        <Tag>{batch.questions.length} 个问题</Tag>
      </div>
      <div className={styles.questionList}>
        {batch.questions.map((question, index) => (
          <fieldset key={question.question_id} className={styles.question}>
            <legend className={styles.questionLegend}>
              <span className={styles.questionNumber}>
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className={styles.questionPrompt}>{question.prompt}</span>
              <span className={styles.questionMeta}>
                {question.kind !== "free_text" && (
                  <em className={styles.questionType}>
                    {question.kind === "multi_select" ? "多选" : "单选"}
                  </em>
                )}
                {question.required && (
                  <em className={styles.requiredMark}>必填</em>
                )}
              </span>
            </legend>
            {question.help_text && <p>{question.help_text}</p>}
            <QuestionField
              question={question}
              value={answers[question.question_id]}
              disabled={busy}
              onChange={(value) => onAnswer(question.question_id, value)}
            />
          </fieldset>
        ))}
      </div>
      <div className={styles.sectionActions}>
        <span className={styles.actionHint}>
          {!runtimeReady
            ? "正在完成上一轮处理"
            : complete
            ? "回答已齐全"
            : "请先完成所有必填项"}
        </span>
        <Button
          type="primary"
          loading={busy}
          disabled={!complete || !runtimeReady}
          onClick={onSubmit}
        >
          {runtimeReady
            ? `提交本轮 ${batch.questions.length} 个回答`
            : "正在完成上一轮处理"}
        </Button>
      </div>
    </section>
  );
}

function TrialPanel({
  session,
  feedback,
  busy,
  onFeedback,
  onRerun,
  onAccept,
}: {
  session: WPlusSopSession;
  feedback: string;
  busy: boolean;
  onFeedback: (value: string) => void;
  onRerun: () => void;
  onAccept: () => void;
}) {
  const trial = session.trial;
  if (!trial) return null;
  const table = buildResultTable(trial.result_rows, trial.result_columns);
  return (
    <section className={styles.workSection} aria-labelledby="trial-title">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.eyebrow}>流程 03</span>
          <h2 id="trial-title">系统预跑结果</h2>
          <p>系统已调用真实能力；检查结果后可反馈并重新预跑。</p>
        </div>
        <Tag
          color={
            trial.status === "completed"
              ? "success"
              : trial.status === "failed"
              ? "error"
              : "processing"
          }
        >
          {trial.status === "completed"
            ? "预跑完成"
            : trial.status === "failed"
            ? "预跑失败"
            : "预跑中"}
        </Tag>
      </div>

      {trial.steps.length > 0 && (
        <ol className={styles.runSteps}>
          {trial.steps.map((step) => (
            <li key={step.step_id} data-status={step.status}>
              {step.status === "completed" ? (
                <CircleCheck size={18} />
              ) : step.status === "failed" ? (
                <CircleAlert size={18} />
              ) : (
                <Clock3 size={18} />
              )}
              <div>
                <strong>{step.title}</strong>
                {step.summary && <span>{step.summary}</span>}
              </div>
            </li>
          ))}
        </ol>
      )}

      {trial.summary && <p className={styles.trialSummary}>{trial.summary}</p>}
      {table.columns.length > 0 && (
        <div className={styles.tableWrap}>
          <table>
            <caption className={styles.visuallyHidden}>
              系统预跑结果明细
            </caption>
            <thead>
              <tr>
                {table.columns.map((column) => (
                  <th key={column.field} scope="col">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, index) => (
                <tr key={index}>
                  {table.columns.map((column) => (
                    <td key={column.field}>{row[column.field]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {session.state === "AwaitingTrialFeedback" && (
        <div className={styles.feedbackBox}>
          <label htmlFor="wplus-trial-feedback">预跑反馈</label>
          <Input.TextArea
            id="wplus-trial-feedback"
            autoSize={{ minRows: 4, maxRows: 9 }}
            value={feedback}
            onChange={(event) => onFeedback(event.target.value)}
            placeholder="例如：排除缺少任务日期的记录，并在结果中补充客户分层"
          />
          <div className={styles.sectionActions}>
            <Button
              icon={<Check size={16} />}
              disabled={busy}
              onClick={onAccept}
            >
              结果符合预期
            </Button>
            <Button
              type="primary"
              icon={<RotateCcw size={16} />}
              loading={busy}
              disabled={!feedback.trim()}
              onClick={onRerun}
            >
              提交反馈并重新预跑
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

function EvidenceRail({ session }: { session: WPlusSopSession }) {
  return (
    <aside className={styles.evidenceRail} aria-label="本次 SOP 证据">
      <div className={styles.railSection}>
        <h2>已确认事实</h2>
        {session.facts?.length ? (
          <ul>
            {session.facts.map((fact) => (
              <li key={fact}>
                <Check size={14} />
                <span title={fact}>{fact}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>回答后会在这里汇总稳定事实。</p>
        )}
      </div>
      <div className={styles.railSection}>
        <h2>仍需确认</h2>
        {session.unknowns?.length ? (
          <ul>
            {session.unknowns.map((unknown) => (
              <li key={unknown}>
                <Clock3 size={14} />
                <span title={unknown}>{unknown}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>当前没有记录中的未知项。</p>
        )}
      </div>
      <div className={styles.railSection}>
        <h2>能力证据</h2>
        {session.capabilities?.length ? (
          <ul className={styles.capabilityList}>
            {session.capabilities.map((capability) => (
              <li key={capability.capability_id}>
                <span title={capability.name}>{capability.name}</span>
                <Tag
                  color={
                    capability.verification_status === "verified"
                      ? "success"
                      : "warning"
                  }
                >
                  {capability.verification_status === "verified"
                    ? "已验证"
                    : "待补证"}
                </Tag>
              </li>
            ))}
          </ul>
        ) : (
          <p>预跑后会显示所用能力与验证状态。</p>
        )}
      </div>
    </aside>
  );
}

export default function WPlusSopWorkspace() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [session, setSession] = useState<WPlusSopSession | null>(null);
  const sessionRef = useRef<WPlusSopSession | null>(null);
  const [stages, setStages] = useState<WPlusSopStage[]>([]);
  const [answerDraft, setAnswerDraft] = useState<AnswerDraft>({
    scope: null,
    values: {},
  });
  const [feedback, setFeedback] = useState("");
  const [memoryDecisionDraft, setMemoryDecisionDraft] =
    useState<MemoryDecisionDraft>({
      scope: null,
      values: {},
    });
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [safeStreamTrace, setSafeStreamTrace] =
    useState<ActiveSafeStreamTrace | null>(null);
  const [downloadingArtifactId, setDownloadingArtifactId] = useState<
    string | null
  >(null);
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const commitSession = useCallback(
    (
      snapshot: WPlusSopSession,
      options: { preserveStageDraft?: boolean } = {},
    ) => {
      const current = sessionRef.current;
      if (
        current?.session_id === snapshot.session_id &&
        current.state_version > snapshot.state_version
      ) {
        return false;
      }
      sessionRef.current = snapshot;
      setSession(snapshot);
      if (!options.preserveStageDraft) {
        setStages(snapshot.stages.map((stage) => ({ ...stage })));
      }
      return true;
    },
    [],
  );

  const loadSession = useCallback(
    async (signal?: AbortSignal, options: LoadSessionOptions = {}) => {
      try {
        const requestedSessionId = sessionId;
        const snapshot = await wplusSopApi.getSession(
          requestedSessionId,
          signal,
        );
        if (sessionIdRef.current !== requestedSessionId) return null;
        commitSession(snapshot, options);
        setLoadState("ready");
        return snapshot;
      } catch (error) {
        if (signal?.aborted) return null;
        if (errorStatus(error) === 404) {
          setLoadState("unavailable");
        } else if (!options.background) {
          setLoadState("error");
        }
        return null;
      }
    },
    [commitSession, sessionId],
  );

  useEffect(() => {
    const controller = new AbortController();
    if (sessionRef.current?.session_id !== sessionId) {
      sessionRef.current = null;
      setSession(null);
      setLoadState("loading");
      setNotice(null);
    }
    void loadSession(controller.signal);
    return () => controller.abort();
  }, [loadSession, sessionId]);

  useEffect(() => {
    const subscribedSession = sessionRef.current;
    if (
      loadState !== "ready" ||
      !subscribedSession ||
      subscribedSession.session_id !== sessionId
    ) {
      return;
    }
    const subscribedSessionId = subscribedSession.session_id;
    const initialStateVersion = subscribedSession.state_version;

    let disposed = false;
    let reconnectAttempts = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let recovering = false;
    let subscription: ReturnType<
      typeof wplusSopApi.subscribeSessionEvents
    > | null = null;
    const recoverStream = async () => {
      if (disposed || recovering) return;
      recovering = true;
      await loadSession(undefined, {
        background: true,
        preserveStageDraft:
          sessionRef.current?.state === "AwaitingQueueConfirmation",
      });
      recovering = false;
      if (disposed) return;

      const current = sessionRef.current;
      if (
        !current ||
        current.session_id !== subscribedSessionId ||
        current.state === "Completed" ||
        current.state === "Terminated"
      ) {
        return;
      }
      if (reconnectAttempts >= STREAM_MAX_RECONNECTS) {
        setNotice("实时连接多次中断，已保留最新快照；可重新加载页面继续。");
        return;
      }

      const delay = STREAM_RECONNECT_BASE_DELAY_MS * 2 ** reconnectAttempts;
      reconnectAttempts += 1;
      setNotice("实时连接暂时中断，已刷新最新状态，正在尝试重新连接。");
      reconnectTimer = setTimeout(() => connect(current.state_version), delay);
    };

    const connect = (afterStateVersion: number) => {
      if (disposed) return;
      subscription?.close();
      subscription = wplusSopApi.subscribeSessionEvents(
        subscribedSessionId,
        afterStateVersion,
        (event) => {
          const current = sessionRef.current;
          if (
            !current ||
            event.session_id !== subscribedSessionId ||
            current.session_id !== subscribedSessionId
          ) {
            return;
          }
          reconnectAttempts = 0;
          if (event.kind === "runtime_status") {
            if (
              event.state_version === current.state_version &&
              event.runtime_status
            ) {
              commitSession(
                { ...current, runtime_status: event.runtime_status },
                { preserveStageDraft: true },
              );
            }
            return;
          }
          if (event.kind === "safe_stream_trace") {
            const trace = event.safe_stream_trace;
            const currentRunId = current.trial?.run_id;
            if (
              disposed ||
              event.session_id !== subscribedSessionId ||
              current.session_id !== subscribedSessionId ||
              !isGenerating(current) ||
              !event.run_id ||
              event.run_id !== currentRunId ||
              !trace
            ) {
              return;
            }
            setSafeStreamTrace((existing) => {
              if (
                existing?.session_id === current.session_id &&
                existing?.run_id === event.run_id &&
                existing.sequence >= trace.sequence
              ) {
                return existing;
              }
              return {
                session_id: event.session_id,
                run_id: event.run_id,
                sequence: trace.sequence,
                summary_text: trace.summary_text,
                truncated: trace.truncated,
                entries: trace.entries,
              };
            });
            return;
          }
          const decision = applySessionEvent(current, event);
          if (decision.action === "reload") {
            void loadSession(undefined, {
              background: true,
              preserveStageDraft: current.state === "AwaitingQueueConfirmation",
            });
            return;
          }
          if (decision.action === "apply") {
            reconnectAttempts = 0;
            commitSession(decision.session, {
              preserveStageDraft:
                current.state === "AwaitingQueueConfirmation" &&
                decision.session.state === "AwaitingQueueConfirmation",
            });
          }
        },
        () => {
          void recoverStream();
        },
      );
    };

    connect(initialStateVersion);
    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      subscription?.close();
    };
  }, [commitSession, loadSession, loadState, session?.session_id, sessionId]);

  const currentRunId = session?.trial?.run_id ?? null;
  const sessionIsGenerating = session ? isGenerating(session) : false;
  const visibleSafeStreamTrace =
    safeStreamTrace &&
    safeStreamTrace.session_id === session?.session_id &&
    safeStreamTrace.run_id === currentRunId
      ? safeStreamTrace
      : null;

  useEffect(() => {
    setSafeStreamTrace(null);
    setEvidenceDrawerOpen(false);
  }, [session?.session_id, sessionId]);

  const answerScope = session?.question_batch
    ? `${session.session_id}:${session.question_batch.batch_id}`
    : null;
  const answers = useMemo(
    () => (answerDraft.scope === answerScope ? answerDraft.values : {}),
    [answerDraft, answerScope],
  );

  useEffect(() => {
    setAnswerDraft((current) =>
      current.scope === answerScope
        ? current
        : { scope: answerScope, values: {} },
    );
  }, [answerScope]);

  const memoryDecisionScope = session?.session_id ?? sessionId;
  const memoryDecisions = useMemo(
    () =>
      memoryDecisionDraft.scope === memoryDecisionScope
        ? memoryDecisionDraft.values
        : {},
    [memoryDecisionDraft, memoryDecisionScope],
  );

  useEffect(() => {
    setMemoryDecisionDraft((current) =>
      current.scope === memoryDecisionScope
        ? current
        : { scope: memoryDecisionScope, values: {} },
    );
  }, [memoryDecisionScope]);

  const downloadArtifact = useCallback(
    async (artifactId: string, filename: string) => {
      if (!session) return;
      setDownloadingArtifactId(artifactId);
      setNotice(null);
      try {
        const blob = await wplusSopApi.downloadArtifact(
          session.session_id,
          artifactId,
        );
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = filename;
        anchor.style.display = "none";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(objectUrl);
      } catch {
        setNotice("产物下载失败，请稍后重试。");
      } finally {
        setDownloadingArtifactId(null);
      }
    },
    [session],
  );

  const sendCommand = useCallback(
    async (
      command: WPlusSopCommandType,
      payload: Record<string, unknown> = {},
    ) => {
      if (!session || session.session_id !== sessionIdRef.current) return null;
      setBusy(true);
      setNotice(null);
      try {
        const receipt = await wplusSopApi.sendCommand(session.session_id, {
          command,
          command_request_id: createCommandRequestId(),
          expected_state_version: session.state_version,
          payload,
        });
        if (sessionIdRef.current !== session.session_id) return null;
        commitSession(receipt.session);
        if (command === "resolve_memory") {
          setMemoryDecisionDraft((current) =>
            current.scope === session.session_id
              ? { scope: session.session_id, values: {} }
              : current,
          );
        }
        if (command === "save_and_exit") {
          navigate(`/chat/${encodeURIComponent(receipt.session.chat_id)}`);
        }
        return receipt.session;
      } catch (error) {
        if (sessionIdRef.current !== session.session_id) return null;
        const status = errorStatus(error);
        if (
          status === 409 &&
          commandErrorCode(error) === "owning_chat_finalizing"
        ) {
          const refreshed = await loadSession(undefined, {
            background: true,
            preserveStageDraft: true,
          });
          if (!refreshed) {
            const current = sessionRef.current;
            if (current) {
              commitSession({
                ...current,
                runtime_status: {
                  status: "finalizing",
                  runtime_ready: false,
                  blocking_run_id:
                    current.runtime_status?.blocking_run_id ?? null,
                },
              });
            }
          }
          setNotice("上一轮处理仍在结束中，回答已保留，请稍候再提交。");
        } else if (status === 409) {
          await loadSession(undefined, {
            background: true,
            preserveStageDraft: command === "confirm_stage_queue",
          });
          setNotice("页面状态已变化，已重新同步；你的输入草稿仍然保留。");
        } else if (status === 404) {
          setLoadState("unavailable");
        } else {
          setNotice("操作没有完成，请稍后重试。");
        }
        return null;
      } finally {
        setBusy(false);
      }
    },
    [commitSession, loadSession, navigate, session],
  );

  const submitAnswers = useCallback(async () => {
    if (!session?.question_batch) return;
    const next = await sendCommand("submit_answers", {
      batch_id: session.question_batch.batch_id,
      answers,
    });
    if (next) {
      setAnswerDraft({ scope: null, values: {} });
    }
  }, [answers, sendCommand, session]);

  const mainPanel = useMemo(() => {
    if (!session) return null;
    if (session.state === "AwaitingQueueConfirmation") {
      return (
        <StageQueueEditor
          session={session}
          stages={stages}
          busy={busy}
          onChange={setStages}
          onConfirm={() => void sendCommand("confirm_stage_queue", { stages })}
        />
      );
    }
    if (session.state === "AwaitingAnswer") {
      return (
        <QuestionBatchPanel
          session={session}
          answers={answers}
          busy={busy}
          runtimeReady={session.runtime_status?.runtime_ready === true}
          onAnswer={(questionId, value) => {
            setAnswerDraft((current) => ({
              scope: answerScope,
              values: {
                ...(current.scope === answerScope ? current.values : {}),
                [questionId]: value,
              },
            }));
          }}
          onSubmit={() => void submitAnswers()}
        />
      );
    }
    if (session.state === "AwaitingTrialFeedback" && session.trial) {
      return (
        <TrialPanel
          session={session}
          feedback={feedback}
          busy={busy}
          onFeedback={setFeedback}
          onRerun={() =>
            void sendCommand("submit_trial_feedback", {
              feedback: feedback.trim(),
              rerun_of_run_id: session.trial?.run_id,
            })
          }
          onAccept={() => void sendCommand("accept_trial")}
        />
      );
    }
    if (session.state === "AwaitingStageConfirmation") {
      const currentStage = session.stages.find(
        (stage) => stage.stage_id === session.current_stage_id,
      );
      return (
        <section className={styles.decisionPanel}>
          <CircleCheck size={34} />
          <span className={styles.eyebrow}>环节验收</span>
          <h2>{currentStage?.title || "当前环节"}已通过预跑</h2>
          <p>确认后将锁定本环节事实，并进入下一个环节。</p>
          <Button
            type="primary"
            size="large"
            loading={busy}
            onClick={() => void sendCommand("confirm_stage")}
          >
            确认并继续
          </Button>
        </section>
      );
    }
    if (session.state === "PendingExit") {
      return (
        <section className={styles.decisionPanel}>
          <Pause size={34} />
          <span className={styles.eyebrow}>正在安全退出</span>
          <h2>等待当前完整响应落盘</h2>
          <p>
            系统会在下一个稳定事件边界暂停；你也可以取消本轮运行并立即暂停。
          </p>
          <Space wrap>
            <Button
              loading={busy}
              onClick={() => void sendCommand("continue_waiting")}
            >
              继续等待
            </Button>
            <Button
              danger
              loading={busy}
              onClick={() => void sendCommand("cancel_run_and_pause")}
            >
              取消本轮并暂停
            </Button>
          </Space>
        </section>
      );
    }
    if (session.state === "Paused") {
      return (
        <section className={styles.decisionPanel}>
          <Pause size={34} />
          <span className={styles.eyebrow}>已保存</span>
          <h2>工作台已暂停</h2>
          <p>所有环节、回答和预跑结果都已保留。</p>
          <Button
            type="primary"
            icon={<Play size={16} />}
            loading={busy}
            onClick={() => void sendCommand("resume")}
          >
            从上次位置继续
          </Button>
        </section>
      );
    }
    if (session.state === "RecoverableFailure") {
      return (
        <section className={styles.decisionPanel}>
          <CircleAlert size={34} />
          <span className={styles.eyebrow}>可恢复失败</span>
          <h2>本轮运行没有完成</h2>
          <p>{session.failure?.message || "运行时暂时不可用。"}</p>
          <Button
            type="primary"
            icon={<RefreshCw size={16} />}
            loading={busy}
            onClick={() =>
              void sendCommand("retry_current_turn", {
                target_state: session.resume_state || "GeneratingQuestions",
                retry_of_run_id: session.failure?.failed_run_id,
              })
            }
          >
            重试当前轮
          </Button>
        </section>
      );
    }
    if (session.state === "OutputReview") {
      const preview = session.result_preview;
      return (
        <section className={styles.workSection}>
          <div className={styles.sectionHeading}>
            <div>
              <span className={styles.eyebrow}>结果确认</span>
              <h2>检查最终结果</h2>
              <p>确认内容和文件无误后，才会进入记忆授权环节。</p>
            </div>
            <Tag color="blue">待确认</Tag>
          </div>
          <ResultPreview preview={preview} />
          <div className={styles.artifactList}>
            {(session.artifacts || []).map((artifact) => (
              <Button
                key={artifact.artifact_id}
                type="text"
                disabled={!artifact.download_url}
                loading={downloadingArtifactId === artifact.artifact_id}
                title={artifact.name}
                onClick={() =>
                  void downloadArtifact(artifact.artifact_id, artifact.name)
                }
              >
                <FileCheck2 size={16} />
                <span className={styles.artifactName}>{artifact.name}</span>
              </Button>
            ))}
          </div>
          <div className={styles.outputReviewActions}>
            <Button
              type="primary"
              icon={<Check size={16} />}
              loading={busy}
              onClick={() => void sendCommand("confirm_outputs")}
            >
              确认结果并继续
            </Button>
          </div>
        </section>
      );
    }
    if (session.state === "MemoryReview" || session.state === "WritingMemory") {
      const memoryWriting = session.state === "WritingMemory";
      const unresolvedCandidates = (session.memory_candidates || []).filter(
        (candidate) =>
          candidate.status === "pending" || candidate.status === "failed",
      );
      const allMemoryDecisionsSelected = unresolvedCandidates.every(
        (candidate) => memoryDecisions[candidate.candidate_id] !== undefined,
      );
      const canCompleteResolvedReview =
        !memoryWriting && unresolvedCandidates.length === 0;
      const runtimeReady = session.runtime_status?.runtime_ready === true;
      return (
        <section className={styles.workSection}>
          <div className={styles.sectionHeading}>
            <div>
              <span className={styles.eyebrow}>完成前检查</span>
              <h2>选择可复用记忆</h2>
              <p>
                {memoryWriting
                  ? "Agent 正在一个回合内写入全部获批候选，完成后统一返回结果。"
                  : "请为每个候选选择是否保存，全部选择后一次提交。"}
              </p>
            </div>
          </div>
          <div className={styles.memoryList}>
            {(session.memory_candidates || []).map((candidate) => (
              <article key={candidate.candidate_id}>
                <div className={styles.memoryCandidateBody}>
                  <div>
                    <strong>{candidate.title}</strong>
                    <Tag>
                      {candidate.memory_type === "common_wplus_knowledge"
                        ? "公共 W+ 知识"
                        : candidate.memory_type === "user_wplus_usage"
                        ? "个人使用偏好"
                        : candidate.memory_type === "sop_case"
                        ? "脱敏 SOP 模式"
                        : "历史候选"}
                    </Tag>
                  </div>
                  <pre className={styles.memoryCandidateContent}>
                    {typeof candidate.content === "string"
                      ? candidate.content
                      : JSON.stringify(candidate.content, null, 2)}
                  </pre>
                  {candidate.evidence && (
                    <div className={styles.memoryEvidence}>
                      <span>准确对话证据</span>
                      <p>{candidate.evidence}</p>
                    </div>
                  )}
                  <dl className={styles.memoryCandidateMeta}>
                    <div>
                      <dt>写入范围</dt>
                      <dd>
                        {candidate.target_scope === "common"
                          ? "公共 W+ 知识"
                          : candidate.target_scope === "user"
                          ? "匿名用户偏好"
                          : candidate.target_scope === "cases"
                          ? "脱敏 SOP 案例"
                          : "历史候选"}
                      </dd>
                    </div>
                    <div>
                      <dt>目标位置</dt>
                      <dd>{candidate.target_file}</dd>
                    </div>
                  </dl>
                  {candidate.failure_reason && (
                    <Alert
                      type="error"
                      showIcon
                      message="上次写入失败"
                      description={candidate.failure_reason}
                    />
                  )}
                  {candidate.status === "writing" && (
                    <Alert
                      type="info"
                      showIcon
                      message="正在调用 memory_store.py"
                      description="完成后将返回 appended 或 duplicate 回执。"
                    />
                  )}
                  {candidate.write_receipt && (
                    <div className={styles.memoryReceipt}>
                      <span>写入回执</span>
                      <code>{candidate.write_receipt.memory_id}</code>
                      <small>
                        {candidate.write_receipt.target_file} ·{" "}
                        {candidate.write_receipt.store_result === "duplicate" ||
                        candidate.write_receipt.reused_existing
                          ? "已复用既有写入"
                          : "脚本校验并写入"}
                      </small>
                    </div>
                  )}
                </div>
                {candidate.status === "pending" ||
                candidate.status === "failed" ? (
                  <div
                    role="radiogroup"
                    aria-label={`记忆候选：${candidate.title}`}
                  >
                    <Radio.Group
                      name={`memory-candidate-${candidate.candidate_id}`}
                      value={memoryDecisions[candidate.candidate_id]}
                      optionType="button"
                      buttonStyle="solid"
                      disabled={busy || memoryWriting}
                      onChange={(event) =>
                        setMemoryDecisionDraft((current) => ({
                          scope: session.session_id,
                          values: {
                            ...(current.scope === session.session_id
                              ? current.values
                              : {}),
                            [candidate.candidate_id]: event.target.value,
                          },
                        }))
                      }
                    >
                      {!candidate.legacy_read_only && (
                        <Radio value="approve">
                          {candidate.status === "failed" ? "重试写入" : "保存"}
                        </Radio>
                      )}
                      <Radio value="reject">不保存</Radio>
                    </Radio.Group>
                  </div>
                ) : candidate.status === "writing" ? (
                  <Tag color="processing">写入中</Tag>
                ) : (
                  <Tag
                    color={
                      candidate.status === "approved" ? "green" : "default"
                    }
                  >
                    {candidate.status === "approved"
                      ? candidate.legacy_read_only
                        ? "历史已批准（无可验证写入回执）"
                        : "已写入"
                      : "已拒绝"}
                  </Tag>
                )}
              </article>
            ))}
          </div>
          {!memoryWriting && !runtimeReady && (
            <Alert
              type="info"
              showIcon
              message="正在等待上一轮 Agent 完成"
              description="运行环境就绪后才能统一提交，当前选择会保留在页面中。"
            />
          )}
          <Button
            type="primary"
            loading={busy}
            disabled={
              busy ||
              memoryWriting ||
              !runtimeReady ||
              !allMemoryDecisionsSelected
            }
            onClick={() =>
              void (canCompleteResolvedReview
                ? sendCommand("skip_memory")
                : sendCommand("resolve_memory", {
                    decisions: unresolvedCandidates.map((candidate) => ({
                      candidate_id: candidate.candidate_id,
                      decision: memoryDecisions[candidate.candidate_id],
                    })),
                  }))
            }
          >
            {canCompleteResolvedReview ? "完成" : "统一提交记忆选择"}
          </Button>
        </section>
      );
    }
    if (session.state === "Completed") {
      return (
        <section className={styles.decisionPanel}>
          <FileCheck2 size={34} />
          <span className={styles.eyebrow}>SOP 已完成</span>
          <h2>结果已生成并通过结构校验</h2>
          <div className={styles.artifactList}>
            {(session.artifacts || []).map((artifact) => (
              <Button
                key={artifact.artifact_id}
                type="text"
                disabled={!artifact.download_url}
                loading={downloadingArtifactId === artifact.artifact_id}
                title={artifact.name}
                onClick={() =>
                  void downloadArtifact(artifact.artifact_id, artifact.name)
                }
              >
                <FileCheck2 size={16} />
                <span className={styles.artifactName}>{artifact.name}</span>
              </Button>
            ))}
          </div>
          {(session.memory_candidates || []).length > 0 && (
            <section className={styles.memoryList} aria-label="记忆处理历史">
              <h3>记忆处理历史</h3>
              {(session.memory_candidates || []).map((candidate) => {
                const status = completedMemoryStatus(candidate);
                return (
                  <article key={candidate.candidate_id}>
                    <div>
                      <strong>{candidate.title}</strong>
                      {candidate.write_receipt && (
                        <p>
                          写入回执：
                          <code>{candidate.write_receipt.memory_id}</code>
                        </p>
                      )}
                    </div>
                    <Tag color={status.color}>{status.label}</Tag>
                  </article>
                );
              })}
            </section>
          )}
        </section>
      );
    }
    if (session.state === "Terminated") {
      return (
        <section className={styles.decisionPanel}>
          <X size={34} />
          <span className={styles.eyebrow}>会话结束</span>
          <h2>这个 SOP 工作台已彻底结束</h2>
          <p>历史过程仍可审计，但不能继续运行。</p>
        </section>
      );
    }
    return null;
  }, [
    answers,
    busy,
    downloadArtifact,
    downloadingArtifactId,
    feedback,
    memoryDecisions,
    sendCommand,
    session,
    stages,
    submitAnswers,
    answerScope,
  ]);

  if (loadState === "loading") {
    return (
      <main className={styles.statePage}>
        <section
          className={styles.loadingStatus}
          role="status"
          aria-live="polite"
          aria-labelledby="wplus-loading-title"
        >
          <h1 id="wplus-loading-title">正在加载 W+ SOP 工作台</h1>
          <p>正在同步环节、回答和预跑状态，请稍候。</p>
          <div className={styles.loadingSkeleton} aria-hidden="true">
            <Skeleton active paragraph={{ rows: 5 }} />
          </div>
        </section>
      </main>
    );
  }
  if (loadState === "unavailable") {
    return (
      <main className={styles.statePage}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={null}>
          <h1>无法访问这个工作台</h1>
          <p>它可能不存在，或不属于当前账号与 Chat。</p>
          <Button onClick={() => window.history.back()}>返回上一页</Button>
        </Empty>
      </main>
    );
  }
  if (loadState === "error" || !session) {
    return (
      <main className={styles.statePage}>
        <CircleAlert size={38} />
        <h1>工作台暂时无法加载</h1>
        <p>没有修改任何数据。请检查连接后重试。</p>
        <Button type="primary" onClick={() => void loadSession()}>
          重新加载
        </Button>
      </main>
    );
  }

  const conclusionMilestone = conclusionMilestoneProjection(session);
  const conclusionMilestoneNumber = session.stages.length
    ? session.stages.length + 1
    : 2;

  return (
    <main className={styles.workspace} aria-labelledby="wplus-workspace-title">
      <header className={styles.topbar}>
        <div>
          <Link to={`/chat/${session.chat_id}`} className={styles.backLink}>
            <ArrowLeft size={16} />
            返回所属 Chat
          </Link>
          <div className={styles.titleRow}>
            <div className={styles.productMark}>W+</div>
            <div>
              <h1 id="wplus-workspace-title" title={session.title}>
                {session.title}
              </h1>
              <p>
                状态版本 {session.state_version} · 修订 {session.revision}
              </p>
            </div>
          </div>
        </div>
        <div className={styles.headerActions}>
          <Tag
            color={
              session.state === "Completed"
                ? "success"
                : session.state === "RecoverableFailure"
                ? "error"
                : isGenerating(session)
                ? "processing"
                : "cyan"
            }
          >
            {getSessionStateLabel(session)}
          </Tag>
          {!["Completed", "Terminated", "Paused", "PendingExit"].includes(
            session.state,
          ) && (
            <Button
              icon={<Pause size={15} />}
              disabled={busy}
              onClick={() => void sendCommand("save_and_exit")}
            >
              保存并退出
            </Button>
          )}
        </div>
      </header>

      {notice && (
        <Alert
          className={styles.notice}
          type="info"
          showIcon
          closable
          message={notice}
          onClose={() => setNotice(null)}
        />
      )}

      <section className={styles.progressBand} aria-label="SOP 环节进度">
        <div className={styles.progressMeta}>
          <span>完整预跑流程</span>
          <strong>{stateProgress(session)}%</strong>
        </div>
        <Progress
          aria-label="SOP 总体进度"
          percent={stateProgress(session)}
          showInfo={false}
          strokeColor={PROGRESS_STROKE_COLOR}
          trailColor={PROGRESS_TRAIL_COLOR}
        />
        <ol>
          {session.stages.length ? (
            session.stages.map((stage, index) => (
              <li key={stage.stage_id} data-status={stage.status}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong title={stage.title}>{stage.title}</strong>
                  <small>
                    {stage.status === "confirmed"
                      ? "已确认"
                      : stage.status === "current"
                      ? "当前环节"
                      : "等待中"}
                  </small>
                </div>
              </li>
            ))
          ) : (
            <li data-status="current">
              <span>01</span>
              <div>
                <strong>生成环节提案</strong>
                <small>正在分析请求</small>
              </div>
            </li>
          )}
          <li data-status={conclusionMilestone.status}>
            <span>{String(conclusionMilestoneNumber).padStart(2, "0")}</span>
            <div>
              <strong title="生成结论">生成结论</strong>
              <small>{conclusionMilestone.label}</small>
            </div>
          </li>
        </ol>
      </section>

      <div className={styles.evidenceDrawerEntry}>
        <Button
          icon={<FileCheck2 size={16} />}
          onClick={() => setEvidenceDrawerOpen(true)}
        >
          查看本次 SOP 证据
        </Button>
      </div>

      <div className={styles.workspaceGrid}>
        <div className={styles.primaryColumn}>
          {sessionIsGenerating || visibleSafeStreamTrace ? (
            <LiveRunTranscript
              trace={visibleSafeStreamTrace}
              running={sessionIsGenerating}
              title={getSessionStateLabel(session)}
            />
          ) : null}
          {mainPanel}
        </div>
        <EvidenceRail session={session} />
      </div>

      <Drawer
        rootClassName={styles.evidenceDrawer}
        title="本次 SOP 证据"
        placement="right"
        width="min(92vw, 380px)"
        open={evidenceDrawerOpen}
        destroyOnHidden
        closable={{ "aria-label": "关闭本次 SOP 证据" }}
        onClose={() => setEvidenceDrawerOpen(false)}
      >
        <div className={styles.evidenceDrawerBody}>
          <EvidenceRail session={session} />
        </div>
      </Drawer>
    </main>
  );
}
