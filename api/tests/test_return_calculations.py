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
from scripts import calculate_google_sheet_returns
from scripts import calculate_google_sheet_portfolios
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

    def test_quickfs_start_index_uses_first_period_on_or_after_idea_month(self):
        series = [
            ("2020-03", 100, 0),
            ("2020-06", 110, 0),
            ("2020-09", 120, 0),
        ]

        self.assertEqual(start_index(series, "2020-01"), 0)
        self.assertEqual(start_index(series, "2020-03"), 0)
        self.assertEqual(start_index(series, "2020-04"), 1)
        self.assertEqual(start_index(series, "2020-06"), 1)
        self.assertIsNone(start_index(series, "2020-10"))

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

    def test_google_sheet_match_uses_exact_ticker_date_and_link_title(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            """
            CREATE TABLE companies (
                ticker TEXT PRIMARY KEY,
                company_name TEXT
            );
            CREATE TABLE ideas (
                id TEXT PRIMARY KEY,
                link TEXT,
                company_id TEXT,
                date TEXT,
                is_short BOOLEAN,
                is_contest_winner BOOLEAN
            );
            CREATE TABLE idea_total_returns (
                idea_id TEXT PRIMARY KEY,
                matched_ticker TEXT,
                start_period TEXT,
                end_period TEXT,
                start_price REAL,
                end_price REAL,
                dividends REAL,
                periods_held INTEGER,
                stock_total_return_pct REAL,
                idea_total_return_pct REAL,
                annualized_idea_return_pct REAL,
                benchmark_total_return_pct REAL,
                benchmark_annualized_return_pct REAL,
                excess_total_return_pct REAL,
                excess_annualized_return_pct REAL
            );
            """
        )
        conn.execute("INSERT INTO companies VALUES (?, ?)", ("TSCO", "TESCO PLC "))
        conn.execute(
            """
            INSERT INTO ideas (
                id, link, company_id, date, is_short, is_contest_winner
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "tractor-supply-idea",
                "https://www.valueinvestorsclub.com/idea/Tractor_Supply_Company/8212619875",
                "TSCO",
                "2001-02-07 12:59:00",
                1,
                0,
            ),
        )
        conn.execute(
            """
            INSERT INTO ideas (
                id, link, company_id, date, is_short, is_contest_winner
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "tesco-idea",
                "https://www.valueinvestorsclub.com/idea/Tesco_plc/4567009379",
                "TSCO",
                "2011-04-05 19:14:00",
                1,
                0,
            ),
        )
        conn.execute(
            """
            INSERT INTO idea_total_returns (
                idea_id, matched_ticker, start_period, end_period,
                start_price, end_price, dividends, periods_held,
                stock_total_return_pct, idea_total_return_pct,
                annualized_idea_return_pct, benchmark_total_return_pct,
                benchmark_annualized_return_pct, excess_total_return_pct,
                excess_annualized_return_pct
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tractor-supply-idea",
                "TSCO",
                "2002-03",
                "2025-09",
                1,
                2,
                0,
                94,
                100,
                -100,
                None,
                50,
                5,
                50,
                None,
            ),
        )

        matches = calculate_google_sheet_returns.load_db_matches(conn)
        exact = matches[("TSCO", "2001-02-07")][0]

        self.assertEqual(exact["match_key"], "TSCO|2001-02-07")
        self.assertEqual(exact["company_name"], "Tractor Supply Company")
        self.assertEqual(exact["db_company_name"], "TESCO PLC ")
        self.assertEqual(exact["direction"], "Long")
        self.assertEqual(exact["vic_db_direction"], "Short")
        self.assertEqual(exact["idea_total_return_pct"], 100)
        self.assertNotIn(("TSCO", "2001-02-08"), matches)
        conn.close()

    def test_expanding_equal_weight_portfolio_rebalances_when_new_ideas_arrive(self):
        quickfs = {
            "WIN": [
                ("2020-03", 100, 0),
                ("2020-06", 200, 0),
                ("2020-09", 400, 0),
            ],
            "FLAT": [
                ("2020-06", 100, 0),
                ("2020-09", 100, 0),
            ],
        }
        ideas = [
            {
                "source_sheet": "Group",
                "source_row": 2,
                "ticker": "WIN",
                "matched_ticker": "WIN",
                "company_name": "Winner",
                "sheet_date": "2020-03-15",
                "start_period": "2020-03",
                "end_period": "2020-09",
            },
            {
                "source_sheet": "Group",
                "source_row": 3,
                "ticker": "FLAT",
                "matched_ticker": "FLAT",
                "company_name": "Flat",
                "sheet_date": "2020-06-15",
                "start_period": "2020-06",
                "end_period": "2020-09",
            },
        ]

        result = calculate_google_sheet_portfolios.simulate_expanding_equal_weight_portfolio(
            ideas,
            quickfs,
            initial_capital=100,
        )

        self.assertEqual(result["summary"]["ideas_included"], 2)
        self.assert_close(result["nav_rows"][0]["portfolio_value"], 100)
        self.assert_close(result["nav_rows"][1]["portfolio_value"], 200)
        self.assertEqual(result["nav_rows"][1]["active_positions"], 2)
        self.assert_close(result["nav_rows"][2]["portfolio_value"], 300)
        self.assert_close(result["summary"]["total_return_pct"], 200)

    def test_expanding_equal_weight_portfolio_tracks_duplicate_rows(self):
        quickfs = {
            "AAA": [
                ("2020-03", 100, 0),
                ("2020-06", 110, 0),
            ],
        }
        ideas = [
            {
                "source_sheet": "Group",
                "source_row": 2,
                "ticker": "AAA",
                "matched_ticker": "AAA",
                "company_name": "AAA",
                "sheet_date": "2020-03-15",
                "start_period": "2020-03",
                "end_period": "2020-06",
            },
            {
                "source_sheet": "Group",
                "source_row": 3,
                "ticker": "AAA",
                "matched_ticker": "AAA",
                "company_name": "AAA",
                "sheet_date": "2020-03-15",
                "start_period": "2020-03",
                "end_period": "2020-06",
            },
        ]

        result = calculate_google_sheet_portfolios.simulate_expanding_equal_weight_portfolio(
            ideas,
            quickfs,
            initial_capital=100,
        )

        self.assertEqual(result["summary"]["ideas_included"], 2)
        self.assertEqual(result["summary"]["duplicate_ticker_date_rows"], 1)
        self.assert_close(result["summary"]["final_value"], 110)

    def test_expanding_equal_weight_portfolio_carries_positions_between_price_periods(self):
        quickfs = {
            "AAA": [
                ("2020-03", 100, 0),
                ("2020-09", 200, 0),
            ],
            "BBB": [
                ("2020-06", 100, 0),
                ("2020-09", 100, 0),
            ],
        }
        ideas = [
            {
                "source_sheet": "Group",
                "source_row": 2,
                "ticker": "AAA",
                "matched_ticker": "AAA",
                "company_name": "AAA",
                "sheet_date": "2020-03-15",
                "start_period": "2020-03",
                "end_period": "2020-09",
            },
            {
                "source_sheet": "Group",
                "source_row": 3,
                "ticker": "BBB",
                "matched_ticker": "BBB",
                "company_name": "BBB",
                "sheet_date": "2020-06-15",
                "start_period": "2020-06",
                "end_period": "2020-09",
            },
        ]

        result = calculate_google_sheet_portfolios.simulate_expanding_equal_weight_portfolio(
            ideas,
            quickfs,
            initial_capital=100,
        )

        self.assertEqual(result["summary"]["ideas_skipped"], 0)
        self.assertEqual(result["nav_rows"][1]["period"], "2020-06")
        self.assert_close(result["nav_rows"][1]["portfolio_value"], 100)
        self.assert_close(result["summary"]["final_value"], 150)

    def test_expanding_equal_weight_portfolio_rebalances_immediately_on_exit(self):
        quickfs = {
            "EXIT": [
                ("2020-03", 100, 0),
                ("2020-06", 100, 0),
            ],
            "KEEP": [
                ("2020-03", 100, 0),
                ("2020-06", 100, 0),
                ("2020-09", 200, 0),
            ],
        }
        ideas = [
            {
                "source_sheet": "Group",
                "source_row": 2,
                "ticker": "EXIT",
                "matched_ticker": "EXIT",
                "company_name": "Exit",
                "sheet_date": "2020-03-15",
                "start_period": "2020-03",
                "end_period": "2020-06",
            },
            {
                "source_sheet": "Group",
                "source_row": 3,
                "ticker": "KEEP",
                "matched_ticker": "KEEP",
                "company_name": "Keep",
                "sheet_date": "2020-03-15",
                "start_period": "2020-03",
                "end_period": "2020-09",
            },
        ]

        result = calculate_google_sheet_portfolios.simulate_expanding_equal_weight_portfolio(
            ideas,
            quickfs,
            initial_capital=100,
        )

        self.assertEqual(result["nav_rows"][1]["period"], "2020-06")
        self.assertEqual(result["nav_rows"][1]["exited_positions"], 1)
        self.assertTrue(result["nav_rows"][1]["rebalanced"])
        self.assertEqual(result["nav_rows"][1]["cash"], 0)
        self.assert_close(result["summary"]["final_value"], 200)

    def test_portfolio_sp500_benchmark_uses_same_start_and_end_period(self):
        portfolios = {
            "Group": {
                "summary": {
                    "initial_capital": 100,
                    "final_value": 200,
                    "total_return_pct": 100,
                    "annualized_return_pct": 41.42135623730952,
                    "start_period": "2020-03",
                    "end_period": "2022-03",
                    "years": 2,
                }
            }
        }

        calculate_google_sheet_portfolios.add_sp500_benchmarks(
            portfolios,
            ["2020-01", "2020-03", "2022-03"],
            [90, 100, 144],
        )

        summary = portfolios["Group"]["summary"]
        self.assert_close(summary["sp500_final_value"], 144)
        self.assert_close(summary["sp500_total_return_pct"], 44)
        self.assert_close(summary["sp500_annualized_return_pct"], 20)
        self.assert_close(summary["annualized_beat_pct"], 21.42135623730952)
        self.assert_close(summary["total_beat_pct"], 56)

    def test_expanding_equal_weight_portfolio_golden_edge_case_scenario(self):
        quickfs = {
            "AAA": [
                ("2020-03", 100, 0),
                ("2020-06", 120, 5),
                ("2020-12", 180, 0),
            ],
            "BBB": [
                ("2020-06", 50, 0),
                ("2020-09", 25, 0),
            ],
            "CCC": [
                ("2020-09", 10, 0),
                ("2020-12", 20, 1),
            ],
            "BAD": [
                ("2020-03", 100, 0),
            ],
        }
        ideas = [
            {
                "source_sheet": "Golden",
                "source_row": 2,
                "ticker": "AAA",
                "matched_ticker": "AAA",
                "company_name": "Dividend Winner",
                "sheet_date": "2020-03-15",
                "start_period": "2020-03",
                "end_period": "2020-12",
            },
            {
                "source_sheet": "Golden",
                "source_row": 3,
                "ticker": "BBB",
                "matched_ticker": "BBB",
                "company_name": "Duplicate Loser",
                "sheet_date": "2020-06-15",
                "start_period": "2020-06",
                "end_period": "2020-09",
            },
            {
                "source_sheet": "Golden",
                "source_row": 4,
                "ticker": "BBB",
                "matched_ticker": "BBB",
                "company_name": "Duplicate Loser",
                "sheet_date": "2020-06-15",
                "start_period": "2020-06",
                "end_period": "2020-09",
            },
            {
                "source_sheet": "Golden",
                "source_row": 5,
                "ticker": "CCC",
                "matched_ticker": "CCC",
                "company_name": "Late Winner",
                "sheet_date": "2020-09-15",
                "start_period": "2020-09",
                "end_period": "2020-12",
            },
            {
                "source_sheet": "Golden",
                "source_row": 6,
                "ticker": "MISS",
                "matched_ticker": "",
                "company_name": "Missing",
                "sheet_date": "2020-09-15",
                "start_period": "",
                "end_period": "",
            },
            {
                "source_sheet": "Golden",
                "source_row": 7,
                "ticker": "BAD",
                "matched_ticker": "BAD",
                "company_name": "No Holding Period",
                "sheet_date": "2020-03-15",
                "start_period": "2020-03",
                "end_period": "2020-03",
            },
        ]

        result = calculate_google_sheet_portfolios.simulate_expanding_equal_weight_portfolio(
            ideas,
            quickfs,
            initial_capital=100,
        )
        nav_by_period = {row["period"]: row for row in result["nav_rows"]}

        self.assertEqual(result["summary"]["ideas_included"], 4)
        self.assertEqual(result["summary"]["ideas_skipped"], 2)
        self.assertEqual(result["summary"]["duplicate_ticker_date_rows"], 1)
        self.assertEqual(result["skipped"]["missing_return_data"], 1)
        self.assertEqual(result["skipped"]["no_holding_period"], 1)

        self.assert_close(nav_by_period["2020-03"]["portfolio_value"], 100)
        self.assert_close(nav_by_period["2020-06"]["portfolio_value"], 125)
        self.assertEqual(nav_by_period["2020-06"]["new_positions"], 2)
        self.assertTrue(nav_by_period["2020-06"]["rebalanced"])
        self.assert_close(nav_by_period["2020-09"]["portfolio_value"], 83.33333333333334)
        self.assertEqual(nav_by_period["2020-09"]["exited_positions"], 2)
        self.assertEqual(nav_by_period["2020-09"]["new_positions"], 1)
        self.assertTrue(nav_by_period["2020-09"]["rebalanced"])
        self.assert_close(nav_by_period["2020-12"]["portfolio_value"], 150)
        self.assertEqual(nav_by_period["2020-12"]["exited_positions"], 2)
        self.assertEqual(nav_by_period["2020-12"]["cash"], 150)

        self.assert_close(result["summary"]["final_value"], 150)
        self.assert_close(result["summary"]["total_return_pct"], 50)
        self.assert_close(result["summary"]["years"], 0.75)

        constituents = {
            (row["ticker"], row["source_row"]): row for row in result["constituents"]
        }
        self.assert_close(constituents[("AAA", 2)]["initial_allocated_value"], 100)
        self.assert_close(constituents[("AAA", 2)]["final_value"], 62.5)
        self.assert_close(
            constituents[("BBB", 3)]["initial_allocated_value"],
            41.666666666666664,
        )
        self.assert_close(constituents[("BBB", 3)]["final_value"], 20.833333333333332)
        self.assert_close(
            constituents[("BBB", 4)]["initial_allocated_value"],
            41.666666666666664,
        )
        self.assert_close(constituents[("BBB", 4)]["final_value"], 20.833333333333332)
        self.assert_close(
            constituents[("CCC", 5)]["initial_allocated_value"],
            41.66666666666667,
        )
        self.assert_close(constituents[("CCC", 5)]["final_value"], 87.5)

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
                    ("starts-at-first-future-period", "XYZ", "2019-12-15 12:00:00", 0),
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

            self.assertEqual(
                set(rows),
                {"long-idea", "short-idea", "starts-at-first-future-period"},
            )
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

            future_start_row = rows["starts-at-first-future-period"]
            self.assertEqual(future_start_row[3], "2020-03")
            self.assertEqual(future_start_row[4], "2021-03")

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
            self.assert_close(
                long_group["time_weighted_annual_beat_pct"],
                long_group["time_weighted_idea_annual_return_pct"]
                - long_group["time_weighted_benchmark_annual_return_pct"],
            )

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
