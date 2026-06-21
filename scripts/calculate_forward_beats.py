import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.calculate_sp500_benchmark import (
    compound_annual_return,
    load_sp500_series,
    value_at_or_before,
)
from scripts.calculate_total_returns import (
    DEFAULT_QUICKFS_DB,
    DEFAULT_VIC_DB,
    find_series,
    idea_month,
    load_quickfs_series,
    start_index,
)


GROUPS = (
    ("All ideas", "Long"),
    ("All ideas", "Short"),
    ("Contest winners", "Long"),
    ("Contest winners", "Short"),
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Calculate forward annualized idea beat versus S&P 500 Total Return."
    )
    parser.add_argument("--vic-db", type=Path, default=DEFAULT_VIC_DB)
    parser.add_argument("--quickfs-db", type=Path, default=DEFAULT_QUICKFS_DB)
    parser.add_argument(
        "--forward-quarters",
        type=int,
        default=4,
        help="Maximum number of QuickFS quarters to look forward from the idea start period.",
    )
    return parser.parse_args()


def empty_group_stats():
    return {
        "total_ideas": 0,
        "with_beat": 0,
        "year_weight_sum": 0.0,
        "weighted_beat_sum": 0.0,
        "simple_beat_sum": 0.0,
        "idea_annual_sum": 0.0,
        "benchmark_annual_sum": 0.0,
    }


def calculate_window_return(series, start, forward_quarters):
    end = min(start + forward_quarters, len(series) - 1)
    if end <= start:
        return None

    start_period, start_price, _ = series[start]
    end_period, end_price, _ = series[end]
    dividends = sum(row[2] for row in series[start + 1 : end + 1])
    stock_total_return = ((end_price + dividends) / start_price - 1) * 100

    return {
        "start_period": start_period,
        "end_period": end_period,
        "dividends": dividends,
        "stock_total_return_pct": stock_total_return,
        "periods_held": end - start,
        "years_held": (end - start) / 4,
    }


def add_result(stats, scope, side, beat, years_held, idea_annual, benchmark_annual):
    group = stats[(scope, side)]
    group["with_beat"] += 1
    group["year_weight_sum"] += years_held
    group["weighted_beat_sum"] += beat * years_held
    group["simple_beat_sum"] += beat
    group["idea_annual_sum"] += idea_annual
    group["benchmark_annual_sum"] += benchmark_annual


def finalize_group(group):
    with_beat = group["with_beat"]
    year_weight_sum = group["year_weight_sum"]
    if not with_beat or not year_weight_sum:
        return {
            **group,
            "avg_years_used": None,
            "time_weighted_annual_beat_pct": None,
            "simple_avg_annual_beat_pct": None,
            "avg_idea_annual_return_pct": None,
            "avg_benchmark_annual_return_pct": None,
        }

    return {
        **group,
        "avg_years_used": year_weight_sum / with_beat,
        "time_weighted_annual_beat_pct": group["weighted_beat_sum"] / year_weight_sum,
        "simple_avg_annual_beat_pct": group["simple_beat_sum"] / with_beat,
        "avg_idea_annual_return_pct": group["idea_annual_sum"] / with_beat,
        "avg_benchmark_annual_return_pct": group["benchmark_annual_sum"] / with_beat,
    }


