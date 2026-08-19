import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ScenarioPresetSelector from "./index";
import { scenarioPresetApi } from "@/api/modules/scenarioPreset";

vi.mock("@/api/modules/scenarioPreset", () => ({
  scenarioPresetApi: { getEffectiveCatalog: vi.fn() },
}));

const getEffectiveCatalog = vi.mocked(scenarioPresetApi.getEffectiveCatalog);

describe("ScenarioPresetSelector", () => {
  afterEach(cleanup);

  it("stays absent for an empty effective catalog", async () => {
    getEffectiveCatalog.mockResolvedValueOnce({ domains: [] });
    const { container } = render(<ScenarioPresetSelector onSelect={vi.fn()} />);

    await waitFor(() => expect(getEffectiveCatalog).toHaveBeenCalledOnce());

    expect(container.querySelector(".scenario-preset-selector")).toBeNull();
  });

  it("opens only the first path and submits the selected leaf without resolving resources", async () => {
    getEffectiveCatalog.mockResolvedValueOnce({
      domains: [
        {
          id: "domain-a",
          name: "文档",
          capabilities: [
            {
              id: "capability-a",
              name: "信息提取",
              scenarios: [{ id: "scenario-a", name: "提取字段", prompt_draft: "提取" }],
            },
          ],
        },
      ],
    });
    const onSelect = vi.fn();
    render(<ScenarioPresetSelector onSelect={onSelect} />);

    const scenario = await screen.findByRole("button", { name: "提取字段" });
    fireEvent.click(scenario);

    expect(onSelect).toHaveBeenCalledWith({
      capability: expect.objectContaining({ id: "capability-a" }),
      scenario: expect.objectContaining({ id: "scenario-a" }),
    });
  });
});
