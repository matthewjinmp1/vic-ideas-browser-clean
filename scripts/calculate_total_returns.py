import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_VIC_DB = Path(__file__).resolve().parents[1] / "data" / "vic_ideas.sqlite"
DEFAULT_QUICKFS_DB = Path(
    "/Users/matthewjohnson/Downloads/stock_analysis/AI_stock_scorer/data/financials.db"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Calculate approximate VIC idea total returns from local QuickFS quarterly data."
    )
    parser.add_argument("--vic-db", type=Path, default=DEFAULT_VIC_DB)
    parser.add_argument("--quickfs-db", type=Path, default=DEFAULT_QUICKFS_DB)
    return parser.parse_args()


def normalize_ticker(ticker):
    return (ticker or "").strip().upper()


def candidate_tickers(ticker):
    normalized = normalize_ticker(ticker)
    candidates = [normalized]

    if "." in normalized:
        candidates.append(normalized.replace(".", "-"))
    if "-" in normalized:
        candidates.append(normalized.replace("-", "."))
    if "/" in normalized:
        candidates.extend(part.strip() for part in normalized.split("/") if part.strip())

    seen = set()
    result = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def load_quickfs_series(path):
    conn = sqlite3.connect(path)
    quickfs = {}

    for ticker, data_json in conn.execute("SELECT ticker, data_json FROM financials"):
        try:
            data = json.loads(data_json)
        except json.JSONDecodeError:
            continue

        dates = data.get("period_end_date") or []
        prices = data.get("period_end_price") or []
        dividends = data.get("dividends") or []
        if not (len(dates) == len(prices) == len(dividends)):
            continue

        rows = []
        for period, price, dividend in zip(dates, prices, dividends):
            try:
                price_value = float(price or 0)
                dividend_value = float(dividend or 0)
            except (TypeError, ValueError):
                continue

            if period and price_value > 0:
                rows.append((str(period), price_value, dividend_value))

        rows.sort(key=lambda row: row[0])
        if rows:
            quickfs[normalize_ticker(ticker)] = rows

    conn.close()
    return quickfs


def find_series(quickfs, ticker):
    for candidate in candidate_tickers(ticker):
        if candidate in quickfs:
            return candidate, quickfs[candidate]
    return None, None


def idea_month(idea_date):
    return str(idea_date)[:7]


def start_index(series, target_month):
    for index, row in enumerate(series):
        if row[0] >= target_month:
            return index
    return None


def calculate_return(series, start):
    end = len(series) - 1
    start_period, start_price, _ = series[start]
    end_period, end_price, _ = series[end]
    dividends = sum(row[2] for row in series[start + 1 : end + 1])
    stock_return = ((end_price + dividends) / start_price - 1) * 100

    return {
        "start_period": start_period,
        "end_period": end_period,
        "start_price": start_price,
        "end_price": end_price,
        "dividends": dividends,
        "stock_total_return_pct": stock_return,
        "periods_held": end - start,
    }


def compound_annual_return(total_return_pct, years_held):
    if years_held <= 0:
        return None

    growth_factor = 1 + total_return_pct / 100
    if growth_factor <= 0:
        return None

    return (growth_factor ** (1 / years_held) - 1) * 100


def ensure_table(conn):
    conn.execute("DROP TABLE IF EXISTS idea_total_returns")
    conn.execute(
        """
        CREATE TABLE idea_total_returns (
            idea_id TEXT NOT NULL PRIMARY KEY,
            ticker TEXT NOT NULL,
            matched_ticker TEXT NOT NULL,
            start_period TEXT NOT NULL,
            end_period TEXT NOT NULL,
            start_price REAL NOT NULL,
            end_price REAL NOT NULL,
            dividends REAL NOT NULL,
            stock_total_return_pct REAL NOT NULL,
            idea_total_return_pct REAL NOT NULL,
            annualized_idea_return_pct REAL,
            periods_held INTEGER NOT NULL,
            calculation_note TEXT NOT NULL,
            computed_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_idea_total_returns_ticker ON idea_total_returns(ticker)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_idea_total_returns_idea_return "
        "ON idea_total_returns(idea_total_return_pct)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_idea_total_returns_annualized_return "
        "ON idea_total_returns(annualized_idea_return_pct)"
    )


def main():
    args = parse_args()
    quickfs = load_quickfs_series(args.quickfs_db)
    conn = sqlite3.connect(args.vic_db)
    ensure_table(conn)
    conn.execute("DELETE FROM idea_total_returns")

    ideas = conn.execute(
        """
        SELECT id, company_id, date, is_short
        FROM ideas
        WHERE id IS NOT NULL
          AND company_id IS NOT NULL
          AND date IS NOT NULL
        """
    ).fetchall()

    computed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    note = (
        "Approximate return from local QuickFS quarter-end prices plus dividends; "
        "start period is the first available QuickFS period on or after the idea month; "
        "annual return is compounded CAGR when the directional return has a positive growth factor."
    )
    rows = []
    missing_ticker = missing_start = stale = 0

    for idea_id, ticker, date_value, is_short in ideas:
        matched_ticker, series = find_series(quickfs, ticker)
        if not series:
            missing_ticker += 1
            continue

        start = start_index(series, idea_month(date_value))
        if start is None:
            missing_start += 1
            continue
        if start >= len(series) - 1:
            stale += 1
            continue

        result = calculate_return(series, start)
        stock_return = result["stock_total_return_pct"]
        idea_return = -stock_return if bool(is_short) else stock_return
        years_held = result["periods_held"] / 4
        annualized_return = compound_annual_return(idea_return, years_held)
        rows.append(
            (
                idea_id,
                ticker,
                matched_ticker,
                result["start_period"],
                result["end_period"],
                result["start_price"],
                result["end_price"],
                result["dividends"],
                stock_return,
                idea_return,
                annualized_return,
                result["periods_held"],
                note,
                computed_at,
            )
        )

    conn.executemany(
        """
        INSERT INTO idea_total_returns (
            idea_id, ticker, matched_ticker, start_period, end_period,
            start_price, end_price, dividends, stock_total_return_pct,
            idea_total_return_pct, annualized_idea_return_pct, periods_held,
            calculation_note, computed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()

    print(f"ideas={len(ideas)}")
    print(f"quickfs_tickers={len(quickfs)}")
    print(f"returns_computed={len(rows)}")
    print(f"missing_ticker={missing_ticker}")
    print(f"missing_start_period={missing_start}")
    print(f"no_later_period={stale}")


if __name__ == "__main__":
    main()