def calculate_forward_beat_summary(vic_db, quickfs_db, forward_quarters=4):
    if forward_quarters <= 0:
        raise ValueError("forward_quarters must be greater than zero")

    quickfs = load_quickfs_series(quickfs_db)
    conn = sqlite3.connect(vic_db)
    sp_periods, sp_values = load_sp500_series(conn)
    ideas = conn.execute(
        """
        SELECT id, company_id, date, COALESCE(is_short, 0), COALESCE(is_contest_winner, 0)
        FROM ideas
        WHERE id IS NOT NULL
          AND company_id IS NOT NULL
          AND date IS NOT NULL
        """
    ).fetchall()
    conn.close()

    stats = {group: empty_group_stats() for group in GROUPS}
    skipped = defaultdict(int)

    for _idea_id, ticker, date_value, is_short, is_winner in ideas:
        side = "Short" if bool(is_short) else "Long"
        stats[("All ideas", side)]["total_ideas"] += 1
        if bool(is_winner):
            stats[("Contest winners", side)]["total_ideas"] += 1

        _matched_ticker, series = find_series(quickfs, ticker)
        if not series:
            skipped["missing_quickfs_ticker"] += 1
            continue

        start = start_index(series, idea_month(date_value))
        if start is None:
            skipped["missing_start_period"] += 1
            continue

        window_return = calculate_window_return(series, start, forward_quarters)
        if window_return is None:
            skipped["no_forward_quickfs_period"] += 1
            continue

        stock_total = window_return["stock_total_return_pct"]
        idea_total = -stock_total if bool(is_short) else stock_total
        years_held = window_return["years_held"]
        idea_annual = compound_annual_return(idea_total, years_held)
        if idea_annual is None:
            skipped["undefined_idea_annual"] += 1
            continue

        start_value = value_at_or_before(
            sp_periods, sp_values, window_return["start_period"]
        )
        end_value = value_at_or_before(sp_periods, sp_values, window_return["end_period"])
        if start_value is None or end_value is None:
            skipped["missing_sp500_period"] += 1
            continue

        benchmark_total = (end_value / start_value - 1) * 100
        benchmark_annual = compound_annual_return(benchmark_total, years_held)
        if benchmark_annual is None:
            skipped["undefined_benchmark_annual"] += 1
            continue

        beat = idea_annual - benchmark_annual
        add_result(stats, "All ideas", side, beat, years_held, idea_annual, benchmark_annual)
        if bool(is_winner):
            add_result(
                stats,
                "Contest winners",
                side,
                beat,
                years_held,
                idea_annual,
                benchmark_annual,
            )

    return {
        "forward_quarters": forward_quarters,
        "ideas": len(ideas),
        "quickfs_tickers": len(quickfs),
        "sp500_start": sp_periods[0],
        "sp500_end": sp_periods[-1],
        "groups": {group: finalize_group(stats[group]) for group in GROUPS},
        "skipped": dict(skipped),
    }


def format_pct(value):
    return "n/a" if value is None else f"{value:+.2f}%"


def format_years(value):
    return "n/a" if value is None else f"{value:.2f}"


def main():
    args = parse_args()
    summary = calculate_forward_beat_summary(
        args.vic_db,
        args.quickfs_db,
        forward_quarters=args.forward_quarters,
    )

    print(
        "Method: forward window capped at "
        f"{summary['forward_quarters']} QuickFS quarters; shorter windows are "
        "annualized over actual available quarters and weighted by years used."
    )
    print(f"Ideas in DB: {summary['ideas']:,}")
    print(f"QuickFS tickers loaded: {summary['quickfs_tickers']:,}")
    print(f"S&P 500 TR period: {summary['sp500_start']} to {summary['sp500_end']}")
    print()
    print(
        "Scope\tSide\tTotal ideas\tWith beat\tAvg years used\t"
        "Time-weighted annual beat\tSimple avg annual beat\t"
        "Avg idea annual\tAvg S&P annual"
    )
    for scope, side in GROUPS:
        group = summary["groups"][(scope, side)]
        print(
            f"{scope}\t{side}\t{int(group['total_ideas']):,}\t"
            f"{int(group['with_beat']):,}\t"
            f"{format_years(group['avg_years_used'])}\t"
            f"{format_pct(group['time_weighted_annual_beat_pct'])}\t"
            f"{format_pct(group['simple_avg_annual_beat_pct'])}\t"
            f"{format_pct(group['avg_idea_annual_return_pct'])}\t"
            f"{format_pct(group['avg_benchmark_annual_return_pct'])}"
        )

    print()
    print("Skipped / unmatched counts:")
    for key in sorted(summary["skipped"]):
        print(f"{key}: {summary['skipped'][key]:,}")


if __name__ == "__main__":
    main()
