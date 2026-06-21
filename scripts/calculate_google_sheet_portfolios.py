import argparse
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.calculate_total_returns import (  # noqa: E402
    DEFAULT_QUICKFS_DB,
    DEFAULT_VIC_DB,
    compound_annual_return,
    load_quickfs_series,
    normalize_ticker,
)
from scripts.calculate_sp500_benchmark import (  # noqa: E402
    load_sp500_series,
    value_at_or_before,
)


DEFAULT_INPUT = ROOT / "analysis" / "google_sheet_idea_returns.json"
DEFAULT_OUTPUT = Path("/private/tmp/vic_google_sheet_portfolios.json")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Simulate expanding equal-weight portfolios from Google Sheet idea groups."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--quickfs-db", type=Path, default=DEFAULT_QUICKFS_DB)
    parser.add_argument("--vic-db", type=Path, default=DEFAULT_VIC_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--initial-capital", type=float, default=100.0)
    return parser.parse_args()


def series_maps(series):
    return {
        "price": {period: price for period, price, _ in series},
        "dividend": {period: dividend for period, _, dividend in series},
        "periods": [period for period, _, _ in series],
    }


def position_period_return(position, current_period):
    price_map = position["price_map"]
    dividend_map = position["dividend_map"]
    previous_period = position["last_period"]
    if previous_period == current_period:
        return 0.0
    if current_period not in price_map:
        return 0.0
    if previous_period not in price_map:
        return None
    previous_price = price_map[previous_period]
    current_price = price_map[current_period]
    dividend = dividend_map.get(current_period, 0.0)
    if previous_price <= 0:
        return None
    return (current_price + dividend) / previous_price - 1


def rebalance_equal_weight(active_positions, cash):
    if not active_positions:
        return cash
    total_value = cash + sum(position["value"] for position in active_positions)
    target = total_value / len(active_positions)
    for position in active_positions:
        position["value"] = target
    return 0.0


def simulate_expanding_equal_weight_portfolio(
    ideas,
    quickfs,
    initial_capital=100.0,
):
    positions_by_start = defaultdict(list)
    skipped = Counter()
    duplicate_keys = Counter()

    for index, idea in enumerate(ideas, start=1):
        matched_ticker = normalize_ticker(idea.get("matched_ticker"))
        start_period = idea.get("start_period")
        end_period = idea.get("end_period")
        if not matched_ticker or not start_period or not end_period:
            skipped["missing_return_data"] += 1
            continue
        series = quickfs.get(matched_ticker)
        if not series:
            skipped["missing_quickfs_series"] += 1
            continue
        maps = series_maps(series)
        if start_period not in maps["price"] or end_period not in maps["price"]:
            skipped["missing_start_or_end_price"] += 1
            continue
        if start_period >= end_period:
            skipped["no_holding_period"] += 1
            continue

        duplicate_key = (
            idea.get("source_sheet"),
            idea.get("ticker"),
            idea.get("sheet_date"),
        )
        duplicate_keys[duplicate_key] += 1
        positions_by_start[start_period].append(
            {
                "id": f"{idea.get('source_sheet')}:{idea.get('source_row')}:{index}",
                "group": idea.get("source_sheet"),
                "source_row": idea.get("source_row"),
                "ticker": idea.get("ticker"),
                "matched_ticker": matched_ticker,
                "company": idea.get("company_name"),
                "sheet_date": idea.get("sheet_date"),
                "start_period": start_period,
                "end_period": end_period,
                "price_map": maps["price"],
                "dividend_map": maps["dividend"],
                "last_period": start_period,
                "value": 0.0,
                "initial_weight": None,
                "final_value": None,
                "duplicate_key": "|".join(str(part) for part in duplicate_key),
            }
        )

    periods = sorted(
        {
            period
            for positions in positions_by_start.values()
            for position in positions
            for period in position["price_map"]
            if position["start_period"] <= period <= position["end_period"]
        }
    )
    if not periods:
        return {
            "summary": {
                "initial_capital": initial_capital,
                "final_value": None,
                "total_return_pct": None,
                "annualized_return_pct": None,
                "start_period": None,
                "end_period": None,
                "ideas_included": 0,
                "ideas_skipped": sum(skipped.values()),
                "duplicate_ticker_date_rows": 0,
            },
            "nav_rows": [],
            "constituents": [],
            "skipped": dict(skipped),
        }

    active = []
    closed_positions = []
    cash = float(initial_capital)
    nav_rows = []
    additions_count = 0
    start_period = None

    for period in periods:
        exited_positions = 0
        for position in list(active):
            period_return = position_period_return(position, period)
            if period_return is None:
                skipped["missing_intermediate_price"] += 1
                active.remove(position)
                cash += position["value"]
                position["final_value"] = position["value"]
                closed_positions.append(position)
                exited_positions += 1
                continue
            position["value"] *= 1 + period_return
            if period in position["price_map"]:
                position["last_period"] = period

        for position in list(active):
            if position["end_period"] == period:
                active.remove(position)
                cash += position["value"]
                position["final_value"] = position["value"]
                closed_positions.append(position)
                exited_positions += 1

        new_positions = positions_by_start.get(period, [])
        rebalanced = False
        if new_positions:
            active.extend(new_positions)
            cash = rebalance_equal_weight(active, cash)
            rebalanced = True
            additions_count += len(new_positions)
            if start_period is None:
                start_period = period
            for position in active:
                if position["initial_weight"] is None:
                    position["initial_weight"] = position["value"]
        elif exited_positions and active:
            cash = rebalance_equal_weight(active, cash)
            rebalanced = True

        portfolio_value = cash + sum(position["value"] for position in active)
        nav_rows.append(
            {
                "period": period,
                "portfolio_value": portfolio_value,
                "cash": cash,
                "active_positions": len(active),
                "new_positions": len(new_positions),
                "exited_positions": exited_positions,
                "rebalanced": rebalanced,
                "total_positions_added": additions_count,
            }
        )

    final_value = nav_rows[-1]["portfolio_value"]
    end_period = nav_rows[-1]["period"]
    years = years_between_periods(start_period, end_period) if start_period else None
    total_return_pct = (final_value / initial_capital - 1) * 100
    annualized_return_pct = (
        compound_annual_return(total_return_pct, years)
        if years and final_value > 0
        else None
    )

    for position in active:
        position["final_value"] = position["value"]
    constituents = closed_positions + active
    duplicate_count = sum(count - 1 for count in duplicate_keys.values() if count > 1)

    return {
        "summary": {
            "initial_capital": initial_capital,
            "final_value": final_value,
            "total_return_pct": total_return_pct,
            "annualized_return_pct": annualized_return_pct,
            "start_period": start_period,
            "end_period": end_period,
            "years": years,
            "ideas_included": additions_count,
            "ideas_skipped": sum(skipped.values()),
            "duplicate_ticker_date_rows": duplicate_count,
        },
        "nav_rows": nav_rows,
        "constituents": [
            {
                "group": position["group"],
                "source_row": position["source_row"],
                "ticker": position["ticker"],
                "matched_ticker": position["matched_ticker"],
                "company": position["company"],
                "sheet_date": position["sheet_date"],
                "start_period": position["start_period"],
                "end_period": position["end_period"],
                "initial_allocated_value": position["initial_weight"],
                "final_value": position["final_value"],
                "duplicate_key": position["duplicate_key"],
            }
            for position in constituents
        ],
        "skipped": dict(skipped),
    }


def years_between_periods(start_period, end_period):
    start_year, start_month = [int(part) for part in start_period.split("-")]
    end_year, end_month = [int(part) for part in end_period.split("-")]
    months = (end_year - start_year) * 12 + (end_month - start_month)
    return months / 12


def simulate_groups(rows, quickfs, initial_capital=100.0):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["source_sheet"]].append(row)

    results = {}
    for group, ideas in grouped.items():
        ideas.sort(key=lambda row: (row.get("start_period") or "9999-99", row["source_row"]))
        results[group] = simulate_expanding_equal_weight_portfolio(
            ideas,
            quickfs,
            initial_capital=initial_capital,
        )
    all_ideas = sorted(
        rows,
        key=lambda row: (
            row.get("start_period") or "9999-99",
            row["source_sheet"],
            row["source_row"],
        ),
    )
    results["All Three Sheets Combined"] = simulate_expanding_equal_weight_portfolio(
        all_ideas,
        quickfs,
        initial_capital=initial_capital,
    )
    return results


