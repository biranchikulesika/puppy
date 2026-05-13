import sqlite3
import mysql.connector
from mysql.connector import Error

# =========================
# MYSQL CONFIG
# =========================
MYSQL_HOST = "127.0.0.1"
MYSQL_USER = "username"
MYSQL_PASSWORD = "user_password"
MYSQL_DATABASE = "database_name"

# =========================
# SQLITE DATABASE FILE
# =========================
SQLITE_DB_PATH = "puppy.db"

# =========================
# BATCH SIZE
# =========================
BATCH_SIZE = 5000

# =========================
# CONNECT SQLITE
# =========================
sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
sqlite_cursor = sqlite_conn.cursor()

# =========================
# CONNECT MYSQL
# =========================
mysql_conn = mysql.connector.connect(
    host=MYSQL_HOST,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DATABASE,
    autocommit=False,
    connection_timeout=600
)

mysql_cursor = mysql_conn.cursor()

# =========================
# GET ALL TABLES
# =========================
sqlite_cursor.execute(
    "SELECT name FROM sqlite_master WHERE type='table';"
)

tables = sqlite_cursor.fetchall()

print(f"Found {len(tables)} tables")

# =========================
# TRANSFER EACH TABLE
# =========================
for table in tables:

    table_name = table[0]

    print(f"\nProcessing table: {table_name}")

    # Skip sqlite internal tables
    if table_name.startswith("sqlite_"):
        continue

    # -------------------------
    # GET TABLE STRUCTURE
    # -------------------------
    sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = sqlite_cursor.fetchall()

    columns = []

    for col in columns_info:

        col_name = col[1]
        col_type = col[2].upper()

        # Basic datatype mapping
        if "INT" in col_type:
            mysql_type = "INT"

        elif "CHAR" in col_type or "TEXT" in col_type:
            mysql_type = "TEXT"

        elif (
            "REAL" in col_type
            or "FLOA" in col_type
            or "DOUB" in col_type
        ):
            mysql_type = "DOUBLE"

        elif "BLOB" in col_type:
            mysql_type = "BLOB"

        else:
            mysql_type = "TEXT"

        columns.append(f"`{col_name}` {mysql_type}")

    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
        {", ".join(columns)}
    )
    """

    mysql_cursor.execute(create_table_query)

    # -------------------------
    # PREPARE INSERT QUERY
    # -------------------------
    placeholders = ", ".join(["%s"] * len(columns_info))

    column_names = ", ".join(
        [f"`{col[1]}`" for col in columns_info]
    )

    insert_query = f"""
    INSERT INTO `{table_name}`
    ({column_names})
    VALUES ({placeholders})
    """

    # -------------------------
    # FETCH + INSERT IN BATCHES
    # -------------------------
    sqlite_cursor.execute(f"SELECT * FROM `{table_name}`")

    total_inserted = 0

    while True:

        rows = sqlite_cursor.fetchmany(BATCH_SIZE)

        if not rows:
            break

        try:

            mysql_cursor.executemany(insert_query, rows)
            mysql_conn.commit()

            total_inserted += len(rows)

            print(
                f"Inserted {total_inserted} rows into {table_name}"
            )

        except Error as e:

            print(f"Error inserting batch: {e}")

            mysql_conn.rollback()

    print(f"Finished table: {table_name}")

# =========================
# CLOSE CONNECTIONS
# =========================
sqlite_conn.close()
mysql_conn.close()

print("\nMigration completed successfully.")