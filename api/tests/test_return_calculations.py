import math
import io
import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import calculate_sp500_benchmark
from scripts import calculate_forward_beats
from scripts import calculate_total_returns
from scripts import import_quickfs_latest_metrics
from scripts.calculate_sp500_benchmark import (
    compound_annual_return as benchmark_compound_annual_return,
)
from scripts.calculate_sp500_benchmark import value_at_or_before
from scripts.calculate_total_returns import (
    DEFAULT_QUICKFS_DB,
    DEFAULT_VIC_DB,
    calculate_return,
    compound_annual_return as idea_compound_annual_return,
    find_series,
    idea_month,
    load_quickfs_series,
    start_index,
)


class ReturnCalculationTests(unittest.TestCase):
    def assert_close(self, actual, expected):
        self.assertIsNotNone(actual)
        self.assertTrue(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9))

    def test_compound_annual_return_uses_cagr_not_linear_average(self):
        total_return_pct = 5000
        years_held = 10

        result = idea_compound_annual_return(total_return_pct, years_held)

        self.assert_close(
            result,
            ((1 + total_return_pct / 100) ** (1 / years_held) - 1) * 100,
        )
        self.assertLess(result, 50)
        self.assertNotEqual(result, total_return_pct / years_held)

    def test_compound_annual_return_handles_losses_above_minus_100_percent(self):
        result = idea_compound_annual_return(-50, 2)

        self.assert_close(result, (0.5 ** 0.5 - 1) * 100)

    def test_compound_annual_return_is_undefined_when_growth_factor_is_not_positive(self):
        for total_return_pct in [-100, -101, -5000]:
            with self.subTest(total_return_pct=total_return_pct):
                self.assertIsNone(idea_compound_annual_return(total_return_pct, 5))

    def test_sp500_benchmark_uses_same_compounded_annual_return_formula(self):
        total_return_pct = 44
        years_held = 2

        self.assert_close(
            benchmark_compound_annual_return(total_return_pct, years_held),
            ((1 + total_return_pct / 100) ** (1 / years_held) - 1) * 100,
        )

    def test_value_at_or_before_uses_latest_available_period_not_exact_match_only(self):
        periods = ["2020-01", "2020-03", "2020-06"]
        values = [100, 110, 121]

        self.assertEqual(value_at_or_before(periods, values, "2020-04"), 110)
        self.assertEqual(value_at_or_before(periods, values, "2020-06"), 121)
        self.assertIsNone(value_at_or_before(periods, values, "2019-12"))

    def test_quickfs_total_return_includes_only_dividends_after_start_through_end(self):
        series = [
            ("2020-03", 100, 10),
            ("2020-06", 110, 2),
            ("2020-09", 120, 3),
            ("2020-12", 130, 4),
        ]

        result = calculate_return(series, start=0)

        self.assertEqual(result["start_period"], "2020-03")
        self.assertEqual(result["end_period"], "2020-12")
        self.assertEqual(result["dividends"], 9)
        self.assert_close(result["stock_total_return_pct"], 39)


