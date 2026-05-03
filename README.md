# Puppy

Puppy is a resilient result-scraping and data collection pipeline built to discover roll numbers, fetch student result data, normalize it into a relational database, and resume safely after interruptions.

It was designed for large-scale scraping where reliability matters more than elegance, because public result portals are often held together by ancient HTML and administrative optimism.

# Features

- Crawl roll numbers by paginated name search
- Auto-fill small roll number gaps intelligently
- Fetch full student result data
- Normalize subject/marks into relational schema
- Auto-discover subjects at runtime
- Resume after interruption/crash
- Track fetch status per roll number
- Store raw HTML for audit/debugging
- Configurable via `.env`
- SQLite by default, extensible to other DBs

# Project Structure

```text
puppy/
│
├── pup.py
├── schema.sql
├── .env
├── .env.example
├── requirements.txt
└── puppy.db
````

# Installation

## 1. Clone Repository

```bash
git clone <repo-url>
cd puppy
```

## 2. Create Virtual Environment

```bash
python -m venv venv
```

Activate:

### Windows

```bash
venv\Scripts\activate
```

### Linux / Mac

```bash
source venv/bin/activate
```

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

# Configuration

Create `.env` from `.env.example`.

```bash
cp .env.example .env
```

Fill in actual values.

# Database Setup

Database is auto-created on first run.

```bash
python pup.py
```

This will create:

```text
puppy.db
```

using schema from:

```text
schema.sql
```

# Usage

Run:

```bash
python pup.py
```

Menu:

```text
1. Collect Roll Numbers
2. Auto Fill Missing Roll Numbers
3. Fetch Student Data
4. Exit
```

# Workflow

## Step 1: Collect Roll Numbers

Runs paginated search crawl.

Stores discovered roll numbers in:

```text
roll_numbers
```

## Step 2: Auto Fill Missing Roll Numbers (Optional)

Fills small gaps in sequential roll ranges.

Useful when:

* portal search misses some rolls
* numbering is mostly continuous

Configured by:

```python
max_gap_to_fill
```

in code.

## Step 3: Fetch Student Data

Fetches full result page for every pending roll.

Stores:

* personal details
* final result
* subject marks
* raw HTML

# Database Schema

## roll_numbers

Master queue of discovered/generated roll numbers.

| Column         | Description                  |
| -------------- | ---------------------------- |
| roll_no        | Full roll number             |
| region_code    | Region/prefix code           |
| student_seq_no | Numeric sequence             |
| source         | search / gap_fill / migrated |
| fetch_status   | pending / fetched / failed   |
| discovered_at  | Discovery timestamp          |
| last_attempt   | Last fetch attempt           |

## roll_fix_log

Audit log of gap-filled roll numbers.

| Column             | Description        |
| ------------------ | ------------------ |
| roll_no            | Added roll         |
| region_code        | Region code        |
| gap_threshold_used | Gap threshold used |
| added_at           | Timestamp          |

## crawl_progress

Tracks crawl resume state.

| Column | Description           |
| ------ | --------------------- |
| key    | Progress key          |
| value  | Stored progress value |

## students

Stores student result summary.

| Column         | Description       |
| -------------- | ----------------- |
| roll_no        | Primary key       |
| candidate_name | Student name      |
| father_name    | Father name       |
| mother_name    | Mother name       |
| dob            | Date of birth     |
| school_name    | School name       |
| grand_total    | Total marks       |
| grade          | Final grade       |
| fetched_at     | Fetch timestamp   |
| raw_html       | Raw HTML response |

## subjects

Canonical subject catalog.

| Column       | Description   |
| ------------ | ------------- |
| subject_code | Subject code  |
| subject_name | Subject name  |
| max_marks    | Maximum marks |

## student_subject_marks

Per-student marks.

| Column        | Description    |
| ------------- | -------------- |
| id            | PK             |
| roll_no       | Student roll   |
| subject_code  | Subject code   |
| marks_secured | Obtained marks |

# Useful SQL Queries

## Count Fetched Students

```sql
SELECT COUNT(*) FROM students;
```

## Fetch Progress Overview

```sql
SELECT
    COUNT(*) AS total_rolls,
    SUM(CASE WHEN fetch_status='fetched' THEN 1 ELSE 0 END) AS fetched,
    SUM(CASE WHEN fetch_status='failed' THEN 1 ELSE 0 END) AS failed,
    SUM(CASE WHEN fetch_status='pending' OR fetch_status IS NULL THEN 1 ELSE 0 END) AS pending
FROM roll_numbers;
```

## Verify Grand Total Matches Subject Sum

```sql
SELECT
    s.roll_no,
    s.grand_total,
    SUM(ssm.marks_secured) AS calculated_total
FROM students s
JOIN student_subject_marks ssm
    ON s.roll_no = ssm.roll_no
GROUP BY s.roll_no;
```

## View Student Data

```sql
SELECT
    roll_no,
    candidate_name,
    father_name,
    mother_name,
    dob,
    school_name,
    grand_total,
    grade
FROM students;
```

# Recovery / Resume

Puppy is crash-safe.

If interrupted:

```bash
Ctrl + C
```

Simply rerun:

```bash
python pup.py
```

It resumes automatically using:

* `crawl_progress`
* `fetch_status`

# Backup Recommendation

During long scraping runs:

```bash
cp puppy.db puppy_backup_YYYYMMDD_HHMMSS.db
```

Take periodic backups.

Because databases corrupt, disks fail, power dies, and suffering is evergreen.

# Notes

* Subject catalog auto-populates at runtime.
* Raw HTML is stored for every fetched student for audit/debugging.
* Failed rows remain marked failed and can be retried later.
* SQLite performs well for moderate datasets, but large-scale use may justify PostgreSQL/MySQL migration.



# Disclaimer

Use responsibly and ensure your data collection complies with applicable laws, website terms, and ethical considerations.
