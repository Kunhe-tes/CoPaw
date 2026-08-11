import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { Table } from "antd";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FeaturedCase } from "@/api/types/featuredCases";
import { createCaseColumns } from "./columns";

const caseItem: FeaturedCase = {
  id: 7,
  source_id: "source-1",
  bbk_id: "branch-a",
  label: "跨境汇款",
  value: "如何办理跨境汇款？",
  sort_order: 4,
  is_active: true,
};

function renderColumns({
  onReorder = vi.fn().mockResolvedValue(undefined),
  writable = true,
  editing = writable,
}: {
  onReorder?: (item: FeaturedCase, sortOrder: number) => Promise<void>;
  writable?: boolean;
  editing?: boolean;
} = {}) {
  const onStartSort = vi.fn();
  const onFinishSort = vi.fn();
  const onEdit = vi.fn();
  const onDelete = vi.fn();
  const view = render(
    <Table
      columns={createCaseColumns({
        writable,
        editingSortId: editing ? caseItem.id : null,
        sortingId: null,
        onStartSort,
        onFinishSort,
        onReorder,
        onEdit,
        onDelete,
      })}
      dataSource={[caseItem]}
      pagination={false}
      rowKey="id"
    />,
  );
  return {
    ...view,
    onDelete,
    onEdit,
    onFinishSort,
    onReorder,
    onStartSort,
  };
}

describe("featured case sort column", () => {
  afterEach(cleanup);

  it("enters editing through a visible action", () => {
    const { onStartSort } = renderColumns({ editing: false });

    fireEvent.click(
      screen.getByRole("button", { name: "编辑“跨境汇款”的排序" }),
    );

    expect(onStartSort).toHaveBeenCalledWith(caseItem);
  });

  it("submits only once when Enter is immediately followed by blur", async () => {
    let resolveSave: (() => void) | undefined;
    const onReorder = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveSave = resolve;
        }),
    );
    renderColumns({ onReorder });
    const input = screen.getByRole("spinbutton", {
      name: "“跨境汇款”的排序值",
    });

    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.blur(input);

    expect(onReorder).toHaveBeenCalledTimes(1);
    expect(onReorder).toHaveBeenCalledWith(caseItem, 2);
    resolveSave?.();
    await waitFor(() =>
      expect(
        screen.queryByText("排序保存失败，请重试或按 Esc 取消"),
      ).not.toBeInTheDocument(),
    );
  });

  it("keeps the edited value and edit mode visible when saving fails", async () => {
    const onReorder = vi.fn().mockRejectedValue(new Error("network"));
    renderColumns({ onReorder });
    const input = screen.getByRole("spinbutton", {
      name: "“跨境汇款”的排序值",
    });

    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(
      await screen.findByText("排序保存失败，请重试或按 Esc 取消"),
    ).toBeInTheDocument();
    expect(input).toHaveValue("2");
    expect(
      screen.getByRole("button", { name: "保存排序" }),
    ).toBeInTheDocument();
  });

  it("rejects non-positive and decimal values without sending a request", async () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderColumns({ onReorder });
    const input = screen.getByRole("spinbutton", {
      name: "“跨境汇款”的排序值",
    });

    fireEvent.change(input, { target: { value: "1.5" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(
      await screen.findByText("请输入大于等于 1 的整数"),
    ).toBeInTheDocument();
    expect(onReorder).not.toHaveBeenCalled();
  });

  it("commits valid changes on blur", async () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    const { onFinishSort } = renderColumns({ onReorder });
    const input = screen.getByRole("spinbutton", {
      name: "“跨境汇款”的排序值",
    });

    expect(input).toHaveValue("4");
    fireEvent.change(input, { target: { value: "3" } });
    fireEvent.blur(input);

    await waitFor(() => expect(onReorder).toHaveBeenCalledWith(caseItem, 3));
    expect(onFinishSort).toHaveBeenCalledTimes(1);
  });

  it("cancels with Escape and skips an unchanged submission", async () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    const { onFinishSort } = renderColumns({ onReorder });
    const input = screen.getByRole("spinbutton", {
      name: "“跨境汇款”的排序值",
    });

    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onReorder).not.toHaveBeenCalled();
    expect(onFinishSort).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(onFinishSort).toHaveBeenCalledTimes(2));
    expect(onReorder).not.toHaveBeenCalled();
  });

  it("allows retrying the retained value after a failed save", async () => {
    const onReorder = vi
      .fn()
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce(undefined);
    const { onFinishSort } = renderColumns({ onReorder });
    const input = screen.getByRole("spinbutton", {
      name: "“跨境汇款”的排序值",
    });
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await screen.findByText("排序保存失败，请重试或按 Esc 取消");

    fireEvent.click(screen.getByRole("button", { name: "保存排序" }));

    await waitFor(() => expect(onReorder).toHaveBeenCalledTimes(2));
    expect(onReorder).toHaveBeenLastCalledWith(caseItem, 2);
    expect(onFinishSort).toHaveBeenCalledTimes(1);
  });

  it("does not expose write actions in a read-only scope", () => {
    renderColumns({ writable: false });

    expect(screen.getByText("仅查看")).toBeInTheDocument();
    expect(screen.queryByText("编辑")).not.toBeInTheDocument();
    expect(screen.queryByText("删除")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "编辑“跨境汇款”的排序" }),
    ).not.toBeInTheDocument();
  });
});
