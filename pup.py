import re
import sys
import time
import random
import os
import sqlite3
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

# =============================
# CONFIG
# =============================
SEARCH_URL = os.getenv("SEARCH_URL")
RESULT_URL = os.getenv("RESULT_URL")
USER_AGENT = os.getenv("USER_AGENT")
INPUT_SELECTOR = os.getenv("INPUT_SELECTOR")
HIDDEN_SELECTOR = os.getenv("HIDDEN_SELECTOR")
PAGINATION_SELECTOR = os.getenv("PAGINATION_SELECTOR")
ROLL_REGEX = os.getenv("ROLL_REGEX")

DB_PATH = os.getenv("DB_PATH", "puppy.db")
SQL_FILE = os.getenv("SQL_FILE", "schema.sql")

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 30))
MIN_DELAY = float(os.getenv("MIN_DELAY", 1.0))
MAX_DELAY = float(os.getenv("MAX_DELAY", 2.0))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

REQUIRED_ENV = [
    SEARCH_URL,
    RESULT_URL,
    USER_AGENT,
    INPUT_SELECTOR,
    HIDDEN_SELECTOR,
    PAGINATION_SELECTOR,
    ROLL_REGEX,
]

if any(v is None for v in REQUIRED_ENV):
    raise RuntimeError("Missing required .env configuration values")


