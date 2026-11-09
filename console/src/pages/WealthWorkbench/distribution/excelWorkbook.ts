export const MAX_EXCEL_FILE_MB = 5;
const MAX_FILE = MAX_EXCEL_FILE_MB * 1024 * 1024;
const MAX_XML = 4 * 1024 * 1024;
export const EXCEL_HEADER = "客户经理ID";
const LEGACY_EXCEL_HEADER = "SAP 用户 ID";
const NAME_HEADER = "客户经理姓名";
export const EXCEL_SHEET = "分发名单";
const FORMAT_ERROR = "无法读取工作簿，请使用下载的 .xlsx 模板";
const utf8 = new TextDecoder();

interface ZipEntry {
  method: number;
  size: number;
  offset: number;
  length: number;
}

function zipEntries(bytes: Uint8Array, view: DataView) {
  let end = bytes.length - 22;
  const min = Math.max(0, end - 65535);
  while (end >= min) {
    if (
      view.getUint32(end, true) === 0x06054b50 &&
      end + 22 + view.getUint16(end + 20, true) === bytes.length
    )
      break;
    end--;
  }
  if (end < min) throw new Error(FORMAT_ERROR);
  const count = view.getUint16(end + 10, true);
  const entries = new Map<string, ZipEntry>();
  let pos = view.getUint32(end + 16, true);
  if (count > 256 || view.getUint32(end + 4, true) !== 0)
    throw new Error(FORMAT_ERROR);

  for (let i = 0; i < count; i++) {
    if (pos + 46 > end || view.getUint32(pos, true) !== 0x02014b50)
      throw new Error(FORMAT_ERROR);
    const nameLength = view.getUint16(pos + 28, true);
    const next =
      pos +
      46 +
      nameLength +
      view.getUint16(pos + 30, true) +
      view.getUint16(pos + 32, true);
    if (next > end || view.getUint16(pos + 8, true) & 1)
      throw new Error(FORMAT_ERROR);
    const name = utf8.decode(bytes.subarray(pos + 46, pos + 46 + nameLength));
    if (entries.has(name)) throw new Error(FORMAT_ERROR);
    entries.set(name, {
      method: view.getUint16(pos + 10, true),
      size: view.getUint32(pos + 24, true),
      offset: view.getUint32(pos + 42, true),
      length: view.getUint32(pos + 20, true),
    });
    pos = next;
  }
  return entries;
}

async function readXml(
  bytes: Uint8Array<ArrayBuffer>,
  view: DataView,
  entry: ZipEntry | undefined,
) {
  if (!entry) throw new Error(FORMAT_ERROR);
  const { method, size, offset, length } = entry;
  if (offset + 30 > bytes.length || view.getUint32(offset, true) !== 0x04034b50)
    throw new Error(FORMAT_ERROR);
  const start =
    offset +
    30 +
    view.getUint16(offset + 26, true) +
    view.getUint16(offset + 28, true);
  if (start + length > bytes.length) throw new Error(FORMAT_ERROR);
  if (size > MAX_XML) throw new Error("Excel 内部单个数据文件解压后超过 4 MB");

  const compressed = bytes.subarray(start, start + length);
  let xml: string;
  if (method === 0 && length === size) {
    xml = utf8.decode(compressed);
  } else if (method === 8) {
    let stream: DecompressionStream;
    try {
      stream = new DecompressionStream("deflate-raw");
    } catch {
      throw new Error("当前浏览器无法读取 Excel，可切换到按机构选人");
    }
    const reader = new Blob([compressed])
      .stream()
      .pipeThrough(stream)
      .getReader();
    const result = new Uint8Array(size);
    let total = 0;
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        if (total + value.length > size) throw new Error(FORMAT_ERROR);
        result.set(value, total);
        total += value.length;
      }
      if (total !== size) throw new Error(FORMAT_ERROR);
    } catch {
      await reader.cancel().catch(() => {});
      throw new Error(FORMAT_ERROR);
    }
    xml = utf8.decode(result);
  } else {
    throw new Error(FORMAT_ERROR);
  }

  if (/<!DOCTYPE/i.test(xml)) throw new Error(FORMAT_ERROR);
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.getElementsByTagNameNS("*", "parsererror").length)
    throw new Error(FORMAT_ERROR);
  return doc;
}

function elements(node: Document | Element, name: string) {
  return Array.from(node.getElementsByTagNameNS("*", name));
}

