import argparse
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.calculate_forward_beats import (  # noqa: E402
    GROUPS,
    calculate_forward_beat_summaries,
)
from scripts.calculate_total_returns import DEFAULT_QUICKFS_DB, DEFAULT_VIC_DB  # noqa: E402


SERIES = (
    (("All ideas", "Long"), "All long", "#1b7f5c"),
    (("All ideas", "Short"), "All short", "#b23a48"),
    (("Contest winners", "Long"), "Winner long", "#2468b2"),
    (("Contest winners", "Short"), "Winner short", "#8a5fbf"),
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Graph forward time-weighted annual beat curves."
    )
    parser.add_argument("--vic-db", type=Path, default=DEFAULT_VIC_DB)
    parser.add_argument("--quickfs-db", type=Path, default=DEFAULT_QUICKFS_DB)
    parser.add_argument("--min-quarters", type=int, default=1)
    parser.add_argument("--max-quarters", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis")
    return parser.parse_args()


def fmt(value):
    return "" if value is None else f"{value:.6f}"


def write_tsv(summaries, path):
    columns = [
        "forward_quarters",
        "forward_years",
        "scope",
        "side",
        "total_ideas",
        "with_beat",
        "avg_years_used",
        "time_weighted_annual_beat_pct",
        "simple_avg_annual_beat_pct",
        "avg_idea_annual_return_pct",
        "avg_benchmark_annual_return_pct",
    ]
    lines = ["\t".join(columns)]
    for summary in summaries:
        quarters = summary["forward_quarters"]
        years = quarters / 4
        for scope, side in GROUPS:
            group = summary["groups"][(scope, side)]
            lines.append(
                "\t".join(
                    [
                        str(quarters),
                        f"{years:.2f}",
                        scope,
                        side,
                        str(int(group["total_ideas"])),
                        str(int(group["with_beat"])),
                        fmt(group["avg_years_used"]),
                        fmt(group["time_weighted_annual_beat_pct"]),
                        fmt(group["simple_avg_annual_beat_pct"]),
                        fmt(group["avg_idea_annual_return_pct"]),
                        fmt(group["avg_benchmark_annual_return_pct"]),
                    ]
                )
            )
    path.write_text("\n".join(lines) + "\n")


def axis_ticks(min_value, max_value, step):
    first = int(min_value // step) * step
    tick = first
    while tick <= max_value + step:
        if tick >= min_value:
            yield tick
        tick += step


def write_svg(summaries, path):
    width = 1200
    height = 720
    left = 90
    right = 40
    top = 70
    bottom = 90
    plot_width = width - left - right
    plot_height = height - top - bottom

    values = []
    by_series = {}
    for key, label, color in SERIES:
        points = []
        for summary in summaries:
            value = summary["groups"][key]["time_weighted_annual_beat_pct"]
            if value is None:
                continue
            x_value = summary["forward_quarters"] / 4
            points.append((x_value, value))
            values.append(value)
        by_series[key] = {"label": label, "color": color, "points": points}

    y_min = min(values + [0])
    y_max = max(values + [0])
    padding = max((y_max - y_min) * 0.12, 5)
    y_min -= padding
    y_max += padding
    x_min = summaries[0]["forward_quarters"] / 4
    x_max = summaries[-1]["forward_quarters"] / 4

    def sx(x_value):
        return left + ((x_value - x_min) / (x_max - x_min)) * plot_width

    def sy(y_value):
        return top + (1 - ((y_value - y_min) / (y_max - y_min))) * plot_height

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        f'<text x="{left}" y="34" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#1f2933">Forward Annual Beat vs S&amp;P 500 TR</text>',
        f'<text x="{left}" y="58" font-family="Arial, sans-serif" font-size="13" fill="#5b6572">Time-weighted annualized outperformance, windows from 1 quarter to 5 years</text>',
    ]

    for tick in axis_ticks(y_min, y_max, 10):
        y = sy(tick)
        stroke = "#c9c2b8" if tick == 0 else "#e3ded6"
        width_attr = "1.5" if tick == 0 else "1"
        svg.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="{stroke}" stroke-width="{width_attr}"/>'
        )
        svg.append(
            f'<text x="{left - 12}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#56606b">{tick:+.0f}%</text>'
        )

    for year in range(1, 6):
        x = sx(year)
        svg.append(
            f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_height}" stroke="#eee9e1" stroke-width="1"/>'
        )
        svg.append(
            f'<text x="{x:.2f}" y="{top + plot_height + 28}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#56606b">{year}y</text>'
        )

    svg.append(
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="none" stroke="#d5cec3" stroke-width="1"/>'
    )

    for key, data in by_series.items():
        points = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in data["points"])
        svg.append(
            f'<polyline points="{points}" fill="none" stroke="{data["color"]}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for x_value, y_value in data["points"]:
            svg.append(
                f'<circle cx="{sx(x_value):.2f}" cy="{sy(y_value):.2f}" r="3" fill="{data["color"]}"/>'
            )

    legend_x = left + 640
    legend_y = 24
    for index, (_key, data) in enumerate(by_series.items()):
        x = legend_x + (index % 2) * 190
        y = legend_y + (index // 2) * 24
        svg.append(
            f'<line x1="{x}" y1="{y}" x2="{x + 28}" y2="{y}" stroke="{data["color"]}" stroke-width="4" stroke-linecap="round"/>'
        )
        svg.append(
            f'<text x="{x + 38}" y="{y + 4}" font-family="Arial, sans-serif" font-size="13" fill="#28313b">{html.escape(data["label"])}</text>'
        )

    svg.append(
        f'<text x="{left + plot_width / 2}" y="{height - 26}" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#38414c">Forward holding window</text>'
    )
    svg.append(
        f'<text x="26" y="{top + plot_height / 2}" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#38414c" transform="rotate(-90 26 {top + plot_height / 2})">Annual beat</text>'
    )
    svg.append("</svg>")
    path.write_text("\n".join(svg) + "\n")


def main():
    args = parse_args()
    if args.min_quarters <= 0 or args.max_quarters < args.min_quarters:
        raise ValueError("quarter range must start above zero and end after the start")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    quarters = list(range(args.min_quarters, args.max_quarters + 1))
    summaries = calculate_forward_beat_summaries(args.vic_db, args.quickfs_db, quarters)
    tsv_path = args.output_dir / "forward_beat_curves.tsv"
    svg_path = args.output_dir / "forward_beat_curves.svg"
    write_tsv(summaries, tsv_path)
    write_svg(summaries, svg_path)

    print(f"wrote {tsv_path}")
    print(f"wrote {svg_path}")
    print()
    print("Final 5-year time-weighted annual beats:")
    final = summaries[-1]
    for scope, side in GROUPS:
        group = final["groups"][(scope, side)]
        value = group["time_weighted_annual_beat_pct"]
        label = f"{scope} {side}".ljust(22)
        print(f"{label} {value:+.2f}% ({int(group['with_beat']):,} ideas)")


if __name__ == "__main__":
    main()
