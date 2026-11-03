"""
測試資料手動管理腳本 (Manage Test Data)。
支援手動插入或刪除指定的測試數據（支援 PnL, Balance Bond, 以及 Stock 持倉與靜態數據），方便配合 SQL 查詢腳本進行測試。

用法示例：
1. 插入 PnL 測試數據：
   python manage_test_data.py --target pnl --action insert --fund-id BHMMF001 --as-of-date 2026-06-25
2. 刪除 PnL 測試數據：
   python manage_test_data.py --target pnl --action delete --fund-id BHMMF001 --as-of-date 2026-06-25
3. 插入 Balance Bond 測試數據：
   python manage_test_data.py --target balance_bond --action insert --fund-id BHMMF001 --as-of-date 2026-06-25
4. 刪除 Balance Bond 測試數據：
   python manage_test_data.py --target balance_bond --action delete --fund-id BHMMF001 --as-of-date 2026-06-25
5. 插入 Stock (持倉 + 靜態行業) 測試數據：
   python manage_test_data.py --target stock --action insert --fund-id BHMMF001 --as-of-date 2026-06-25
6. 刪除 Stock (持倉 + 靜態行業) 測試數據：
   python manage_test_data.py --target stock --action delete --fund-id BHMMF001 --as-of-date 2026-06-25
7. 插入變現天數 (Days to Liquidate) 全套測試數據（組合 + NAV + 持倉 + 行情）：
   python manage_test_data.py --target liquidation --action insert --fund-id LIQTEST001 --as-of-date 2026-06-25
8. 刪除變現天數測試數據：
   python manage_test_data.py --target liquidation --action delete --fund-id LIQTEST001 --as-of-date 2026-06-25
9. 插入 DV01 全套測試數據（組合 + NAV + 債券持倉 + 債券行情）：
   python manage_test_data.py --target dv01 --action insert --fund-id DV01TEST001 --as-of-date 2026-06-25
10. 刪除 DV01 測試數據：
   python manage_test_data.py --target dv01 --action delete --fund-id DV01TEST001 --as-of-date 2026-06-25
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 設定工作路徑
CURRENT_DIR = Path(__file__).resolve().parent
PROCESSING_ROOT = CURRENT_DIR.parent
if str(PROCESSING_ROOT) not in sys.path:
    sys.path.insert(0, str(PROCESSING_ROOT))

ROOT = PROCESSING_ROOT.parent

# 定義統一的測試標記，方便精準識別與刪除
TEST_DATA_SOURCE = "MANUAL_TEST_MGR"
TEST_STOCK_CODE = "0700.HK"

# 變現天數測試：兩檔股票 + 30 日行情，便於手算驗證
LIQUIDATION_TEST_FUND_ID = "LIQTEST001"
LIQUIDATION_TEST_STOCKS = (
    {
        "security_code": "0700.HK",
        "security_name": "騰訊控股",
        "quantity": 100_000,
        "market_value": 3_800_000.00,
        "daily_volume": 1_000_000,
        "close_price": 380.00,
    },
    {
        "security_code": "9988.HK",
        "security_name": "阿里巴巴-SW",
        "quantity": 50_000,
        "market_value": 2_000_000.00,
        "daily_volume": 200_000,
        "close_price": 40.00,
    },
)
LIQUIDATION_TEST_NAV = 10_000_000.00

# DV01 測試：兩檔債券（一檔久期來自持倉、一檔來自行情表），便於手算驗證
DV01_TEST_FUND_ID = "DV01TEST001"
DV01_TEST_NAV = 20_000_000.00
DV01_TEST_BONDS = (
    {
        "security_code": "CN0002001234",
        "security_name": "26國債01",
        "market_value": 10_000_000.00,
        "quantity": 100_000,
        "duration": 5.0,
        "risk_duration": 5.0,
        "maturity_date": date(2031, 6, 15),
    },
    {
        "security_code": "HK0002005678",
        "security_name": "港府債測試券",
        "market_value": 6_000_000.00,
        "quantity": 60_000,
        "duration": None,
        "risk_duration": 3.0,
        "maturity_date": date(2029, 12, 1),
    },
)


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
        choices=["pnl", "balance_bond", "stock", "liquidation", "dv01"],
        help="目標資料表：'pnl' / 'balance_bond' / 'stock' / 'liquidation' / 'dv01'",
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


async def handle_pnl(db: AsyncSession, action: str, port_id: str, eval_date: date) -> None:
    """處理 PnL 測試數據插入與清理"""
    if action == "insert":
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

    elif action == "delete":
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
        print("[SUCCESS] PnL 測試數據清理完畢。")


async def handle_balance_bond(db: AsyncSession, action: str, port_id: str, eval_date: date) -> None:
    """處理 Balance Bond 測試數據插入與清理"""
    if action == "insert":
        print(f"[INFO] 正在向 fsi.balance_bond 插入測試數據 (Port: {port_id}, Date: {eval_date})...")
        await db.execute(
            text("""
                INSERT INTO fsi.balance_bond (
                    evaluate_date, port_id, security_code, security_name,
                    asset_subtype, issuer_name,
                    market_value, total_market_value, debt_rating, issuer_rating,
                    currency, quantity, cost, loaded_at
                ) VALUES (
                    :eval_date, :port_id, 'CN0002001234', '26國債01',
                    'BOND_GOVT', '中國財政部',
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

    elif action == "delete":
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
        print("[SUCCESS] Balance Bond 測試數據清理完畢。")

async def handle_stock(db: AsyncSession, action: str, port_id: str, eval_date: date) -> None:
    """處理 Stock (fsi.balance_stock & fsi.mktdata_stock_static) 測試數據插入與清理"""
    if action == "insert":
        print(f"[INFO] 正在插入股票靜態與持倉測試數據 (Port: {port_id}, Code: {TEST_STOCK_CODE}, Date: {eval_date})...")

        # 1. 避免衝突：先清除同 security_code 的歷史測試數據
        await db.execute(
            text("""
                DELETE FROM fsi.mktdata_stock_static
                WHERE security_code = :security_code
                  AND data_source = :data_source;
            """),
            {
                "security_code": TEST_STOCK_CODE,
                "data_source": TEST_DATA_SOURCE,
            },
        )

        # 2. 插入 mktdata_stock_static 數據
        await db.execute(
            text("""
                INSERT INTO fsi.mktdata_stock_static (
                    internal_id, security_code, security_name, security_name_en,
                    market_id, sector_level1, sector_level2, currency, country,
                    data_source, is_active, created_at, updated_at
                ) VALUES (
                    :internal_id, :security_code, '騰訊控股', 'Tencent Holdings',
                    'HKEX', 'Information Technology', 'Software & Services', 'HKD', 'HK',
                    :data_source, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                );
            """),
            {
                "internal_id": f"STK_{TEST_STOCK_CODE.replace('.', '_')}",
                "security_code": TEST_STOCK_CODE,
                "data_source": TEST_DATA_SOURCE,
            },
        )
        await db.execute(
            text("""
                INSERT INTO fsi.mktdata_stock_industry (
                    security_code, internal_id, standard,
                    industry_code, industry_name,
                    level1_code, level1_name, level2_code, level2_name,
                    begin_date, end_date, is_primary, data_source
                ) VALUES (
                    :security_code, :internal_id, 'GICS',
                    'INFORMATION-TECHNOLOGY', 'Information Technology',
                    'INFORMATION-TECHNOLOGY', 'Information Technology',
                    'SOFTWARE-SERVICES', 'Software & Services',
                    DATE '1900-01-01', NULL, TRUE, :data_source
                )
                ON CONFLICT (security_code, standard, industry_code, begin_date) DO UPDATE
                SET industry_name = EXCLUDED.industry_name,
                    level1_name = EXCLUDED.level1_name,
                    level2_name = EXCLUDED.level2_name,
                    is_primary = TRUE
            """),
            {
                "internal_id": f"STK_{TEST_STOCK_CODE.replace('.', '_')}",
                "security_code": TEST_STOCK_CODE,
                "data_source": TEST_DATA_SOURCE,
            },
        )

        # 3. 插入 balance_stock 持倉數據（補上 market_id）
        await db.execute(
            text("""
                INSERT INTO fsi.balance_stock (
                    evaluate_date, port_id, security_code, security_name,
                    market_id, sector, quantity, market_value, market_value_base, currency,
                    loaded_at
                ) VALUES (
                    :eval_date, :port_id, :security_code, '騰訊控股',
                    'HKEX', 'Information Technology', 10000, 3800000.00, 3800000.00, 'HKD',
                    CURRENT_TIMESTAMP
                );
            """),
            {
                "eval_date": eval_date,
                "port_id": port_id,
                "security_code": TEST_STOCK_CODE,
            },
        )

        await db.commit()
        print(f"[SUCCESS] 成功插入股票持倉及靜態行業測試數據：Port ID = {port_id}, 股票代碼 = {TEST_STOCK_CODE}")

    elif action == "delete":
        print(f"[INFO] 正在清理股票持倉與靜態數據 (Port: {port_id}, Code: {TEST_STOCK_CODE}, Date: {eval_date})...")

        # 1. 刪除 balance_stock 數據
        await db.execute(
            text("""
                DELETE FROM fsi.balance_stock
                WHERE port_id = :port_id
                  AND evaluate_date = :eval_date
                  AND security_code = :security_code;
            """),
            {
                "port_id": port_id,
                "eval_date": eval_date,
                "security_code": TEST_STOCK_CODE,
            },
        )

        # 2. 清理行业映射与静态主数据
        await db.execute(
            text("""
                DELETE FROM fsi.mktdata_stock_industry
                WHERE security_code = :security_code
                  AND data_source = :data_source;
            """),
            {
                "security_code": TEST_STOCK_CODE,
                "data_source": TEST_DATA_SOURCE,
            },
        )
        await db.execute(
            text("""
                DELETE FROM fsi.mktdata_stock_static
                WHERE security_code = :security_code
                  AND data_source = :data_source;
            """),
            {
                "security_code": TEST_STOCK_CODE,
                "data_source": TEST_DATA_SOURCE,
            },
        )

        await db.commit()
        print("[SUCCESS] 股票測試數據清理完畢。")


def _trading_days(end_date: date, count: int) -> list[date]:
    """取得含 end_date 在內、往前 count 個工作日。"""
    days: list[date] = []
    d = end_date
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return days


async def handle_liquidation(db: AsyncSession, action: str, port_id: str, eval_date: date) -> None:
    """處理變現天數計算所需的全套測試數據（para_portfolio / NAV / 持倉 / 行情）。"""
    stock_codes = [s["security_code"] for s in LIQUIDATION_TEST_STOCKS]

    if action == "insert":
        print(
            f"[INFO] 正在插入變現天數全套測試數據 "
            f"(Port: {port_id}, Date: {eval_date}, Stocks: {', '.join(stock_codes)})..."
        )

        await db.execute(
            text("""
                INSERT INTO fsi.para_portfolio (
                    port_id, port_name, port_name_en, port_type, base_currency,
                    inception_date, is_active
                ) VALUES (
                    :port_id, '變現天數測試組合', 'Liquidation Test Fund', 'EQUITY', 'HKD',
                    '2020-01-01', TRUE
                )
                ON CONFLICT (port_id) DO UPDATE SET
                    port_name = EXCLUDED.port_name,
                    is_active = TRUE,
                    updated_at = CURRENT_TIMESTAMP;
            """),
            {"port_id": port_id},
        )

        await db.execute(
            text("""
                INSERT INTO fsi.balance_portfolio_nav (
                    evaluate_date, port_id, currency, total_asset, total_liability,
                    net_asset, shares_outstanding, unit_nav, loaded_at
                ) VALUES (
                    :eval_date, :port_id, 'HKD', :total_asset, 0.00,
                    :net_asset, 10000000, 1.00000000, CURRENT_TIMESTAMP
                )
                ON CONFLICT (evaluate_date, port_id, currency) DO UPDATE SET
                    net_asset = EXCLUDED.net_asset,
                    total_asset = EXCLUDED.total_asset,
                    loaded_at = CURRENT_TIMESTAMP;
            """),
            {
                "eval_date": eval_date,
                "port_id": port_id,
                "total_asset": LIQUIDATION_TEST_NAV,
                "net_asset": LIQUIDATION_TEST_NAV,
            },
        )

        for stock in LIQUIDATION_TEST_STOCKS:
            await db.execute(
                text("""
                    INSERT INTO fsi.balance_stock (
                        evaluate_date, port_id, security_code, security_name,
                        market_id, sector, quantity, market_value, market_value_base, currency,
                        price, loaded_at
                    ) VALUES (
                        :eval_date, :port_id, :security_code, :security_name,
                        'HKEX', 'Information Technology', :quantity, :market_value, :market_value, 'HKD',
                        :close_price, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (evaluate_date, port_id, security_code) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        market_value = EXCLUDED.market_value,
                        market_value_base = EXCLUDED.market_value_base,
                        loaded_at = CURRENT_TIMESTAMP;
                """),
                {
                    "eval_date": eval_date,
                    "port_id": port_id,
                    "security_code": stock["security_code"],
                    "security_name": stock["security_name"],
                    "quantity": stock["quantity"],
                    "market_value": stock["market_value"],
                    "close_price": stock["close_price"],
                },
            )

        quote_dates = _trading_days(eval_date, 30)
        for stock in LIQUIDATION_TEST_STOCKS:
            for price_date in quote_dates:
                await db.execute(
                    text("""
                        INSERT INTO fsi.mktdata_quotes (
                            price_date, security_code, market_id, price_type,
                            close_price, volume, data_source, loaded_at
                        ) VALUES (
                            :price_date, :security_code, 'HKEX', 'CLOSE',
                            :close_price, :volume, :data_source, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (price_date, security_code, price_type) DO UPDATE SET
                            volume = EXCLUDED.volume,
                            close_price = EXCLUDED.close_price,
                            data_source = EXCLUDED.data_source,
                            loaded_at = CURRENT_TIMESTAMP;
                    """),
                    {
                        "price_date": price_date,
                        "security_code": stock["security_code"],
                        "close_price": stock["close_price"],
                        "volume": stock["daily_volume"],
                        "data_source": TEST_DATA_SOURCE,
                    },
                )

        await db.commit()
        print(
            f"[SUCCESS] 變現天數測試數據已就緒：Port={port_id}, NAV={LIQUIDATION_TEST_NAV:,.2f} HKD, "
            f"持倉 {len(LIQUIDATION_TEST_STOCKS)} 檔, 行情 {len(quote_dates)} 個交易日/檔。"
        )
        print(
            "[HINT] 預期結果 (adv_participation_rate=0.20)："
            " max_days=2, weighted_avg≈1.34, stock_exposure≈58%"
        )

    elif action == "delete":
        print(f"[INFO] 正在清理變現天數測試數據 (Port: {port_id}, Date: {eval_date})...")

        await db.execute(
            text("""
                DELETE FROM fsi.balance_stock
                WHERE port_id = :port_id
                  AND evaluate_date = :eval_date
                  AND security_code = ANY(:stock_codes);
            """),
            {"port_id": port_id, "eval_date": eval_date, "stock_codes": stock_codes},
        )

        await db.execute(
            text("""
                DELETE FROM fsi.balance_portfolio_nav
                WHERE port_id = :port_id
                  AND evaluate_date = :eval_date;
            """),
            {"port_id": port_id, "eval_date": eval_date},
        )

        await db.execute(
            text("""
                DELETE FROM fsi.mktdata_quotes
                WHERE security_code = ANY(:stock_codes)
                  AND data_source = :data_source;
            """),
            {"stock_codes": stock_codes, "data_source": TEST_DATA_SOURCE},
        )

        if port_id == LIQUIDATION_TEST_FUND_ID:
            await db.execute(
                text("""
                    DELETE FROM fsi.para_portfolio
                    WHERE port_id = :port_id;
                """),
                {"port_id": port_id},
            )

        await db.commit()
        print("[SUCCESS] 變現天數測試數據清理完畢。")


async def handle_dv01(db: AsyncSession, action: str, port_id: str, eval_date: date) -> None:
    """處理 DV01 計算所需的全套測試數據（para_portfolio / NAV / 債券持倉 / 債券行情）。"""
    bond_codes = [b["security_code"] for b in DV01_TEST_BONDS]

    if action == "insert":
        print(
            f"[INFO] 正在插入 DV01 全套測試數據 "
            f"(Port: {port_id}, Date: {eval_date}, Bonds: {', '.join(bond_codes)})..."
        )

        await db.execute(
            text("""
                INSERT INTO fsi.para_portfolio (
                    port_id, port_name, port_name_en, port_type, base_currency,
                    inception_date, is_active
                ) VALUES (
                    :port_id, 'DV01測試債券組合', 'DV01 Test Bond Fund', 'BOND', 'HKD',
                    '2020-01-01', TRUE
                )
                ON CONFLICT (port_id) DO UPDATE SET
                    port_name = EXCLUDED.port_name,
                    is_active = TRUE,
                    updated_at = CURRENT_TIMESTAMP;
            """),
            {"port_id": port_id},
        )

        await db.execute(
            text("""
                INSERT INTO fsi.balance_portfolio_nav (
                    evaluate_date, port_id, currency, total_asset, total_liability,
                    net_asset, shares_outstanding, unit_nav, loaded_at
                ) VALUES (
                    :eval_date, :port_id, 'HKD', :total_asset, 0.00,
                    :net_asset, 20000000, 1.00000000, CURRENT_TIMESTAMP
                )
                ON CONFLICT (evaluate_date, port_id, currency) DO UPDATE SET
                    net_asset = EXCLUDED.net_asset,
                    total_asset = EXCLUDED.total_asset,
                    loaded_at = CURRENT_TIMESTAMP;
            """),
            {
                "eval_date": eval_date,
                "port_id": port_id,
                "total_asset": DV01_TEST_NAV,
                "net_asset": DV01_TEST_NAV,
            },
        )

        for bond in DV01_TEST_BONDS:
            await db.execute(
                text("""
                    INSERT INTO fsi.balance_bond (
                        evaluate_date, port_id, security_code, security_name,
                        asset_subtype, issuer_name, currency, quantity, cost,
                        market_value, market_value_base, total_market_value,
                        ytm, duration, convexity, coupon_rate, maturity_date,
                        debt_rating, loaded_at
                    ) VALUES (
                        :eval_date, :port_id, :security_code, :security_name,
                        'BOND_GOVT', '測試發行人', 'HKD', :quantity, :cost,
                        :market_value, :market_value, :market_value,
                        0.0350, :duration, 0.50, 0.0325, :maturity_date,
                        'AAA', CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (evaluate_date, port_id, security_code) DO UPDATE SET
                        market_value = EXCLUDED.market_value,
                        market_value_base = EXCLUDED.market_value_base,
                        total_market_value = EXCLUDED.total_market_value,
                        duration = EXCLUDED.duration,
                        loaded_at = CURRENT_TIMESTAMP;
                """),
                {
                    "eval_date": eval_date,
                    "port_id": port_id,
                    "security_code": bond["security_code"],
                    "security_name": bond["security_name"],
                    "quantity": bond["quantity"],
                    "cost": bond["market_value"] * 0.99,
                    "market_value": bond["market_value"],
                    "duration": bond["duration"],
                    "maturity_date": bond["maturity_date"],
                },
            )

            await db.execute(
                text("""
                    INSERT INTO fsi.mktdata_bond_risk (
                        price_date, internal_id, clean_price, dirty_price,
                        ytm, duration, convexity, dv01, data_source, loaded_at
                    ) VALUES (
                        :price_date, :internal_id, 100.50, 101.20,
                        0.0350, :duration, 0.50, :dv01, :data_source, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (price_date, internal_id) DO UPDATE SET
                        duration = EXCLUDED.duration,
                        dv01 = EXCLUDED.dv01,
                        data_source = EXCLUDED.data_source,
                        loaded_at = CURRENT_TIMESTAMP;
                """),
                {
                    "price_date": eval_date,
                    "internal_id": bond["security_code"],
                    "duration": bond["risk_duration"],
                    "dv01": bond["market_value"] * bond["risk_duration"] * 0.0001 / bond["quantity"] * 100,
                    "data_source": TEST_DATA_SOURCE,
                },
            )

        await db.commit()
        total_bond_mv = sum(b["market_value"] for b in DV01_TEST_BONDS)
        expected_dv01 = sum(
            b["market_value"] * (b["duration"] if b["duration"] is not None else b["risk_duration"]) * 0.0001
            for b in DV01_TEST_BONDS
        )
        print(
            f"[SUCCESS] DV01 測試數據已就緒：Port={port_id}, NAV={DV01_TEST_NAV:,.2f} HKD, "
            f"債券 {len(DV01_TEST_BONDS)} 檔, 債券總市值={total_bond_mv:,.2f} HKD。"
        )
        print(
            f"[HINT] 預期結果：portfolio_dv01≈{expected_dv01:,.2f}, "
            f"bond_exposure≈{total_bond_mv / DV01_TEST_NAV * 100:.2f}%, "
            f"dv01_per_million_nav≈{expected_dv01 / DV01_TEST_NAV * 1_000_000:,.2f}"
        )

    elif action == "delete":
        print(f"[INFO] 正在清理 DV01 測試數據 (Port: {port_id}, Date: {eval_date})...")

        await db.execute(
            text("""
                DELETE FROM fsi.balance_bond
                WHERE port_id = :port_id
                  AND evaluate_date = :eval_date
                  AND security_code = ANY(:bond_codes);
            """),
            {"port_id": port_id, "eval_date": eval_date, "bond_codes": bond_codes},
        )

        await db.execute(
            text("""
                DELETE FROM fsi.balance_portfolio_nav
                WHERE port_id = :port_id
                  AND evaluate_date = :eval_date;
            """),
            {"port_id": port_id, "eval_date": eval_date},
        )

        await db.execute(
            text("""
                DELETE FROM fsi.mktdata_bond_risk
                WHERE internal_id = ANY(:bond_codes)
                  AND data_source = :data_source;
            """),
            {"bond_codes": bond_codes, "data_source": TEST_DATA_SOURCE},
        )

        if port_id == DV01_TEST_FUND_ID:
            await db.execute(
                text("""
                    DELETE FROM fsi.para_portfolio
                    WHERE port_id = :port_id;
                """),
                {"port_id": port_id},
            )

        await db.commit()
        print("[SUCCESS] DV01 測試數據清理完畢。")


async def _execute_action(args: argparse.Namespace) -> None:
    engine = create_async_engine(_build_database_url(args.database_url))
    async_session_local = async_sessionmaker(engine, expire_on_commit=False)

    eval_date = date.fromisoformat(args.as_of_date)
    port_id = args.fund_id.strip()

    async with async_session_local() as db:
        if args.target == "pnl":
            await handle_pnl(db, args.action, port_id, eval_date)
        elif args.target == "balance_bond":
            await handle_balance_bond(db, args.action, port_id, eval_date)
        elif args.target == "stock":
            await handle_stock(db, args.action, port_id, eval_date)
        elif args.target == "liquidation":
            await handle_liquidation(db, args.action, port_id, eval_date)
        elif args.target == "dv01":
            await handle_dv01(db, args.action, port_id, eval_date)

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