function cellText(cell: Element, strings: string[]) {
  if (elements(cell, "f").length) return undefined;
  const value = elements(cell, "v")[0]?.textContent ?? "";
  switch (cell.getAttribute("t")) {
    case "s":
      return /^\d+$/.test(value) ? strings[Number(value)] : undefined;
    case "inlineStr":
      return elements(cell, "t")
        .map((item) => item.textContent)
        .join("");
    default:
      return value ? undefined : "";
  }
}

export interface ExcelRow {
  sapId: string;
  row: number;
}

export async function readExcelRoster(file: File) {
  if (!/\.xlsx$/i.test(file.name) || file.size > MAX_FILE || file.size < 22)
    throw new Error(`请选择不超过 ${MAX_EXCEL_FILE_MB} MB 的 .xlsx 文件`);
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  const entries = zipEntries(bytes, view);
  const read = (path: string) => readXml(bytes, view, entries.get(path));
  const workbook = await read("xl/workbook.xml");
  const sheets = elements(workbook, "sheet");
  if (sheets.length !== 1 || sheets[0].getAttribute("name") !== EXCEL_SHEET)
    throw new Error("请保留模板中的「分发名单」工作表");
  const relationships = await read("xl/_rels/workbook.xml.rels");
  const sheetId = sheets[0].getAttributeNS(
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "id",
  );
  const rel = elements(relationships, "Relationship").find(
    (item) => item.getAttribute("Id") === sheetId,
  );
  const path = rel?.getAttribute("Target")?.replace(/^\/?(?:xl\/)?/, "xl/");
  if (!path || !/^xl\/worksheets\/[\w.-]+\.xml$/.test(path))
    throw new Error(FORMAT_ERROR);
  const sheet = await read(path);
  const shared = entries.has("xl/sharedStrings.xml")
    ? elements(await read("xl/sharedStrings.xml"), "si").map((item) =>
        elements(item, "t")
          .map((text) => text.textContent)
          .join(""),
      )
    : [];

  const rows: ExcelRow[] = [];
  const errors: string[] = [];
  const seen = new Set<string>();
  let duplicates = 0;
  const data = elements(sheet, "sheetData")[0];
  if (!data) throw new Error(FORMAT_ERROR);
  const entriesByRow = elements(data, "row");
  const header = entriesByRow[0];
  const headerCells = header ? elements(header, "c") : [];
  const headerCell = headerCells.find(
    (cell) => cell.getAttribute("r") === "A1",
  );
  const idHeader = headerCell && cellText(headerCell, shared)?.trim();
  if (idHeader !== EXCEL_HEADER && idHeader !== LEGACY_EXCEL_HEADER)
    throw new Error(`首行 A1 必须为「${EXCEL_HEADER}」，请使用下载的模板`);
  const nameCell = headerCells.find((cell) => cell.getAttribute("r") === "B1");
  const hasNameColumn = Boolean(
    nameCell && cellText(nameCell, shared)?.trim() === NAME_HEADER,
  );

  let previousRow = 0;
  for (const row of entriesByRow) {
    const number = Number(row.getAttribute("r"));
    if (!Number.isSafeInteger(number) || number <= previousRow)
      throw new Error(FORMAT_ERROR);
    previousRow = number;
    let id: string | undefined = "";
    let hasName = false;
    for (const cell of elements(row, "c")) {
      if (cell === headerCell || (hasNameColumn && cell === nameCell)) continue;
      const value = cellText(cell, shared)?.trim();
      if (value === "") continue;
      const address = cell.getAttribute("r");
      if (number > 1 && address === `A${number}`) {
        id = value;
      } else if (number > 1 && hasNameColumn && address === `B${number}`) {
        hasName = true;
      } else {
        throw new Error(`模板仅支持 A 列${EXCEL_HEADER}和 B 列${NAME_HEADER}`);
      }
    }
    if (id === "" && !hasName) continue;
    if (!id || !/^[A-Za-z0-9_-]{1,64}$/.test(id)) {
      errors.push(`第 ${number} 行：请填写文本格式的${EXCEL_HEADER}`);
    } else if (seen.has(id)) {
      duplicates++;
    } else {
      seen.add(id);
      rows.push({ sapId: id, row: number });
    }
  }
  if (!rows.length && !errors.length)
    throw new Error(`请至少填写一个${EXCEL_HEADER}`);
  return { rows, errors, duplicates };
}
