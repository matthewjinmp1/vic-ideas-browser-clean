import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = path.resolve(new URL("..", import.meta.url).pathname);
const inputPath = path.join(ROOT, "analysis", "google_sheet_idea_returns.json");
const outputDir = path.join(ROOT, "outputs", "google-sheet-returns");
const outputPath = path.join(outputDir, "google_sheet_idea_returns.xlsx");

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));

const columns = [
  ["Ticker", "ticker", "text"],
  ["Date", "sheet_date", "date"],
  ["Status", "match_status", "text"],
  ["Direction", "direction", "text"],
  ["VIC DB Direction", "vic_db_direction", "text"],
  ["Company", "company_name", "text"],
  ["DB Company Name", "db_company_name", "text"],
  ["Match Key", "match_key", "text"],
  ["Contest Winner", "is_contest_winner", "bool"],
  ["Matched Ticker", "matched_ticker", "text"],
  ["Start Period", "start_period", "text"],
  ["End Period", "end_period", "text"],
  ["Years Held", "years_held", "number"],
  ["Stock Total Return", "stock_total_return_pct", "pct"],
  ["Idea Total Return", "idea_total_return_pct", "pct"],
  ["Idea Annual Return", "annualized_idea_return_pct", "pct"],
  ["S&P TR Total Return", "benchmark_total_return_pct", "pct"],
  ["S&P TR Annual Return", "benchmark_annualized_return_pct", "pct"],
  ["Total Beat", "excess_total_return_pct", "pct"],
  ["Annual Beat", "excess_annualized_return_pct", "pct"],
  ["Start Price", "start_price", "currency"],
  ["End Price", "end_price", "currency"],
  ["Dividends", "dividends", "currency"],
  ["Idea ID", "idea_id", "text"],
  ["Link", "idea_link", "text"],
];

function sheetSafeName(name) {
  return name.replace(/[\\/?*:[\\]]/g, "").slice(0, 31);
}

function pctValue(value) {
  return value == null ? null : value / 100;
}

function typedValue(value, type) {
  if (value == null) return null;
  if (type === "pct") return pctValue(value);
  if (type === "bool") return value ? "Yes" : "No";
  return value;
}

function writeMatrix(sheet, startRow, startCol, matrix) {
  sheet
    .getRangeByIndexes(startRow, startCol, matrix.length, matrix[0].length)
    .values = matrix;
}

function styleTable(sheet, rowCount, colCount, options = {}) {
  const offset = options.metricOffset ?? 0;
  const all = sheet.getRangeByIndexes(0, 0, rowCount, colCount);
  all.format.font.name = "Aptos";
  all.format.font.size = 10;
  const header = sheet.getRangeByIndexes(0, 0, 1, colCount);
  header.format.fill.color = "#25324A";
  header.format.font.color = "#FFFFFF";
  header.format.font.bold = true;
  header.format.rowHeight = 24;
  header.format.wrapText = true;
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;

  const body = sheet.getRangeByIndexes(1, 0, Math.max(1, rowCount - 1), colCount);
  body.format.borders = {
    insideHorizontal: { style: "thin", color: "#E3E7ED" },
  };

  const pctCols = [13, 14, 15, 16, 17, 18, 19].map((col) => col + offset);
  for (const col of pctCols) {
    if (col < colCount) {
      sheet.getRangeByIndexes(1, col, Math.max(1, rowCount - 1), 1).setNumberFormat("0.0%");
    }
  }
  for (const col of [20, 21, 22].map((col) => col + offset)) {
    if (col < colCount) {
      sheet.getRangeByIndexes(1, col, Math.max(1, rowCount - 1), 1).setNumberFormat("$#,##0.00");
    }
  }
  if (12 + offset < colCount) {
    sheet.getRangeByIndexes(1, 12 + offset, Math.max(1, rowCount - 1), 1).setNumberFormat("0.0");
  }
  sheet.getRangeByIndexes(1, 0, Math.max(1, rowCount - 1), colCount).format.rowHeight = 20;

  const widths = [
    11, 12, 42, 14, 14, 28, 24, 16, 14, 14, 12, 12, 11, 14, 14, 14, 15, 15, 12,
    12, 12, 12, 12, 38, 42,
  ];
  const finalWidths = options.prependWidths ? [...options.prependWidths, ...widths] : widths;
  finalWidths.slice(0, colCount).forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, rowCount, 1).format.columnWidth = width;
  });
}

const workbook = Workbook.create();

const summarySheet = workbook.worksheets.add("Summary");
summarySheet.showGridLines = false;
summarySheet.getRange("A1:H1").merge();
summarySheet.getRange("A1").values = [["Google Sheet Idea Returns"]];
summarySheet.getRange("A1").format.font.bold = true;
summarySheet.getRange("A1").format.font.size = 16;
summarySheet.getRange("A1").format.fill.color = "#EAF0F6";
summarySheet.getRange("A1").format.rowHeight = 30;

