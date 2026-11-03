"""用持仓市值与行情区间收益回填 transact_pnl_item，供资产贡献/个券损益排名。"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

PORT = "BHMMF001"
START = date(2026, 3, 25)
END = date(2026, 6, 25)


def aliases(code: str) -> list[str]:
    out = [code]
    if "." in code:
        out.append(code.split(".", 1)[0])
    return out


def period_return(points: list[tuple[date, float]]) -> float:
    if len(points) < 2:
        return 0.0
    begin, finish = points[0][1], points[-1][1]
    if not begin:
        return 0.0
    return finish / begin - 1.0


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(url)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT security_code, MAX(security_name), 'STOCK'::text,
               AVG(COALESCE(market_value_base, market_value, 0)),
               AVG(COALESCE(weight_pct, 0)) / 100.0
        FROM fsi.balance_stock
        WHERE port_id=%s AND evaluate_date BETWEEN %s AND %s
        GROUP BY security_code
        UNION ALL
        SELECT security_code, MAX(security_name), 'BOND_CORP'::text,
               AVG(COALESCE(market_value_base, market_value, 0)),
               AVG(COALESCE(weight_pct, 0)) / 100.0
        FROM fsi.balance_bond
        WHERE port_id=%s AND evaluate_date BETWEEN %s AND %s
        GROUP BY security_code
        """,
        (PORT, START, END, PORT, START, END),
    )
    holdings = cur.fetchall()
    codes = [row[0] for row in holdings]
    lookup = sorted({alias for code in codes for alias in aliases(code)})
    cur.execute(
        """
        SELECT security_code, price_date, close_price
        FROM fsi.mktdata_quotes
        WHERE price_type='CLOSE' AND security_code = ANY(%s)
          AND price_date BETWEEN %s AND %s
        ORDER BY security_code, price_date
        """,
        (lookup, START, END),
    )
    raw: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for code, day, price in cur.fetchall():
        if price:
            raw[str(code)].append((day, float(price)))

    cur.execute(
        """
        SELECT net_asset FROM fsi.balance_portfolio_nav
        WHERE port_id=%s AND evaluate_date=%s
        """,
        (PORT, START),
    )
    nav_row = cur.fetchone()
    start_nav = float(nav_row[0]) if nav_row and nav_row[0] else 0.0

    rows = []
    by_asset: dict[str, float] = defaultdict(float)
    for code, name, asset, mv, weight in holdings:
        series = raw.get(code)
        if not series:
            for alias in aliases(code):
                if alias in raw:
                    series = raw[alias]
                    break
        ret = period_return(series or [])
        end_mv = float(mv or 0.0)
        if end_mv > 0 and abs(1.0 + ret) > 1e-12:
            pnl = end_mv * ret / (1.0 + ret)
        elif weight and start_nav:
            pnl = float(weight) * start_nav * ret
        else:
            pnl = 0.0
        by_asset[asset] += pnl
        rows.append(
            (
                END,
                PORT,
                code,
                asset,
                None,
                pnl,
                0.0,
                0.0,
                0.0,
                0.0,
                pnl,
                pnl,
                "HKD",
            )
        )

    cur.execute(
        """
        DELETE FROM fsi.transact_pnl_item
        WHERE port_id=%s AND evaluate_date BETWEEN %s AND %s
          AND security_code = ANY(%s)
        """,
        (PORT, START, END, codes),
    )
    execute_values(
        cur,
        """
        INSERT INTO fsi.transact_pnl_item (
            evaluate_date, port_id, security_code, asset_class, asset_subtype,
            mtm_delta, interest_income, realized_gain, fx_pnl, fee_expense,
            net_pnl, net_pnl_base, currency
        ) VALUES %s
        """,
        rows,
    )

    cur.execute(
        """
        DELETE FROM fsi.transact_portfolio_pnl
        WHERE port_id=%s AND evaluate_date=%s AND data_source='YFINANCE_EST'
        """,
        (PORT, END),
    )
    for asset, pnl in by_asset.items():
        l1 = "STOCK" if asset == "STOCK" else "BOND"
        cur.execute(
            """
            INSERT INTO fsi.transact_portfolio_pnl (
                evaluate_date, port_id, asset_class_l1, asset_class_l2,
                net_pnl, mtm_delta, interest_income, realized_return, fx_pnl, fees,
                currency, data_source
            ) VALUES (%s,%s,%s,%s,%s,%s,0,0,0,0,'HKD','YFINANCE_EST')
            ON CONFLICT (evaluate_date, port_id, asset_class_l1, asset_class_l2) DO UPDATE
            SET net_pnl = EXCLUDED.net_pnl,
                mtm_delta = EXCLUDED.mtm_delta,
                data_source = EXCLUDED.data_source,
                loaded_at = NOW()
            """,
            (END, PORT, l1, asset, pnl, pnl),
        )
    conn.commit()
    cur.execute(
        """
        SELECT asset_class::text, count(*), round(sum(net_pnl)::numeric, 2)
        FROM fsi.transact_pnl_item WHERE port_id=%s GROUP BY 1
        """,
        (PORT,),
    )
    print("seeded pnl_item", cur.fetchall())
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
