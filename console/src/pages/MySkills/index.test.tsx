import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MySkillsPage from "./index";
import type { MySkill } from "../../api/modules/mySkills";

const mocks = vi.hoisted(() => ({
  refresh: vi.fn(),
  refreshSkill: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("./useMySkills", () => ({
  useMySkills: () => ({
    createdSkills,
    receivedSkills: [],
    loading: false,
    refresh: mocks.refresh,
    refreshSkill: mocks.refreshSkill,
  }),
}));

vi.mock("../../stores/iframeStore", () => ({
  useIframeStore: (selector: (state: { source: string; manager: boolean }) => unknown) =>
    selector({ source: "default", manager: false }),
}));

vi.mock("../../utils/identity", () => ({
  getUserId: () => "user-1",
}));

vi.mock("../Market/PublishModal", () => ({
  PublishModal: () => null,
}));

const createdSkills: MySkill[] = [
  {
    skill_name: "risk_policy_check",
    display_name: "Legacy Risk Alias",
    source: "customized",
    description: "Risk policy checker",
    version: "1.0.0",
    received_version: null,
    distributed_by: null,
    is_received: false,
    has_update: false,
    enabled: true,
    cn_name: "风控策略检查",
  },
  {
    skill_name: "report_summary",
    display_name: "Legacy Report Alias",
    source: "customized",
    description: "Report summary",
    version: "1.0.0",
    received_version: null,
    distributed_by: null,
    is_received: false,
    has_update: false,
    enabled: true,
  },
];

describe("MySkillsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows cn_name first and falls back to skill_name in the left skill list", () => {
    render(<MySkillsPage />);

    expect(screen.getByText("风控策略检查")).toBeInTheDocument();
    expect(screen.getByText("report_summary")).toBeInTheDocument();
    expect(screen.queryByText("Legacy Risk Alias")).not.toBeInTheDocument();
    expect(screen.queryByText("Legacy Report Alias")).not.toBeInTheDocument();
  });
});
