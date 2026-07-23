"""
通用原子 SQL 與 Python 模組動態測試執行器 (Atomic Asset Test Runner)。
支援透過命令列傳入指定的 SQL 檔名或 Python 檔名，進行單獨的數據查詢或函式計算測試。

用法示例：
1. 測試指定的 SQL 檔案：
   python test_atomic_runner.py --file atomic_stock_net_trade_to_nav_ratio.sql --fund-id FUND_TEST_001
2. 測試指定的 Python 模組：
   python test_atomic_runner.py --file atomic_stock_net_trade_to_nav_ratio_calculator.py --fund-id FUND_TEST_001
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 設定工作路徑與模組搜尋路徑
CURRENT_DIR = Path(__file__).resolve().parent
PROCESSING_ROOT = CURRENT_DIR.parent
if str(PROCESSING_ROOT) not in sys.path:
    sys.path.insert(0, str(PROCESSING_ROOT))

ROOT = PROCESSING_ROOT.parent

# Python 模組與其對應的計算函式名稱映射表
PYTHON_MODULE_MAP = {
    "atomic_portfolio_leverage_calculator.py": ("compute_atomic_portfolio_leverage", "tools.risk.leverage_calculator"), # 根據實際存放路徑調整，若在 tools/ 內
    "atomic_repo_exposure_ratio_calculator.py": ("compute_atomic_repo_exposure_ratio", "atomic_repo_exposure_ratio_calculator"),
    "atomic_portfolio_hla_ratio_calculator.py": ("compute_atomic_portfolio_hla_ratio", "atomic_portfolio_hla_ratio_calculator"),
    "atomic_portfolio_days_to_liquidate_calculator.py": ("compute_atomic_portfolio_days_to_liquidate", "atomic_portfolio_days_to_liquidate_calculator"),
    "atomic_stock_net_trade_to_nav_ratio_calculator.py": ("compute_atomic_stock_net_trade_to_nav_ratio", "atomic_stock_net_trade_to_nav_ratio_calculator"),
}


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
    parser = argparse.ArgumentParser(description="Test individual atomic SQL or Python modules.")
    parser.add_argument(
        "--file",
        required=True,
        help="要測試的 SQL 檔名或 Python 檔名",
    )
    parser.add_argument("--fund-id", default="FUND_TEST_001", help="基金 ID")
    parser.add_argument("--as-of-date", default="2026-07-22", help="估值基準日 YYYY-MM-DD")
    parser.add_argument("--start-date", default="2026-07-01", help="區間起始日 YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-07-22", help="區間結束日 YYYY-MM-DD")
    parser.add_argument("--security-code", default="0700.HK", help="股票代號")
    parser.add_argument("--adv-participation-rate", type=float, default=0.20, help="變現參與率")
    parser.add_argument("--database-url", default=None, help="可選：覆蓋 DATABASE_URL")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式輸出執行結果")
    return parser.parse_args()


async def _run_sql_test(file_name: str, args: argparse.Namespace, db: Any) -> Any:
    """動態讀取並執行指定的 SQL 檔案。"""
    # 尋找 SQL 檔（支援目前目錄、上層目錄或遞迴尋找）
    sql_path = CURRENT_DIR / file_name
    if not sql_path.exists():
        sql_path = PROCESSING_ROOT / file_name
    if not sql_path.exists():
        # 嘗試在整個 2_processing 內搜尋
        matches = list(PROCESSING_ROOT.rglob(file_name))
        if matches:
            sql_path = matches[0]

    if not sql_path.exists():
        raise FileNotFoundError(f"找不到指定的 SQL 檔案: {file_name}")

    sql_query = sql_path.read_text(encoding="utf-8")
    
    as_of = date.fromisoformat(args.as_of_date)
    start_dt = date.fromisoformat(args.start_date)
    end_dt = date.fromisoformat(args.end_date)

    params = {
        "fid": args.fund_id,
        "as_of_date": as_of,
        "start_date": start_dt,
        "end_date": end_dt,
        "security_code": args.security_code,
        "adv_participation_rate": args.adv_participation_rate,
    }

    result = await db.execute(text(sql_query), params)
    rows = result.fetchall()
    columns = result.keys()
    serialized_rows = [dict(zip(columns, row)) for row in rows]
    
    return {"file_type": "sql", "file_name": file_name, "row_count": len(serialized_rows), "data": serialized_rows}


async def _run_python_test(file_name: str, args: argparse.Namespace, db: Any) -> Any:
    """動態載入並執行指定的 Python 計算模組。"""
    # 如果使用者直接輸入檔名，嘗試在 2_processing 內動態尋找模組
    target_py = file_name.strip()
    if target_py not in PYTHON_MODULE_MAP:
        # 動態抓取主檔名作為模組名稱
        mod_base_name = Path(target_py).stem
        matches = list(PROCESSING_ROOT.rglob(target_py))
        if not matches:
            raise ValueError(f"未知的 Python 模組: {target_py}")
        # 動態匯入
        spec = importlib.util.spec_from_file_location(mod_base_name, str(matches[0]))
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_base_name] = module
        spec.loader.exec_module(module)
        
        # 推斷計算函式名稱（通常為 compute_開頭）
        func_name = next((attr for attr in dir(module) if attr.startswith("compute_")), None)
        if not func_name:
            raise AttributeError(f"在 {target_py} 中找不到以 compute_ 開頭的計算函式。")
        func = getattr(module, func_name)
    else:
        func_name, mod_name = PYTHON_MODULE_MAP[target_py]
        module = importlib.import_module(mod_name)
        func = getattr(module, func_name)

    as_of = date.fromisoformat(args.as_of_date)
    start_dt = date.fromisoformat(args.start_date)
    end_dt = date.fromisoformat(args.end_date)

    # 根據參數多寡動態傳遞
    if "net_trade" in target_py:
        res = await func(fund_id=args.fund_id, security_code=args.security_code, start_date=start_dt, end_date=end_dt, db=db)
    elif "days_to_liquidate" in target_py:
        res = await func(fund_id=args.fund_id, as_of_date=as_of, db=db, adv_participation_rate=args.adv_participation_rate)
    else:
        res = await func(fund_id=args.fund_id, as_of_date=as_of, db=db)

    serialized_data = asdict(res) if res else None
    return {"file_type": "python", "file_name": file_name, "data": serialized_data}


async def _execute(args: argparse.Namespace) -> Any:
    engine = create_async_engine(_build_database_url(args.database_url))
    async_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_local() as db:
        file_name = args.file.strip()
        if file_name.endswith(".sql"):
            result = await _run_sql_test(file_name, args, db)
        elif file_name.endswith(".py"):
            result = await _run_python_test(file_name, args, db)
        else:
            raise ValueError(f"不支援的檔案格式: {file_name}")

    await engine.dispose()
    return result


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = _parse_args()

    try:
        output = asyncio.run(_execute(args))
    except Exception as exc:
        message = str(exc)
        print(f"[ERROR] Atomic execution failed for '{args.file}': {message}")
        raise SystemExit(1)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return

    print(f"=== Target File: {output['file_name']} ({output['file_type'].upper()}) ===")
    print("-" * 70)
    
    if output["file_type"] == "sql":
        print(f"Query returned {output['row_count']} row(s):")
        for idx, row in enumerate(output["data"], start=1):
            print(f"  Row {idx}: {row}")
    else:
        print("Module execution result:")
        data = output["data"]
        if not data:
            print("  -> Result is None or empty.")
        else:
            for k, v in data.items():
                print(f"  {k}: {v}")
    print("-" * 70)


if __name__ == "__main__":
    main()


    