class ReturnPipelineTests(unittest.TestCase):
    def assert_close(self, actual, expected):
        self.assertIsNotNone(actual)
        self.assertTrue(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9))

    def make_db_path(self, directory, name):
        return Path(directory) / name

    def insert_quickfs_row(
        self,
        conn,
        ticker,
        periods,
        prices,
        dividends,
        revenue=None,
        company_name=None,
    ):
        conn.execute(
            """
            INSERT INTO financials (
                ticker, company_name, exchange, data_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ticker,
                company_name or f"{ticker} Corp",
                "NYSE",
                json.dumps(
                    {
                        "period_end_date": periods,
                        "period_end_price": prices,
                        "dividends": dividends,
                        "revenue": revenue or [],
                    }
                ),
                "2026-01-01",
            ),
        )

    def run_total_return_script(self, vic_db, quickfs_db):
        argv = [
            "calculate_total_returns.py",
            "--vic-db",
            str(vic_db),
            "--quickfs-db",
            str(quickfs_db),
        ]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            calculate_total_returns.main()

    def run_sp500_script(self, vic_db):
        argv = ["calculate_sp500_benchmark.py", "--sqlite", str(vic_db)]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            calculate_sp500_benchmark.main()

    def run_latest_metrics_script(self, vic_db, quickfs_db):
        argv = [
            "import_quickfs_latest_metrics.py",
            "--vic-db",
            str(vic_db),
            "--quickfs-db",
            str(quickfs_db),
        ]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            import_quickfs_latest_metrics.main()

    def test_total_return_script_writes_long_short_and_ticker_match_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            vic_db = self.make_db_path(directory, "vic.sqlite")
            quickfs_db = self.make_db_path(directory, "quickfs.sqlite")

            vic = sqlite3.connect(vic_db)
            vic.execute(
                """
                CREATE TABLE ideas (
                    id TEXT PRIMARY KEY,
                    company_id TEXT,
                    date TEXT,
                    is_short INTEGER
                )
                """
            )
            vic.executemany(
                "INSERT INTO ideas (id, company_id, date, is_short) VALUES (?, ?, ?, ?)",
                [
                    ("long-idea", "ABC", "2020-03-15 12:00:00", 0),
                    ("short-idea", "BRK.B", "2020-03-15 12:00:00", 1),
                    ("too-early", "XYZ", "2019-12-15 12:00:00", 0),
                    ("too-late", "ABC", "2021-03-15 12:00:00", 0),
                ],
            )
            vic.commit()
            vic.close()

            quickfs = sqlite3.connect(quickfs_db)
            quickfs.execute(
                """
                CREATE TABLE financials (
                    ticker TEXT,
                    company_name TEXT,
                    exchange TEXT,
                    data_json TEXT,
                    updated_at TEXT
                )
                """
            )
            periods = ["2020-03", "2020-06", "2020-09", "2020-12", "2021-03"]
            self.insert_quickfs_row(
                quickfs,
                "ABC",
                periods,
                [100, 101, 102, 103, 110],
                [0, 1, 2, 3, 4],
            )
            self.insert_quickfs_row(
                quickfs,
                "BRK-B",
                periods,
                [100, 95, 90, 85, 80],
                [0, 0, 0, 0, 0],
            )
            self.insert_quickfs_row(
                quickfs,
                "XYZ",
                periods,
                [100, 100, 100, 100, 100],
                [0, 0, 0, 0, 0],
            )
            quickfs.commit()
            quickfs.close()

            self.run_total_return_script(vic_db, quickfs_db)

            conn = sqlite3.connect(vic_db)
            rows = {
                row[0]: row
                for row in conn.execute(
                    """
                    SELECT idea_id, ticker, matched_ticker, start_period, end_period,
                           dividends, stock_total_return_pct, idea_total_return_pct,
                           annualized_idea_return_pct, periods_held
                    FROM idea_total_returns
                    ORDER BY idea_id
                    """
                ).fetchall()
            }
            conn.close()

            self.assertEqual(set(rows), {"long-idea", "short-idea"})
            long_row = rows["long-idea"]
            self.assertEqual(long_row[3], "2020-03")
            self.assertEqual(long_row[4], "2021-03")
            self.assertEqual(long_row[9], 4)
            self.assert_close(long_row[5], 10)
            self.assert_close(long_row[6], 20)
            self.assert_close(long_row[7], 20)
            self.assert_close(long_row[8], 20)

            short_row = rows["short-idea"]
            self.assertEqual(short_row[2], "BRK-B")
            self.assert_close(short_row[6], -20)
            self.assert_close(short_row[7], 20)
            self.assert_close(short_row[8], 20)

    def test_sp500_benchmark_script_uses_matching_periods_and_compounded_excess(self):
        with tempfile.TemporaryDirectory() as directory:
            vic_db = self.make_db_path(directory, "vic.sqlite")
            conn = sqlite3.connect(vic_db)
            conn.execute(
                """
                CREATE TABLE idea_total_returns (
                    idea_id TEXT PRIMARY KEY,
                    start_period TEXT,
                    end_period TEXT,
                    periods_held INTEGER,
                    idea_total_return_pct REAL,
                    annualized_idea_return_pct REAL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO idea_total_returns (
                    idea_id, start_period, end_period, periods_held,
                    idea_total_return_pct, annualized_idea_return_pct
                )
                VALUES ('idea-1', '2020-04', '2021-03', 4, 20, 20)
                """
            )
            conn.execute(
                """
                CREATE TABLE sp500_total_return_index (
                    period TEXT PRIMARY KEY,
                    index_value REAL
                )
                """
            )
            conn.executemany(
                "INSERT INTO sp500_total_return_index (period, index_value) VALUES (?, ?)",
                [("2020-03", 100), ("2020-12", 110), ("2021-03", 121)],
            )
            conn.commit()
            conn.close()

            self.run_sp500_script(vic_db)

            conn = sqlite3.connect(vic_db)
            row = conn.execute(
                """
                SELECT benchmark_total_return_pct, benchmark_annualized_return_pct,
                       excess_total_return_pct, excess_annualized_return_pct
                FROM idea_total_returns
                WHERE idea_id = 'idea-1'
                """
            ).fetchone()
            conn.close()

            self.assert_close(row[0], 21)
            self.assert_close(row[1], 21)
            self.assert_close(row[2], -1)
            self.assert_close(row[3], -1)

    def test_latest_metrics_import_uses_latest_numeric_revenue(self):
        with tempfile.TemporaryDirectory() as directory:
            vic_db = self.make_db_path(directory, "vic.sqlite")
            quickfs_db = self.make_db_path(directory, "quickfs.sqlite")

            sqlite3.connect(vic_db).close()
            quickfs = sqlite3.connect(quickfs_db)
            quickfs.execute(
                """
                CREATE TABLE financials (
                    ticker TEXT,
                    company_name TEXT,
                    exchange TEXT,
                    data_json TEXT,
                    updated_at TEXT
                )
                """
            )
            self.insert_quickfs_row(
                quickfs,
                "abc",
                ["2024-12", "2025-03", "2025-06"],
                [10, 11, 12],
                [0, 0, 0],
                revenue=[1000, None, "1250.5"],
                company_name="ABC Co",
            )
            self.insert_quickfs_row(
                quickfs,
                "NOREV",
                ["2025-03"],
                [10],
                [0],
                revenue=["n/a"],
            )
            quickfs.commit()
            quickfs.close()

            self.run_latest_metrics_script(vic_db, quickfs_db)

            conn = sqlite3.connect(vic_db)
            rows = {
                row[0]: row
                for row in conn.execute(
                    """
                    SELECT ticker, company_name, latest_revenue, latest_revenue_period
                    FROM quickfs_latest_metrics
                    ORDER BY ticker
                    """
                ).fetchall()
            }
            conn.close()

            self.assertEqual(set(rows), {"ABC", "NOREV"})
            self.assertEqual(rows["ABC"][1], "ABC Co")
            self.assert_close(rows["ABC"][2], 1250.5)
            self.assertEqual(rows["ABC"][3], "2025-06")
            self.assertIsNone(rows["NOREV"][2])
            self.assertIsNone(rows["NOREV"][3])

    def test_forward_beat_summary_uses_requested_window_and_time_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            vic_db = self.make_db_path(directory, "vic.sqlite")
            quickfs_db = self.make_db_path(directory, "quickfs.sqlite")

            vic = sqlite3.connect(vic_db)
            vic.execute(
                """
                CREATE TABLE ideas (
                    id TEXT PRIMARY KEY,
                    company_id TEXT,
                    date TEXT,
                    is_short INTEGER,
                    is_contest_winner INTEGER
                )
                """
            )
            vic.executemany(
                """
                INSERT INTO ideas (
                    id, company_id, date, is_short, is_contest_winner
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("long-full-year", "AAA", "2020-03-10", 0, 1),
                    ("long-half-year", "BBB", "2020-03-10", 0, 0),
                    ("short-full-year", "CCC", "2020-03-10", 1, 1),
                ],
            )
            vic.execute(
                """
                CREATE TABLE sp500_total_return_index (
                    period TEXT PRIMARY KEY,
                    index_value REAL
                )
                """
            )
            vic.executemany(
                "INSERT INTO sp500_total_return_index (period, index_value) VALUES (?, ?)",
                [
                    ("2020-03", 100),
                    ("2020-06", 102),
                    ("2020-09", 104),
                    ("2020-12", 106),
                    ("2021-03", 110),
                ],
            )
            vic.commit()
            vic.close()

            quickfs = sqlite3.connect(quickfs_db)
            quickfs.execute(
                """
                CREATE TABLE financials (
                    ticker TEXT,
                    company_name TEXT,
                    exchange TEXT,
                    data_json TEXT,
                    updated_at TEXT
                )
                """
            )
            self.insert_quickfs_row(
                quickfs,
                "AAA",
                ["2020-03", "2020-06", "2020-09", "2020-12", "2021-03"],
                [100, 105, 110, 115, 121],
                [0, 0, 0, 0, 0],
            )
            self.insert_quickfs_row(
                quickfs,
                "BBB",
                ["2020-03", "2020-06", "2020-09"],
                [100, 103, 110],
                [0, 0, 0],
            )
            self.insert_quickfs_row(
                quickfs,
                "CCC",
                ["2020-03", "2020-06", "2020-09", "2020-12", "2021-03"],
                [100, 95, 94, 93, 90],
                [0, 0, 0, 0, 0],
            )
            quickfs.commit()
            quickfs.close()

            summary = calculate_forward_beats.calculate_forward_beat_summary(
                vic_db,
                quickfs_db,
                forward_quarters=4,
            )

            long_group = summary["groups"][("All ideas", "Long")]
            short_group = summary["groups"][("All ideas", "Short")]
            winner_long = summary["groups"][("Contest winners", "Long")]
            winner_short = summary["groups"][("Contest winners", "Short")]

            aaa_beat = 21 - 10
            bbb_idea_annual = ((1.10 ** 2) - 1) * 100
            bbb_benchmark_annual = ((1.04 ** 2) - 1) * 100
            bbb_beat = bbb_idea_annual - bbb_benchmark_annual
            weighted_long = ((aaa_beat * 1) + (bbb_beat * 0.5)) / 1.5

            self.assertEqual(long_group["total_ideas"], 2)
            self.assertEqual(long_group["with_beat"], 2)
            self.assert_close(long_group["avg_years_used"], 0.75)
            self.assert_close(long_group["time_weighted_annual_beat_pct"], weighted_long)

            self.assertEqual(short_group["total_ideas"], 1)
            self.assertEqual(short_group["with_beat"], 1)
            self.assert_close(short_group["time_weighted_annual_beat_pct"], 0)

            self.assertEqual(winner_long["total_ideas"], 1)
            self.assertEqual(winner_long["with_beat"], 1)
            self.assert_close(winner_long["time_weighted_annual_beat_pct"], aaa_beat)
            self.assertEqual(winner_short["total_ideas"], 1)
            self.assertEqual(winner_short["with_beat"], 1)

    def test_golden_return_sample_matches_raw_local_inputs(self):
        root = Path(__file__).resolve().parents[2]
        golden_path = root / "analysis" / "golden_return_sample.tsv"
        if not golden_path.exists():
            self.skipTest("golden return sample file is not available")
        if not DEFAULT_VIC_DB.exists() or not DEFAULT_QUICKFS_DB.exists():
            self.skipTest("local VIC or QuickFS database is not available")

        quickfs = load_quickfs_series(DEFAULT_QUICKFS_DB)
        conn = sqlite3.connect(DEFAULT_VIC_DB)
        sp_periods, sp_values = calculate_sp500_benchmark.load_sp500_series(conn)

        with golden_path.open(newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))

        self.assertEqual(len(rows), 20)
        for expected in rows:
            with self.subTest(
                ticker=expected["ticker"],
                forward_quarters=expected["forward_quarters"],
            ):
                idea = conn.execute(
                    """
                    SELECT id, company_id, date, COALESCE(is_short, 0),
                           COALESCE(is_contest_winner, 0)
                    FROM ideas
                    WHERE id = ?
                    """,
                    (expected["idea_id"],),
                ).fetchone()
                self.assertIsNotNone(idea)
                _idea_id, ticker, idea_date, is_short, is_winner = idea

                matched_ticker, series = find_series(quickfs, ticker)
                self.assertEqual(matched_ticker, expected["matched_ticker"])
                start = start_index(series, idea_month(idea_date))
                self.assertIsNotNone(start)
                result = calculate_forward_beats.calculate_window_return(
                    series,
                    start,
                    int(expected["forward_quarters"]),
                )

                stock_total = result["stock_total_return_pct"]
                idea_total = -stock_total if bool(is_short) else stock_total
                idea_annual = idea_compound_annual_return(
                    idea_total,
                    result["years_held"],
                )
                sp_start = value_at_or_before(
                    sp_periods,
                    sp_values,
                    result["start_period"],
                )
                sp_end = value_at_or_before(
                    sp_periods,
                    sp_values,
                    result["end_period"],
                )
                benchmark_total = (sp_end / sp_start - 1) * 100
                benchmark_annual = benchmark_compound_annual_return(
                    benchmark_total,
                    result["years_held"],
                )
                excess_annual = (
                    None
                    if idea_annual is None or benchmark_annual is None
                    else idea_annual - benchmark_annual
                )

                self.assertEqual(ticker, expected["ticker"])
                self.assertEqual(str(idea_date), expected["idea_date"])
                self.assertEqual(int(bool(is_short)), int(expected["is_short"]))
                self.assertEqual(
                    int(bool(is_winner)),
                    int(expected["is_contest_winner"]),
                )
                self.assertEqual(result["start_period"], expected["start_period"])
                self.assertEqual(result["end_period"], expected["end_period"])
                self.assertEqual(result["periods_held"], int(expected["periods_held"]))
                self.assert_golden_close(result["years_held"], expected["years_held"])
                self.assert_golden_close(result["start_price"], expected["start_price"])
                self.assert_golden_close(result["end_price"], expected["end_price"])
                self.assert_golden_close(result["dividends"], expected["dividends"])
                self.assert_golden_close(
                    result["stock_total_return_pct"],
                    expected["stock_total_return_pct"],
                )
                self.assert_golden_close(
                    idea_total,
                    expected["idea_total_return_pct"],
                )
                self.assert_golden_close(
                    idea_annual,
                    expected["idea_annualized_return_pct"],
                )
                self.assert_golden_close(sp_start, expected["sp500_start_value"])
                self.assert_golden_close(sp_end, expected["sp500_end_value"])
                self.assert_golden_close(
                    benchmark_total,
                    expected["benchmark_total_return_pct"],
                )
                self.assert_golden_close(
                    benchmark_annual,
                    expected["benchmark_annualized_return_pct"],
                )
                self.assert_golden_close(
                    excess_annual,
                    expected["excess_annualized_return_pct"],
                )
        conn.close()

    def assert_golden_close(self, actual, expected_text):
        if expected_text == "":
            self.assertIsNone(actual)
            return

        self.assertIsNotNone(actual)
        expected = float(expected_text)
        self.assertTrue(
            math.isclose(float(actual), expected, rel_tol=1e-9, abs_tol=1e-9),
            f"{actual} != {expected}",
        )


if __name__ == "__main__":
    unittest.main()
