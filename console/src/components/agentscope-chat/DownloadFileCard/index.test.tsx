import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DownloadFileCard from "./index";
import { AutoPreviewHtmlProvider } from "../AutoPreviewHtmlContext";

vi.mock("@agentscope-ai/icons", () => ({
  SparkDownloadLine: () => <span data-testid="download-icon" />,
}));

vi.mock("../FilePreviewModal", () => ({
  default: (props: {
    open: boolean;
    fileName: string;
    enableClickTracking?: boolean;
  }) =>
    props.open ? (
      <div
        data-click-tracking={String(Boolean(props.enableClickTracking))}
        data-testid="file-preview-modal"
      >
        {props.fileName}
      </div>
    ) : null,
}));

afterEach(() => {
  cleanup();
});

describe("DownloadFileCard", () => {
  it("显式启用时自动打开带 auto-preview 标记的 HTML 预览", async () => {
    render(
      <DownloadFileCard
        url="https://example.test/static/report[auto-preview]-1.html"
        fileName="report[auto-preview]-1.html"
        autoPreview
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("file-preview-modal")).toHaveTextContent(
        "report[auto-preview]-1.html",
      );
    });
  });

  it("显式启用时自动打开带存款到期完整客户名单关键词的 HTML 预览", async () => {
    render(
      <DownloadFileCard
        url="https://example.test/static/report-1.html"
        fileName="存款到期完整客户名单-2026-05-29.html"
        autoPreview
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("file-preview-modal")).toHaveTextContent(
        "存款到期完整客户名单-2026-05-29.html",
      );
    });
  });

  it("普通 HTML 链接不自动打开预览", () => {
    render(
      <DownloadFileCard
        url="https://example.test/static/report.html"
        fileName="report.html"
      />,
    );

    expect(screen.queryByTestId("file-preview-modal")).not.toBeInTheDocument();
  });

  it("页面级自动预览只打开最后一个匹配的 HTML", async () => {
    render(
      <AutoPreviewHtmlProvider triggerKey={1} onConsumed={vi.fn()}>
        <DownloadFileCard
          url="https://example.test/static/report-old.html"
          fileName="存款到期完整客户名单-old.html"
        />
        <DownloadFileCard
          url="https://example.test/static/report-new.html"
          fileName="存款到期完整客户名单-new.html"
        />
      </AutoPreviewHtmlProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("file-preview-modal")).toHaveTextContent(
        "存款到期完整客户名单-new.html",
      );
    });
    expect(screen.getAllByTestId("file-preview-modal")).toHaveLength(1);
  });

  it("仍然支持用户点击卡片后打开预览", () => {
    render(
      <DownloadFileCard
        url="https://example.test/static/report.html"
        fileName="report.html"
      />,
    );

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByTestId("file-preview-modal")).toHaveTextContent(
      "report.html",
    );
    expect(screen.getByTestId("file-preview-modal")).toHaveAttribute(
      "data-click-tracking",
      "false",
    );
  });

  it("显式传入采集开关时才启用 HTML 点击统计", () => {
    render(
      <DownloadFileCard
        url="https://example.test/static/report[auto-preview].html"
        fileName="report[auto-preview].html"
        enableClickTracking
      />,
    );

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByTestId("file-preview-modal")).toHaveAttribute(
      "data-click-tracking",
      "true",
    );
  });

  it("auto-preview HTML 即使只传 autoPreview 也会启用点击统计", async () => {
    render(
      <DownloadFileCard
        url="https://example.test/static/report[auto-preview].html"
        fileName="report[auto-preview].html"
        autoPreview
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("file-preview-modal")).toHaveAttribute(
        "data-click-tracking",
        "true",
      );
    });
  });

  it("auto-preview HTML 即使关闭自动弹窗，手动打开后也会启用点击统计", () => {
    render(
      <DownloadFileCard
        url="https://example.test/static/report[auto-preview].html"
        fileName="report[auto-preview].html"
        autoPreview={false}
      />,
    );

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByTestId("file-preview-modal")).toHaveAttribute(
      "data-click-tracking",
      "true",
    );
  });
});
