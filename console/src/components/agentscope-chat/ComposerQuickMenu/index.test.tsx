import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ComposerQuickMenu, { ComposerQuickMenuItem } from "./index";

describe("ComposerQuickMenu", () => {
  afterEach(() => {
    cleanup();
  });

  it("opens and closes the menu from the plus trigger", async () => {
    render(
      <ComposerQuickMenu triggerLabel="快捷操作">
        <ComposerQuickMenuItem label="上传文件" />
      </ComposerQuickMenu>,
    );

    expect(screen.queryByText("上传文件")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "快捷操作" }));

    expect(await screen.findByText("上传文件")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "快捷操作" }));

    await waitFor(() => {
      expect(screen.queryByText("上传文件")).not.toBeInTheDocument();
    });
  });

  it("runs the item handler and closes the menu after click", async () => {
    const onClick = vi.fn();

    render(
      <ComposerQuickMenu triggerLabel="快捷操作">
        <ComposerQuickMenuItem label="计划模式" onClick={onClick} />
      </ComposerQuickMenu>,
    );

    fireEvent.click(screen.getByRole("button", { name: "快捷操作" }));
    fireEvent.click(await screen.findByText("计划模式"));

    expect(onClick).toHaveBeenCalledTimes(1);

    await waitFor(() => {
      expect(screen.queryByText("计划模式")).not.toBeInTheDocument();
    });
  });
});