def add_sp500_benchmarks(portfolios, sp500_periods, sp500_values):
    for result in portfolios.values():
        summary = result["summary"]
        start_period = summary.get("start_period")
        end_period = summary.get("end_period")
        initial_capital = summary.get("initial_capital")
        years = summary.get("years")
        if not start_period or not end_period or initial_capital is None:
            summary.update(empty_benchmark())
            continue

        start_value = value_at_or_before(sp500_periods, sp500_values, start_period)
        end_value = value_at_or_before(sp500_periods, sp500_values, end_period)
        if start_value is None or end_value is None:
            summary.update(empty_benchmark())
            continue

        benchmark_total_return_pct = (end_value / start_value - 1) * 100
        benchmark_final_value = initial_capital * (end_value / start_value)
        benchmark_annualized_return_pct = (
            compound_annual_return(benchmark_total_return_pct, years)
            if years
            else None
        )
        annualized_return_pct = summary.get("annualized_return_pct")
        summary.update(
            {
                "sp500_final_value": benchmark_final_value,
                "sp500_total_return_pct": benchmark_total_return_pct,
                "sp500_annualized_return_pct": benchmark_annualized_return_pct,
                "annualized_beat_pct": (
                    None
                    if annualized_return_pct is None
                    or benchmark_annualized_return_pct is None
                    else annualized_return_pct - benchmark_annualized_return_pct
                ),
                "total_beat_pct": (
                    None
                    if summary.get("total_return_pct") is None
                    else summary["total_return_pct"] - benchmark_total_return_pct
                ),
            }
        )


