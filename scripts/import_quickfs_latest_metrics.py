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
        description="Import latest QuickFS company metrics used by spreadsheet exports."
    )
    parser.add_argument("--vic-db", type=Path, default=DEFAULT_VIC_DB)
    parser.add_argument("--quickfs-db", type=Path, default=DEFAULT_QUICKFS_DB)
    return parser.parse_args()


def latest_numeric_metric(periods, values):
    for period, value in reversed(list(zip(periods, values))):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue

        return str(period), numeric_value

    return None, None


def main():
    args = parse_args()
    source = sqlite3.connect(args.quickfs_db)
    destination = sqlite3.connect(args.vic_db)
    computed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    destination.execute("DROP TABLE IF EXISTS quickfs_latest_metrics")
    destination.execute(
        """
        CREATE TABLE quickfs_latest_metrics (
            ticker TEXT NOT NULL PRIMARY KEY,
            company_name TEXT,
            exchange TEXT,
            latest_revenue REAL,
            latest_revenue_period TEXT,
            quickfs_updated_at TEXT,
            computed_at TEXT NOT NULL
        )
        """
    )

    rows = []
    missing_revenue = 0
    for ticker, company_name, exchange, data_json, updated_at in source.execute(
        "SELECT ticker, company_name, exchange, data_json, updated_at FROM financials"
    ):
        try:
            data = json.loads(data_json)
        except json.JSONDecodeError:
            continue

        revenue_period, latest_revenue = latest_numeric_metric(
            data.get("period_end_date") or [],
            data.get("revenue") or [],
        )
        if latest_revenue is None:
            missing_revenue += 1

        rows.append(
            (
                ticker.upper(),
                company_name,
                exchange,
                latest_revenue,
                revenue_period,
                updated_at,
                computed_at,
            )
        )

    destination.executemany(
        """
        INSERT INTO quickfs_latest_metrics (
            ticker, company_name, exchange, latest_revenue, latest_revenue_period,
            quickfs_updated_at, computed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    destination.commit()
    source.close()
    destination.close()

    print(f"quickfs_rows={len(rows)}")
    print(f"missing_revenue={missing_revenue}")


if __name__ == "__main__":
    main()
