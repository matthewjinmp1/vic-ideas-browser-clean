import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.calculate_forward_beats import calculate_window_return  # noqa: E402
from scripts.calculate_sp500_benchmark import (  # noqa: E402
    compound_annual_return,
    load_sp500_series,
    value_at_or_before,
)
from scripts.calculate_total_returns import (  # noqa: E402
    DEFAULT_QUICKFS_DB,
    DEFAULT_VIC_DB,
    find_series,
    idea_month,
    load_quickfs_series,
    start_index,
)


GOLDEN_IDEA_IDS = [
    "2b0709d5-827d-4f27-a37b-40f58957fad7",  # long, early
    "2847ee58-17dd-44cd-a31b-3f631bcc725f",  # long, mid-period
    "20deff36-515e-420b-adb9-88e32b4ed8c0",  # long, partial history
    "826d2a8a-6588-4de1-9c0f-a8a9737ce84f",  # short, early
    "5b9b3c8d-3bf9-4521-85d1-8e4d4f3cdd22",  # short, mid-period
    "561375e4-7a59-4dc4-851f-30a1d0ea92ab",  # short, recent
    "faf57bf7-c0d0-4a0c-baa9-450d515c62ee",  # contest winner long
    "8de51575-bb89-416b-8f30-c81cf26216e3",  # contest winner long
    "1fa60957-a33b-4740-97aa-fbe9be4121a8",  # contest winner short
    "ce4f35b9-dbee-4573-8ac0-ae431d2af3a5",  # contest winner short
]

FORWARD_QUARTERS = [4, 20]

FIELDS = [
    "idea_id",
    "ticker",
    "idea_date",
    "is_short",
    "is_contest_winner",
    "matched_ticker",
    "forward_quarters",
    "start_period",
    "end_period",
    "periods_held",
    "years_held",
    "start_price",
    "end_price",
    "dividends",
    "stock_total_return_pct",
    "idea_total_return_pct",
    "idea_annualized_return_pct",
    "sp500_start_value",
    "sp500_end_value",
    "benchmark_total_return_pct",
    "benchmark_annualized_return_pct",
    "excess_annualized_return_pct",
]


def round_value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.10f}"
    return value


def build_rows(vic_db=DEFAULT_VIC_DB, quickfs_db=DEFAULT_QUICKFS_DB):
    quickfs = load_quickfs_series(quickfs_db)
    conn = sqlite3.connect(vic_db)
    sp_periods, sp_values = load_sp500_series(conn)
    placeholders = ",".join("?" for _ in GOLDEN_IDEA_IDS)
    ideas = {
        row[0]: row
        for row in conn.execute(
            f"""
            SELECT id, company_id, date, COALESCE(is_short, 0), COALESCE(is_contest_winner, 0)
            FROM ideas
            WHERE id IN ({placeholders})
            """,
            GOLDEN_IDEA_IDS,
        )
    }
    conn.close()

    rows = []
    for idea_id in GOLDEN_IDEA_IDS:
        idea_id, ticker, idea_date, is_short, is_winner = ideas[idea_id]
        matched_ticker, series = find_series(quickfs, ticker)
        start = start_index(series, idea_month(idea_date))

        for forward_quarters in FORWARD_QUARTERS:
            result = calculate_window_return(series, start, forward_quarters)
            stock_total = result["stock_total_return_pct"]
            idea_total = -stock_total if bool(is_short) else stock_total
            idea_annual = compound_annual_return(idea_total, result["years_held"])
            sp_start = value_at_or_before(
                sp_periods, sp_values, result["start_period"]
            )
            sp_end = value_at_or_before(sp_periods, sp_values, result["end_period"])
            benchmark_total = (sp_end / sp_start - 1) * 100
            benchmark_annual = compound_annual_return(
                benchmark_total, result["years_held"]
            )
            rows.append(
                {
                    "idea_id": idea_id,
                    "ticker": ticker,
                    "idea_date": idea_date,
                    "is_short": int(bool(is_short)),
                    "is_contest_winner": int(bool(is_winner)),
                    "matched_ticker": matched_ticker,
                    "forward_quarters": forward_quarters,
                    "start_period": result["start_period"],
                    "end_period": result["end_period"],
                    "periods_held": result["periods_held"],
                    "years_held": result["years_held"],
                    "start_price": result["start_price"],
                    "end_price": result["end_price"],
                    "dividends": result["dividends"],
                    "stock_total_return_pct": stock_total,
                    "idea_total_return_pct": idea_total,
                    "idea_annualized_return_pct": idea_annual,
                    "sp500_start_value": sp_start,
                    "sp500_end_value": sp_end,
                    "benchmark_total_return_pct": benchmark_total,
                    "benchmark_annualized_return_pct": benchmark_annual,
                    "excess_annualized_return_pct": (
                        None
                        if idea_annual is None or benchmark_annual is None
                        else idea_annual - benchmark_annual
                    ),
                }
            )

    return rows


def main():
    output_path = ROOT / "analysis" / "golden_return_sample.tsv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: round_value(row[field]) for field in FIELDS})

    print(f"wrote {output_path}")
    print(f"rows={len(rows)}")


if __name__ == "__main__":
    main()
