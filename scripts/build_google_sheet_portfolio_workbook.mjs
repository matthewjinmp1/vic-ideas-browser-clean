import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPath = "/private/tmp/vic_google_sheet_portfolios.json";
const outputPath = "/private/tmp/vic_ranking_portfolio_returns.xlsx";

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));

function pct(value) {
  return value == null ? null : value / 100;
}

function writeMatrix(sheet, matrix) {
  sheet.getRangeByIndexes(0, 0, matrix.length, matrix[0].length).values = matrix;
}

function styleSheet(sheet, rows, cols, pctColumns = [], currencyColumns = []) {
  const all = sheet.getRangeByIndexes(0, 0, rows, cols);
  all.format.font.name = "Aptos";
  all.format.font.size = 10;
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);

  const header = sheet.getRangeByIndexes(0, 0, 1, cols);
  header.format.fill.color = "#25324A";
  header.format.font.color = "#FFFFFF";
  header.format.font.bold = true;
  header.format.wrapText = true;
  header.format.rowHeight = 26;

  if (rows > 1) {
    sheet.getRangeByIndexes(1, 0, rows - 1, cols).format.borders = {
      insideHorizontal: { style: "thin", color: "#E3E7ED" },
    };
  }

  for (const col of pctColumns) {
    sheet.getRangeByIndexes(1, col, Math.max(1, rows - 1), 1).setNumberFormat("0.0%");
  }
  for (const col of currencyColumns) {
    sheet.getRangeByIndexes(1, col, Math.max(1, rows - 1), 1).setNumberFormat("$#,##0.00");
  }
}

const workbook = Workbook.create();

const summary = workbook.worksheets.add("Summary");
const summaryRows = [
  [
    "Portfolio",
    "Initial Capital",
    "Final Value",
    "Total Return",
    "Annualized Return",
    "S&P 500 TR Final Value",
    "S&P 500 TR Total Return",
    "S&P 500 TR Annual Return",
    "Total Beat",
    "Annualized Beat",
    "Start Period",
    "End Period",
    "Years",
    "Ideas Included",
    "Ideas Skipped",
    "Duplicate Ticker/Date Rows",
  ],
];

for (const [name, result] of Object.entries(payload.portfolios)) {
  const item = result.summary;
  summaryRows.push([
    name,
    item.initial_capital,
    item.final_value,
    pct(item.total_return_pct),
    pct(item.annualized_return_pct),
    item.sp500_final_value,
    pct(item.sp500_total_return_pct),
    pct(item.sp500_annualized_return_pct),
    pct(item.total_beat_pct),
    pct(item.annualized_beat_pct),
    item.start_period,
    item.end_period,
    item.years,
    item.ideas_included,
    item.ideas_skipped,
    item.duplicate_ticker_date_rows,
  ]);
}
writeMatrix(summary, summaryRows);
styleSheet(summary, summaryRows.length, summaryRows[0].length, [3, 4, 6, 7, 8, 9], [1, 2, 5]);
[
  30, 16, 16, 14, 14, 18, 16, 16, 14, 14, 12, 12, 10, 14, 14, 20,
].forEach((width, index) => {
  summary.getRangeByIndexes(0, index, summaryRows.length, 1).format.columnWidth = width;
});

const nav = workbook.worksheets.add("Portfolio NAV");
const navRows = [
  [
    "Portfolio",
    "Period",
    "Portfolio Value",
    "Cash",
    "Active Positions",
    "New Positions",
    "Exited Positions",
    "Rebalanced",
    "Total Positions Added",
  ],
];
for (const [name, result] of Object.entries(payload.portfolios)) {
  for (const row of result.nav_rows) {
    navRows.push([
      name,
      row.period,
      row.portfolio_value,
      row.cash,
      row.active_positions,
      row.new_positions,
      row.exited_positions,
      row.rebalanced ? "Yes" : "No",
      row.total_positions_added,
    ]);
  }
}
writeMatrix(nav, navRows);
styleSheet(nav, navRows.length, navRows[0].length, [], [2, 3]);
[30, 12, 16, 14, 14, 14, 14, 12, 18].forEach((width, index) => {
  nav.getRangeByIndexes(0, index, navRows.length, 1).format.columnWidth = width;
});

