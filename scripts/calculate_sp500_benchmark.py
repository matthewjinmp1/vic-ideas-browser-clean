import argparse
import sqlite3
from bisect import bisect_right
from pathlib import Path


DEFAULT_VIC_DB = Path(__file__).resolve().parents[1] / "data" / "vic_ideas.sqlite"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Calculate idea benchmark/excess returns against S&P 500 Total Return."
    )
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_VIC_DB)
    return parser.parse_args()


def load_sp500_series(conn):
    rows = conn.execute(
        """
        SELECT period, index_value
        FROM sp500_total_return_index
        ORDER BY period
        """
    ).fetchall()
    if not rows:
        raise RuntimeError("sp500_total_return_index is empty. Run fetch_sp500_total_return.py first.")

    return [row[0] for row in rows], [float(row[1]) for row in rows]


def value_at_or_before(periods, values, period):
    index = bisect_right(periods, period) - 1
    if index < 0:
        return None
    return values[index]


def compound_annual_return(total_return_pct, years_held):
    if years_held <= 0:
        return None

    growth_factor = 1 + total_return_pct / 100
    if growth_factor <= 0:
        return None

    return (growth_factor ** (1 / years_held) - 1) * 100


def ensure_columns(conn):
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(idea_total_returns)").fetchall()
    }
    additions = {
        "benchmark_total_return_pct": "REAL",
        "benchmark_annualized_return_pct": "REAL",
        "excess_total_return_pct": "REAL",
        "excess_annualized_return_pct": "REAL",
    }
    for column, column_type in additions.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE idea_total_returns ADD COLUMN {column} {column_type}")


def main():
    args = parse_args()
    conn = sqlite3.connect(args.sqlite)
    ensure_columns(conn)
    periods, values = load_sp500_series(conn)

    conn.execute("DROP TABLE IF EXISTS quickfs_equal_weight_benchmarks")
    conn.execute("DROP TABLE IF EXISTS quickfs_equal_weight_index")

    updates = []
    missing = 0
    for (
        idea_id,
        start_period,
        end_period,
        periods_held,
        idea_total_return,
        idea_annual_return,
    ) in conn.execute(
        """
        SELECT idea_id, start_period, end_period, periods_held,
               idea_total_return_pct, annualized_idea_return_pct
        FROM idea_total_returns
        WHERE start_period IS NOT NULL
          AND end_period IS NOT NULL
          AND periods_held > 0
        """
    ):
        start_value = value_at_or_before(periods, values, start_period)
        end_value = value_at_or_before(periods, values, end_period)
        if start_value is None or end_value is None:
            missing += 1
            continue

        benchmark_total = (end_value / start_value - 1) * 100
        years_held = periods_held / 4
        benchmark_annual = compound_annual_return(benchmark_total, years_held)
        excess_annual = (
            None
            if idea_annual_return is None or benchmark_annual is None
            else idea_annual_return - benchmark_annual
        )
        updates.append(
            (
                benchmark_total,
                benchmark_annual,
                idea_total_return - benchmark_total,
                excess_annual,
                idea_id,
            )
        )

    conn.executemany(
        """
        UPDATE idea_total_returns
        SET benchmark_total_return_pct = ?,
            benchmark_annualized_return_pct = ?,
            excess_total_return_pct = ?,
            excess_annualized_return_pct = ?
        WHERE idea_id = ?
        """,
        updates,
    )
    conn.commit()
    conn.close()

    print(f"sp500_start={periods[0]}")
    print(f"sp500_end={periods[-1]}")
    print(f"ideas_updated={len(updates)}")
    print(f"missing_benchmark={missing}")


if __name__ == "__main__":
    main()
