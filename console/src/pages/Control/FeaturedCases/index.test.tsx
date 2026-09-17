import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FeaturedCase } from "@/api/types/featuredCases";
import FeaturedCasesPage from "./index";

const mocks = vi.hoisted(() => ({
  bbk: "branch-a" as string | null,
  cases: [] as FeaturedCase[],
  total: 0,
  loadCases: vi.fn(),
  createCase: vi.fn(),
  updateCase: vi.fn(),
  deleteCase: vi.fn(),
  reorderCase: vi.fn(),
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock("@/stores/iframeStore", () => ({
  useIframeStore: (selector: (state: { bbk: string | null }) => unknown) =>
    selector({ bbk: mocks.bbk }),
}));

vi.mock("@/hooks/useAppMessage", () => ({
  useAppMessage: () => ({ message: mocks.message }),
}));

vi.mock("./components/CaseDrawer", () => ({
  CaseDrawer: () => null,
}));

vi.mock("./components/hooks", () => ({
  useFeaturedCases: () => ({
    cases: mocks.cases,
    loading: false,
    total: mocks.total,
    loadCases: mocks.loadCases,
    createCase: mocks.createCase,
    updateCase: mocks.updateCase,
    deleteCase: mocks.deleteCase,
    reorderCase: mocks.reorderCase,
  }),
}));

const branchCase: FeaturedCase = {
  id: 7,
  source_id: "source-1",
  bbk_id: "branch-a",
  label: "跨境汇款",
  value: "如何办理跨境汇款？",
  sort_order: 4,
  is_active: true,
};

describe("FeaturedCasesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.bbk = "branch-a";
    mocks.cases = [branchCase];
    mocks.total = 40;
    mocks.loadCases.mockResolvedValue({
      cases: mocks.cases,
      total: mocks.total,
    });
    mocks.reorderCase.mockResolvedValue({
      case_id: branchCase.id,
      sort_order: 2,
      total: mocks.total,
    });
  });

  afterEach(cleanup);

  it("queries branch and head-office management queues separately", async () => {
    const { container } = render(<FeaturedCasesPage />);

    await waitFor(() =>
      expect(mocks.loadCases).toHaveBeenCalledWith({
        bbk_id: "branch-a",
        page: 1,
        page_size: 20,
      }),
    );
    expect(
      screen.getByRole("navigation", { name: "面包屑" }),
    ).toHaveTextContent("精选案例管理");
    expect(
      screen.getByRole("heading", { name: "精选案例管理", level: 1 }),
    ).toBeInTheDocument();
    expect(container.querySelector(".anticon-star")).toBeInTheDocument();
    expect(container.querySelector(".anticon-plus")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "新建案例" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("2"));
    await waitFor(() =>
      expect(mocks.loadCases).toHaveBeenCalledWith({
        bbk_id: "branch-a",
        page: 2,
        page_size: 20,
      }),
    );

    fireEvent.click(screen.getByRole("tab", { name: "总行案例" }));

    await waitFor(() =>
      expect(mocks.loadCases).toHaveBeenCalledWith({
        bbk_id: "100",
        page: 1,
        page_size: 20,
      }),
    );
    expect(
      screen.getByText("总行案例仅供查看，如需调整请切换至总行管理上下文。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "新建案例" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("仅查看")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "本机构案例" }));
    await waitFor(() =>
      expect(mocks.loadCases).toHaveBeenLastCalledWith({
        bbk_id: "branch-a",
        page: 2,
        page_size: 20,
      }),
    );
  }, 15_000);

  it("keeps head-office management writable without redundant scope tabs", async () => {
    mocks.bbk = "100";
    render(<FeaturedCasesPage />);

    await waitFor(() =>
      expect(mocks.loadCases).toHaveBeenCalledWith({
        bbk_id: "100",
        page: 1,
        page_size: 20,
      }),
    );
    expect(
      screen.queryByRole("tab", { name: "本机构案例" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "总行案例" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "新建案例" }),
    ).toBeInTheDocument();
  });

  it("moves to the server-confirmed destination page after reordering", async () => {
    mocks.reorderCase.mockResolvedValue({
      case_id: branchCase.id,
      sort_order: 21,
      total: 40,
    });
    render(<FeaturedCasesPage />);
    await waitFor(() => expect(mocks.loadCases).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole("button", { name: "编辑“跨境汇款”的排序" }),
    );
    const input = screen.getByRole("spinbutton", {
      name: "“跨境汇款”的排序值",
    });
    fireEvent.change(input, { target: { value: "30" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(mocks.reorderCase).toHaveBeenCalledWith(7, 30));
    await waitFor(() =>
      expect(mocks.loadCases).toHaveBeenCalledWith({
        bbk_id: "branch-a",
        page: 2,
        page_size: 20,
      }),
    );
    expect(mocks.reorderCase).toHaveBeenCalledTimes(1);
    expect(mocks.message.success).toHaveBeenCalledWith("排序已调整为 21");
    await waitFor(() =>
      expect(screen.getByText("跨境汇款").closest("tr")?.className).toContain(
        "highlightedRow",
      ),
    );
  });

  it("keeps the attempted order visible when the post-save reload fails", async () => {
    render(<FeaturedCasesPage />);
    await waitFor(() => expect(mocks.loadCases).toHaveBeenCalledTimes(1));
    mocks.loadCases.mockRejectedValueOnce(new Error("reload failed"));

    fireEvent.click(
      screen.getByRole("button", { name: "编辑“跨境汇款”的排序" }),
    );
    const input = screen.getByRole("spinbutton", {
      name: "“跨境汇款”的排序值",
    });
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(
      await screen.findByText(
        "排序已保存，但列表刷新失败，请重试或按 Esc 取消",
      ),
    ).toBeInTheDocument();
    expect(input).toHaveValue("2");
    expect(mocks.message.warning).toHaveBeenCalledWith(
      "排序已保存，但列表刷新失败，请重试",
    );
    expect(mocks.message.error).not.toHaveBeenCalledWith(
      "排序保存失败，请重试",
    );
    expect(mocks.message.success).not.toHaveBeenCalled();
  });
});
