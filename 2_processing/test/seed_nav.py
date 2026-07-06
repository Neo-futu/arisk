"""Seed NAV time series for VaR testing.

Example:
python 2_processing/test/seed_nav.py --fund-id BHMMF001 --as-of-date 2026-06-25 --days 320
"""

from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import numpy as np
import psycopg2
from dotenv import load_dotenv


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(ROOT_DIR, ".env"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed NAV history into fsi.balance_portfolio_nav")
    parser.add_argument("--fund-id", required=True, help="基金/組合ID，例如 BHMMF001")
    parser.add_argument("--as-of-date", required=True, help="截止日期 YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=320, help="生成交易日數（預設 320）")
    parser.add_argument("--currency", default="HKD", help="幣別（預設 HKD）")
    parser.add_argument("--start-nav", type=float, default=2_700_000_000, help="起始淨資產，預設 27億")
    parser.add_argument("--unit-nav", type=float, default=1.0, help="單位淨值，預設 1.0")
    parser.add_argument("--drift", type=float, default=0.00005, help="日漂移（預設 5bp*0.01 = 0.005%）")
    parser.add_argument("--vol", type=float, default=0.00012, help="日波動（預設 0.012%）")
    parser.add_argument("--seed", type=int, default=42, help="隨機種子（預設 42）")
    return parser.parse_args()


def _connect_with_fallbacks():
    candidates = []

    # Priority 1: .env / environment configured credentials
    candidates.append(
        {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "dbname": os.getenv("POSTGRES_DB", "fsi_risk"),
            "user": os.getenv("POSTGRES_USER", "fsi_user"),
            "password": os.getenv("POSTGRES_PASSWORD", "change_me"),
        }
    )

    # Priority 2/3: common local defaults
    candidates.append({"host": "localhost", "port": 5432, "dbname": "postgres", "user": "postgres", "password": "postgres"})
    candidates.append({"host": "localhost", "port": 5432, "dbname": "fsi_risk", "user": "fsi_user", "password": "change_me"})

    last_err = None
    for cfg in candidates:
        try:
            conn = psycopg2.connect(**cfg)
            return conn, cfg
        except Exception as exc:  # pragma: no cover - diagnostics path
            last_err = exc
            continue
    raise RuntimeError(f"Failed to connect to postgres with fallback configs: {last_err}")


def _trading_days(end_date: date, count: int) -> list[date]:
    days: list[date] = []
    d = end_date
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return days


def _q2(v: float) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def seed_nav_series(args: argparse.Namespace) -> None:
    end_date = date.fromisoformat(args.as_of_date)
    trade_days = _trading_days(end_date, args.days)
    rng = np.random.default_rng(args.seed)

    # MMF-like small daily movement; clip extremes to avoid unrealistic jumps.
    shocks = rng.normal(loc=args.drift, scale=args.vol, size=len(trade_days))
    shocks = np.clip(shocks, -0.001, 0.001)

    nav_series: list[float] = []
    cur_nav = float(args.start_nav)
    for ret in shocks:
        cur_nav = max(cur_nav * (1 + float(ret)), 1.0)
        nav_series.append(cur_nav)

    conn, used_cfg = _connect_with_fallbacks()
    try:
        with conn.cursor() as cur:
            inserted = 0
            for i, eval_date in enumerate(trade_days):
                net_asset = _q2(nav_series[i])
                unit_nav = Decimal(str(args.unit_nav)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
                shares = (net_asset / unit_nav).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                acc_unit_nav = Decimal("1.00000000") + Decimal(str(i)) * Decimal("0.00001000")
                day_ret = Decimal(str(shocks[i])).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)

                cur.execute(
                    """
                    INSERT INTO fsi.balance_portfolio_nav
                        (evaluate_date, port_id, currency, total_asset, total_liability,
                         net_asset, shares_outstanding, unit_nav, acc_unit_nav, day_return, loaded_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (evaluate_date, port_id, currency)
                    DO UPDATE SET
                        total_asset = EXCLUDED.total_asset,
                        total_liability = EXCLUDED.total_liability,
                        net_asset = EXCLUDED.net_asset,
                        shares_outstanding = EXCLUDED.shares_outstanding,
                        unit_nav = EXCLUDED.unit_nav,
                        acc_unit_nav = EXCLUDED.acc_unit_nav,
                        day_return = EXCLUDED.day_return,
                        loaded_at = NOW()
                    """,
                    (
                        eval_date,
                        args.fund_id,
                        args.currency,
                        net_asset,
                        Decimal("0.00"),
                        net_asset,
                        shares,
                        unit_nav,
                        acc_unit_nav,
                        day_ret,
                    ),
                )
                inserted += 1

            conn.commit()

            cur.execute(
                """
                SELECT MIN(evaluate_date), MAX(evaluate_date), COUNT(*)
                FROM fsi.balance_portfolio_nav
                WHERE port_id = %s AND currency = %s
                """,
                (args.fund_id, args.currency),
            )
            mn, mx, cnt = cur.fetchone()

        print(
            f"Seeded {inserted} rows for {args.fund_id} ({args.currency}) using "
            f"{used_cfg['user']}@{used_cfg['host']}:{used_cfg['port']}/{used_cfg['dbname']}"
        )
        print(f"Available history window: {mn} -> {mx}, rows={cnt}")
    finally:
        conn.close()


def main() -> None:
    args = _parse_args()
    seed_nav_series(args)


if __name__ == "__main__":
    main()
