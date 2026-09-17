import React from "react";
import { render, screen } from "@testing-library/react";
import { Form } from "antd";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("./SliderWithValue", () => ({
  SliderWithValue: () => <div data-testid="slider-with-value" />,
}));

import { ContextCompactCard } from "./ContextCompactCard";

describe("ContextCompactCard", () => {
  it("shows the staged 65/5/80/90 controls", () => {
    render(
      <Form
        initialValues={{
          context_compact: {
            lightweight_governance_ratio: 0.65,
            precompaction_step_ratio: 0.05,
            memory_compact_ratio: 0.8,
            emergency_compact_ratio: 0.9,
          },
        }}
      >
        <ContextCompactCard maxInputLength={128_000} />
      </Form>,
    );

    expect(
      screen.getByText("agentConfig.lightweightGovernanceRatio"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("agentConfig.precompactionStepRatio"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("agentConfig.emergencyCompactRatio"),
    ).toBeInTheDocument();
  });
});
