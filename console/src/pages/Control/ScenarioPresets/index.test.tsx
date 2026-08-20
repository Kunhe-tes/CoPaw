import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ScenarioPresetsPage from "./index";
import { scenarioPresetApi } from "@/api/modules/scenarioPreset";

vi.mock("@/hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
  }),
}));
vi.mock("@/stores/iframeStore", () => ({
  useIframeStore: (selector: (state: { source: string }) => unknown) =>
    selector({ source: "source-a" }),
}));
vi.mock("@/api/modules/scenarioPreset", () => ({
  scenarioPresetApi: {
    getAdminCatalog: vi.fn(),
    createNode: vi.fn(),
    updateNode: vi.fn(),
    deleteNode: vi.fn(),
    getBindings: vi.fn(),
    replaceBindings: vi.fn(),
    moveNode: vi.fn(),
    reorderNode: vi.fn(),
  },
}));
vi.mock("@/api/modules/market", () => ({
  marketApi: { listMarketSkills: vi.fn().mockResolvedValue([]) },
}));
vi.mock("@/api/modules/marketMcp", () => ({
  marketMcpApi: { listMarketMCP: vi.fn().mockResolvedValue([]) },
}));

const scenarioNodes = [
  {
    id: "domain-1",
    source_id: "source-a",
    parent_id: null,
    kind: "domain" as const,
    name: "内容创作",
    prompt_draft: "",
    is_active: true,
    sort_order: 1,
  },
  {
    id: "capability-1",
    source_id: "source-a",
    parent_id: "domain-1",
    kind: "capability" as const,
    name: "文章写作",
    prompt_draft: "",
    is_active: true,
    sort_order: 1,
  },
  {
    id: "scenario-1",
    source_id: "source-a",
    parent_id: "capability-1",
    kind: "scenario" as const,
    name: "小红书标题生成",
    prompt_draft: "生成三个标题",
    is_active: true,
    sort_order: 1,
  },
];

describe("ScenarioPresetsPage", () => {
  afterEach(cleanup);

  it("shows only the create-domain action for an empty catalog", async () => {
    vi.mocked(scenarioPresetApi.getAdminCatalog).mockResolvedValueOnce({
      nodes: [],
    });
    render(<ScenarioPresetsPage />);

    await waitFor(() =>
      expect(scenarioPresetApi.getAdminCatalog).toHaveBeenCalledOnce(),
    );

    expect(
      screen.getByRole("button", { name: /新建能力域/ }),
    ).toBeInTheDocument();
    expect(screen.queryByText("场景预设管理")).toBeNull();
  });

  it("renders the hierarchical catalog as rows", async () => {
    vi.mocked(scenarioPresetApi.getAdminCatalog).mockResolvedValueOnce({
      nodes: scenarioNodes,
    });
    render(<ScenarioPresetsPage />);

    expect(await screen.findByText("内容创作")).toBeInTheDocument();
    expect(screen.getByText("文章写作")).toBeInTheDocument();
    expect(screen.getByText("小红书标题生成")).toBeInTheDocument();
    expect(screen.getByText("状态")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("loads a selected scenario into the fixed details panel", async () => {
    vi.mocked(scenarioPresetApi.getAdminCatalog).mockResolvedValueOnce({
      nodes: scenarioNodes,
    });
    vi.mocked(scenarioPresetApi.getBindings).mockResolvedValueOnce({
      bindings: [],
    });
    render(<ScenarioPresetsPage />);

    fireEvent.click(await screen.findByText("小红书标题生成"));

    expect(
      await screen.findByRole("heading", { name: "小红书标题生成" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("名称")).toHaveValue("小红书标题生成");
    expect(screen.getByRole("button", { name: "保存更改" })).toBeEnabled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("disables save when scenario bindings cannot be loaded", async () => {
    vi.mocked(scenarioPresetApi.getAdminCatalog).mockResolvedValueOnce({
      nodes: scenarioNodes,
    });
    vi.mocked(scenarioPresetApi.getBindings).mockRejectedValueOnce(
      new Error("network"),
    );
    render(<ScenarioPresetsPage />);

    fireEvent.click(await screen.findByText("小红书标题生成"));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "保存更改" })).toBeDisabled(),
    );
  });

  it("keeps the details panel open after saving a node", async () => {
    vi.mocked(scenarioPresetApi.getAdminCatalog)
      .mockResolvedValueOnce({ nodes: scenarioNodes })
      .mockResolvedValueOnce({ nodes: scenarioNodes });
    vi.mocked(scenarioPresetApi.getBindings).mockResolvedValueOnce({
      bindings: [],
    });
    vi.mocked(scenarioPresetApi.updateNode).mockResolvedValueOnce(
      scenarioNodes[2],
    );
    render(<ScenarioPresetsPage />);

    fireEvent.click(await screen.findByText("小红书标题生成"));
    const saveButton = await screen.findByRole("button", {
      name: "保存更改",
    });
    fireEvent.click(saveButton);

    await waitFor(() =>
      expect(scenarioPresetApi.updateNode).toHaveBeenCalledWith(
        "scenario-1",
        expect.objectContaining({ name: "小红书标题生成" }),
      ),
    );
    expect(
      screen.getByRole("heading", { name: "小红书标题生成" }),
    ).toBeInTheDocument();
  });
});
