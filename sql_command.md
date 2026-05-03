# Useful SQL Scripts for Puppy

A collection of practical SQL queries for monitoring, validating, debugging, and analyzing the Puppy database. Because once you have half a million rows, staring at raw tables like a confused archaeologist stops being effective.

# Progress Monitoring

## Total Fetch Progress

```sql
SELECT
    COUNT(*) AS total_rolls,
    SUM(CASE WHEN fetch_status='fetched' THEN 1 ELSE 0 END) AS fetched,
    SUM(CASE WHEN fetch_status='failed' THEN 1 ELSE 0 END) AS failed,
    SUM(CASE WHEN fetch_status='pending' OR fetch_status IS NULL THEN 1 ELSE 0 END) AS pending,
    ROUND(
        100.0 * SUM(CASE WHEN fetch_status='fetched' THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) AS completion_percent
FROM roll_numbers;
````

## Count Fetched Students

```sql
SELECT COUNT(*) AS fetched_students
FROM students;
```

## Count Failed Fetches

```sql
SELECT COUNT(*) AS failed_fetches
FROM roll_numbers
WHERE fetch_status='failed';
```

## View Failed Roll Numbers

```sql
SELECT roll_no, last_attempt
FROM roll_numbers
WHERE fetch_status='failed';
```

# Data Integrity Checks

## Verify Grand Total Matches Sum of Subject Marks

```sql
SELECT
    s.roll_no,
    s.candidate_name,
    s.grand_total,
    SUM(ssm.marks_secured) AS calculated_total
FROM students s
JOIN student_subject_marks ssm
    ON s.roll_no = ssm.roll_no
GROUP BY s.roll_no
HAVING s.grand_total != calculated_total;
```

## Students Missing Marks

```sql
SELECT
    s.roll_no,
    s.candidate_name
FROM students s
LEFT JOIN student_subject_marks ssm
    ON s.roll_no = ssm.roll_no
WHERE ssm.id IS NULL;
```

## Orphan Marks Without Student

```sql
SELECT *
FROM student_subject_marks
WHERE roll_no NOT IN (
    SELECT roll_no FROM students
);
```

## Orphan Marks With Invalid Subject

```sql
SELECT *
FROM student_subject_marks
WHERE subject_code NOT IN (
    SELECT subject_code FROM subjects
);
```

## Duplicate Subject Marks Per Student

```sql
SELECT
    roll_no,
    subject_code,
    COUNT(*) AS duplicates
FROM student_subject_marks
GROUP BY roll_no, subject_code
HAVING COUNT(*) > 1;
```

# Student Data Inspection

## View Students (Without Raw HTML)

```sql
SELECT
    roll_no,
    candidate_name,
    father_name,
    mother_name,
    dob,
    school_name,
    grand_total,
    grade,
    fetched_at
FROM students;
```

## View Full Marksheet Data

```sql
SELECT
    s.roll_no,
    s.candidate_name,
    sub.subject_code,
    sub.subject_name,
    sub.max_marks,
    ssm.marks_secured
FROM students s
JOIN student_subject_marks ssm
    ON s.roll_no = ssm.roll_no
JOIN subjects sub
    ON ssm.subject_code = sub.subject_code
ORDER BY s.roll_no, sub.subject_code;
```

## View Raw HTML Size

```sql
SELECT
    roll_no,
    LENGTH(raw_html) AS html_size
FROM students;
```

Useful for detecting stored error pages instead of result pages.

# Analytics

## Average Marks Per Subject

```sql
SELECT
    sub.subject_code,
    sub.subject_name,
    ROUND(AVG(ssm.marks_secured), 2) AS avg_marks
FROM student_subject_marks ssm
JOIN subjects sub
    ON ssm.subject_code = sub.subject_code
GROUP BY sub.subject_code, sub.subject_name
ORDER BY avg_marks DESC;
```

## Top 10 Students By Grand Total

```sql
SELECT
    roll_no,
    candidate_name,
    grand_total,
    grade
FROM students
ORDER BY grand_total DESC
LIMIT 10;
```

## Grade Distribution

```sql
SELECT
    grade,
    COUNT(*) AS student_count
FROM students
GROUP BY grade
ORDER BY student_count DESC;
```

## Students Per School

```sql
SELECT
    school_name,
    COUNT(*) AS student_count
FROM students
GROUP BY school_name
ORDER BY student_count DESC;
```

# Roll Number Analysis

## Roll Numbers Per Region

```sql
SELECT
    region_code,
    COUNT(*) AS total_rolls
FROM roll_numbers
GROUP BY region_code
ORDER BY total_rolls DESC;
```

## Gap-Filled Roll Numbers Count

```sql
SELECT COUNT(*) AS gap_filled_rolls
FROM roll_fix_log;
```

## Gap-Filled Rolls By Region

```sql
SELECT
    region_code,
    COUNT(*) AS gap_filled_count
FROM roll_fix_log
GROUP BY region_code
ORDER BY gap_filled_count DESC;
```

# Maintenance Scripts

## Reset Failed Rolls To Pending

```sql
UPDATE roll_numbers
SET fetch_status='pending'
WHERE fetch_status='failed';
```

## Reset All Fetched Rows For Refetch

```sql
UPDATE roll_numbers
SET fetch_status='pending',
    last_attempt=NULL;
```

## Clear Parsed Student Data

```sql
DELETE FROM student_subject_marks;
DELETE FROM students;
DELETE FROM subjects;
```

## Delete Invalid Header Subject If Ever Inserted Again

```sql
DELETE FROM subjects
WHERE subject_code='Subject Code';

DELETE FROM student_subject_marks
WHERE subject_code='Subject Code';
```

# Performance / Debugging

## Largest Stored HTML Rows

```sql
SELECT
    roll_no,
    LENGTH(raw_html) AS html_size
FROM students
ORDER BY html_size DESC
LIMIT 20;
```

## Smallest Stored HTML Rows

```sql
SELECT
    roll_no,
    LENGTH(raw_html) AS html_size
FROM students
ORDER BY html_size ASC
LIMIT 20;
```

Tiny HTML often means error page captured instead of result.

# Recommended Workflow

Run these periodically during scraping:

1. Progress Monitoring
2. Grand Total Validation
3. HTML Size Check
4. Failed Fetch Review
5. Backup Database