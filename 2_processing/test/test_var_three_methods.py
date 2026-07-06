"""單基金 VaR 三方法測試腳本。

用法示例：
python 2_processing/test/test_var_three_methods.py --fund-id BHMMF001 --as-of-date 2026-06-25
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
PROCESSING_ROOT = ROOT / "2_processing"
if str(PROCESSING_ROOT) not in sys.path:
    sys.path.insert(0, str(PROCESSING_ROOT))

if TYPE_CHECKING:
    from tools.risk.var_calculator import VaRResult


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk",
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
    parser = argparse.ArgumentParser(description="Run VaR for one fund with 3 methods")
    parser.add_argument("--fund-id", required=True, help="基金 ID，例如 BHMMF001")
    parser.add_argument("--as-of-date", required=True, help="估值日 YYYY-MM-DD")
    parser.add_argument("--confidence", type=float, default=0.99, help="置信度，預設 0.99")
    parser.add_argument("--horizon-days", type=int, default=1, help="期限天數，預設 1")
    parser.add_argument("--lookback-days", type=int, default=252, help="歷史窗口天數，預設 252")
    parser.add_argument(
        "--min-observations",
        type=int,
        default=2,
        help="最小收益率樣本數（測試環境可設小一些，預設 2）",
    )
    parser.add_argument("--simulations", type=int, default=10000, help="蒙特卡洛模擬次數，預設 10000")
    parser.add_argument(
        "--database-url",
        default=None,
        help="可選：覆蓋 DATABASE_URL，例如 postgresql+asyncpg://user:pwd@localhost:5432/postgres",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出")
    return parser.parse_args()


def _format_row(result: Any) -> str:
    return (
        f"{result.method:<24} | "
        f"VaR(HKD)={result.var_amount_hkd:>14,.2f} | "
        f"VaR(%NAV)={result.var_pct_nav:>8.4f}% | "
        f"CVaR(HKD)={result.cvar_amount_hkd:>14,.2f} | "
        f"N={result.sample_size}"
    )


async def _run(args: argparse.Namespace) -> list[Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from tools.risk.var_calculator import (  # type: ignore
        compute_distribution_var,
        compute_historical_var,
        compute_monte_carlo_var,
    )

    as_of = date.fromisoformat(args.as_of_date)
    engine = create_async_engine(_build_database_url(args.database_url))
    async_session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session_local() as db:
        historical = await compute_historical_var(
            fund_id=args.fund_id,
            as_of_date=as_of,
            db=db,
            confidence=args.confidence,
            horizon_days=args.horizon_days,
            lookback_days=args.lookback_days,
            min_observations=args.min_observations,
        )
        monte_carlo = await compute_monte_carlo_var(
            fund_id=args.fund_id,
            as_of_date=as_of,
            db=db,
            confidence=args.confidence,
            horizon_days=args.horizon_days,
            lookback_days=args.lookback_days,
            min_observations=args.min_observations,
            simulations=args.simulations,
        )
        distribution = await compute_distribution_var(
            fund_id=args.fund_id,
            as_of_date=as_of,
            db=db,
            confidence=args.confidence,
            horizon_days=args.horizon_days,
            lookback_days=args.lookback_days,
            min_observations=args.min_observations,
        )
    await engine.dispose()
    return [historical, monte_carlo, distribution]


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = _parse_args()
    try:
        results = asyncio.run(_run(args))
    except Exception as exc:
        message = str(exc)
        print("[ERROR] VaR test failed.")
        if "password authentication failed" in message:
            print("[HINT] Database auth failed. Please set correct DATABASE_URL or POSTGRES_* in .env.")
        elif "does not exist" in message and "nav_history" in message:
            print("[HINT] Missing table fsi.nav_history in target DB. Please load schema/data first.")
        else:
            print(f"[DETAIL] {type(exc).__name__}: {message}")
        print("[INFO] Effective DB URL source: --database-url > DATABASE_URL > POSTGRES_* > defaults")
        raise SystemExit(1)

    if args.json:
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2, default=str))
        return

    print(f"fund_id={args.fund_id}, as_of_date={args.as_of_date}")
    print("-" * 108)
    for item in results:
        print(_format_row(item))


if __name__ == "__main__":
    main()
