import argparse
import datetime as dt
import sqlite3
import urllib.parse
from pathlib import Path

import requests


DEFAULT_VIC_DB = Path(__file__).resolve().parents[1] / "data" / "vic_ideas.sqlite"
SYMBOL = "^SP500TR"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch S&P 500 Total Return Index monthly history into SQLite."
    )
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_VIC_DB)
    parser.add_argument("--start-year", type=int, default=1988)
    return parser.parse_args()


def timestamp(year, month, day):
    return int(dt.datetime(year, month, day, tzinfo=dt.timezone.utc).timestamp())


def fetch_monthly_history(start_year):
    period1 = timestamp(start_year, 1, 1)
    period2 = int(dt.datetime.now(dt.timezone.utc).timestamp())
    encoded_symbol = urllib.parse.quote(SYMBOL, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
        f"?period1={period1}&period2={period2}&interval=1mo"
        "&events=history&includeAdjustedClose=true"
    )
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    payload = response.json()
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"No chart data returned for {SYMBOL}")

    timestamps = result.get("timestamp") or []
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    rows = []

    for raw_timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        date = dt.datetime.fromtimestamp(raw_timestamp, tz=dt.timezone.utc).date()
        rows.append((date.isoformat(), date.strftime("%Y-%m"), float(close)))

    rows.sort(key=lambda row: row[0])
    return rows


def store_rows(path, rows):
    computed_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE IF EXISTS sp500_total_return_index")
    conn.execute(
        """
        CREATE TABLE sp500_total_return_index (
            date TEXT NOT NULL PRIMARY KEY,
            period TEXT NOT NULL,
            index_value REAL NOT NULL,
            normalized_value REAL NOT NULL,
            period_return_pct REAL,
            cumulative_return_pct REAL NOT NULL,
            source TEXT NOT NULL,
            computed_at TEXT NOT NULL
        )
        """
    )

    stored = []
    first_value = rows[0][2]
    previous_value = None
    for date, period, index_value in rows:
        normalized_value = index_value / first_value * 100
        period_return = (
            None if previous_value is None else (index_value / previous_value - 1) * 100
        )
        cumulative_return = (index_value / first_value - 1) * 100
        stored.append(
            (
                date,
                period,
                index_value,
                normalized_value,
                period_return,
                cumulative_return,
                "Yahoo Finance ^SP500TR monthly close",
                computed_at,
            )
        )
        previous_value = index_value

    conn.executemany(
        """
        INSERT INTO sp500_total_return_index (
            date, period, index_value, normalized_value, period_return_pct,
            cumulative_return_pct, source, computed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        stored,
    )
    conn.commit()
    conn.close()


def main():
    args = parse_args()
    rows = fetch_monthly_history(args.start_year)
    if not rows:
        raise RuntimeError("No S&P 500 Total Return rows fetched")
    store_rows(args.sqlite, rows)
    print(f"symbol={SYMBOL}")
    print(f"rows={len(rows)}")
    print(f"start={rows[0][0]} value={rows[0][2]:.2f}")
    print(f"end={rows[-1][0]} value={rows[-1][2]:.2f}")


if __name__ == "__main__":
    main()
