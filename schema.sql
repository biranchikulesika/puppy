-- =============================
-- Roll Numbers Master Queue
-- =============================
CREATE TABLE IF NOT EXISTS roll_numbers (
    roll_no TEXT PRIMARY KEY,
    region_code TEXT NOT NULL,
    student_seq_no INTEGER NOT NULL,
    source TEXT DEFAULT 'search',
    fetch_status TEXT DEFAULT 'pending',
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_attempt TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_roll_fetch_status
ON roll_numbers(fetch_status);

CREATE INDEX IF NOT EXISTS idx_roll_region
ON roll_numbers(region_code);


-- =============================
-- Gap Fill Audit Log
-- =============================
CREATE TABLE IF NOT EXISTS roll_fix_log (
    roll_no TEXT PRIMARY KEY,
    region_code TEXT NOT NULL,
    gap_threshold_used INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (roll_no) REFERENCES roll_numbers(roll_no)
);


-- =============================
-- Crawl Resume State
-- =============================
CREATE TABLE IF NOT EXISTS crawl_progress (
    key TEXT PRIMARY KEY,
    value TEXT
);


-- =============================
-- Students
-- =============================
CREATE TABLE IF NOT EXISTS students (
    roll_no TEXT PRIMARY KEY,
    candidate_name TEXT,
    father_name TEXT,
    mother_name TEXT,
    dob TEXT,
    school_name TEXT,
    grand_total INTEGER,
    grade TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_html TEXT,
    FOREIGN KEY (roll_no) REFERENCES roll_numbers(roll_no)
);

CREATE INDEX IF NOT EXISTS idx_students_school
ON students(school_name);


-- =============================
-- Subject Catalog
-- =============================
CREATE TABLE IF NOT EXISTS subjects (
    subject_code TEXT PRIMARY KEY,
    subject_name TEXT NOT NULL,
    max_marks INTEGER
);


-- =============================
-- Student Subject Marks
-- =============================
CREATE TABLE IF NOT EXISTS student_subject_marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no TEXT NOT NULL,
    subject_code TEXT NOT NULL,
    marks_secured INTEGER,

    FOREIGN KEY (roll_no) REFERENCES students(roll_no),
    FOREIGN KEY (subject_code) REFERENCES subjects(subject_code),

    UNIQUE(roll_no, subject_code)
);

CREATE INDEX IF NOT EXISTS idx_ssm_roll
ON student_subject_marks(roll_no);

CREATE INDEX IF NOT EXISTS idx_ssm_subject
ON student_subject_marks(subject_code);