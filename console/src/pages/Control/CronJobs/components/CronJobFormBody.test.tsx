import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Form } from "@agentscope-ai/design";
import { CronJobFormBody } from "./CronJobFormBody";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("CronJobFormBody", () => {
  it("does not render the batch dispatch switch in the create/edit form", () => {
    const Wrapper = () => {
      const [form] = Form.useForm();

      return (
        <Form form={form}>
          <CronJobFormBody
            form={form}
            executionModelOptions={[]}
            executionModelLoading={false}
            tenantDefaultModelLabel="Tenant default"
          />
        </Form>
      );
    };

    render(<Wrapper />);

    expect(screen.queryByText("批调度")).not.toBeInTheDocument();
    expect(
      screen.queryByText("cronJobs.broadcastDispatchIntents"),
    ).not.toBeInTheDocument();
  });
});
