import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  FeaturedCase,
  FeaturedCaseListResponse,
} from "@/api/types/featuredCases";
import { useFeaturedCases } from "./hooks";

const mocks = vi.hoisted(() => ({
  adminListCases: vi.fn(),
}));

vi.mock("@/api/modules/featuredCases", () => ({
  featuredCasesApi: {
    adminListCases: mocks.adminListCases,
  },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function caseItem(id: number, bbkId: string): FeaturedCase {
  return {
    id,
    source_id: "source-1",
    bbk_id: bbkId,
    label: `案例${id}`,
    value: `内容${id}`,
    sort_order: 1,
    is_active: true,
  };
}

describe("useFeaturedCases", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps late responses isolated from the active scope", async () => {
    const branchResponse = deferred<FeaturedCaseListResponse>();
    const headOfficeResponse = deferred<FeaturedCaseListResponse>();
    mocks.adminListCases.mockImplementation(({ bbk_id }: { bbk_id: string }) =>
      bbk_id === "branch-a"
        ? branchResponse.promise
        : headOfficeResponse.promise,
    );
    const { result, rerender } = renderHook(
      ({ scope }) => useFeaturedCases(scope),
      { initialProps: { scope: "branch-a" } },
    );

    let branchRequest!: Promise<FeaturedCaseListResponse>;
    act(() => {
      branchRequest = result.current.loadCases({ bbk_id: "branch-a" });
    });
    rerender({ scope: "100" });
    let headOfficeRequest!: Promise<FeaturedCaseListResponse>;
    act(() => {
      headOfficeRequest = result.current.loadCases({ bbk_id: "100" });
    });

    await act(async () => {
      headOfficeResponse.resolve({ cases: [caseItem(100, "100")], total: 1 });
      await headOfficeRequest;
    });
    expect(result.current.cases.map((item) => item.id)).toEqual([100]);
    expect(result.current.total).toBe(1);

    await act(async () => {
      branchResponse.resolve({
        cases: [caseItem(1, "branch-a")],
        total: 21,
      });
      await branchRequest;
    });
    expect(result.current.cases.map((item) => item.id)).toEqual([100]);
    expect(result.current.total).toBe(1);

    rerender({ scope: "branch-a" });
    expect(result.current.cases.map((item) => item.id)).toEqual([1]);
    expect(result.current.total).toBe(21);
  });

  it("ignores an older page response within the same scope", async () => {
    const firstPageResponse = deferred<FeaturedCaseListResponse>();
    const secondPageResponse = deferred<FeaturedCaseListResponse>();
    mocks.adminListCases
      .mockReturnValueOnce(firstPageResponse.promise)
      .mockReturnValueOnce(secondPageResponse.promise);
    const { result } = renderHook(() => useFeaturedCases("branch-a"));

    let firstRequest!: Promise<FeaturedCaseListResponse>;
    let secondRequest!: Promise<FeaturedCaseListResponse>;
    act(() => {
      firstRequest = result.current.loadCases({
        bbk_id: "branch-a",
        page: 1,
      });
      secondRequest = result.current.loadCases({
        bbk_id: "branch-a",
        page: 2,
      });
    });

    await act(async () => {
      secondPageResponse.resolve({
        cases: [caseItem(2, "branch-a")],
        total: 40,
      });
      await secondRequest;
    });
    await act(async () => {
      firstPageResponse.resolve({
        cases: [caseItem(1, "branch-a")],
        total: 40,
      });
      await firstRequest;
    });

    expect(result.current.cases.map((item) => item.id)).toEqual([2]);
    expect(result.current.total).toBe(40);
    expect(result.current.loading).toBe(false);
  });
});
