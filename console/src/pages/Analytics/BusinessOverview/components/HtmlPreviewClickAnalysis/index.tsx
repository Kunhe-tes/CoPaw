import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Database } from "lucide-react";
import { Modal, Pagination, Select, Spin, Switch, Tooltip } from "antd";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import { htmlPreviewEventsApi } from "../../../../../api/modules/htmlPreviewEvents";
import type {
  HtmlPreviewClickSummaryItem,
  HtmlPreviewCustomerClickItem,
  HtmlPreviewListSummaryItem,
} from "../../../../../api/types/htmlPreviewEvents";
import { formatNumber, formatPercent } from "../../types";
import styles from "./index.module.less";

const { Option } = Select;
const HTML_PREVIEW_LIST_PAGE_SIZE_OPTIONS = [20, 50, 100];

interface HtmlPreviewClickAnalysisProps {
  dateRange: [Dayjs, Dayjs];
  effectiveBbkIds?: string[];
  refreshKey?: number;
}

const safeNumber = (value: unknown): number =>
  typeof value === "number" && !Number.isNaN(value) ? value : 0;

const EMPTY_HTML_PREVIEW_LIST_SUMMARY: HtmlPreviewListSummaryItem = {
  list_key: "all",
  list_name: "全部名单",
  customer_count: 0,
  clicked_customer_count: 0,
  insight_count: 0,
  phone_count: 0,
  plan_count: 0,
  total_click_count: 0,
};

function buildHtmlPreviewListSummaryFallback(
  items: HtmlPreviewListSummaryItem[],
): HtmlPreviewListSummaryItem {
  return items.reduce<HtmlPreviewListSummaryItem>(
    (summary, item) => ({
      ...summary,
      customer_count: summary.customer_count + safeNumber(item.customer_count),
      clicked_customer_count:
        summary.clicked_customer_count +
        safeNumber(item.clicked_customer_count),
      insight_count: summary.insight_count + safeNumber(item.insight_count),
      phone_count: summary.phone_count + safeNumber(item.phone_count),
      plan_count: summary.plan_count + safeNumber(item.plan_count),
      total_click_count:
        summary.total_click_count + safeNumber(item.total_click_count),
      last_clicked_at:
        item.last_clicked_at &&
        (!summary.last_clicked_at ||
          item.last_clicked_at > summary.last_clicked_at)
          ? item.last_clicked_at
          : summary.last_clicked_at,
    }),
    { ...EMPTY_HTML_PREVIEW_LIST_SUMMARY },
  );
}

const formatManagerName = (name?: string | null, userId?: string | null) =>
  name || userId || "-";

const formatHtmlPreviewTime = (
  value?: string | null,
  format = "MM-DD HH:mm",
) => {
  if (!value) {
    return "-";
  }
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  return dayjs(hasTimezone ? normalized : `${normalized}Z`).format(format);
};