const constituents = workbook.worksheets.add("Constituents");
const constituentRows = [
  [
    "Portfolio",
    "Group",
    "Source Row",
    "Ticker",
    "Matched Ticker",
    "Company",
    "Idea Date",
    "Start Period",
    "End Period",
    "Initial Allocated Value",
    "Final Value",
    "Duplicate Key",
  ],
];
for (const [name, result] of Object.entries(payload.portfolios)) {
  for (const row of result.constituents) {
    constituentRows.push([
      name,
      row.group,
      row.source_row,
      row.ticker,
      row.matched_ticker,
      row.company,
      row.sheet_date,
      row.start_period,
      row.end_period,
      row.initial_allocated_value,
      row.final_value,
      row.duplicate_key,
    ]);
  }
}
writeMatrix(constituents, constituentRows);
styleSheet(constituents, constituentRows.length, constituentRows[0].length, [], [9, 10]);
[30, 28, 11, 12, 14, 28, 12, 12, 12, 18, 16, 34].forEach((width, index) => {
  constituents.getRangeByIndexes(0, index, constituentRows.length, 1).format.columnWidth = width;
});

const annual = workbook.worksheets.add("Annual Returns");
const annualRows = [
  [
    "Portfolio",
    "Year",
    "Period",
    "Portfolio Return",
    "S&P 500 TR Return",
    "Annual Beat",
    "Portfolio Value",
  ],
];
for (const [name, result] of Object.entries(payload.portfolios)) {
  for (const row of result.annual_return_rows ?? []) {
    annualRows.push([
      name,
      row.year,
      row.period,
      pct(row.portfolio_return_pct),
      pct(row.sp500_return_pct),
      pct(row.annual_beat_pct),
      row.portfolio_value,
    ]);
  }
}
writeMatrix(annual, annualRows);
styleSheet(annual, annualRows.length, annualRows[0].length, [3, 4, 5], [6]);
[30, 10, 12, 16, 16, 14, 16].forEach((width, index) => {
  annual.getRangeByIndexes(0, index, annualRows.length, 1).format.columnWidth = width;
});

const notes = workbook.worksheets.add("Method Notes");
const noteRows = [
  ["Topic", "Note"],
  ["Method", payload.method],
  [
    "Why this exists",
    "Simple average CAGR can misrepresent skewed stock returns. This sheet simulates dollars in a portfolio instead.",
  ],
  [
    "Rebalance rule",
    "At each new idea start period, all currently active positions plus new ideas are rebalanced to equal dollar weights. Exits also trigger immediate rebalancing across remaining active positions.",
  ],
  [
    "Benchmark",
    "S&P 500 Total Return is measured from the portfolio's first calculable start period to its ending period. Beat is portfolio return minus S&P 500 Total Return over that same window.",
  ],
  [
    "Annual Returns",
    "The Annual Returns tab uses the last available portfolio NAV period in each calendar year. The first live year is blank because there is no prior year-end portfolio value.",
  ],
  ["Entry", "A position enters at the first available local QuickFS period on or after the idea month."],
  [
    "Exit",
    "A position exits at its last available local QuickFS period. If other positions remain active, proceeds are immediately rebalanced into them. If none remain, proceeds stay in cash until the next calculable idea enters.",
  ],
  ["Dividends", "Dividends are included in period returns when the stock has a new available price period."],
  ["Missing data", "Rows without usable local QuickFS start/end data are skipped."],
  [
    "Duplicates",
    "Duplicate ticker/date rows are counted as separate idea rows, which intentionally overweights them; duplicate counts are shown.",
  ],
  [
    "Caveat",
    "This is not a real trade blotter. It is an approximate equal-weight portfolio based on available local quarter/month-end data.",
  ],
];
writeMatrix(notes, noteRows);
styleSheet(notes, noteRows.length, noteRows[0].length);
notes.getRangeByIndexes(0, 0, noteRows.length, 1).format.columnWidth = 22;
notes.getRangeByIndexes(0, 1, noteRows.length, 1).format.columnWidth = 110;
notes.getRangeByIndexes(0, 1, noteRows.length, 1).format.wrapText = true;

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
