# VIC Ideas Browser

Clean project folder for the local VIC ideas browser and return analytics.

This folder intentionally excludes the downloaded upstream scraper project, raw SQL dump,
notebooks, screenshot assets, and historical link text files. It keeps only the pieces
needed for the local web app, API, return scripts, tests, and SQLite database.

## Local Data

The app reads `data/vic_ideas.sqlite`. That database was created from already-downloaded
repo data plus local QuickFS/SP500-derived analytics. Do not scrape VIC from this project.

## Run Tests

```bash
./run_local_tests.sh
```

The runner checks:

- return and beat calculation unit tests
- 20-row golden return sample against local raw VIC/QuickFS/S&P inputs
- forward beat calculator CLI
- frontend TypeScript
- frontend production build

The golden sample is generated locally at `analysis/golden_return_sample.tsv`.
It locks down a small inspected mix of long, short, contest-winner, and
partial-history ideas for 1-year and 5-year forward windows. The TSV is ignored
by Git because it contains raw values derived from local datasets.

## Run API

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## Run Frontend

```bash
cd frontend
./node_modules/.bin/vite --host 127.0.0.1 --port 3000
```

The frontend proxies `/api` calls to `http://localhost:8000`.