export default function HtmlPreviewClickAnalysis({
  dateRange,
  effectiveBbkIds,
  refreshKey,
}: HtmlPreviewClickAnalysisProps) {
  const htmlPreviewFilterKey = useMemo(
    () =>
      [
        dateRange[0].startOf("day").toISOString(),
        dateRange[1].endOf("day").toISOString(),
        effectiveBbkIds?.join(",") || "",
      ].join("|"),
    [dateRange, effectiveBbkIds],
  );
  const [htmlPreviewClicks, setHtmlPreviewClicks] = useState<
    HtmlPreviewClickSummaryItem[]
  >([]);
  const [htmlPreviewLists, setHtmlPreviewLists] = useState<
    HtmlPreviewListSummaryItem[]
  >([]);
  const [htmlPreviewListSummary, setHtmlPreviewListSummary] =
    useState<HtmlPreviewListSummaryItem>(EMPTY_HTML_PREVIEW_LIST_SUMMARY);
  const [htmlPreviewListTotal, setHtmlPreviewListTotal] = useState(0);
  const [htmlPreviewClickedListTotal, setHtmlPreviewClickedListTotal] =
    useState(0);
  const [htmlPreviewListPage, setHtmlPreviewListPage] = useState(1);
  const [htmlPreviewListPageSize, setHtmlPreviewListPageSize] = useState(20);
  const [htmlPreviewCustomerClicks, setHtmlPreviewCustomerClicks] = useState<
    HtmlPreviewCustomerClickItem[]
  >([]);
  const [selectedHtmlPreviewCustomer, setSelectedHtmlPreviewCustomer] =
    useState<HtmlPreviewCustomerClickItem | null>(null);
  const [selectedHtmlPreviewListKey, setSelectedHtmlPreviewListKey] =
    useState<string>("all");
  const [includeUnclickedCustomers, setIncludeUnclickedCustomers] =
    useState(false);
  const [isHtmlPreviewTopListCollapsed, setIsHtmlPreviewTopListCollapsed] =
    useState(false);
  const [htmlPreviewOverviewLoading, setHtmlPreviewOverviewLoading] =
    useState(false);
  const [htmlPreviewListLoading, setHtmlPreviewListLoading] = useState(false);
  const [appliedHtmlPreviewFilterKey, setAppliedHtmlPreviewFilterKey] =
    useState(htmlPreviewFilterKey);
  const htmlPreviewLoading =
    htmlPreviewOverviewLoading || htmlPreviewListLoading;
  const htmlPreviewOverviewRequestIdRef = useRef(0);
  const htmlPreviewListRequestIdRef = useRef(0);

  const fetchHtmlPreviewOverview = useCallback(async () => {
    const requestId = htmlPreviewOverviewRequestIdRef.current + 1;
    htmlPreviewOverviewRequestIdRef.current = requestId;
    setHtmlPreviewOverviewLoading(true);
    try {
      const params = {
        startTime: dateRange[0].startOf("day").toISOString(),
        endTime: dateRange[1].endOf("day").toISOString(),
        bbkIds: effectiveBbkIds?.join(","),
      };
      const selectedListKey =
        selectedHtmlPreviewListKey === "all"
          ? null
          : selectedHtmlPreviewListKey;
      const detailParams = {
        ...params,
        listKey: selectedListKey,
      };
      const [summaryResult, customerResult] = await Promise.allSettled([
        htmlPreviewEventsApi.getSummary({ ...detailParams, limit: 100 }),
        htmlPreviewEventsApi.getCustomerClicks({
          ...detailParams,
          includeUnclicked: includeUnclickedCustomers,
          limit: 500,
        }),
      ]);
      if (requestId !== htmlPreviewOverviewRequestIdRef.current) {
        return;
      }
      if (summaryResult.status === "fulfilled") {
        setHtmlPreviewClicks(summaryResult.value.items || []);
      } else {
        console.error(
          "Failed to fetch HTML preview click summary:",
          summaryResult.reason,
        );
        setHtmlPreviewClicks([]);
      }
      if (customerResult.status === "fulfilled") {
        setHtmlPreviewCustomerClicks(customerResult.value.items || []);
      } else {
        console.error(
          "Failed to fetch HTML preview customer clicks:",
          customerResult.reason,
        );
        setHtmlPreviewCustomerClicks([]);
      }
    } catch (error) {
      if (requestId !== htmlPreviewOverviewRequestIdRef.current) {
        return;
      }
      console.error("Failed to fetch HTML preview click statistics:", error);
      setHtmlPreviewClicks([]);
      setHtmlPreviewCustomerClicks([]);
    } finally {
      if (requestId === htmlPreviewOverviewRequestIdRef.current) {
        setHtmlPreviewOverviewLoading(false);
      }
    }
  }, [
    dateRange,
    effectiveBbkIds,
    includeUnclickedCustomers,
    selectedHtmlPreviewListKey,
  ]);

  const fetchHtmlPreviewLists = useCallback(async () => {
    const requestId = htmlPreviewListRequestIdRef.current + 1;
    htmlPreviewListRequestIdRef.current = requestId;
    setHtmlPreviewListLoading(true);
    try {
      const params = {
        startTime: dateRange[0].startOf("day").toISOString(),
        endTime: dateRange[1].endOf("day").toISOString(),
        bbkIds: effectiveBbkIds?.join(","),
      };
      const listResult = await htmlPreviewEventsApi.getLists({
        ...params,
        page: htmlPreviewListPage,
        pageSize: htmlPreviewListPageSize,
      });
      if (requestId !== htmlPreviewListRequestIdRef.current) {
        return;
      }
      const listItems = listResult.items || [];
      setHtmlPreviewLists(listItems);
      setHtmlPreviewListTotal(listResult.total ?? listItems.length);
      setHtmlPreviewClickedListTotal(
        listResult.clicked_list_count ??
          listItems.filter((item) => safeNumber(item.total_click_count) > 0)
            .length,
      );
      setHtmlPreviewListSummary(
        listResult.summary || buildHtmlPreviewListSummaryFallback(listItems),
      );
    } catch (error) {
      if (requestId !== htmlPreviewListRequestIdRef.current) {
        return;
      }
      console.error("Failed to fetch HTML preview list summary:", error);
      setHtmlPreviewLists([]);
      setHtmlPreviewListTotal(0);
      setHtmlPreviewClickedListTotal(0);
      setHtmlPreviewListSummary(EMPTY_HTML_PREVIEW_LIST_SUMMARY);
    } finally {
      if (requestId === htmlPreviewListRequestIdRef.current) {
        setHtmlPreviewListLoading(false);
      }
    }
  }, [
    dateRange,
    effectiveBbkIds,
    htmlPreviewListPage,
    htmlPreviewListPageSize,
  ]);

  useEffect(() => {
    if (appliedHtmlPreviewFilterKey === htmlPreviewFilterKey) {
      return;
    }
    htmlPreviewOverviewRequestIdRef.current += 1;
    htmlPreviewListRequestIdRef.current += 1;
    setHtmlPreviewOverviewLoading(false);
    setHtmlPreviewListLoading(false);
    setHtmlPreviewListPage(1);
    setSelectedHtmlPreviewListKey("all");
    setAppliedHtmlPreviewFilterKey(htmlPreviewFilterKey);
  }, [appliedHtmlPreviewFilterKey, htmlPreviewFilterKey]);

  useEffect(() => {
    if (appliedHtmlPreviewFilterKey !== htmlPreviewFilterKey) {
      return;
    }
    fetchHtmlPreviewOverview();
  }, [
    appliedHtmlPreviewFilterKey,
    fetchHtmlPreviewOverview,
    htmlPreviewFilterKey,
    refreshKey,
  ]);

  useEffect(() => {
    if (appliedHtmlPreviewFilterKey !== htmlPreviewFilterKey) {
      return;
    }
    fetchHtmlPreviewLists();
  }, [
    appliedHtmlPreviewFilterKey,
    fetchHtmlPreviewLists,
    htmlPreviewFilterKey,
    refreshKey,
  ]);

  useEffect(() => {
    const maxPage = Math.max(
      1,
      Math.ceil(htmlPreviewListTotal / htmlPreviewListPageSize),
    );
    if (htmlPreviewListPage > maxPage) {
      setHtmlPreviewListPage(maxPage);
    }
  }, [htmlPreviewListPage, htmlPreviewListPageSize, htmlPreviewListTotal]);

  useEffect(() => {
    if (
      selectedHtmlPreviewListKey !== "all" &&
      !htmlPreviewLists.some(
        (item) => item.list_key === selectedHtmlPreviewListKey,
      )
    ) {
      setSelectedHtmlPreviewListKey("all");
    }
  }, [htmlPreviewLists, selectedHtmlPreviewListKey]);

  const selectedHtmlPreviewList = useMemo(
    () =>
      htmlPreviewLists.find(
        (item) => item.list_key === selectedHtmlPreviewListKey,
      ) || null,
    [htmlPreviewLists, selectedHtmlPreviewListKey],
  );
  const displayedHtmlPreviewLists = useMemo(
    () =>
      selectedHtmlPreviewListKey === "all"
        ? htmlPreviewLists
        : htmlPreviewLists.filter(
            (item) => item.list_key === selectedHtmlPreviewListKey,
          ),
    [htmlPreviewLists, selectedHtmlPreviewListKey],
  );
  const htmlPreviewMetricSource =
    selectedHtmlPreviewListKey === "all"
      ? htmlPreviewListSummary
      : selectedHtmlPreviewList || EMPTY_HTML_PREVIEW_LIST_SUMMARY;
  const htmlPreviewListCount =
    selectedHtmlPreviewListKey === "all"
      ? htmlPreviewListTotal
      : selectedHtmlPreviewList
      ? 1
      : 0;
  const htmlPreviewClickedListCount =
    selectedHtmlPreviewListKey === "all"
      ? htmlPreviewClickedListTotal
      : safeNumber(selectedHtmlPreviewList?.total_click_count) > 0
      ? 1
      : 0;
  const htmlPreviewListClickRate =
    htmlPreviewListCount > 0
      ? (htmlPreviewClickedListCount / htmlPreviewListCount) * 100
      : 0;
  const htmlPreviewInsightClicks = safeNumber(
    htmlPreviewMetricSource.insight_count,
  );
  const htmlPreviewPhoneClicks = safeNumber(
    htmlPreviewMetricSource.phone_count,
  );
  const htmlPreviewPlanClicks = safeNumber(htmlPreviewMetricSource.plan_count);
  const htmlPreviewTotalClicks = safeNumber(
    htmlPreviewMetricSource.total_click_count,
  );
  const htmlPreviewMaxActionClicks = Math.max(
    htmlPreviewInsightClicks,
    htmlPreviewPhoneClicks,
    htmlPreviewPlanClicks,
    1,
  );
  const htmlPreviewActionTotal =
    htmlPreviewInsightClicks + htmlPreviewPhoneClicks + htmlPreviewPlanClicks;
  const htmlPreviewInsightPercent =
    htmlPreviewActionTotal > 0
      ? Math.round((htmlPreviewInsightClicks / htmlPreviewActionTotal) * 100)
      : 0;
  const htmlPreviewPhonePercent =
    htmlPreviewActionTotal > 0
      ? Math.round((htmlPreviewPhoneClicks / htmlPreviewActionTotal) * 100)
      : 0;
  const htmlPreviewPlanPercent =
    htmlPreviewActionTotal > 0
      ? Math.round((htmlPreviewPlanClicks / htmlPreviewActionTotal) * 100)
      : 0;
  const htmlPreviewCustomerTotal = safeNumber(
    htmlPreviewMetricSource.customer_count,
  );
  const htmlPreviewClickedCustomerCount = safeNumber(
    htmlPreviewMetricSource.clicked_customer_count,
  );
  const htmlPreviewCustomerCoverageRate =
    htmlPreviewCustomerTotal > 0
      ? (htmlPreviewClickedCustomerCount / htmlPreviewCustomerTotal) * 100
      : 0;
  const htmlPreviewLatestClick = useMemo(() => {
    const sortedClickTimes = htmlPreviewClicks
      .map((item) => item.last_clicked_at)
      .filter(Boolean)
      .sort();
    const latest = sortedClickTimes[sortedClickTimes.length - 1];
    return formatHtmlPreviewTime(latest, "YYYY-MM-DD HH:mm");
  }, [htmlPreviewClicks]);
  const hasHtmlPreviewAnalysisData =
    htmlPreviewClicks.length > 0 ||
    htmlPreviewLists.length > 0 ||
    htmlPreviewListTotal > 0 ||
    htmlPreviewCustomerClicks.length > 0;

  return (
    <>
      <section
        className={styles.htmlPreviewSection}
        data-testid="html-preview-click-section"
      >
        <article className={styles.panelLarge}>
          <div className={styles.panelHeader}>
            <h3 className={styles.panelTitle}>客户经营点击分析</h3>
            <span className={styles.panelMeta}>
              最近点击：{htmlPreviewLatestClick}
            </span>
          </div>
          <div className={styles.htmlPreviewFilters}>
            <Select
              className={styles.htmlPreviewListSelect}
              value={selectedHtmlPreviewListKey}
              onChange={setSelectedHtmlPreviewListKey}
              placeholder="全部名单"
              showSearch
              optionFilterProp="label"
              disabled={htmlPreviewLoading}
            >
              <Option value="all" label="全部名单">
                全部名单
              </Option>
              {htmlPreviewLists.map((item) => (
                <Option
                  key={item.list_key}
                  value={item.list_key}
                  label={item.list_name}
                >
                  {item.list_name}
                </Option>
              ))}
            </Select>
            <label className={styles.htmlPreviewSwitch}>
              <Switch
                size="small"
                checked={includeUnclickedCustomers}
                onChange={setIncludeUnclickedCustomers}
                disabled={htmlPreviewLoading}
              />
              <span>显示未点击客户</span>
            </label>
          </div>
          {!hasHtmlPreviewAnalysisData ? (
            <div className={styles.emptyChartState}>
              <Database className={styles.emptyBreakdownIcon} />
              <span>
                {htmlPreviewLoading ? "加载中..." : "暂无客户经营点击数据"}
              </span>
            </div>
          ) : (
            <Spin spinning={htmlPreviewLoading} tip="加载中...">
              <div className={styles.htmlPreviewDashboard}>
                <div className={styles.htmlPreviewStats}>
                  <div className={styles.htmlPreviewStatCard}>
                    <span>名单数</span>
                    <strong>{formatNumber(htmlPreviewListCount)}</strong>
                  </div>
                  <div className={styles.htmlPreviewStatCard}>
                    <span>被点击名单数</span>
                    <strong>{formatNumber(htmlPreviewClickedListCount)}</strong>
                  </div>
                  <div className={styles.htmlPreviewStatCard}>
                    <span>名单点击率</span>
                    <strong>{formatPercent(htmlPreviewListClickRate)}</strong>
                  </div>
                  <div className={styles.htmlPreviewStatCard}>
                    <span>名单总客户数</span>
                    <strong>{formatNumber(htmlPreviewCustomerTotal)}</strong>
                  </div>
                  <div className={styles.htmlPreviewStatCard}>
                    <span>被点击客户数</span>
                    <strong>
                      {formatNumber(htmlPreviewClickedCustomerCount)}
                    </strong>
                  </div>
                  <div className={styles.htmlPreviewStatCard}>
                    <span>客户点击覆盖率</span>
                    <strong>
                      {formatPercent(htmlPreviewCustomerCoverageRate)}
                    </strong>
                  </div>
                  <div className={styles.htmlPreviewStatCard}>
                    <span>点击总数</span>
                    <strong>{formatNumber(htmlPreviewTotalClicks)}</strong>
                  </div>
                </div>
                <div className={styles.htmlPreviewDistribution}>
                  <div className={styles.htmlPreviewTopTitle}>点击分布</div>
                  <div className={styles.htmlPreviewDistributionRows}>
                    <div className={styles.htmlPreviewDistributionRow}>
                      <div className={styles.htmlPreviewDistributionMeta}>
                        <span>洞察</span>
                        <strong>
                          {formatNumber(htmlPreviewInsightClicks)}
                          <em>{htmlPreviewInsightPercent}%</em>
                        </strong>
                      </div>
                      <div className={styles.htmlPreviewDistributionTrack}>
                        <i
                          className={styles.htmlPreviewInsightBar}
                          style={{
                            width: `${Math.max(
                              6,
                              (htmlPreviewInsightClicks /
                                htmlPreviewMaxActionClicks) *
                                100,
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                    <div className={styles.htmlPreviewDistributionRow}>
                      <div className={styles.htmlPreviewDistributionMeta}>
                        <span>电访</span>
                        <strong>
                          {formatNumber(htmlPreviewPhoneClicks)}
                          <em>{htmlPreviewPhonePercent}%</em>
                        </strong>
                      </div>
                      <div className={styles.htmlPreviewDistributionTrack}>
                        <i
                          className={styles.htmlPreviewPhoneBar}
                          style={{
                            width: `${Math.max(
                              6,
                              (htmlPreviewPhoneClicks /
                                htmlPreviewMaxActionClicks) *
                                100,
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                    <div className={styles.htmlPreviewDistributionRow}>
                      <div className={styles.htmlPreviewDistributionMeta}>
                        <span>查看方案</span>
                        <strong>
                          {formatNumber(htmlPreviewPlanClicks)}
                          <em>{htmlPreviewPlanPercent}%</em>
                        </strong>
                      </div>
                      <div className={styles.htmlPreviewDistributionTrack}>
                        <i
                          className={styles.htmlPreviewPlanBar}
                          style={{
                            width: `${Math.max(
                              6,
                              (htmlPreviewPlanClicks /
                                htmlPreviewMaxActionClicks) *
                                100,
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
                {!isHtmlPreviewTopListCollapsed && (
                  <div className={styles.htmlPreviewTopList}>
                    <div className={styles.htmlPreviewBlockTitleRow}>
                      <div className={styles.htmlPreviewTopTitle}>
                        名单点击概览
                      </div>
                      <Tooltip title="收起名单点击概览" placement="top">
                        <button
                          type="button"
                          className={styles.htmlPreviewCollapseButton}
                          aria-label="收起名单点击概览"
                          onClick={() => setIsHtmlPreviewTopListCollapsed(true)}
                        >
                          <ChevronLeft />
                        </button>
                      </Tooltip>
                    </div>
                    {displayedHtmlPreviewLists.map((item) => (
                      <div
                        key={item.list_key}
                        className={styles.htmlPreviewListRow}
                      >
                        <Tooltip
                          title={
                            item.file_name || item.file_url || item.list_name
                          }
                          placement="top"
                        >
                          <span className={styles.htmlPreviewTopName}>
                            {item.list_name}
                          </span>
                        </Tooltip>
                        <div className={styles.htmlPreviewListMetrics}>
                          <span>
                            <em>名单客户</em>
                            <strong>{formatNumber(item.customer_count)}</strong>
                          </span>
                          <span>
                            <em>点击客户</em>
                            <strong>
                              {formatNumber(item.clicked_customer_count)}
                            </strong>
                          </span>
                          <span>
                            <em>洞察</em>
                            <strong>{formatNumber(item.insight_count)}</strong>
                          </span>
                          <span>
                            <em>电访</em>
                            <strong>{formatNumber(item.phone_count)}</strong>
                          </span>
                          <span>
                            <em>查看方案</em>
                            <strong>{formatNumber(item.plan_count)}</strong>
                          </span>
                        </div>
                      </div>
                    ))}
                    {displayedHtmlPreviewLists.length === 0 && (
                      <div className={styles.htmlPreviewEmptyLine}>
                        暂无名单点击概览数据
                      </div>
                    )}
                    {selectedHtmlPreviewListKey === "all" &&
                      htmlPreviewListTotal > 0 && (
                        <div className={styles.htmlPreviewPagination}>
                          <Pagination
                            size="small"
                            current={htmlPreviewListPage}
                            pageSize={htmlPreviewListPageSize}
                            total={htmlPreviewListTotal}
                            pageSizeOptions={HTML_PREVIEW_LIST_PAGE_SIZE_OPTIONS.map(
                              String,
                            )}
                            showSizeChanger
                            showLessItems
                            disabled={htmlPreviewLoading}
                            onChange={(page, pageSize) => {
                              setHtmlPreviewListPage(page);
                              setHtmlPreviewListPageSize(pageSize);
                            }}
                          />
                        </div>
                      )}
                  </div>
                )}
                <div
                  className={`${styles.htmlPreviewEventList} ${
                    isHtmlPreviewTopListCollapsed
                      ? styles.htmlPreviewEventListFull
                      : ""
                  }`}
                >
                  <div className={styles.htmlPreviewBlockTitleRow}>
                    <div className={styles.htmlPreviewTopTitle}>
                      客户点击明细
                    </div>
                    {isHtmlPreviewTopListCollapsed && (
                      <Tooltip title="展开名单点击概览" placement="top">
                        <button
                          type="button"
                          className={styles.htmlPreviewCollapseButton}
                          aria-label="展开名单点击概览"
                          onClick={() =>
                            setIsHtmlPreviewTopListCollapsed(false)
                          }
                        >
                          <ChevronRight />
                        </button>
                      </Tooltip>
                    )}
                  </div>
                  {selectedHtmlPreviewList && (
                    <div className={styles.htmlPreviewSelectedList}>
                      当前名单：{selectedHtmlPreviewList.list_name}
                    </div>
                  )}
                  {htmlPreviewCustomerClicks.length === 0 ? (
                    <div className={styles.htmlPreviewEmptyLine}>
                      暂无客户点击明细
                    </div>
                  ) : (
                    <div className={styles.htmlPreviewCustomerTable}>
                      <div className={styles.htmlPreviewCustomerHeader}>
                        <span>客户</span>
                        <span>洞察</span>
                        <span>电访</span>
                        <span>查看方案</span>
                        <span>总点击</span>
                        <span>客户经理</span>
                        <span>最近</span>
                      </div>
                      {htmlPreviewCustomerClicks.map((item) => (
                        <div
                          key={`${item.customer_id || item.customer_name}-${
                            item.last_clicked_at || ""
                          }`}
                          className={styles.htmlPreviewCustomerRow}
                        >
                          <div className={styles.htmlPreviewCustomerCell}>
                            <span className={styles.htmlPreviewCustomerName}>
                              {item.customer_name || "未知客户"}
                            </span>
                            {item.customer_id && (
                              <span className={styles.htmlPreviewCustomerId}>
                                {item.customer_id}
                              </span>
                            )}
                          </div>
                          <strong>{formatNumber(item.insight_count)}</strong>
                          <strong>{formatNumber(item.phone_count)}</strong>
                          <strong>{formatNumber(item.plan_count)}</strong>
                          <strong>
                            {formatNumber(item.total_click_count)}
                          </strong>
                          <div className={styles.htmlPreviewManagerCell}>
                            <span>
                              {formatManagerName(
                                item.last_clicked_user_name,
                                item.last_clicked_user_id,
                              )}
                            </span>
                            {item.manager_clicks?.length ? (
                              <button
                                type="button"
                                disabled={htmlPreviewLoading}
                                onClick={() =>
                                  setSelectedHtmlPreviewCustomer(item)
                                }
                              >
                                详情
                              </button>
                            ) : null}
                          </div>
                          <span className={styles.htmlPreviewEventTime}>
                            {formatHtmlPreviewTime(item.last_clicked_at)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </Spin>
          )}
        </article>
      </section>

      <Modal
        open={Boolean(selectedHtmlPreviewCustomer)}
        title={
          selectedHtmlPreviewCustomer
            ? `${selectedHtmlPreviewCustomer.customer_name} 客户经理点击详情`
            : "客户经理点击详情"
        }
        footer={null}
        width={640}
        onCancel={() => setSelectedHtmlPreviewCustomer(null)}
      >
        <div className={styles.htmlPreviewManagerDetail}>
          <div className={styles.htmlPreviewManagerDetailHeader}>
            <span>客户经理</span>
            <span>洞察</span>
            <span>电访</span>
            <span>查看方案</span>
            <span>总点击</span>
            <span>最近</span>
          </div>
          {selectedHtmlPreviewCustomer?.manager_clicks?.map((item) => (
            <div
              key={`${item.user_id}-${item.last_clicked_at || ""}`}
              className={styles.htmlPreviewManagerDetailRow}
            >
              <span>{formatManagerName(item.user_name, item.user_id)}</span>
              <strong>{formatNumber(item.insight_count)}</strong>
              <strong>{formatNumber(item.phone_count)}</strong>
              <strong>{formatNumber(item.plan_count)}</strong>
              <strong>{formatNumber(item.total_click_count)}</strong>
              <span>{formatHtmlPreviewTime(item.last_clicked_at)}</span>
            </div>
          ))}
        </div>
      </Modal>
    </>
  );
}
