import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import styles from "../index.module.less";
import { SceneDescription } from "./index";

describe("SceneDescription", () => {
  it("用两行截断样式展示描述，并保留完整文本供悬停查看", () => {
    const description =
      "这是一段超过两行时仍可通过悬停查看全文的经营场景技能描述";

    render(<SceneDescription description={description} />);

    const element = screen.getByText(description);
    expect(element).toHaveClass(styles.sceneDescription);
    expect(element).toHaveAttribute("title", description);
  });
});
