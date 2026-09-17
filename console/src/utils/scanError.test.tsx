import { render, screen } from "@testing-library/react";
import { Modal } from "@agentscope-ai/design";
import { afterEach, describe, expect, it, vi } from "vitest";

import { captureScanWarningCursor, checkScanWarnings } from "./scanError";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("checkScanWarnings", () => {
  it("queries the requested skill directly instead of a global page", async () => {
    const warning = vi.spyOn(Modal, "warning").mockImplementation(() => ({
      destroy: vi.fn(),
      update: vi.fn(),
    }));
    const fetchWarning = vi.fn().mockResolvedValue({
      id: "new",
      skill_name: "demo",
      blocked_at: "2026-08-03T09:00:00+00:00",
      max_severity: "HIGH",
      findings: [{ title: "new finding", file_path: "new.py" }],
      content_hash: "",
      action: "warned",
    });

    await checkScanWarnings(
      "demo",
      "2026-08-03T08:30:00+00:00",
      fetchWarning,
      vi.fn().mockResolvedValue({ mode: "warn", timeout: 30, whitelist: [] }),
      ((key: string) => key) as never,
    );

    expect(fetchWarning).toHaveBeenCalledWith(
      "demo",
      "2026-08-03T08:30:00+00:00",
    );
    const content = warning.mock.calls[0][0].content;
    render(<>{content}</>);
    expect(screen.getByText("new finding")).toBeInTheDocument();
  });

  it("keeps warnings visible for batches larger than one history page", async () => {
    const warning = vi.spyOn(Modal, "warning").mockImplementation(() => ({
      destroy: vi.fn(),
      update: vi.fn(),
    }));
    const fetchWarning = vi.fn(async (skillName: string) =>
      skillName === "skill-25"
        ? {
            id: "warning-25",
            skill_name: skillName,
            blocked_at: "2026-08-03T09:00:00+00:00",
            max_severity: "HIGH",
            findings: [
              {
                severity: "HIGH",
                title: "batch finding",
                description: "batch warning",
                file_path: "batch.py",
                line_number: 25,
                rule_id: "BATCH-25",
              },
            ],
            content_hash: "",
            action: "warned" as const,
          }
        : null,
    );
    const fetchConfig = vi
      .fn()
      .mockResolvedValue({ mode: "warn", timeout: 30, whitelist: [] });

    for (let index = 1; index <= 25; index += 1) {
      await checkScanWarnings(
        `skill-${index}`,
        "2026-08-03T08:30:00+00:00",
        fetchWarning,
        fetchConfig,
        ((key: string) => key) as never,
      );
    }

    expect(fetchWarning).toHaveBeenCalledTimes(25);
    expect(fetchWarning).toHaveBeenLastCalledWith(
      "skill-25",
      "2026-08-03T08:30:00+00:00",
    );
    expect(warning).toHaveBeenCalledTimes(1);
    const content = warning.mock.calls[0][0].content;
    render(<>{content}</>);
    expect(screen.getByText("batch finding")).toBeInTheDocument();
  });

  it("does not query historical warnings when the operation cursor is unavailable", async () => {
    const warning = vi.spyOn(Modal, "warning").mockImplementation(() => ({
      destroy: vi.fn(),
      update: vi.fn(),
    }));
    const fetchWarning = vi.fn();
    const cursor = await captureScanWarningCursor(
      vi.fn().mockRejectedValue(new Error("cursor unavailable")),
    );

    await checkScanWarnings(
      "demo",
      cursor,
      fetchWarning,
      vi.fn(),
      ((key: string) => key) as never,
    );

    expect(fetchWarning).not.toHaveBeenCalled();
    expect(warning).not.toHaveBeenCalled();
  });
});