const summaryHeaders = [
  "Sheet",
  "Rows",
  "Exact VIC Matches",
  "Assumed Long Calculated",
  "Rows With Returns",
  "Avg Annual Return",
  "Avg Annual Beat",
  "Note",
];
const summaryRows = Object.entries(payload.summary).map(([sheet, data]) => [
  sheet,
  data.total_rows,
  data.exact_vic_matches,
  data.assumed_long_calculated,
  data.with_returns,
  pctValue(data.avg_annual_return_pct),
  pctValue(data.avg_annual_beat_pct),
  "All rows are calculated as long. VIC DB Direction is included only as an audit column.",
]);
writeMatrix(summarySheet, 2, 0, [summaryHeaders, ...summaryRows]);
styleTable(summarySheet, summaryRows.length + 3, summaryHeaders.length);
summarySheet.getRange("F4:G6").setNumberFormat("0.0%");
summarySheet.getRangeByIndexes(2, 0, 1, summaryHeaders.length).format.fill.color = "#25324A";
summarySheet.getRangeByIndexes(2, 0, 1, summaryHeaders.length).format.font.color = "#FFFFFF";
summarySheet.getRangeByIndexes(2, 0, 1, summaryHeaders.length).format.font.bold = true;
summarySheet.getRangeByIndexes(0, 0, summaryRows.length + 3, 1).format.columnWidth = 28;
summarySheet.getRangeByIndexes(0, 1, summaryRows.length + 3, 1).format.columnWidth = 10;
summarySheet.getRangeByIndexes(0, 2, summaryRows.length + 3, 1).format.columnWidth = 18;
summarySheet.getRangeByIndexes(0, 3, summaryRows.length + 3, 1).format.columnWidth = 24;
summarySheet.getRangeByIndexes(0, 4, summaryRows.length + 3, 1).format.columnWidth = 18;
summarySheet.getRangeByIndexes(0, 5, summaryRows.length + 3, 2).format.columnWidth = 16;
summarySheet.getRangeByIndexes(0, 7, summaryRows.length + 3, 1).format.wrapText = true;
summarySheet.getRangeByIndexes(0, 7, summaryRows.length + 3, 1).format.columnWidth = 78;

const sourceSheets = [...new Set(payload.rows.map((row) => row.source_sheet))];
const allStocks = workbook.worksheets.add("All Individual Stocks");
const allColumns = [["Group", "source_sheet", "text"], ...columns];
const allMatrix = [
  allColumns.map((column) => column[0]),
  ...payload.rows.map((row) =>
    allColumns.map(([, key, type]) => typedValue(row[key], type)),
  ),
];
writeMatrix(allStocks, 0, 0, allMatrix);
styleTable(allStocks, allMatrix.length, allColumns.length, {
  metricOffset: 1,
  prependWidths: [28],
});

for (const sourceSheet of sourceSheets) {
  const ws = workbook.worksheets.add(sheetSafeName(sourceSheet));
  const rows = payload.rows.filter((row) => row.source_sheet === sourceSheet);
  const matrix = [
    columns.map((column) => column[0]),
    ...rows.map((row) =>
      columns.map(([, key, type]) => typedValue(row[key], type)),
    ),
  ];
  writeMatrix(ws, 0, 0, matrix);
  styleTable(ws, matrix.length, columns.length);
}

const notes = workbook.worksheets.add("Method Notes");
notes.showGridLines = false;
notes.getRange("A1:D1").merge();
notes.getRange("A1").values = [["Method Notes"]];
notes.getRange("A1").format.font.bold = true;
notes.getRange("A1").format.font.size = 16;
notes.getRange("A1").format.fill.color = "#EAF0F6";
writeMatrix(notes, 2, 0, [
  ["Topic", "Method"],
  ["Input", "Ticker and date rows from the three visible tabs in the shared Google Sheet export."],
  ["Exact match", "Ticker plus date matched against the local VIC ideas SQLite database. The Match Key column shows the exact ticker|date key used."],
  ["Company/title", "Company uses the local idea-link slug when present, because the ticker-level company table can be ambiguous for reused tickers such as TSCO. DB Company Name is preserved as an audit column."],
  ["Direction", "Every row in these three ranking sheets is calculated as a long idea. VIC DB Direction is preserved only as an audit column for exact local DB matches."],
  ["Fallback", "If no local VIC idea match exists, returns are calculated as long from QuickFS ticker/date data and clearly flagged."],
  ["Start date", "First available QuickFS period on or after the idea month."],
  ["End date", "Most recent available QuickFS period for that ticker."],
  ["Dividends", "Dividends are summed only after the start period through the end period."],
  ["Annual return", "Compounded annual return, not linear average."],
  ["Benchmark", "S&P 500 Total Return index matched at or before the same start and end periods."],
  ["Beat", "Long idea annual return minus S&P TR annual return; total beat is long idea total return minus S&P TR total return."],
]);
styleTable(notes, 14, 2);
notes.getRange("B:B").format.columnWidth = 88;
notes.getRange("B:B").format.wrapText = true;

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
