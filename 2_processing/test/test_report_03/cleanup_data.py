"""
cleanup_data.py  刪除 report_03 測試數據
==========================================
運行：python 1_datastorage/test/test_report_03/cleanup_data.py
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

TEST_DATE = "2026-06-25"
PORT_IDS  = ("BHMMF001", "BHMMF002")


def connect():
    return psycopg2.connect(
        host     = os.getenv("POSTGRES_HOST", "localhost"),
        port     = int(os.getenv("POSTGRES_PORT", "5432")),
        dbname   = os.getenv("POSTGRES_DB", "fsi_risk"),
        user     = os.getenv("POSTGRES_USER", "fsi_user"),
        password = os.getenv("POSTGRES_PASSWORD", "change_me"),
    )


CLEANUP_SQL = [
    # 持倉/數據表（按 port_id + evaluate_date / confirm_date）
    ("balance_holder_by_channel","confirm_date  = %s AND port_id = ANY(%s)"),
    ("balance_holder_rank",      "confirm_date  = %s AND port_id = ANY(%s)"),
    ("balance_holder_summary", "confirm_date  = %s AND port_id = ANY(%s)"),
    ("balance_valuation_sheet","evaluate_date = %s AND port_id = ANY(%s)"),
    ("balance_repo",           "evaluate_date = %s AND port_id = ANY(%s)"),
    ("balance_deposit",        "evaluate_date = %s AND port_id = ANY(%s)"),
    ("balance_cd",             "evaluate_date = %s AND port_id = ANY(%s)"),
    ("balance_bond",           "evaluate_date = %s AND port_id = ANY(%s)"),
    ("balance_portfolio_asset","evaluate_date = %s AND port_id = ANY(%s)"),
    ("balance_portfolio_mmf",  "evaluate_date = %s AND port_id = ANY(%s)"),  # 貨基專有
    ("transact_portfolio_cashflow","evaluate_date = %s AND port_id = ANY(%s)"),
    ("balance_portfolio_nav",     "evaluate_date = %s AND port_id = ANY(%s)"),
    ("svc_risk_perf",             "as_of_date    = %s AND port_id = ANY(%s)"),
    # 主數據表（僅刪測試組合）
    ("para_portfolio",         "port_id = ANY(%s)"),
]


def cleanup(conn):
    cur = conn.cursor()
    total = 0
    # 日期範圍：TEST_DATE-2 ~ TEST_DATE+1（含歷史和T+1數據）
    from datetime import timedelta, date
    base = date.fromisoformat(TEST_DATE) if isinstance(TEST_DATE, str) else TEST_DATE
    date_range = [str(base + timedelta(days=d)) for d in range(-2, 2)]

    for tbl, where in CLEANUP_SQL:
        if any(k in where for k in ("confirm_date", "evaluate_date", "as_of_date")):
            # 清所有相關日期的測試數據
            date_col = next(k for k in ("confirm_date","evaluate_date","as_of_date") if k in where)
            cur.execute(
                f"DELETE FROM fsi.{tbl} WHERE {date_col} = ANY(%s::date[]) AND port_id = ANY(%s)",
                (date_range, list(PORT_IDS))
            )
        else:
            cur.execute(
                f"DELETE FROM fsi.{tbl} WHERE {where}",
                (list(PORT_IDS),)
            )
        n = cur.rowcount
        total += n
        print(f"  DELETE {tbl}: {n} rows")

    conn.commit()
    print(f"\n[OK] cleanup done. {total} rows deleted.")


if __name__ == "__main__":
    confirm = input(f"刪除 {PORT_IDS} 在 {TEST_DATE} 的所有測試數據？(yes/no): ")
    if confirm.strip().lower() != "yes":
        print("已取消。")
    else:
        conn = connect()
        try:
            cleanup(conn)
        finally:
            conn.close()
