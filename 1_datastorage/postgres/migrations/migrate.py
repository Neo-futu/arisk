"""
migrate.py  ARISK — Schema Migration Runner
=========================================================
用法：
  python 1_datastorage/postgres/migrations/migrate.py          # 執行所有待跑遷移
  python 1_datastorage/postgres/migrations/migrate.py --status  # 顯示遷移狀態
  python 1_datastorage/postgres/migrations/migrate.py --reset   # 重置遷移記錄（危險！）

設計原則：
  · schema 文件存放在 ../schema/，按文件名排序依次執行
  · 每個文件只執行一次，執行結果記錄在 fsi.schema_migration 表
  · 冪等：已執行成功的文件不重跑；失敗的文件標記 ERROR 可重試
  · 不依賴 Alembic/Flyway，純 Python + psycopg2
"""

import os
import hashlib
import argparse
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

SCHEMA_DIR = Path(__file__).parent.parent / "schema"

INIT_DDL = """
CREATE TABLE IF NOT EXISTS fsi.schema_migration (
    id            SERIAL       PRIMARY KEY,
    filename      VARCHAR(128) NOT NULL UNIQUE,
    checksum      VARCHAR(64)  NOT NULL,
    applied_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    duration_ms   INTEGER,
    status        VARCHAR(16)  NOT NULL DEFAULT 'OK',  -- OK / ERROR
    error_msg     TEXT
);
DO $$
BEGIN
    IF pg_get_userbyid(
        (SELECT relowner FROM pg_class
         WHERE oid = 'fsi.schema_migration'::regclass)
    ) = CURRENT_USER THEN
        COMMENT ON TABLE fsi.schema_migration IS
            'Schema 遷移版本記錄：追蹤每個 SQL 文件的執行狀態';
    END IF;
END $$;
"""


def connect():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "fsi_risk"),
        user=os.getenv("POSTGRES_USER", "fsi_user"),
        password=os.getenv("POSTGRES_PASSWORD", "change_me"),
    )


def ensure_migration_table(conn):
    with conn.cursor() as cur:
        # 確保 fsi schema 存在
        cur.execute("CREATE SCHEMA IF NOT EXISTS fsi;")
        cur.execute(INIT_DDL)
    conn.commit()


def get_applied(conn) -> dict:
    """返回 {filename: status} 已執行記錄"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT filename, status, applied_at FROM fsi.schema_migration ORDER BY id"
        )
        return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def file_checksum(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def run_migration(conn, path: Path) -> tuple[str, int, str]:
    """執行單個 SQL 文件，返回 (status, duration_ms, error_msg)"""
    sql = path.read_text(encoding="utf-8")
    start = datetime.now(timezone.utc)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        return "OK", ms, ""
    except Exception as e:
        conn.rollback()
        ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        return "ERROR", ms, str(e)


def record_migration(conn, filename: str, checksum: str,
                     status: str, duration_ms: int, error_msg: str):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO fsi.schema_migration
                (filename, checksum, status, duration_ms, error_msg)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (filename) DO UPDATE SET
                checksum    = EXCLUDED.checksum,
                applied_at  = NOW(),
                status      = EXCLUDED.status,
                duration_ms = EXCLUDED.duration_ms,
                error_msg   = EXCLUDED.error_msg
        """, (filename, checksum, status, duration_ms, error_msg or None))
    conn.commit()


def cmd_status(conn):
    applied = get_applied(conn)
    sql_files = sorted(SCHEMA_DIR.glob("*.sql"))
    print(f"\n{'FILE':<40} {'STATUS':<8} {'APPLIED AT'}")
    print("-" * 70)
    for f in sql_files:
        if f.name in applied:
            status, applied_at = applied[f.name]
            tag = "OK  " if status == "OK" else "ERR "
            print(f"  {f.name:<38} {tag}  {applied_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"  {f.name:<38} PENDING")
    print()


def cmd_migrate(conn):
    applied = get_applied(conn)
    sql_files = sorted(SCHEMA_DIR.glob("*.sql"))
    pending = [f for f in sql_files
               if f.name not in applied or applied[f.name][0] == "ERROR"]

    if not pending:
        print("Nothing to migrate — all files already applied.")
        return

    print(f"Running {len(pending)} migration(s)...\n")
    ok_count = err_count = 0

    for f in pending:
        checksum = file_checksum(f)
        print(f"  [{f.name}] ", end="", flush=True)
        status, ms, err = run_migration(conn, f)
        record_migration(conn, f.name, checksum, status, ms, err)
        if status == "OK":
            print(f"OK  ({ms}ms)")
            ok_count += 1
        else:
            print(f"ERROR ({ms}ms)")
            print(f"    → {err[:120]}")
            err_count += 1
            break  # 遇到錯誤停止，避免後續文件依賴失敗

    print(f"\nDone: {ok_count} OK, {err_count} ERROR")


def cmd_reset(conn):
    ans = input("Reset ALL migration records? (type YES to confirm): ")
    if ans.strip() == "YES":
        with conn.cursor() as cur:
            cur.execute("TRUNCATE fsi.schema_migration")
        conn.commit()
        print("Migration records reset.")
    else:
        print("Cancelled.")


def main():
    parser = argparse.ArgumentParser(description="FSI Schema Migration Runner")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    parser.add_argument("--reset",  action="store_true", help="Reset migration records")
    args = parser.parse_args()

    conn = connect()
    ensure_migration_table(conn)

    if args.status:
        cmd_status(conn)
    elif args.reset:
        cmd_reset(conn)
    else:
        cmd_migrate(conn)

    conn.close()


if __name__ == "__main__":
    main()
