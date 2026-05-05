import os
import re
import sys
import time
import queue
import random
import signal
import sqlite3
import threading
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

# =========================================================
# CONFIG
# =========================================================
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
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

WORKER_COUNT = int(os.getenv("WORKER_COUNT", 20))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 100))
QUEUE_SIZE = int(os.getenv("QUEUE_SIZE", 1000))

MIN_DELAY = float(os.getenv("MIN_DELAY", 0))
MAX_DELAY = float(os.getenv("MAX_DELAY", 0.05))

shutdown_event = threading.Event()


# =========================================================
# DB INIT
# =========================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")

    with open(SQL_FILE, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    conn.commit()
    conn.close()


# =========================================================
# SESSION FACTORY
# =========================================================
def create_session():
    session = requests.Session()

    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=WORKER_COUNT * 2,
        pool_maxsize=WORKER_COUNT * 2,
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})

    return session


# =========================================================
# PARSER
# =========================================================
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

        elif section == "marks":
            if len(cells) >= 4 and cells[0].lower() != "subject code":
                try:
                    max_marks = int(re.search(r"\d+", cells[2]).group())
                    marks_secured = int(re.search(r"\d+", cells[3]).group())
                except Exception:
                    continue

                data["subjects"].append(
                    {
                        "subject_code": cells[0].strip(),
                        "subject_name": cells[1].strip(),
                        "max_marks": max_marks,
                        "marks_secured": marks_secured,
                    }
                )

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


