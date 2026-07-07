"""
scripts/setup_db.py — 本地數據庫初始化（首次執行一次）

功能：
  1. 用 PostgreSQL 超級用戶（postgres）連接，創建 fsi_user 和 fsi_risk 數據庫
  2. 按順序執行 1_datastorage/postgres/schema/ 下的 11 個 SQL 文件

前置條件：
  - PostgreSQL 16 已本機安裝並運行
  - .env 文件已配置（POSTGRES_PASSWORD 等）

用法：
  python scripts/setup_db.py
  python scripts/setup_db.py --pg-superuser postgres --pg-superpass your_pg_password
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    import psycopg2
    from dotenv import load_dotenv
except ImportError:
    print("請先安裝依賴：pip install psycopg2-binary python-dotenv")
    sys.exit(1)

load_dotenv(ROOT / ".env")

# ── 目標數據庫配置（從 .env 讀取） ────────────────────────────────
DB_HOST     = os.getenv("POSTGRES_SERVER", "localhost")
DB_PORT     = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME     = os.getenv("POSTGRES_DB", "fsi_risk")
DB_USER     = os.getenv("POSTGRES_USER", "fsi_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "change_me")

SCHEMA_DIR = ROOT / "1_datastorage" / "postgres" / "schema"
SCHEMA_FILES = sorted(SCHEMA_DIR.glob("*.sql"))


def parse_args():
    p = argparse.ArgumentParser(description="FSI 數據庫初始化")
    p.add_argument("--pg-superuser", default="postgres", help="PostgreSQL 超級用戶名")
    p.add_argument("--pg-superpass", default="", help="PostgreSQL 超級用戶密碼")
    p.add_argument("--skip-create", action="store_true", help="跳過創建用戶/數據庫步驟")
    p.add_argument("--skip-schema", action="store_true", help="跳過 SQL Schema 初始化")
    return p.parse_args()


def _conn(dbname: str, user: str, password: str) -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=dbname,
        user=user, password=password,
    )


def create_db_and_user(superuser: str, superpass: str) -> None:
    """用 postgres 超級用戶創建 fsi_user 和 fsi_risk 數據庫。"""
    print(f"\n[1/2] 連接 PostgreSQL (user={superuser}, db=postgres)...")
    conn = _conn("postgres", superuser, superpass)
    conn.autocommit = True
    cur = conn.cursor()

    # 創建角色
    cur.execute(f"SELECT 1 FROM pg_roles WHERE rolname = '{DB_USER}'")
    if not cur.fetchone():
        cur.execute(
            f"CREATE ROLE {DB_USER} WITH LOGIN PASSWORD '{DB_PASSWORD}'"
        )
        print(f"  ✓ 用戶 {DB_USER} 已創建")
    else:
        # 確保密碼同步
        cur.execute(f"ALTER ROLE {DB_USER} WITH PASSWORD '{DB_PASSWORD}'")
        print(f"  · 用戶 {DB_USER} 已存在，密碼已同步")

    # 創建數據庫
    cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
    if not cur.fetchone():
        cur.execute(
            f"CREATE DATABASE {DB_NAME} OWNER {DB_USER} ENCODING 'UTF8'"
        )
        print(f"  ✓ 數據庫 {DB_NAME} 已創建")
    else:
        print(f"  · 數據庫 {DB_NAME} 已存在")

    cur.close()
    conn.close()


def run_schema_files() -> None:
    """按序執行 1_datastorage/postgres/schema/*.sql。"""
    print(f"\n[2/2] 初始化 FSI Schema（共 {len(SCHEMA_FILES)} 個文件）...")
    if not SCHEMA_FILES:
        print("  ⚠ 未找到 SQL 文件，請確認 1_datastorage/postgres/schema/ 目錄存在")
        return

    conn = _conn(DB_NAME, DB_USER, DB_PASSWORD)
    conn.autocommit = False

    for sql_file in SCHEMA_FILES:
        sql = sql_file.read_text(encoding="utf-8")
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"  ✓ {sql_file.name}")
        except Exception as e:
            conn.rollback()
            # 常見的「already exists」錯誤不中止
            if "already exists" in str(e) or "AlreadyExists" in type(e).__name__:
                conn.autocommit = True  # reset for next file
                conn = _conn(DB_NAME, DB_USER, DB_PASSWORD)
                conn.autocommit = False
                print(f"  · {sql_file.name}（已存在，跳過）")
            else:
                print(f"  ✗ {sql_file.name}: {e}")
                conn.close()
                raise

    conn.close()


def main() -> None:
    args = parse_args()

    print("=" * 55)
    print("  ARISK — 數據庫初始化")
    print(f"  目標：{DB_HOST}:{DB_PORT}/{DB_NAME}  用戶：{DB_USER}")
    print("=" * 55)

    if not args.skip_create:
        superpass = args.pg_superpass or os.getenv("PG_SUPERPASS", "")
        if not superpass:
            superpass = input(f"請輸入 PostgreSQL 超級用戶 '{args.pg_superuser}' 的密碼：")
        create_db_and_user(args.pg_superuser, superpass)

    if not args.skip_schema:
        run_schema_files()

    print("\n✅ 數據庫初始化完成！")
    print("   下一步：")
    print("   cd backend && alembic upgrade head && python app/initial_data.py")


if __name__ == "__main__":
    main()
