import { useCallback, useEffect, useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  Table,
  Card,
  Input,
  Button,
  DatePicker,
  Tooltip,
  message,
  Select,
  Modal,
  Alert,
  Empty,
  Segmented,
  Spin,
} from "antd";
import { BarChart3, Clock3, Database, Download, RefreshCw } from "lucide-react";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { PageHeader } from "@/components/PageHeader";
import { tracingApi, UserMessageItem } from "../../../api/modules/tracing";
import {
  monitorApi,
  type HighFrequencyQuestionCriteria,
  type HighFrequencyQuestionResult,
} from "../../../api/modules/monitor";
import { getBbkDisplayName, BBK_ID_MAP } from "../../../constants/bbk";
import styles from "./index.module.less";

const { RangePicker } = DatePicker;

function getDefaultAnalysisRange(): [Dayjs, Dayjs] {
  return [dayjs().subtract(6, "day").startOf("day"), dayjs().endOf("day")];
}

function toHighFrequencyCriteria(
  range: [Dayjs, Dayjs],
  bbkId?: string,
): HighFrequencyQuestionCriteria {
  return {
    start_time: range[0].startOf("day").format("YYYY-MM-DD HH:mm:ss"),
    end_time: range[1].endOf("day").format("YYYY-MM-DD HH:mm:ss"),
    bbk_id: bbkId || null,
  };
}

function getTopicPercent(topic: HighFrequencyQuestionResult["topics"][number]) {
  if (!topic.valid_message_count) {
    return "0.0%";
  }
  return `${((topic.message_count / topic.valid_message_count) * 100).toFixed(
    1,
  )}%`;
}

function formatAnalysisTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  return dayjs(value).format("YYYY-MM-DD HH:mm:ss");
}

function getPercentClassName(rankNo: number) {
  if (rankNo === 1) return styles.analysisPercentFirst;
  if (rankNo === 2) return styles.analysisPercentSecond;
  if (rankNo === 3) return styles.analysisPercentThird;
  return styles.analysisPercentDefault;
}

