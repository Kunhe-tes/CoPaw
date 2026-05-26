import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EnvironmentsPage from "./index";

const mocks = vi.hoisted(() => ({
  listEnvs: vi.fn(),
  saveEnvs: vi.fn(),
  patchEnvs: vi.fn(),
  deleteEnv: vi.fn(),
  fetchAll: vi.fn(),
  messageApi: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("../../../api", () => ({
  default: {
    listEnvs: mocks.listEnvs,
    saveEnvs: mocks.saveEnvs,
    patchEnvs: mocks.patchEnvs,
    deleteEnv: mocks.deleteEnv,
  },
}));

vi.mock("../../../hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: mocks.messageApi,
  }),
}));

vi.mock("@/components/PageHeader", () => ({
  PageHeader: () => null,
}));

vi.mock("./useEnvVars", () => ({
  useEnvVars: () => ({
    envVars: [
      { key: "API_TOKEN", value: "********" },
      { key: "PLAIN_KEY", value: "visible-value" },
    ],
    loading: false,
    error: null,
    fetchAll: mocks.fetchAll,
  }),
}));

vi.mock("./components", () => ({
  EmptyState: () => null,
  AddButton: ({ onClick }: { onClick: () => void }) => (
    <button onClick={onClick} type="button">
      add-row
    </button>
  ),
  Toolbar: ({
    onSave,
    onReset,
  }: {
    onSave: () => void;
    onReset: () => void;
  }) => (
    <div>
      <button onClick={onSave} type="button">
        save
      </button>
      <button onClick={onReset} type="button">
        reset
      </button>
    </div>
  ),
  EnvRow: ({
    row,
    idx,
    onChange,
  }: {
    row: { key: string; value: string; isNew?: boolean };
    idx: number;
    onChange: (
      idx: number,
      field: "key" | "value",
      value: string,
    ) => void;
  }) => (
    <div data-testid={`row-${idx}`}>
      <span>{row.key}</span>
      <span>{row.value}</span>
      {!row.isNew ? (
        <>
          <button
            onClick={() => onChange(idx, "value", "********")}
            type="button"
          >
            keep-stars-{idx}
          </button>
          <button
            onClick={() => onChange(idx, "key", "RENAMED_KEY")}
            type="button"
          >
            rename-key-{idx}
          </button>
        </>
      ) : null}
      {row.isNew ? (
        <>
          <button
            onClick={() => onChange(idx, "key", "NEW_SECRET")}
            type="button"
          >
            set-key-{idx}
          </button>
          <button
            onClick={() => onChange(idx, "value", "fresh-secret")}
            type="button"
          >
            set-value-{idx}
          </button>
        </>
      ) : null}
    </div>
  ),
}));

describe("EnvironmentsPage", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.patchEnvs.mockResolvedValue([]);
    mocks.saveEnvs.mockResolvedValue([]);
  });

  it("preserves masked secrets when saving after adding a new variable", async () => {
    render(<EnvironmentsPage />);

    fireEvent.click(screen.getByRole("button", { name: "add-row" }));
    fireEvent.click(screen.getByRole("button", { name: "set-key-2" }));
    fireEvent.click(screen.getByRole("button", { name: "set-value-2" }));
    fireEvent.click(screen.getByRole("button", { name: "save" }));

    await waitFor(() => {
      expect(mocks.patchEnvs).toHaveBeenCalledWith({
        values: { NEW_SECRET: "fresh-secret" },
        delete: [],
      });
    });
    expect(mocks.saveEnvs).not.toHaveBeenCalled();
  });

  it("treats an explicitly edited masked literal as a new value", async () => {
    render(<EnvironmentsPage />);

    fireEvent.click(screen.getByRole("button", { name: "keep-stars-0" }));
    fireEvent.click(screen.getByRole("button", { name: "save" }));

    await waitFor(() => {
      expect(mocks.patchEnvs).toHaveBeenCalledWith({
        values: { API_TOKEN: "********" },
        delete: [],
      });
    });
  });

  it("deletes the old key when renaming an existing variable", async () => {
    render(<EnvironmentsPage />);

    fireEvent.click(screen.getByRole("button", { name: "rename-key-1" }));
    fireEvent.click(screen.getByRole("button", { name: "save" }));

    await waitFor(() => {
      expect(mocks.patchEnvs).toHaveBeenCalledWith({
        values: { RENAMED_KEY: "visible-value" },
        delete: ["PLAIN_KEY"],
      });
    });
  });
});
