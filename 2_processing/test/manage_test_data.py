"""
測試資料手動管理腳本 (Manage Test Data)。
支援手動插入或刪除指定的測試數據（支援 PnL 或 Balance Bond），方便配合 SQL 查詢腳本進行測試。

用法示例：
1. 插入 PnL 測試數據：
   python manage_test_data.py --target pnl --action insert --fund-id BHMMF001 --as-of-date 2026-06-25
2. 刪除 PnL 測試數據：
   python manage_test_data.py --target pnl --action delete --fund-id BHMMF001 --as-of-date 2026-06-25
3. 插入 Balance Bond 測試數據：
   python manage_test_data.py --target balance_bond --action insert --fund-id BHMMF001 --as-of-date 2026-06-25
4. 刪除 Balance Bond 測試數據：
   python manage_test_data.py --target balance_bond --action delete --fund-id BHMMF001 --as-of-date 2026-06-25
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 設定工作路徑
CURRENT_DIR = Path(__file__).resolve().parent
PROCESSING_ROOT = CURRENT_DIR.parent
if str(PROCESSING_ROOT) not in sys.path:
    sys.path.insert(0, str(PROCESSING_ROOT))

ROOT = PROCESSING_ROOT.parent

# 定義統一的測試標記，方便精準識別與刪除
TEST_DATA_SOURCE = "MANUAL_TEST_MGR"


def _build_database_url(db_url_arg: str | None) -> str:
    if db_url_arg:
        return db_url_arg
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ.get("POSTGRES_DB", "fsi_risk")
    user = os.environ.get("POSTGRES_USER", "fsi_user")
    password = os.environ.get("POSTGRES_PASSWORD", "change_me")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manually insert or delete test data for fsi tables.")
    parser.add_argument(
        "--target",
        required=True,
        choices=["pnl", "balance_bond"],
        help="目標資料表：'pnl' 代表 transact_portfolio_pnl，'balance_bond' 代表 balance_bond",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["insert", "delete"],
        help="執行動作：'insert' 代表插入測試數據，'delete' 代表清理測試數據",
    )
    parser.add_argument("--fund-id", default="BHMMF001", help="基金/組合 ID，預設 BHMMF001")
    parser.add_argument("--as-of-date", default="2026-06-25", help="基準日 YYYY-MM-DD，預設 2026-06-25")
    parser.add_argument("--database-url", default=None, help="可選：覆蓋 DATABASE_URL")
    return parser.parse_args()


async def _execute_action(args: argparse.Namespace) -> None:
    engine = create_async_engine(_build_database_url(args.database_url))
    async_session_local = async_sessionmaker(engine, expire_on_commit=False)

    eval_date = date.fromisoformat(args.as_of_date)
    port_id = args.fund_id.strip()

    async with async_session_local() as db:
        if args.target == "pnl":
            if args.action == "insert":
                print(f"[INFO] 正在向 fsi.transact_portfolio_pnl 插入測試數據 (Port: {port_id}, Date: {eval_date})...")
                await db.execute(
                    text("""
                        INSERT INTO fsi.transact_portfolio_pnl (
                            evaluate_date, port_id, asset_class_l1, asset_class_l2,
                            net_pnl, mtm_delta, interest_income, realized_return,
                            fx_pnl, fees, currency, data_source, loaded_at
                        ) VALUES (
                            :eval_date, :port_id, 'Equity', 'Stock',
                            1500000.00, 500000.00, 100000.00, 900000.00,
                            0.00, 5000.00, 'HKD', :data_source, CURRENT_TIMESTAMP
                        );
                    """),
                    {
                        "eval_date": eval_date,
                        "port_id": port_id,
                        "data_source": TEST_DATA_SOURCE,
                    },
                )
                await db.commit()
                print(f"[SUCCESS] 成功插入 PnL 測試數據：Port ID = {port_id}, 評估日 = {eval_date}")

            elif args.action == "delete":
                print(f"[INFO] 正在從 fsi.transact_portfolio_pnl 清理測試數據 (Port: {port_id}, Date: {eval_date})...")
                await db.execute(
                    text("""
                        DELETE FROM fsi.transact_portfolio_pnl
                        WHERE port_id = :port_id
                          AND evaluate_date = :eval_date
                          AND data_source = :data_source;
                    """),
                    {
                        "port_id": port_id,
                        "eval_date": eval_date,
                        "data_source": TEST_DATA_SOURCE,
                    },
                )
                await db.commit()
                print(f"[SUCCESS] PnL 測試數據清理完畢。")

        elif args.target == "balance_bond":
            if args.action == "insert":
                print(f"[INFO] 正在向 fsi.balance_bond 插入測試數據 (Port: {port_id}, Date: {eval_date})...")
                await db.execute(
                    text("""
                       INSERT INTO fsi.balance_bond (
                            evaluate_date, port_id, security_code, security_name,
                            market_value, total_market_value, debt_rating, issuer_rating,
                            currency, quantity, cost, loaded_at
                        ) VALUES (
                            :eval_date, :port_id, 'CN0002001234', '26國債01',
                            10000000.00, 10000000.00, 'AAA', 'AAA',
                            'CNY', 100000, 9950000.00, CURRENT_TIMESTAMP
                        );
                    """),
                    {
                        "eval_date": eval_date,
                        "port_id": port_id,
                    },
                )
                await db.commit()
                print(f"[SUCCESS] 成功插入 Balance Bond 測試數據：Port ID = {port_id}, 評估日 = {eval_date}")

            elif args.action == "delete":
                print(f"[INFO] 正在從 fsi.balance_bond 清理測試數據 (Port: {port_id}, Date: {eval_date})...")
                await db.execute(
                    text("""
                        DELETE FROM fsi.balance_bond
                        WHERE port_id = :port_id
                          AND evaluate_date = :eval_date
                          AND security_code = 'CN0002001234';
                    """),
                    {
                        "port_id": port_id,
                        "eval_date": eval_date,
                    },
                )
                await db.commit()
                print(f"[SUCCESS] Balance Bond 測試數據清理完畢。")

    await engine.dispose()


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = _parse_args()
    try:
        asyncio.run(_execute_action(args))
    except Exception as exc:
        print(f"[ERROR] 操作失敗: {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()