export default function MessagesPage() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState<UserMessageItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [searchQuery, setSearchQuery] = useState("");
  const [userIdFilter, setUserIdFilter] = useState("");
  const [sessionIdFilter, setSessionIdFilter] = useState("");
  const [bbkIdFilter, setBbkIdFilter] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(
    [dayjs().subtract(7, "day"), dayjs()],
  );
  const [exporting, setExporting] = useState(false);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [analysisRange, setAnalysisRange] = useState<[Dayjs, Dayjs]>(
    getDefaultAnalysisRange,
  );
  const [analysisQuickRange, setAnalysisQuickRange] = useState("7");
  const [analysisBbkId, setAnalysisBbkId] = useState<string | undefined>();
  const [analysisResult, setAnalysisResult] =
    useState<HighFrequencyQuestionResult | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisSubmitting, setAnalysisSubmitting] = useState(false);
  const [analysisTaskId, setAnalysisTaskId] = useState<string | null>(null);
  const [analysisTaskStatus, setAnalysisTaskStatus] = useState<
    "idle" | "running" | "failed"
  >("idle");
  const [analysisQueried, setAnalysisQueried] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // 用于追踪筛选条件变化，避免 useEffect 重复触发
  const filtersRef = useRef({
    searchQuery: "",
    userIdFilter: "",
    sessionIdFilter: "",
    bbkIdFilter: undefined as string | undefined,
    dateRange: [dayjs().subtract(7, "day"), dayjs()] as
      | [dayjs.Dayjs, dayjs.Dayjs]
      | null,
  });

  useEffect(() => {
    // 检查筛选条件是否变化
    const filtersChanged =
      filtersRef.current.searchQuery !== searchQuery ||
      filtersRef.current.userIdFilter !== userIdFilter ||
      filtersRef.current.sessionIdFilter !== sessionIdFilter ||
      filtersRef.current.bbkIdFilter !== bbkIdFilter ||
      filtersRef.current.dateRange !== dateRange;

    // 更新 ref
    filtersRef.current = {
      searchQuery,
      userIdFilter,
      sessionIdFilter,
      bbkIdFilter,
      dateRange,
    };

    // 如果筛选条件变化且不是第一页，只重置页码不查询（等待 page 变化触发查询）
    if (filtersChanged && page !== 1) {
      setPage(1);
      return;
    }

    fetchMessages();
  }, [page, pageSize, bbkIdFilter, dateRange]);

  const handleSearch = () => {
    setPage(1);
    fetchMessages();
  };

  const fetchMessages = async () => {
    setLoading(true);
    try {
      const data = await tracingApi.getUserMessages(page, pageSize, {
        user_id: userIdFilter || undefined,
        session_id: sessionIdFilter || undefined,
        bbk_ids: bbkIdFilter,
        start_date: dateRange?.[0]?.format("YYYY-MM-DD"),
        end_date: dateRange?.[1]?.format("YYYY-MM-DD"),
        query: searchQuery || undefined,
      });
      setMessages(data.items || []);
      setTotal(data.total || 0);
    } catch (error) {
      console.error("Failed to fetch messages:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await tracingApi.exportUserMessages(
        {
          user_id: userIdFilter || undefined,
          session_id: sessionIdFilter || undefined,
          bbk_ids: bbkIdFilter,
          start_date: dateRange?.[0]?.format("YYYY-MM-DD"),
          end_date: dateRange?.[1]?.format("YYYY-MM-DD"),
          query: searchQuery || undefined,
        },
        "xlsx",
      );
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `user_messages_${dayjs().format("YYYYMMDD_HHmmss")}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Failed to export messages:", error);
      const errorMsg = error instanceof Error ? error.message : "Export failed";
      message.error(errorMsg);
    } finally {
      setExporting(false);
    }
  };

  const resetAnalysisResultState = () => {
    setAnalysisResult(null);
    setAnalysisError(null);
    setAnalysisTaskId(null);
    setAnalysisTaskStatus("idle");
    setAnalysisQueried(false);
  };

  const queryAnalysisResult = useCallback(
    async (range = analysisRange, bbkId = analysisBbkId) => {
      setAnalysisLoading(true);
      setAnalysisError(null);
      setAnalysisTaskId(null);
      setAnalysisTaskStatus("idle");
      try {
        const data = await monitorApi.getHighFrequencyQuestionResults(
          toHighFrequencyCriteria(range, bbkId),
        );
        setAnalysisResult(data);
        setAnalysisQueried(true);
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : "查询高频问题结果失败";
        setAnalysisError(errorMsg);
        message.error(errorMsg);
      } finally {
        setAnalysisLoading(false);
      }
    },
    [analysisRange, analysisBbkId],
  );

  const openAnalysisModal = () => {
    setAnalysisOpen(true);
    void queryAnalysisResult(analysisRange, analysisBbkId);
  };

  const handleAnalysisQuickRangeChange = (value: string | number) => {
    const days = Number(value);
    setAnalysisQuickRange(String(value));
    setAnalysisRange([
      dayjs()
        .subtract(days - 1, "day")
        .startOf("day"),
      dayjs().endOf("day"),
    ]);
    resetAnalysisResultState();
  };

  const handleAnalysisRangeChange = (
    dates: null | [Dayjs | null, Dayjs | null],
  ) => {
    if (!dates?.[0] || !dates?.[1]) {
      return;
    }
    if (dates[1].startOf("day").diff(dates[0].startOf("day"), "day") > 6) {
      message.warning("高频问题分析最多支持 7 天的数据范围");
      return;
    }
    setAnalysisRange([dates[0], dates[1]]);
    setAnalysisQuickRange("custom");
    resetAnalysisResultState();
  };

  const handleAnalysisBbkChange = (value?: string) => {
    setAnalysisBbkId(value);
    resetAnalysisResultState();
  };

  const submitAnalysisTask = async () => {
    setAnalysisSubmitting(true);
    setAnalysisError(null);
    try {
      const data = await monitorApi.submitHighFrequencyQuestionTask(
        toHighFrequencyCriteria(analysisRange, analysisBbkId),
      );
      if (data.state === "AVAILABLE") {
        setAnalysisResult({ ...data, state: "AVAILABLE" });
        setAnalysisTaskId(null);
        setAnalysisTaskStatus("idle");
        setAnalysisQueried(true);
        return;
      }
      setAnalysisResult(null);
      setAnalysisQueried(true);
      setAnalysisTaskId(data.task_id || null);
      setAnalysisTaskStatus("running");
    } catch (error) {
      const errorMsg =
        error instanceof Error ? error.message : "提交高频问题分析任务失败";
      setAnalysisError(errorMsg);
      message.error(errorMsg);
    } finally {
      setAnalysisSubmitting(false);
    }
  };

  useEffect(() => {
    if (!analysisOpen || !analysisTaskId || analysisTaskStatus !== "running") {
      return;
    }

    let cancelled = false;
    const timer = window.setInterval(() => {
      monitorApi
        .getAsyncTaskDetail(analysisTaskId)
        .then((task) => {
          if (cancelled) {
            return;
          }
          const status = String(task.status || "").toLowerCase();
          if (status === "succeeded" || status === "success") {
            window.clearInterval(timer);
            setAnalysisTaskStatus("idle");
            setAnalysisTaskId(null);
            void queryAnalysisResult();
          } else if (status === "failed" || status === "error") {
            window.clearInterval(timer);
            setAnalysisTaskStatus("failed");
            setAnalysisError(
              task.error_message || "高频问题分析生成失败，请稍后重新生成",
            );
          }
        })
        .catch((error) => {
          if (cancelled) {
            return;
          }
          const errorMsg =
            error instanceof Error ? error.message : "查询任务状态失败";
          setAnalysisError(errorMsg);
        });
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [analysisOpen, analysisTaskId, analysisTaskStatus, queryAnalysisResult]);

  const renderAnalysisContent = () => {
    if (analysisLoading) {
      return (
        <div className={styles.analysisCenterState}>
          <Spin />
          <span>正在查询高频问题结果</span>
        </div>
      );
    }

    if (analysisTaskStatus === "running") {
      return (
        <div className={styles.analysisCenterState}>
          <Spin />
          <strong>高频问题分析生成中</strong>
          <span>结果生成后将自动刷新，你也可以关闭弹窗稍后再看。</span>
        </div>
      );
    }

    if (
      analysisResult?.state === "AVAILABLE" ||
      analysisResult?.state === "AVAILABLE_STALE"
    ) {
      return (
        <>
          {analysisResult.state === "AVAILABLE_STALE" && (
            <Alert
              className={styles.analysisAlert}
              type="warning"
              showIcon
              message={
                analysisResult.message || "最近一次更新失败，当前展示历史结果"
              }
            />
          )}
          <div className={styles.analysisStatusBar}>
            <div className={styles.analysisStatusMain}>
              <span className={styles.analysisStatusIcon}>
                <Clock3 size={18} />
              </span>
              <div>
                <strong>当前结果已生成</strong>
                <span>
                  本结果更新于{" "}
                  {formatAnalysisTime(analysisResult.result_updated_at)}
                </span>
              </div>
            </div>
            <div className={styles.analysisSource}>
              <Database size={16} />
              <span>数据来源：{analysisResult.source_id || "-"}</span>
            </div>
          </div>
          <section className={styles.analysisResults}>
            <h3>高频问题 TOP10</h3>
            <div className={styles.analysisTopicList}>
              {analysisResult.topics.map((topic) => (
                <article className={styles.analysisTopic} key={topic.rank_no}>
                  <div
                    className={`${styles.analysisRank} ${
                      topic.rank_no <= 3 ? styles.analysisRankTop : ""
                    }`}
                  >
                    {topic.rank_no}
                  </div>
                  <div className={styles.analysisTopicContent}>
                    <strong>{topic.topic_name}</strong>
                    <div className={styles.analysisQuestions}>
                      {topic.sample_questions.slice(0, 3).map((question) => (
                        <span key={question}>“{question}”</span>
                      ))}
                    </div>
                  </div>
                  <span
                    className={`${styles.analysisPercent} ${getPercentClassName(
                      topic.rank_no,
                    )}`}
                  >
                    {getTopicPercent(topic)}
                  </span>
                </article>
              ))}
            </div>
          </section>
        </>
      );
    }

    if (analysisQueried && analysisResult?.state === "EMPTY") {
      return (
        <Empty
          className={styles.analysisEmpty}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="当前筛选条件暂无分析结果"
        />
      );
    }

    return (
      <Empty
        className={styles.analysisEmpty}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="请先查询当前筛选条件下的分析结果"
      />
    );
  };

  const formatDuration = (ms: number | null) => {
    if (ms === null) return "-";
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const truncateMessage = (msg: string | null, maxLen: number = 100) => {
    if (!msg) return "-";
    if (msg.length <= maxLen) return msg;
    return msg.slice(0, maxLen) + "...";
  };

  const columns: ColumnsType<UserMessageItem> = [
    {
      title: t("analytics.traceId"),
      dataIndex: "trace_id",
      key: "trace_id",
      width: 140,
      ellipsis: true,
      render: (v) => (
        <Tooltip title={v}>
          <span style={{ fontFamily: "monospace", fontSize: 12 }}>{v}</span>
        </Tooltip>
      ),
    },
    {
      title: t("analytics.userId", "User ID"),
      dataIndex: "user_id",
      key: "user_id",
      width: 100,
      ellipsis: true,
    },
    {
      title: t("analytics.userName", "用户姓名"),
      dataIndex: "user_name",
      key: "user_name",
      width: 100,
      render: (v) => v || "-",
    },
    {
      title: t("analytics.bbkId", "所属机构"),
      dataIndex: "bbk_id",
      key: "bbk_id",
      width: 100,
      render: (v) => getBbkDisplayName(v),
    },
    {
      title: t("analytics.sessionId", "Session ID"),
      dataIndex: "session_id",
      key: "session_id",
      width: 120,
      ellipsis: true,
    },
    {
      title: t("analytics.userMessage", "User Message"),
      dataIndex: "user_message",
      key: "user_message",
      width: 320,
      render: (msg) => {
        if (!msg) return <span style={{ color: "#999" }}>-</span>;
        const truncated = truncateMessage(msg, 120);
        if (msg.length <= 120) {
          return <span className={styles.userMessage}>{msg}</span>;
        }
        return (
          <Tooltip
            title={<pre className={styles.messagePopover}>{msg}</pre>}
            overlayStyle={{ maxWidth: 500 }}
          >
            <span className={styles.userMessage}>{truncated}</span>
          </Tooltip>
        );
      },
    },
    {
      title: t("analytics.model", "Model"),
      dataIndex: "model_name",
      key: "model_name",
      width: 150,
      ellipsis: true,
      render: (v) => v || "-",
    },
    {
      title: t("analytics.startTime", "Start Time"),
      dataIndex: "start_time",
      key: "start_time",
      width: 150,
      render: (v) => dayjs(v).format("YYYY-MM-DD HH:mm:ss"),
    },
    {
      title: t("analytics.duration", "Duration"),
      dataIndex: "duration_ms",
      key: "duration_ms",
      width: 80,
      render: (v) => formatDuration(v),
    },
  ];

  return (
    <div className={styles.messagesPage}>
      <PageHeader
        items={[
          { title: t("nav.insightCenter", "洞察中心") },
          { title: t("nav.analyticsMessages", "用户消息") },
        ]}
        extra={
          <div className={styles.headerActions}>
            <RangePicker
              value={dateRange}
              onChange={(dates) =>
                setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)
              }
              allowClear
            />
            <Button
              type="primary"
              icon={<BarChart3 size={16} />}
              onClick={openAnalysisModal}
            >
              高频问题分析
            </Button>
          </div>
        }
      />

      <div className={styles.content}>
        <div className={styles.toolbar}>
          <div className={styles.searchBox}>
            <Input
              placeholder={t("analytics.searchMessage", "Search messages...")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onPressEnter={handleSearch}
              allowClear
            />
          </div>
          <div className={styles.filters}>
            <Select
              placeholder={t("analytics.filterBbk")}
              value={bbkIdFilter}
              onChange={(v) => {
                setBbkIdFilter(v);
                setPage(1);
              }}
              allowClear
              showSearch
              optionFilterProp="label"
              style={{ width: 150 }}
              options={BBK_ID_MAP}
            />
            <Input
              placeholder={t("analytics.filterUser", "User ID")}
              value={userIdFilter}
              onChange={(e) => setUserIdFilter(e.target.value)}
              onPressEnter={handleSearch}
              style={{ width: 150 }}
              allowClear
            />
            <Input
              placeholder={t("analytics.filterSession", "Session ID")}
              value={sessionIdFilter}
              onChange={(e) => setSessionIdFilter(e.target.value)}
              onPressEnter={handleSearch}
              style={{ width: 200 }}
              allowClear
            />
            <Button type="primary" onClick={handleSearch}>
              {t("common.search", "Search")}
            </Button>
            <Button
              icon={<Download size={16} />}
              onClick={handleExport}
              loading={exporting}
              style={{ minWidth: 120 }}
            >
              {t("analytics.exportExcel", "Export Excel")}
            </Button>
          </div>
        </div>

        <Card>
          <Table
            dataSource={messages}
            columns={columns}
            rowKey="trace_id"
            loading={loading}
            scroll={{ x: 1200 }}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => t("analytics.totalItems", { total }),
              onChange: (p, ps) => {
                setPage(p);
                setPageSize(ps);
              },
            }}
          />
        </Card>
      </div>

      <Modal
        open={analysisOpen}
        title={
          <div className={styles.analysisTitle}>
            <span className={styles.analysisTitleIcon}>
              <BarChart3 size={22} />
            </span>
            <div className={styles.analysisTitleText}>
              <h2>高频问题分析</h2>
              <p>
                基于所选时间范围和机构的数据，分析用户咨询的高频问题及其分布情况
              </p>
            </div>
          </div>
        }
        width="80vw"
        centered
        destroyOnClose={false}
        onCancel={() => setAnalysisOpen(false)}
        className={styles.analysisModal}
        styles={{ body: { padding: 0 } }}
        footer={[
          <Button key="close" onClick={() => setAnalysisOpen(false)}>
            关闭
          </Button>,
          <Button
            key="query"
            icon={<RefreshCw size={16} />}
            onClick={() => void queryAnalysisResult()}
            loading={analysisLoading}
            disabled={analysisTaskStatus === "running"}
          >
            刷新
          </Button>,
          <Button
            key="generate"
            type="primary"
            onClick={submitAnalysisTask}
            loading={analysisSubmitting}
            disabled={analysisTaskStatus === "running"}
          >
            {analysisTaskStatus === "running"
              ? "生成中..."
              : analysisResult?.state === "AVAILABLE" ||
                analysisResult?.state === "AVAILABLE_STALE"
              ? "重新生成分析"
              : "生成分析"}
          </Button>,
        ]}
      >
        <div className={styles.analysisDialog}>
          <div className={styles.analysisFilters}>
            <label>
              <span>时间范围</span>
              <RangePicker
                value={analysisRange}
                onChange={(dates) =>
                  handleAnalysisRangeChange(
                    dates as null | [Dayjs | null, Dayjs | null],
                  )
                }
                allowClear={false}
              />
            </label>
            <label>
              <span>所属机构</span>
              <Select
                value={analysisBbkId}
                onChange={handleAnalysisBbkChange}
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder="全部机构（ALL）"
                className={styles.analysisBbkSelect}
                options={BBK_ID_MAP}
              />
            </label>
            <label>
              <span>快捷选择</span>
              <Segmented
                value={analysisQuickRange}
                onChange={handleAnalysisQuickRangeChange}
                options={[
                  { label: "最近 1 天", value: "1" },
                  { label: "最近 3 天", value: "3" },
                  { label: "最近 7 天", value: "7" },
                ]}
              />
            </label>
          </div>
          {analysisError && (
            <Alert
              className={styles.analysisAlert}
              type="error"
              showIcon
              message={analysisError}
            />
          )}
          <div className={styles.analysisBody}>{renderAnalysisContent()}</div>
        </div>
      </Modal>
    </div>
  );
}
