# Puppy

Puppy is a resilient result-scraping and data collection pipeline. It discovers roll numbers through a paginated name search, fetches student result pages, and normalizes the data into a relational SQLite database with resume-safe progress tracking.

## Features

- Crawl roll numbers by paginated search
- Optional gap-filling for near-continuous roll ranges
- Fetch full student result data with retries and jitter
- Normalize subjects/marks into relational schema
- Persist raw HTML for audit/debugging
- Resume safely after interruptions
- Configurable via `.env`
- SQLite by default, designed for extension

## Repository Layout

```text
puppy/
├── pup.py             # full pipeline: collect, gap fill, fetch
├── supup.py           # high-throughput fetcher (multi-threaded)
├── undo_gap_fill.py   # remove gap-filled roll numbers
├── schema.sql         # database schema
├── sql_command.md     # operational SQL queries
├── requirements.txt
├── .env.example
└── README.md
```

## Prerequisites

- Python 3 + pip

## Setup

1. Create a virtual environment (optional but recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create your `.env` file:

```bash
cp .env.example .env
```

4. Fill in the required values (see the configuration reference below).

## Configuration Reference (`.env`)

### Required

| Variable | Purpose |
| --- | --- |
| `SEARCH_URL` | URL for the roll-number search page |
| `RESULT_URL` | URL for the result page (POST by roll number) |
| `USER_AGENT` | User-Agent header for requests |
| `INPUT_SELECTOR` | Form field name used for the search letter |
| `HIDDEN_SELECTOR` | CSS selector for hidden fields used in pagination postbacks |
| `PAGINATION_SELECTOR` | CSS selector for the pagination container |
| `ROLL_REGEX` | Regex used to extract roll numbers from HTML |

### Optional

| Variable | Default | Used By | Purpose |
| --- | --- | --- | --- |
| `DB_PATH` | `puppy.db` | `pup.py`, `supup.py` | SQLite database file |
| `SQL_FILE` | `schema.sql` | `pup.py`, `supup.py` | Schema file used on startup |
| `REQUEST_TIMEOUT` | `30` | both | HTTP timeout in seconds |
| `MIN_DELAY` | `1.0` (`pup.py`) / `0` (`supup.py`) | both | Min jitter delay between requests |
| `MAX_DELAY` | `2.0` (`pup.py`) / `0.05` (`supup.py`) | both | Max jitter delay between requests |
| `MAX_RETRIES` | `3` | both | HTTP retry count |
| `WORKER_COUNT` | `20` | `supup.py` | Worker thread count |
| `BATCH_SIZE` | `100` | `supup.py` | Commit frequency for writer thread |
| `QUEUE_SIZE` | `1000` | `supup.py` | Queue size for workers/results |

> Note: `.env.example` includes `DB_TYPE`, `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`, but the current codebase does not read those values yet.

## Usage (Manual)

### 1) Run the full pipeline

```bash
python pup.py
```

Menu options:

```
1. Collect Roll Numbers
2. Auto Fill Missing Roll Numbers
3. Fetch Student Data
4. Exit
```

#### Step 1 — Collect Roll Numbers

- Crawls search results for each letter `a`–`z`.
- Uses `crawl_progress` to resume from the last page per letter.

#### Step 2 — Auto Fill Missing Roll Numbers (Optional)

- Fills small gaps in roll sequences per region.
- Default `max_gap_to_fill` is `5` (edit in `pup.py` if needed).
- Every inserted roll is logged to `roll_fix_log`.

#### Step 3 — Fetch Student Data

- Fetches all rolls where `fetch_status != 'fetched'`.
- Stores parsed data in `students`, `subjects`, and `student_subject_marks`.
- Stores raw HTML in `students.raw_html`.

### 2) High-throughput fetch only (large queues)

If you already collected roll numbers and only need fast fetching:

```bash
python supup.py
```

This script:

- Spawns multiple worker threads (`WORKER_COUNT`).
- Writes results in batches (`BATCH_SIZE`).
- Uses low jitter defaults to increase throughput.

Stop safely with `Ctrl+C`; pending rolls remain in `pending/failed` and can be retried later.

### 3) Undo gap-filled rolls

```bash
python undo_gap_fill.py
```

This removes roll numbers inserted by the gap-filler and clears `roll_fix_log`.

## Database Overview

Core tables:

- `roll_numbers` — master queue with `fetch_status`
- `roll_fix_log` — audit log for gap-filled rolls
- `crawl_progress` — resume state for search crawl
- `students` — student summary + raw HTML
- `subjects` — subject catalog
- `student_subject_marks` — per-student marks

See `schema.sql` for full definitions.

## Operational SQL

`sql_command.md` contains ready-to-run queries for:

- progress monitoring
- data integrity checks
- analytics
- maintenance tasks

## Recovery / Resume

- Safe to interrupt with `Ctrl+C`.
- Re-running `pup.py` or `supup.py` resumes from stored state (`crawl_progress` and `fetch_status`).

## Backup Recommendation

During long runs:

```bash
cp puppy.db puppy_backup_YYYYMMDD_HHMMSS.db
```

## Disclaimer

Use responsibly and ensure your data collection complies with applicable laws, website terms, and ethical considerations.
