import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Modal, Table, Tabs } from "antd";
import { PlusOutlined, RightOutlined, StarOutlined } from "@ant-design/icons";
import { Form } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import { useAppMessage } from "@/hooks/useAppMessage";
import { useIframeStore } from "@/stores/iframeStore";
import { useFeaturedCases } from "./components/hooks";
import { createCaseColumns, ReorderRefreshError } from "./components/columns";
import { CaseDrawer } from "./components/CaseDrawer";
import type { FeaturedCase } from "@/api/types/featuredCases";
import styles from "./index.module.less";

const HEAD_OFFICE_BBK_ID = "100";
const DEFAULT_PAGE_SIZE = 20;

interface PaginationState {
  current: number;
  pageSize: number;
}

function normalizeScopeBbkId(bbkId: string | null | undefined): string {
  const normalized = bbkId?.trim();
  return normalized && normalized !== HEAD_OFFICE_BBK_ID
    ? normalized
    : HEAD_OFFICE_BBK_ID;
}

function FeaturedCasesPage() {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const contextBbkId = useIframeStore((state) => state.bbk);
  const writableScopeBbkId = normalizeScopeBbkId(contextBbkId);
  const isHeadOffice = writableScopeBbkId === HEAD_OFFICE_BBK_ID;
  const [activeScopeBbkId, setActiveScopeBbkId] = useState(writableScopeBbkId);
  const [paginationByScope, setPaginationByScope] = useState<
    Record<string, PaginationState>
  >({
    [writableScopeBbkId]: { current: 1, pageSize: DEFAULT_PAGE_SIZE },
    [HEAD_OFFICE_BBK_ID]: { current: 1, pageSize: DEFAULT_PAGE_SIZE },
  });
  const pagination = paginationByScope[activeScopeBbkId] ?? {
    current: 1,
    pageSize: DEFAULT_PAGE_SIZE,
  };
  const readOnly = !isHeadOffice && activeScopeBbkId === HEAD_OFFICE_BBK_ID;

  const {
    cases,
    loading,
    total,
    loadCases,
    createCase,
    updateCase,
    deleteCase,
    reorderCase,
  } = useFeaturedCases(activeScopeBbkId);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingCase, setEditingCase] = useState<FeaturedCase | null>(null);
  const [saving, setSaving] = useState(false);
  const [editingSortId, setEditingSortId] = useState<number | null>(null);
  const [sortingId, setSortingId] = useState<number | null>(null);
  const [highlightedCaseId, setHighlightedCaseId] = useState<number | null>(
    null,
  );
  const highlightTimerRef = useRef<number | null>(null);
  const [form] = Form.useForm<FeaturedCase>();

  const updatePagination = (
    scopeBbkId: string,
    next: Partial<PaginationState>,
  ) => {
    setPaginationByScope((current) => ({
      ...current,
      [scopeBbkId]: {
        current: current[scopeBbkId]?.current ?? 1,
        pageSize: current[scopeBbkId]?.pageSize ?? DEFAULT_PAGE_SIZE,
        ...next,
      },
    }));
  };

  const fetchScopePage = async (
    scopeBbkId: string,
    pageState: PaginationState,
    reportError = true,
  ) => {
    try {
      return await loadCases({
        bbk_id: scopeBbkId,
        page: pageState.current,
        page_size: pageState.pageSize,
      });
    } catch {
      if (reportError) {
        message.error("精选案例加载失败，请重试");
      }
      return undefined;
    }
  };

  useEffect(() => {
    setActiveScopeBbkId(writableScopeBbkId);
    setEditingSortId(null);
  }, [writableScopeBbkId]);

  useEffect(() => {
    void fetchScopePage(activeScopeBbkId, pagination);
    // Pagination fields are explicit dependencies; fetchScopePage is scoped
    // to the current render and must not turn tab changes into duplicate calls.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeScopeBbkId, pagination.current, pagination.pageSize]);

  useEffect(
    () => () => {
      if (highlightTimerRef.current !== null) {
        window.clearTimeout(highlightTimerRef.current);
      }
    },
    [],
  );

  const handleCreate = () => {
    setEditingCase(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = (caseItem: FeaturedCase) => {
    setEditingCase(caseItem);
    form.setFieldsValue(caseItem);
    setDrawerOpen(true);
  };

  const handleDelete = (id: number) => {
    const targetCase = cases.find((caseItem) => caseItem.id === id);
    Modal.confirm({
      title: "确认删除",
      content: `确定要删除“${targetCase?.label || "该案例"}”吗？`,
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        try {
          await deleteCase(id);
          const remainingTotal = Math.max(0, total - 1);
          const maxPage = Math.max(
            1,
            Math.ceil(remainingTotal / pagination.pageSize),
          );
          const nextPage = Math.min(pagination.current, maxPage);
          updatePagination(activeScopeBbkId, { current: nextPage });
          await fetchScopePage(activeScopeBbkId, {
            ...pagination,
            current: nextPage,
          });
          message.success("案例已删除，排序已更新");
        } catch {
          message.error("案例删除失败，请重试");
          throw new Error("Failed to delete featured case");
        }
      },
    });
  };

  const handleClose = () => {
    setDrawerOpen(false);
    setEditingCase(null);
  };

  const handleSubmit = async (values: FeaturedCase) => {
    setSaving(true);
    try {
      if (editingCase) {
        await updateCase(editingCase.id, values);
      } else {
        await createCase(values);
      }
      setDrawerOpen(false);
      await fetchScopePage(activeScopeBbkId, pagination);
      message.success(editingCase ? "案例已更新" : "案例已创建");
    } catch {
      message.error(editingCase ? "案例更新失败" : "案例创建失败");
    } finally {
      setSaving(false);
    }
  };

  const handleReorder = async (caseItem: FeaturedCase, sortOrder: number) => {
    setSortingId(caseItem.id);
    try {
      const result = await reorderCase(caseItem.id, sortOrder).catch(
        (error) => {
          message.error("排序保存失败，请重试");
          throw error;
        },
      );
      const destinationPage = Math.max(
        1,
        Math.ceil(result.sort_order / pagination.pageSize),
      );
      const refreshed = await fetchScopePage(
        activeScopeBbkId,
        {
          ...pagination,
          current: destinationPage,
        },
        false,
      );
      if (!refreshed) {
        const refreshError = new ReorderRefreshError(
          "排序已保存，但列表刷新失败，请重试或按 Esc 取消",
        );
        message.warning("排序已保存，但列表刷新失败，请重试");
        throw refreshError;
      }
      updatePagination(activeScopeBbkId, { current: destinationPage });
      setHighlightedCaseId(caseItem.id);
      if (highlightTimerRef.current !== null) {
        window.clearTimeout(highlightTimerRef.current);
      }
      highlightTimerRef.current = window.setTimeout(
        () => setHighlightedCaseId(null),
        1800,
      );
      message.success(`排序已调整为 ${result.sort_order}`);
    } finally {
      setSortingId(null);
    }
  };

  const columns = useMemo(
    () =>
      createCaseColumns({
        writable: !readOnly,
        editingSortId,
        sortingId,
        onStartSort: (caseItem) => setEditingSortId(caseItem.id),
        onFinishSort: () => setEditingSortId(null),
        onReorder: handleReorder,
        onEdit: handleEdit,
        onDelete: handleDelete,
      }),
    // Event handlers intentionally close over the current exact scope and page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cases, editingSortId, readOnly, sortingId, pagination, activeScopeBbkId],
  );

  const scopeTabs = isHeadOffice
    ? []
    : [
        { key: writableScopeBbkId, label: "本机构案例" },
        { key: HEAD_OFFICE_BBK_ID, label: "总行案例" },
      ];

  return (
    <div className={`${styles.featuredCasesPage} console-management-theme`}>
      <header className={styles.pageHeading}>
        <div className={styles.pageHeadingIcon} aria-hidden="true">
          <StarOutlined />
        </div>
        <nav className={styles.breadcrumbTrail} aria-label="面包屑">
          <span className={styles.pageEyebrow}>{t("nav.systemSettings")}</span>
          <RightOutlined className={styles.breadcrumbChevron} />
          <span className={styles.breadcrumbCurrent} aria-current="page">
            {t("nav.featuredCasesManagement", "精选案例管理")}
          </span>
        </nav>
        <h1 className={styles.visuallyHiddenHeading}>
          {t("nav.featuredCasesManagement", "精选案例管理")}
        </h1>
        {!readOnly && (
          <Button
            aria-label="新建案例"
            className={styles.createButton}
            icon={<PlusOutlined />}
            type="primary"
            onClick={handleCreate}
          >
            新建案例
          </Button>
        )}
      </header>

      <main className={styles.content}>
        {scopeTabs.length > 0 && (
          <Tabs
            activeKey={activeScopeBbkId}
            className={styles.scopeTabs}
            items={scopeTabs}
            onChange={(scopeBbkId) => {
              setEditingSortId(null);
              setActiveScopeBbkId(scopeBbkId);
            }}
          />
        )}

        {readOnly && (
          <Alert
            className={styles.readOnlyAlert}
            message="总行案例仅供查看，如需调整请切换至总行管理上下文。"
            showIcon
            type="info"
          />
        )}

        <section className={styles.tablePanel} aria-label="精选案例列表">
          <Table
            columns={columns}
            dataSource={cases}
            loading={loading}
            rowClassName={(caseItem) =>
              caseItem.id === highlightedCaseId ? styles.highlightedRow : ""
            }
            rowKey="id"
            pagination={{
              current: pagination.current,
              pageSize: pagination.pageSize,
              total,
              showSizeChanger: true,
              showTotal: (count) => `共 ${count} 条`,
            }}
            scroll={{ x: 720 }}
            size="middle"
            onChange={(nextPagination) => {
              updatePagination(activeScopeBbkId, {
                current: nextPagination.current || 1,
                pageSize: nextPagination.pageSize || DEFAULT_PAGE_SIZE,
              });
            }}
          />
        </section>
      </main>

      <CaseDrawer
        bbkId={activeScopeBbkId}
        open={drawerOpen}
        editingCase={editingCase}
        form={form}
        saving={saving}
        onClose={handleClose}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

export default FeaturedCasesPage;
