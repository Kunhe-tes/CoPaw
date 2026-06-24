import { useCallback, useEffect, useRef, useState } from "react";
import { Modal, message, Select, Input, Spin } from "antd";
import { AlertTriangle, Copy } from "lucide-react";
import {
  tracingApi,
  type ErrorItem,
  type ErrorListResponse,
  type TraceDetail,
  type Span,
  type SessionTracesResponse,
} from "../../../../../api/modules/tracing";
import { getBbkDisplayName } from "../../../../../constants/bbk";
import styles from "./index.module.less";

interface ErrorDetailModalProps {
  open: boolean;
  startDate: string;
  endDate: string;
  bbkIds?: string;
  onClose: () => void;
}

const formatTime = (time: string | null) => {
  if (!time) return "-";
  const date = new Date(time);
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

const formatDuration = (ms: number | null | undefined) => {
  if (!ms) return "-";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
};

const formatTokens = (tokens: number | null | undefined) => {
  if (!tokens) return "0";
  if (tokens < 1000) return tokens.toString();
  if (tokens < 1000000) return `${(tokens / 1000).toFixed(1)}K`;
  return `${(tokens / 1000000).toFixed(1)}M`;
};

const truncateText = (text: string, maxLen: number) => {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "...";
};

const truncateId = (id: string) => {
  if (id.length <= 64) return id;
  return id.slice(0, 64) + "...";
};

const truncateSessionName = (name: string) => {
  if (name.length <= 100) return name;
  return name.slice(0, 100) + "...";
};

// 调用链路步骤类型
interface ChainStep {
  type: "user" | "llm" | "tool";
  name: string;
  status: "success" | "error" | "pending";
  isErrorNode: boolean;
  time: string;
}

// 从 spans 组装调用链路
const buildCallChain = (
  spans: Span[],
  selectedError: ErrorItem | null
): ChainStep[] => {
  if (!spans || spans.length === 0) return [];

  // 按 start_time 排序
  const sortedSpans = [...spans].sort(
    (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
  );

  const chain: ChainStep[] = [];

  // 添加用户消息步骤（从第一个 llm_input 之前推断）
  const firstLlmInput = sortedSpans.find(s => s.event_type === "llm_input");
  if (firstLlmInput) {
    chain.push({
      type: "user",
      name: "用户消息",
      status: "success",
      isErrorNode: false,
      time: firstLlmInput.start_time,
    });
  }

  // 处理每个 span
  for (const span of sortedSpans) {
    // 过滤关键事件类型
    if (
      span.event_type !== "llm_input" &&
      span.event_type !== "llm_output" &&
      span.event_type !== "tool_call_end"
    ) {
      continue;
    }

    // 判断是否是报错节点
    const isErrorNode =
      selectedError &&
      span.span_id === selectedError.span_id &&
      !!span.error;

    // LLM 调用
    if (span.event_type === "llm_input" || span.event_type === "llm_output") {
      const modelName = span.model_name || "LLM";
      // 检查是否已存在相同模型名的 LLM 步骤（避免重复）
      const existingLlm = chain.find(
        c => c.type === "llm" && c.name === modelName
      );
      if (!existingLlm) {
        chain.push({
          type: "llm",
          name: modelName,
          status: isErrorNode ? "error" : span.error ? "error" : "success",
          isErrorNode,
          time: span.start_time,
        });
      }
    }

    // 工具调用（只处理 tool_call_end，代表完成状态）
    if (span.event_type === "tool_call_end") {
      const toolName = span.tool_name || "工具";
      chain.push({
        type: "tool",
        name: toolName,
        status: isErrorNode ? "error" : span.error ? "error" : "success",
        isErrorNode,
        time: span.start_time,
      });
    }
  }

  return chain;
};

export default function ErrorDetailModal({
  open,
  startDate,
  endDate,
  bbkIds,
  onClose,
}: ErrorDetailModalProps) {
  const [errors, setErrors] = useState<ErrorItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const loadingRef = useRef(false);

  const [errorType, setErrorType] = useState<string>("all");
  const [searchText, setSearchText] = useState("");

  const [selectedError, setSelectedError] = useState<ErrorItem | null>(null);
  const [traceDetail, setTraceDetail] = useState<TraceDetail | null>(null);
  const [sessionTraces, setSessionTraces] = useState<SessionTracesResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 使用 ref 跟踪是否需要自动选中第一个
  const shouldAutoSelect = useRef(true);

  const fetchErrors = useCallback(
    async (pageNum: number, append: boolean = false) => {
      if (loadingRef.current) return;
      loadingRef.current = true;

      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }

      try {
        const result = await tracingApi.getErrorList(pageNum, pageSize, {
          start_date: startDate,
          end_date: endDate,
          bbk_ids: bbkIds,
          error_type: errorType === "all" ? undefined : errorType,
          search: searchText || undefined,
        });

        if (append) {
          setErrors(prev => [...prev, ...(result.items || [])]);
        } else {
          setErrors(result.items || []);
        }
        setTotal(result.total || 0);
        setHasMore((result.items || []).length >= pageSize);

        // 默认选中第一个（仅在初始化时）
        if (!append && result.items && result.items.length > 0 && shouldAutoSelect.current) {
          setSelectedError(result.items[0]);
          shouldAutoSelect.current = false;
        }
      } catch (error) {
        console.error("Failed to fetch error list:", error);
        message.error("获取错误列表失败");
      } finally {
        setLoading(false);
        setLoadingMore(false);
        loadingRef.current = false;
      }
    },
    [startDate, endDate, bbkIds, errorType, searchText, pageSize],
  );

  const handleScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      const target = e.currentTarget;
      const scrollBottom = target.scrollHeight - target.scrollTop - target.clientHeight;

      if (scrollBottom < 40 && hasMore && !loadingRef.current) {
        const nextPage = page + 1;
        setPage(nextPage);
        fetchErrors(nextPage, true);
      }
    },
    [page, hasMore, fetchErrors],
  );

  const fetchTraceDetail = useCallback(async (traceId: string, sessionId: string) => {
    setDetailLoading(true);
    try {
      // 并行获取 trace detail 和 session traces
      const [detail, sessionData] = await Promise.all([
        tracingApi.getTraceDetail(traceId),
        tracingApi.getSessionTraces(sessionId, traceId),
      ]);
      setTraceDetail(detail);
      setSessionTraces(sessionData);
    } catch (error) {
      console.error("Failed to fetch trace detail:", error);
      message.error("获取对话详情失败");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // 重置并加载新数据（当筛选条件变化时）
  useEffect(() => {
    if (open) {
      shouldAutoSelect.current = true;
      setErrors([]);
      setPage(1);
      setHasMore(true);
      setSelectedError(null);
      setTraceDetail(null);
      fetchErrors(1, false);
    }
  }, [open, fetchErrors]);

  useEffect(() => {
    if (selectedError) {
      fetchTraceDetail(selectedError.trace_id, selectedError.session_id);
    }
  }, [selectedError, fetchTraceDetail]);

  const handleClose = () => {
    shouldAutoSelect.current = true;
    setErrors([]);
    setTotal(0);
    setPage(1);
    setHasMore(true);
    setSelectedError(null);
    setTraceDetail(null);
    setSessionTraces(null);
    setErrorType("all");
    setSearchText("");
    onClose();
  };

  const handleSelectError = (error: ErrorItem) => {
    setSelectedError(error);
  };

  const handleCopyTraceId = async () => {
    if (!selectedError) return;
    try {
      await navigator.clipboard.writeText(selectedError.trace_id);
      message.success("Trace ID 已复制");
    } catch {
      message.error("复制失败");
    }
  };

  const totalInputTokens = traceDetail?.trace.total_input_tokens ?? 0;
  const totalOutputTokens = traceDetail?.trace.total_output_tokens ?? 0;

  return (
    <Modal
      title={
        <span>
          <AlertTriangle size={18} style={{ marginRight: 8, color: "#ef4444" }} />
          报错详情
        </span>
      }
      open={open}
      onCancel={handleClose}
      width="100vw"
      footer={null}
      destroyOnClose
      className={styles.errorDetailModal}
      classNames={{ body: styles.errorDetailModalBody }}
      style={{ top: 0, paddingBottom: 0 }}
    >
      <div className={styles.modalContent}>
        {/* 左侧：错误列表 */}
        <div className={styles.leftPanel}>
          {/* 固定的头部区域 */}
          <div className={styles.leftPanelHeader}>
            <div className={styles.errorListHeader}>
              <div className={styles.errorListTitle}>错误列表</div>
              <span className={styles.errorListCount}>共 {total} 条</span>
            </div>

            <div className={styles.errorListFilters}>
              <Select
                value={errorType}
                onChange={(val) => {
                  setErrorType(val);
                  shouldAutoSelect.current = true;
                  setSelectedError(null);
                }}
                style={{ flex: 1 }}
                options={[
                  { value: "all", label: "全部类型" },
                  { value: "llm_input", label: "模型报错" },
                  { value: "tool_call_end", label: "工具报错" },
                ]}
              />
              <Input
                placeholder="搜索用户/错误"
                value={searchText}
                onChange={(e) => {
                  setSearchText(e.target.value);
                  shouldAutoSelect.current = true;
                  setSelectedError(null);
                }}
                style={{ width: 140 }}
                allowClear
              />
            </div>
          </div>

          {/* 滚动的列表区域 */}
          <div className={styles.errorListScroll} onScroll={handleScroll}>
            {loading && errors.length === 0 ? (
              <div className={styles.errorListLoading}>
                <Spin size="small" />
              </div>
            ) : errors.length === 0 ? (
              <div className={styles.errorListEmpty}>暂无错误记录</div>
            ) : (
              <>
                {errors.map((err) => (
                  <div
                    key={err.span_id}
                    className={`${styles.errorCard} ${
                      selectedError?.span_id === err.span_id ? styles.selected : ""
                    }`}
                    onClick={() => handleSelectError(err)}
                  >
                    <div className={styles.errorCardHeader}>
                      <span
                        className={`${styles.errorTypeTag} ${
                          err.event_type === "llm_input"
                            ? styles.errorTypeTagModel
                            : styles.errorTypeTagTool
                        }`}
                      >
                        {err.event_type === "llm_input" ? "模型报错" : "工具报错"}
                      </span>
                      <span className={styles.errorCardTime}>
                        {formatTime(err.start_time)}
                      </span>
                    </div>
                    <div className={styles.errorCardMessage}>
                      {truncateText(err.error, 50)}
                    </div>
                    <div className={styles.errorCardMeta}>
                      <span>
                        👤 {err.user_name || err.user_id}
                        {err.bbk_id && ` / ${getBbkDisplayName(err.bbk_id)}`}
                      </span>
                      {err.event_type === "llm_input" && err.model_name && (
                        <span>🤖 {err.model_name}</span>
                      )}
                      {err.event_type === "tool_call_end" && err.tool_name && (
                        <span>🔧 {err.tool_name}</span>
                      )}
                    </div>
                    <div className={styles.errorCardTrace}>
                      trace:{" "}
                      <span className={styles.errorTraceId}>
                        {truncateId(err.trace_id)}
                      </span>{" "}
                      | {formatDuration(err.duration_ms)} |{" "}
                      {formatTokens(
                        (err.input_tokens ?? 0) + (err.output_tokens ?? 0),
                      )}{" "}
                      tokens
                    </div>
                  </div>
                ))}
                {loadingMore && (
                  <div className={styles.loadingMore}>加载中...</div>
                )}
              </>
            )}
          </div>
        </div>

        {/* 右侧：对话详情 */}
        <div className={styles.rightPanel}>
          {detailLoading ? (
            <div className={styles.detailLoading}>
              <Spin size="small" />
            </div>
          ) : !selectedError ? (
            <div className={styles.detailLoading}>请选择一个错误查看详情</div>
          ) : traceDetail ? (
            <>
              {/* 错误摘要卡片 */}
              <div className={styles.errorSummaryCard}>
                <div className={styles.errorSummaryHeader}>
                  <span style={{ color: "#ef4444", fontSize: "16px" }}>⚠️</span>
                  <span className={styles.errorSummaryTitle}>错误摘要</span>
                </div>
                <div className={styles.errorSummaryContent}>
                  {selectedError.error}
                </div>
                <div className={styles.errorSummaryMeta}>
                  <span
                    className={`${styles.errorTypeTag} ${
                      selectedError.event_type === "llm_input"
                        ? styles.errorTypeTagModel
                        : styles.errorTypeTagTool
                    }`}
                  >
                    {selectedError.event_type === "llm_input" ? "模型报错" : "工具报错"}
                  </span>
                  <span style={{ color: "#6b7280", fontSize: "11px" }}>
                    {formatTime(selectedError.start_time)}
                  </span>
                </div>
              </div>

              {/* 对话信息卡片 */}
              <div className={styles.conversationInfoCard}>
                <div className={styles.conversationInfoHeader}>
                  <span>📊</span> 对话信息
                </div>
                <div className={styles.conversationInfoGrid}>
                  <div className={styles.conversationInfoItem}>
                    <span className={styles.conversationInfoLabel}>Trace ID:</span>
                    <span className={styles.traceIdWrap}>
                      <span className={styles.traceIdText}>
                        {truncateId(traceDetail.trace.trace_id)}
                      </span>
                      <button
                        type="button"
                        className={styles.copyIconBtn}
                        onClick={handleCopyTraceId}
                        title="复制 Trace ID"
                      >
                        <Copy size={14} />
                      </button>
                    </span>
                  </div>
                  <div className={styles.conversationInfoItem}>
                    <span className={styles.conversationInfoLabel}>会话:</span>
                    <span className={styles.conversationInfoValue}>
                      {traceDetail.trace.session_name
                        ? truncateSessionName(traceDetail.trace.session_name)
                        : truncateId(traceDetail.trace.session_id)}
                    </span>
                  </div>
                  <div className={styles.conversationInfoItem}>
                    <span className={styles.conversationInfoLabel}>用户:</span>
                    <span className={styles.conversationInfoValue}>
                      {traceDetail.trace.user_name || traceDetail.trace.user_id}
                      {traceDetail.trace.bbk_id &&
                        ` / ${getBbkDisplayName(traceDetail.trace.bbk_id)}`}
                    </span>
                  </div>
                  <div className={styles.conversationInfoItem}>
                    <span className={styles.conversationInfoLabel}>时长:</span>
                    <span className={styles.conversationInfoBadge}>
                      {formatDuration(traceDetail.trace.duration_ms)}
                    </span>
                  </div>
                  <div className={styles.conversationInfoItem}>
                    <span className={styles.conversationInfoLabel}>Token:</span>
                    <span className={styles.conversationInfoBadge}>
                      输入 {formatTokens(totalInputTokens)} / 输出 {formatTokens(totalOutputTokens)}
                    </span>
                  </div>
                  <div className={styles.conversationInfoItem}>
                    <span className={styles.conversationInfoLabel}>模型:</span>
                    <span className={styles.conversationInfoValue}>
                      {traceDetail.trace.model_name || "-"}
                    </span>
                  </div>
                  <div className={styles.conversationInfoItem}>
                    <span className={styles.conversationInfoLabel}>状态:</span>
                    <span className={styles.statusError}>
                      {traceDetail.trace.status}
                    </span>
                  </div>
                </div>
              </div>

              {/* 完整对话卡片 - Session 时间线 */}
              <div className={styles.conversationContentCard}>
                <div className={styles.conversationContentHeader}>
                  <span>💬</span> 完整对话
                  {sessionTraces && (
                    <span className={styles.sessionRoundInfo}>
                      共 {sessionTraces.total_rounds} 轮
                      {sessionTraces.error_round_index !== null && (
                        <span className={styles.errorRoundHint}>
                          · 第 {sessionTraces.error_round_index + 1} 轮报错
                        </span>
                      )}
                    </span>
                  )}
                </div>

                {sessionTraces && sessionTraces.traces.length > 0 ? (
                  <div className={styles.sessionTimeline}>
                    {sessionTraces.traces.map((round, idx) => (
                      <div
                        key={round.trace_id}
                        className={`${styles.roundCard} ${round.is_error_round ? styles.roundError : ""}`}
                      >
                        {/* 轮次头部 */}
                        <div className={styles.roundHeader}>
                          <span className={styles.roundNumberBadge}>
                            第 {round.round_number} 轮
                          </span>
                          <span className={styles.roundTime}>
                            {formatTime(round.start_time)}
                          </span>
                          {round.model_name && (
                            <span className={styles.roundModel}>
                              🤖 {round.model_name}
                            </span>
                          )}
                          <span className={`${styles.roundStatus} ${round.is_error_round ? styles.statusError : styles.statusSuccess}`}>
                            {round.is_error_round ? "❌" : "✓"}
                          </span>
                        </div>

                        {/* 轮次内容 */}
                        <div className={styles.roundContent}>
                          {/* 用户消息 */}
                          {round.user_message && (
                            <div className={styles.roundMessageBlock}>
                              <div className={styles.roundMessageLabel}>👤 用户</div>
                              <div className={styles.roundMessageText}>
                                {round.user_message}
                              </div>
                            </div>
                          )}

                          {/* 模型响应 */}
                          <div className={styles.roundMessageBlock}>
                            <div className={styles.roundMessageLabel}>🤖 模型</div>
                            <div className={`${styles.roundMessageText} ${round.is_error_round ? styles.modelResponseError : ""}`}>
                              {round.model_output || (
                                <span className={styles.emptyResponse}>
                                  {round.is_error_round ? "调用失败，未生成响应" : "等待响应..."}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* 工具使用 */}
                          {round.tools_used && round.tools_used.length > 0 && (
                            <div className={styles.roundTools}>
                              <span className={styles.roundToolsLabel}>🔧 工具:</span>
                              {round.tools_used.map((tool, tIdx) => (
                                <span key={`${tool}-${tIdx}`} className={styles.roundToolTag}>
                                  {tool}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* 指标 */}
                          <div className={styles.roundMetrics}>
                            <span>时长: {formatDuration(round.duration_ms)}</span>
                            <span>
                              Token: {formatTokens(round.input_tokens)} 输入 / {formatTokens(round.output_tokens)} 输出
                            </span>
                          </div>

                          {/* 错误信息 */}
                          {round.is_error_round && round.error && (
                            <div className={styles.roundErrorInfo}>
                              <span>⚠️ 错误: {round.error}</span>
                            </div>
                          )}
                        </div>

                        {/* 轮次分隔箭头 */}
                        {idx < sessionTraces.traces.length - 1 && (
                          <div className={styles.roundSeparator}>
                            <span className={styles.roundArrow}>↓</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  /* 兜底：无 sessionTraces 时显示原有单轮内容 */
                  <>
                    {/* 用户消息 */}
                    {traceDetail.trace.user_message && (
                      <div className={styles.conversationBlock}>
                        <div className={styles.conversationBlockHeader}>
                          <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                            👤 用户消息
                          </span>
                          <span>{formatTime(traceDetail.trace.start_time)}</span>
                        </div>
                        <div className={`${styles.conversationBlockContent} ${styles.userMessageBlock}`}>
                          {traceDetail.trace.user_message}
                        </div>
                      </div>
                    )}

                    {/* 模型响应 */}
                    <div className={styles.conversationBlock}>
                      <div className={styles.conversationBlockHeader}>
                        <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          🤖 模型响应
                        </span>
                      </div>
                      <div className={`${styles.conversationBlockContent} ${styles.modelResponseBlock}`}>
                        {traceDetail.trace.model_output ? (
                          <div>{traceDetail.trace.model_output}</div>
                        ) : (
                          <div className={styles.modelResponseEmpty}>
                            {selectedError.event_type === "llm_input"
                              ? "模型调用失败，未生成响应内容"
                              : "工具调用失败，流程中断"}
                          </div>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>

              {/* 调用链路卡片 */}
              <div className={styles.callChainCard}>
                <div className={styles.callChainHeader}>
                  <span>🔗</span> 调用链路
                </div>
                <div className={styles.callChainFlow}>
                  {(() => {
                    const chain = buildCallChain(traceDetail.spans, selectedError);
                    if (chain.length === 0) {
                      return <span className={styles.callChainEmpty}>无执行记录</span>;
                    }
                    return chain.map((step, idx) => (
                      <>
                        <span
                          key={`${step.type}-${step.name}-${idx}`}
                          className={`${styles.callChainStep} ${
                            step.status === "success"
                              ? styles.callChainStepSuccess
                              : step.status === "error"
                              ? styles.callChainStepError
                              : ""
                          }`}
                        >
                          {step.type === "user" && "👤 "}
                          {step.type === "llm" && "🤖 "}
                          {step.type === "tool" && "🔧 "}
                          {step.name}
                          {step.status === "success" && " ✓"}
                          {step.isErrorNode && " ❌"}
                        </span>
                        {idx < chain.length - 1 && (
                          <span className={styles.callChainArrow}>→</span>
                        )}
                      </>
                    ));
                  })()}
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}