def empty_benchmark():
    return {
        "sp500_final_value": None,
        "sp500_total_return_pct": None,
        "sp500_annualized_return_pct": None,
        "annualized_beat_pct": None,
        "total_beat_pct": None,
    }


def scrub_float(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def main():
    args = parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    quickfs = load_quickfs_series(args.quickfs_db)
    portfolios = simulate_groups(payload["rows"], quickfs, args.initial_capital)
    conn = sqlite3.connect(args.vic_db)
    sp500_periods, sp500_values = load_sp500_series(conn)
    conn.close()
    add_sp500_benchmarks(portfolios, sp500_periods, sp500_values)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": (
            "Expanding equal-weight long portfolio. Starts with initial capital in the first "
            "calculable idea. On each new idea start period, rebalances all active positions "
            "equally. When positions exit, sale proceeds are immediately rebalanced across "
            "remaining active positions. If no active positions remain, proceeds stay in cash "
            "until the next calculable idea enters."
        ),
        "portfolios": portfolios,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, default=scrub_float),
        encoding="utf-8",
    )

    for name, result in portfolios.items():
        summary = result["summary"]
        print(
            f"{name}: final={summary['final_value']:.2f} "
            f"total={summary['total_return_pct']:.2f}% "
            f"annual={summary['annualized_return_pct']:.2f}% "
            f"sp500_annual={summary['sp500_annualized_return_pct']:.2f}% "
            f"beat={summary['annualized_beat_pct']:.2f}% "
            f"included={summary['ideas_included']} skipped={summary['ideas_skipped']}"
        )
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
