import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CronUnreadPauseBranches } from "./CronUnreadPauseBranches";

afterEach(cleanup);

it("分行规则从渠道默认初始化，也能恢复为渠道默认", () => {
  const onChange = vi.fn();
  const defaults = { enabled: true, threshold: 8 };
  const view = render(
    <CronUnreadPauseBranches
      config={defaults}
      disabled={false}
      onChange={onChange}
    />,
  );
  fireEvent.click(screen.getByText("按分行配置未读暂停（0）"));
  fireEvent.change(screen.getByLabelText("分行代码"), {
    target: { value: "110" },
  });
  fireEvent.click(screen.getByRole("button", { name: "添加分行" }));
  expect(onChange).toHaveBeenLastCalledWith({ "110": defaults });
  view.rerender(
    <CronUnreadPauseBranches
      config={{ ...defaults, by_branch: { "110": defaults } }}
      disabled={false}
      onChange={onChange}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "恢复渠道默认" }));
  expect(onChange).toHaveBeenLastCalledWith({});
});
