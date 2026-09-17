import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useIframeStore } from "../stores/iframeStore";
import Header from "./Header";

vi.mock("../contexts/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));

vi.mock("../contexts/BrandThemeContext", () => ({
  useBrandTheme: () => ({
    theme: {
      brandName: "CoPaw",
      logo: "/logo.svg",
      darkLogo: "/logo-dark.svg",
    },
  }),
}));

afterEach(() => {
  cleanup();
  useIframeStore.setState({ source: null });
});

describe("Header", () => {
  it("remains presentational when source is ruice", () => {
    useIframeStore.setState({ source: "ruice" });

    render(<Header />);

    expect(screen.getByRole("img", { name: "CoPaw" })).toBeInTheDocument();
  });

  it("renders for other sources", () => {
    useIframeStore.setState({ source: "other" });

    render(<Header />);

    expect(screen.getByRole("img", { name: "CoPaw" })).toBeInTheDocument();
  });
});
