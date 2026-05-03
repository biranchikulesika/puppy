import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "puppy.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Count rows to be removed
    cur.execute("""
        SELECT COUNT(*)
        FROM roll_numbers
        WHERE roll_no IN (
            SELECT roll_no FROM roll_fix_log
        )
    """)
    count = cur.fetchone()[0]

    if count == 0:
        print("No gap-filled roll numbers found to remove.")
        conn.close()
        return

    print(f"Found {count} gap-filled roll numbers to remove.")

    confirm = input("Type YES to continue deletion: ").strip()

    if confirm != "YES":
        print("Aborted.")
        conn.close()
        return

    # Delete artificial roll numbers
    cur.execute("""
        DELETE FROM roll_numbers
        WHERE roll_no IN (
            SELECT roll_no FROM roll_fix_log
        )
    """)

    deleted_rolls = cur.rowcount

    # Clear the log table
    cur.execute("DELETE FROM roll_fix_log")

    conn.commit()
    conn.close()

    print(f"Successfully removed {deleted_rolls} roll numbers.")
    print("roll_fix_log cleared.")


if __name__ == "__main__":
    main()