# =============================
# DATABASE INIT
# =============================
def init_db():
    conn = sqlite3.connect(DB_PATH)

    with open(SQL_FILE, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    conn.commit()
    return conn


# =============================
# HTTP SESSION
# =============================
def create_session():
    session = requests.Session()

    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.headers.update({"User-Agent": USER_AGENT})

    return session


def sleep_jitter():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


# =============================
# PART 1 - ROLL COLLECTION
# =============================
def extract_hidden(soup):
    return {
        inp.get("name"): inp.get("value", "")
        for inp in soup.select(HIDDEN_SELECTOR)
        if inp.get("name")
    }


def extract_rolls(html):
    return set(re.findall(ROLL_REGEX, html))


def do_postback(session, soup, arg):
    data = extract_hidden(soup)
    data["__EVENTTARGET"] = "GridView1"
    data["__EVENTARGUMENT"] = arg

    resp = session.post(SEARCH_URL, data=data, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_window_info(soup):
    page_numbers = []
    has_next_window = False

    pagination = soup.select_one(PAGINATION_SELECTOR)

    if not pagination:
        return [1], False

    for a in pagination.find_all("a", href=True):
        if "Page$Last" in a["href"]:
            has_next_window = True
        else:
            m = re.search(r"Page\$(\d+)", a["href"])
            if m:
                page_numbers.append(int(m.group(1)))

    span = pagination.find("span")
    if span:
        try:
            page_numbers.append(int(span.text.strip()))
        except:
            pass

    return sorted(set(page_numbers)), has_next_window


def search_letter(session, letter):
    resp = session.post(
        SEARCH_URL, data={INPUT_SELECTOR: letter}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    return resp.text


def process_letter(session, conn, letter):
    print(f"\n=== Processing {letter.upper()} ===")

    progress_key = f"letter_{letter}"

    row = conn.execute(
        "SELECT value FROM crawl_progress WHERE key=?", (progress_key,)
    ).fetchone()

    saved_page = int(row[0]) if row else 1

    html = search_letter(session, letter)
    soup = BeautifulSoup(html, "html.parser")

    while True:
        page_numbers, has_next_window = parse_window_info(soup)

        for page in page_numbers:
            if page < saved_page:
                continue

            if page != 1:
                html = do_postback(session, soup, f"Page${page}")
                soup = BeautifulSoup(html, "html.parser")

            rolls = extract_rolls(html)

            inserted = 0

            for roll in rolls:
                region_code = roll[:5]
                student_seq_no = int(roll[5:])

                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO roll_numbers(
                        roll_no,
                        region_code,
                        student_seq_no,
                        source
                    ) VALUES (?, ?, ?, 'search')
                """,
                    (roll, region_code, student_seq_no),
                )

                if cur.rowcount:
                    inserted += 1

            conn.execute(
                "INSERT OR REPLACE INTO crawl_progress(key,value) VALUES(?,?)",
                (progress_key, page + 1),
            )

            conn.commit()

            print(
                f"[{letter.upper()}] Page {page} | Found {len(rolls)} | New {inserted}"
            )

            sleep_jitter()

        if not has_next_window:
            break

        html = do_postback(session, soup, "Page$Last")
        soup = BeautifulSoup(html, "html.parser")

    conn.execute(
        "INSERT OR REPLACE INTO crawl_progress(key,value) VALUES(?,?)",
        (progress_key, "done"),
    )

    conn.commit()


def pup_part1(session, conn):
    for letter in "abcdefghijklmnopqrstuvwxyz":
        row = conn.execute(
            "SELECT value FROM crawl_progress WHERE key=?", (f"letter_{letter}",)
        ).fetchone()
        if row and row[0] == "done":
            continue

        process_letter(session, conn, letter)


# =============================
# GAP FILLER
# =============================
def fill_gaps(conn, max_gap_to_fill=5):
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT roll_no, region_code, student_seq_no
        FROM roll_numbers
    """).fetchall()

    region_map = {}

    for roll_no, region_code, seq_no in rows:
        region_map.setdefault(region_code, []).append(seq_no)

    total_added = 0

    for region_code, ids in region_map.items():
        ids = sorted(set(ids))

        for i in range(len(ids) - 1):
            current_id = ids[i]
            next_id = ids[i + 1]

            gap_size = next_id - current_id - 1

            if 0 < gap_size <= max_gap_to_fill:
                for missing_id in range(current_id + 1, next_id):
                    roll_no = f"{region_code}{str(missing_id).zfill(4)}"

                    inserted = cur.execute(
                        """
                        INSERT OR IGNORE INTO roll_numbers(
                            roll_no,
                            region_code,
                            student_seq_no,
                            source
                        ) VALUES (?, ?, ?, 'gap_fill')
                    """,
                        (roll_no, region_code, missing_id),
                    )

                    if inserted.rowcount:
                        cur.execute(
                            """
                            INSERT OR IGNORE INTO roll_fix_log(
                                roll_no,
                                region_code,
                                gap_threshold_used
                            ) VALUES (?, ?, ?)
                        """,
                            (roll_no, region_code, max_gap_to_fill),
                        )

                        total_added += 1

        conn.commit()

    print(f"Total added: {total_added}")


# =============================
# RESULT FETCH / PARSE
# =============================
def fetch_result(session, roll_no):
    resp = session.post(RESULT_URL, data={"Rollno": roll_no}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_result_page(soup):
    data = {
        "personal": {},
        "subjects": [],
        "grand_total": None,
        "grade": None,
    }

    rows = soup.select("table.table-condensed tr")

    section = None

    for row in rows:
        cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]

        if not cells:
            continue

        row_text = " ".join(cells).lower()

        if "personal details" in row_text:
            section = "personal"
            continue

        elif "marks awarded" in row_text:
            section = "marks"
            continue

        elif "final result" in row_text:
            section = "final"
            continue

        # =============================
        # PERSONAL DETAILS
        # =============================
        if section == "personal":
            if len(cells) >= 2:
                key = cells[0].lower()
                value = cells[-1]

                if "roll" in key:
                    data["personal"]["roll_no"] = value

                elif "candidate" in key:
                    data["personal"]["candidate_name"] = value

                elif "father" in key:
                    data["personal"]["father_name"] = value

                elif "mother" in key:
                    data["personal"]["mother_name"] = value

                elif "date of birth" in key:
                    data["personal"]["dob"] = value

                elif "school" in key:
                    data["personal"]["school_name"] = value

        # =============================
        # MARKS AWARDED
        # =============================
        elif section == "marks":
            if len(cells) >= 4 and cells[0].lower() != "subject code":
                try:
                    max_marks = int(re.search(r"\d+", cells[2]).group())
                    marks_secured = int(re.search(r"\d+", cells[3]).group())
                except:
                    continue

                data["subjects"].append(
                    {
                        "subject_code": cells[0].strip(),
                        "subject_name": cells[1].strip(),
                        "max_marks": max_marks,
                        "marks_secured": marks_secured,
                    }
                )

        # =============================
        # FINAL RESULT
        # =============================
        elif section == "final":
            joined = " ".join(cells)

            grand_total_match = re.search(
                r"grand\s*total.*?(\d+)", joined, re.IGNORECASE
            )

            if grand_total_match:
                data["grand_total"] = int(grand_total_match.group(1))

            grade_match = re.search(
                r"result\s*grade.*?([A-Z][0-9]?)", joined, re.IGNORECASE
            )

            if grade_match:
                data["grade"] = grade_match.group(1)

    return data


# =============================
# PART 2 - FETCH STUDENT DATA
# =============================
def process_roll(session, conn, roll_no):
    cur_time = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        html = fetch_result(session, roll_no)
        soup = BeautifulSoup(html, "html.parser")

        parsed = parse_result_page(soup)
        personal = parsed["personal"]

        if not personal:
            conn.execute(
                """
                UPDATE roll_numbers
                SET fetch_status=?, last_attempt=?
                WHERE roll_no=?
            """,
                ("failed", cur_time, roll_no),
            )
            conn.commit()
            print(f"[{roll_no}] Invalid / Not Found")
            return

        cur = conn.cursor()

        cur.execute(
            """
            INSERT OR REPLACE INTO students(
                roll_no,
                candidate_name,
                father_name,
                mother_name,
                dob,
                school_name,
                grand_total,
                grade,
                raw_html
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                personal.get("roll_no"),
                personal.get("candidate_name"),
                personal.get("father_name"),
                personal.get("mother_name"),
                personal.get("dob"),
                personal.get("school_name"),
                parsed.get("grand_total"),
                parsed.get("grade"),
                html,
            ),
        )

        cur.execute("DELETE FROM student_subject_marks WHERE roll_no=?", (roll_no,))

        for mark in parsed["subjects"]:
            cur.execute(
                """
                INSERT OR IGNORE INTO subjects(
                    subject_code,
                    subject_name,
                    max_marks
                ) VALUES (?, ?, ?)
            """,
                (mark["subject_code"], mark["subject_name"], mark["max_marks"]),
            )

            cur.execute(
                """
                INSERT INTO student_subject_marks(
                    roll_no,
                    subject_code,
                    marks_secured
                ) VALUES (?, ?, ?)
            """,
                (roll_no, mark["subject_code"], mark["marks_secured"]),
            )

        conn.execute(
            """
            UPDATE roll_numbers
            SET fetch_status=?, last_attempt=?
            WHERE roll_no=?
        """,
            ("fetched", cur_time, roll_no),
        )

        conn.commit()

        print(f"[{roll_no}] Fetched")

        sleep_jitter()

    except KeyboardInterrupt:
        print("\nInterrupted safely.")
        raise

    except requests.exceptions.RetryError:
        print(f"[{roll_no}] Rate limited. Cooling 60s...")

        conn.execute(
            """
            UPDATE roll_numbers
            SET last_attempt=?
            WHERE roll_no=?
        """,
            (cur_time, roll_no),
        )

        conn.commit()

        time.sleep(60)

    except Exception as e:
        print(f"[{roll_no}] ERROR: {e}")

        conn.execute(
            """
            UPDATE roll_numbers
            SET fetch_status=?, last_attempt=?
            WHERE roll_no=?
        """,
            ("failed", cur_time, roll_no),
        )

        conn.commit()


def pup_part2(session, conn):
    rows = conn.execute("""
        SELECT roll_no
        FROM roll_numbers
        WHERE fetch_status IS NULL
           OR fetch_status != 'fetched'
    """).fetchall()

    print(f"Total to fetch: {len(rows)}")

    for (roll_no,) in rows:
        process_roll(session, conn, roll_no)


# =============================
# MAIN
# =============================
def main_menu():
    conn = init_db()
    session = create_session()

    try:
        while True:
            print("\n1. Collect Roll Numbers")
            print("2. Auto Fill Missing Roll Numbers")
            print("3. Fetch Student Data")
            print("4. Exit")

            choice = input("Choice: ").strip()

            if choice == "1":
                pup_part1(session, conn)

            elif choice == "2":
                gap = int(input("Enter the maximum gap"))
                fill_gaps(conn, gap)

            elif choice == "3":
                pup_part2(session, conn)

            elif choice == "4":
                break

    except KeyboardInterrupt:
        print("\nInterrupted safely.")

    finally:
        conn.commit()
        conn.close()


if __name__ == "__main__":
    main_menu()
