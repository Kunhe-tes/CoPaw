import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useExpertBinding } from "./useExpertBinding";
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock("@/api/modules/chat", () => ({
  chatApi: { getExpertBinding: mocks.get, updateExpertBinding: mocks.put },
}));
const view = (expert_id: string | null = null, revision = 0) => ({
  revision,
  expert_id,
  enabled: true,
  available: true,
  expert_name: expert_id,
  reason: null,
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
const options = {
  chatId: "a",
  scopeKey: "source/profile",
  ensureChat: vi.fn(async () => "created"),
  notify: vi.fn(),
};
describe("useExpertBinding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue(view());
  });
  afterEach(cleanup);
  it("saves immediately, retains saved selection while pending, and ignores duplicate clicks", async () => {
    const pending = deferred<ReturnType<typeof view>>();
    mocks.put.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useExpertBinding(options));
    await waitFor(() => expect(result.current.view?.revision).toBe(0));
    let saved!: Promise<string>;
    act(() => {
      saved = result.current.change("expert-1");
      void result.current.change("expert-1");
    });
    expect(result.current.saving).toBe(true);
    expect(result.current.view?.expert_id).toBe(null);
    expect(mocks.put).toHaveBeenCalledTimes(1);
    await act(async () => {
      pending.resolve(view("expert-1", 1));
      await saved;
    });
    expect(result.current.view?.expert_id).toBe("expert-1");
  });
  it("keeps the saved view when saving fails", async () => {
    mocks.put.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useExpertBinding(options));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      expect(await result.current.change("b")).toBe("failed");
    });
    expect(result.current.view?.expert_id).toBe(null);
    expect(options.notify).toHaveBeenCalledWith("offline");
  });
  it("isolates late saves when switching chats", async () => {
    const pending = deferred<ReturnType<typeof view>>();
    mocks.put.mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(
      ({ chatId }) => useExpertBinding({ ...options, chatId }),
      { initialProps: { chatId: "a" } },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    let saved!: Promise<string>;
    act(() => {
      saved = result.current.change("old");
    });
    mocks.get.mockResolvedValue(view("new", 4));
    rerender({ chatId: "b" });
    await waitFor(() => expect(result.current.view?.expert_id).toBe("new"));
    await act(async () => {
      pending.resolve(view("old", 1));
      await saved;
    });
    expect(result.current.view?.expert_id).toBe("new");
  });
  it("creates an empty chat before the first selection and reads its revision", async () => {
    mocks.put.mockResolvedValue(view("e", 1));
    const { result } = renderHook(() =>
      useExpertBinding({ ...options, chatId: null }),
    );
    await act(async () => {
      await result.current.change("e");
    });
    expect(options.ensureChat).toHaveBeenCalledTimes(1);
    expect(mocks.get).toHaveBeenCalledWith("created");
    expect(mocks.put).toHaveBeenCalledWith("created", {
      expected_revision: 0,
      expert_id: "e",
    });
  });
  it("synchronizes a conflicting view without retrying", async () => {
    mocks.put.mockRejectedValue({
      status: 409,
      data: {
        detail: {
          code: "expert_binding_changed",
          expert_binding: view("other", 2),
        },
      },
    });
    const { result } = renderHook(() => useExpertBinding(options));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.change("e");
    });
    expect(result.current.view?.expert_id).toBe("other");
    expect(mocks.put).toHaveBeenCalledTimes(1);
    expect(options.notify).toHaveBeenCalled();
  });
  it("keeps legacy mode as a single-turn choice without a binding write", async () => {
    mocks.get.mockResolvedValue({ ...view(), enabled: false });
    const { result } = renderHook(() => useExpertBinding(options));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () =>
      expect(await result.current.change("e")).toBe("legacy"),
    );
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it("does not let a late load replace a newer refreshed revision", async () => {
    const old = deferred<ReturnType<typeof view>>();
    mocks.get
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce(view("new", 3));
    const { result } = renderHook(() => useExpertBinding(options));
    await act(async () => {
      await result.current.refresh();
      old.resolve(view("old", 1));
    });
    expect(result.current.view?.expert_id).toBe("new");
  });
  it("does not let a late refresh replace a newer saved binding", async () => {
    const old = deferred<ReturnType<typeof view>>();
    mocks.get.mockResolvedValueOnce(view("old", 1));
    const { result } = renderHook(() => useExpertBinding(options));
    await waitFor(() => expect(result.current.loading).toBe(false));
    mocks.get.mockReturnValueOnce(old.promise);
    mocks.put.mockResolvedValueOnce(view("new", 2));
    let refreshed!: Promise<boolean>;
    act(() => {
      refreshed = result.current.refresh();
    });
    await act(async () => {
      await result.current.change("new");
      old.resolve(view("old", 1));
      await refreshed;
    });
    expect(result.current.view?.expert_id).toBe("new");
    expect(result.current.view?.revision).toBe(2);
  });
  it.each(["expert_main_disabled", "expert_unavailable"])(
    "synchronizes %s without losing the retained identity",
    async (code) => {
      const binding = {
        ...view(code === "expert_unavailable" ? "old" : null, 4),
        enabled: code !== "expert_main_disabled",
        available: false,
      };
      mocks.put.mockRejectedValue({
        status: 409,
        data: { detail: { code, expert_binding: binding } },
      });
      const { result } = renderHook(() => useExpertBinding(options));
      await waitFor(() => expect(result.current.loading).toBe(false));
      await act(async () => {
        await result.current.change("e");
      });
      expect(result.current.view).toEqual(binding);
    },
  );
  it("isolates late loads from another Source or Profile", async () => {
    const old = deferred<ReturnType<typeof view>>();
    mocks.get.mockReturnValueOnce(old.promise);
    const { result, rerender } = renderHook(
      ({ scopeKey }) => useExpertBinding({ ...options, scopeKey }),
      { initialProps: { scopeKey: "first" } },
    );
    mocks.get.mockResolvedValueOnce(view("second", 2));
    rerender({ scopeKey: "second" });
    await waitFor(() => expect(result.current.view?.expert_id).toBe("second"));
    await act(async () => {
      old.resolve(view("first", 1));
    });
    expect(result.current.view?.expert_id).toBe("second");
  });
  it("explains a lost approval snapshot without blaming the bound expert", async () => {
    const { result } = renderHook(() => useExpertBinding(options));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => {
      result.current.syncConflict(
        {
          detail: {
            code: "expert_unavailable",
            expert_binding: {
              ...view("expert", 2),
              reason: "expert_execution_unavailable",
            },
          },
        },
        "a",
      );
    });
    expect(options.notify).toHaveBeenCalledWith(
      "原审批执行快照已不可恢复，请重新发起任务。文本和附件已保留。",
    );
  });
});
