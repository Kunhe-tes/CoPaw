import { describe, expect, it } from "vitest";
import {
  CONSOLE_MANAGEMENT_TOKENS,
  applyConsoleDesignTokens,
} from "./consoleDesignTokens";

describe("applyConsoleDesignTokens", () => {
  it("maps the management theme configuration to CSS variables", () => {
    const root = document.createElement("div");

    applyConsoleDesignTokens(root);

    expect(root.style.getPropertyValue("--console-management-canvas")).toBe(
      CONSOLE_MANAGEMENT_TOKENS.colorCanvas,
    );
    expect(root.style.getPropertyValue("--console-management-primary")).toBe(
      CONSOLE_MANAGEMENT_TOKENS.colorPrimary,
    );
    expect(
      root.style.getPropertyValue("--console-management-primary-soft"),
    ).toBe(CONSOLE_MANAGEMENT_TOKENS.colorPrimarySoft);
  });
});
