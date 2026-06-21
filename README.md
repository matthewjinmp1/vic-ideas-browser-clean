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
- forward beat calculator CLI
- frontend TypeScript
- frontend production build

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
