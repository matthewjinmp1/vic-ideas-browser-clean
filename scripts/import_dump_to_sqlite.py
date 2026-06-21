#!/usr/bin/env python3
"""Convert the downloaded PostgreSQL VIC dump into a local SQLite database."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS catalyst;
DROP TABLE IF EXISTS companies;
DROP TABLE IF EXISTS descriptions;
DROP TABLE IF EXISTS ideas;
DROP TABLE IF EXISTS performance;
DROP TABLE IF EXISTS users;

CREATE TABLE catalyst (
    idea_id TEXT NOT NULL PRIMARY KEY,
    catalysts TEXT
);

CREATE TABLE companies (
    ticker TEXT NOT NULL PRIMARY KEY,
    company_name TEXT
);

CREATE TABLE descriptions (
    idea_id TEXT NOT NULL PRIMARY KEY,
    description TEXT
);

CREATE TABLE ideas (
    id TEXT NOT NULL PRIMARY KEY,
    link TEXT,
    company_id TEXT,
    user_id TEXT,
    date TEXT,
    is_short BOOLEAN,
    is_contest_winner BOOLEAN
);

CREATE TABLE performance (
    idea_id TEXT NOT NULL PRIMARY KEY,
    "nextDayOpen" REAL,
    "nextDayClose" REAL,
    "oneWeekClosePerf" REAL,
    "twoWeekClosePerf" REAL,
    "oneMonthPerf" REAL,
    "threeMonthPerf" REAL,
    "sixMonthPerf" REAL,
    "oneYearPerf" REAL,
    "twoYearPerf" REAL,
    "threeYearPerf" REAL,
    "fiveYearPerf" REAL
);

CREATE TABLE users (
    user_link TEXT NOT NULL PRIMARY KEY,
    username TEXT
);

CREATE INDEX idx_ideas_date ON ideas(date);
CREATE INDEX idx_ideas_company_id ON ideas(company_id);
CREATE INDEX idx_ideas_user_id ON ideas(user_id);
CREATE INDEX idx_ideas_short ON ideas(is_short);
CREATE INDEX idx_ideas_contest ON ideas(is_contest_winner);
"""

TABLE_COLUMNS = {
    "catalyst": ["idea_id", "catalysts"],
    "companies": ["ticker", "company_name"],
    "descriptions": ["idea_id", "description"],
    "ideas": ["id", "link", "company_id", "user_id", "date", "is_short", "is_contest_winner"],
    "performance": [
        "idea_id",
        "nextDayOpen",
        "nextDayClose",
        "oneWeekClosePerf",
        "twoWeekClosePerf",
        "oneMonthPerf",
        "threeMonthPerf",
        "sixMonthPerf",
        "oneYearPerf",
        "twoYearPerf",
        "threeYearPerf",
        "fiveYearPerf",
    ],
    "users": ["user_link", "username"],
}


def decode_copy_value(value: str):
    if value == r"\N":
        return None

    replacements = {
        r"\b": "\b",
        r"\f": "\f",
        r"\n": "\n",
        r"\r": "\r",
        r"\t": "\t",
        r"\\": "\\",
    }
    result = value
    for escaped, decoded in replacements.items():
        result = result.replace(escaped, decoded)
    return result


def coerce_value(table: str, column: str, value):
    if value is None:
        return None
    if table == "ideas" and column in {"is_short", "is_contest_winner"}:
        return value.lower() in {"t", "true", "1"}
    if table == "performance" and column != "idea_id":
        return float(value)
    return value


def insert_copy_rows(conn: sqlite3.Connection, table: str, rows: list[list]):
    if not rows:
        return
    columns = TABLE_COLUMNS[table]
    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    conn.executemany(
        f'INSERT OR REPLACE INTO "{table}" ({quoted_columns}) VALUES ({placeholders})',
        rows,
    )


def import_dump(sql_path: Path, sqlite_path: Path, batch_size: int = 1000):
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if sqlite_path.exists():
        sqlite_path.unlink()

    conn = sqlite3.connect(sqlite_path)
    conn.executescript(SCHEMA)

    current_table = None
    rows: list[list] = []
    inserted_counts = {table: 0 for table in TABLE_COLUMNS}

    with sql_path.open("r", encoding="utf-8") as dump:
        for raw_line in dump:
            line = raw_line.rstrip("\n")

            if current_table is None:
                if line.startswith("COPY public."):
                    current_table = line.split("COPY public.", 1)[1].split(" ", 1)[0]
                    rows = []
                continue

            if line == r"\.":
                insert_copy_rows(conn, current_table, rows)
                inserted_counts[current_table] += len(rows)
                conn.commit()
                current_table = None
                rows = []
                continue

            columns = TABLE_COLUMNS[current_table]
            values = line.split("\t")
            if len(values) != len(columns):
                raise ValueError(
                    f"Expected {len(columns)} fields for {current_table}, got {len(values)}"
                )
            rows.append(
                [
                    coerce_value(current_table, column, decode_copy_value(value))
                    for column, value in zip(columns, values)
                ]
            )

            if len(rows) >= batch_size:
                insert_copy_rows(conn, current_table, rows)
                inserted_counts[current_table] += len(rows)
                conn.commit()
                rows = []

    conn.execute("PRAGMA optimize")
    conn.close()
    return inserted_counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", default="VIC_IDEAS.sql", type=Path)
    parser.add_argument("--sqlite", default="data/vic_ideas.sqlite", type=Path)
    args = parser.parse_args()

    counts = import_dump(args.sql, args.sqlite)
    print(f"Wrote {args.sqlite}")
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