# =========================================================
# FETCH
# =========================================================
def fetch_result(session, roll_no):
    resp = session.post(
        RESULT_URL,
        data={"Rollno": roll_no},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.text


# =========================================================
# WORKER
# =========================================================
def worker_thread(worker_id, work_queue, result_queue):
    session = create_session()

    while not shutdown_event.is_set():
        try:
            roll_no = work_queue.get(timeout=1)
        except queue.Empty:
            continue

        if roll_no is None:
            work_queue.task_done()
            break

        try:
            if MAX_DELAY > 0:
                time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

            html = fetch_result(session, roll_no)
            soup = BeautifulSoup(html, "html.parser")
            parsed = parse_result_page(soup)

            if not parsed["personal"]:
                result_queue.put(
                    {
                        "roll_no": roll_no,
                        "status": "failed",
                        "reason": "invalid_result",
                    }
                )
            else:
                result_queue.put(
                    {
                        "roll_no": roll_no,
                        "status": "fetched",
                        "html": html,
                        "parsed": parsed,
                    }
                )

        except Exception as e:
            result_queue.put(
                {
                    "roll_no": roll_no,
                    "status": "failed",
                    "reason": str(e),
                }
            )

        finally:
            work_queue.task_done()


# =========================================================
# WRITER
# =========================================================
def writer_thread(result_queue):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON;")
    cur = conn.cursor()

    processed = 0
    fetched_count = 0
    failed_count = 0

    try:
        while True:
            try:
                item = result_queue.get(timeout=1)
            except queue.Empty:
                if shutdown_event.is_set():
                    break
                continue

            if item is None:
                result_queue.task_done()
                break

            roll_no = item["roll_no"]
            now = time.strftime("%Y-%m-%d %H:%M:%S")

            try:
                if item["status"] == "fetched":
                    parsed = item["parsed"]
                    personal = parsed["personal"]

                    cur.execute(
                        """
                        INSERT OR REPLACE INTO students(
                            roll_no, candidate_name, father_name,
                            mother_name, dob, school_name,
                            grand_total, grade, raw_html
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            roll_no,
                            personal.get("candidate_name"),
                            personal.get("father_name"),
                            personal.get("mother_name"),
                            personal.get("dob"),
                            personal.get("school_name"),
                            parsed.get("grand_total"),
                            parsed.get("grade"),
                            item["html"],
                        ),
                    )

                    cur.execute(
                        "DELETE FROM student_subject_marks WHERE roll_no=?",
                        (roll_no,),
                    )

                    for mark in parsed["subjects"]:
                        cur.execute(
                            """
                            INSERT OR IGNORE INTO subjects(
                                subject_code, subject_name, max_marks
                            ) VALUES (?, ?, ?)
                            """,
                            (
                                mark["subject_code"],
                                mark["subject_name"],
                                mark["max_marks"],
                            ),
                        )
                        cur.execute(
                            """
                            INSERT INTO student_subject_marks(
                                roll_no, subject_code, marks_secured
                            ) VALUES (?, ?, ?)
                            """,
                            (roll_no, mark["subject_code"], mark["marks_secured"]),
                        )

                    cur.execute(
                        """
                        UPDATE roll_numbers
                        SET fetch_status='fetched', last_attempt=?
                        WHERE roll_no=?
                        """,
                        (now, roll_no),
                    )
                    fetched_count += 1

                else:
                    cur.execute(
                        """
                        UPDATE roll_numbers
                        SET fetch_status='failed', last_attempt=?
                        WHERE roll_no=?
                        """,
                        (now, roll_no),
                    )
                    failed_count += 1

                processed += 1

                if processed % BATCH_SIZE == 0:
                    conn.commit()
                    print(
                        f"[Writer] Processed={processed} "
                        f"Fetched={fetched_count} "
                        f"Failed={failed_count}"
                    )

            finally:

                result_queue.task_done()

    finally:

        conn.commit()
        conn.close()
        print(
            f"[Writer] Done. Processed={processed} "
            f"Fetched={fetched_count} "
            f"Failed={failed_count}"
        )


# =========================================================
# MAIN FETCH PIPELINE
# =========================================================
def pup_part2():
    read_conn = sqlite3.connect(DB_PATH)
    rows = read_conn.execute("""
        SELECT roll_no
        FROM roll_numbers
        WHERE fetch_status IS NULL
           OR fetch_status != 'fetched'
    """).fetchall()
    read_conn.close()

    total = len(rows)
    print(f"Total pending rolls: {total}")

    work_queue = queue.Queue(maxsize=QUEUE_SIZE)
    result_queue = queue.Queue(maxsize=QUEUE_SIZE)

    writer = threading.Thread(target=writer_thread, args=(result_queue,), daemon=True)
    writer.start()

    workers = []
    for i in range(WORKER_COUNT):
        t = threading.Thread(
            target=worker_thread, args=(i, work_queue, result_queue), daemon=True
        )
        t.start()
        workers.append(t)

    try:
        for idx, (roll_no,) in enumerate(rows, 1):
            if shutdown_event.is_set():
                break
            work_queue.put(roll_no)
            if idx % 1000 == 0:
                print(f"[Main] Queued {idx}/{total}")

        for _ in workers:
            work_queue.put(None)

        work_queue.join()

        result_queue.put(None)
        result_queue.join()

    except KeyboardInterrupt:

        pass

    finally:
        shutdown_event.set()

        for _ in workers:
            try:
                work_queue.put_nowait(None)
            except queue.Full:
                pass

        for t in workers:
            t.join(timeout=5)

        try:
            result_queue.put_nowait(None)
        except queue.Full:
            pass

        writer.join(timeout=10)


# =========================================================
# SIGNAL HANDLER  (FIX 1)
# =========================================================
def signal_handler(sig, frame):

    print("\nInterrupt received. Shutting down safely...")
    shutdown_event.set()

    raise KeyboardInterrupt


# =========================================================
# MENU
# =========================================================
def main():
    signal.signal(signal.SIGINT, signal_handler)

    init_db()

    while True:
        print("\n1. Fetch Student Data")
        print("2. Exit")

        try:
            choice = input("Choice: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice == "1":
            pup_part2()
        elif choice == "2":
            break


if __name__ == "__main__":
    main()
