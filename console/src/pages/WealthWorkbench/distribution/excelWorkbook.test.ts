import { Blob as NodeBlob, File as NodeFile } from "node:buffer";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readExcelRoster } from "./excelWorkbook";

const rosterBytes = readFileSync(
  "src/pages/WealthWorkbench/distribution/__fixtures__/excel-roster.xlsx",
);

beforeEach(() => {
  // jsdom provides DOMParser. Node supplies the native Blob streaming APIs.
  vi.stubGlobal("Blob", NodeBlob);
  vi.stubGlobal("File", NodeFile);
});
afterEach(() => vi.unstubAllGlobals());

it("读取真实 XLSX 中的文本 SAP ID，保留前导零和行号，并去重", async () => {
  const file = new File([new Uint8Array(rosterBytes)], "名单.xlsx");

  await expect(readExcelRoster(file)).resolves.toEqual({
    rows: [
      { sapId: "000123", row: 2 },
      { sapId: "000456", row: 3 },
    ],
    errors: [],
    duplicates: 1,
  });
});

it("原始文件超过 5 MB 时拒绝读取", async () => {
  const file = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "超限.xlsx");
  const read = vi.spyOn(file, "arrayBuffer");

  await expect(readExcelRoster(file)).rejects.toThrow(
    "请选择不超过 5 MB 的 .xlsx 文件",
  );
  expect(read).not.toHaveBeenCalled();
});

it("新版模板按客户经理 ID 读取和去重，姓名选填且不能代替 ID", async () => {
  const bytes = readFileSync(
    "src/pages/WealthWorkbench/distribution/__fixtures__/excel-roster-with-names.xlsx",
  );
  const file = new File([new Uint8Array(bytes)], "客户经理名单.xlsx");

  await expect(readExcelRoster(file)).resolves.toEqual({
    rows: [
      { sapId: "000123", row: 2 },
      { sapId: "000456", row: 3 },
    ],
    errors: ["第 5 行：请填写文本格式的客户经理ID"],
    duplicates: 1,
  });
});
