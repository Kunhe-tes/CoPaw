import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ScenarioPresetsPage from "./index";
import { scenarioPresetApi } from "@/api/modules/scenarioPreset";

vi.mock("@/hooks/useAppMessage", () => ({ useAppMessage: () => ({ message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }) }));
vi.mock("@/stores/iframeStore", () => ({ useIframeStore: (selector: (state: { source: string }) => unknown) => selector({ source: "source-a" }) }));
vi.mock("@/api/modules/scenarioPreset", () => ({ scenarioPresetApi: { getAdminCatalog: vi.fn(), createNode: vi.fn(), updateNode: vi.fn(), deleteNode: vi.fn(), getBindings: vi.fn(), replaceBindings: vi.fn() } }));

describe("ScenarioPresetsPage", () => {
  afterEach(cleanup);

  it("shows only the create-domain action for an empty catalog", async () => {
    vi.mocked(scenarioPresetApi.getAdminCatalog).mockResolvedValueOnce({ nodes: [] });
    render(<ScenarioPresetsPage />);

    await waitFor(() => expect(scenarioPresetApi.getAdminCatalog).toHaveBeenCalledOnce());

    expect(screen.getByRole("button", { name: /新建能力域/ })).toBeInTheDocument();
    expect(screen.queryByText("场景预设管理")).toBeNull();
  });
});
