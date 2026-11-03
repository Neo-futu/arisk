"""灌入 Campisi 国债效应所需的政府债收益率曲线。

数据源：
- 美债 US_TREAS：yfinance ^IRX(3M) / 2YY=F(2Y) / ^FVX(5Y) / ^TNX(10Y) / ^TYX(30Y)
- 中国国债 CN_TREAS：在美债期限结构上按期限减息差，得到可用的 CNY 政府曲线代理
- 港府债 HKGOV：美债期限结构加小幅息差

rate 存小数（4.25% → 0.0425）。
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import yfinance as yf
from dotenv import load_dotenv
from psycopg2.extras import execute_values

START = "2026-03-20"
END = "2026-06-26"

# ticker → (tenor_label, tenor_days)
US_TICKERS = {
    "^IRX": ("3M", 91),
    "2YY=F": ("2Y", 730),
    "^FVX": ("5Y", 1825),
    "^TNX": ("10Y", 3650),
    "^TYX": ("30Y", 10950),
}

# CN = US - spread(pct points)；HK = US + spread
CN_SPREAD_PCT = {"3M": 2.20, "2Y": 2.30, "5Y": 2.40, "10Y": 2.50, "30Y": 2.65}
HK_SPREAD_PCT = {"3M": 0.05, "2Y": 0.10, "5Y": 0.12, "10Y": 0.15, "30Y": 0.20}


def _close_frame() -> pd.DataFrame:
    frame = yf.download(
        list(US_TICKERS),
        start=START,
        end=END,
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    close = frame["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame()
    if hasattr(close.columns, "levels"):
        close.columns = [str(col) for col in close.columns]
    return close.dropna(how="all").sort_index()


def _pct_to_decimal(value: float) -> float:
    """yfinance 国债指数以百分数报价（如 4.39）。"""
    number = float(value)
    return number / 100.0 if abs(number) > 1.5 else number


def build_rows(close: pd.DataFrame) -> list[tuple]:
    rows: list[tuple] = []
    for idx in close.index:
        day: date = idx.date() if hasattr(idx, "date") else idx
        us: dict[str, float] = {}
        for ticker, (tenor, days) in US_TICKERS.items():
            if ticker not in close.columns:
                continue
            raw = close.at[idx, ticker]
            if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                continue
            rate = _pct_to_decimal(float(raw))
            us[tenor] = rate
            rows.append((day, "US_TREAS", tenor, days, rate, "YFINANCE"))
        if not us:
            continue
        for tenor, days in US_TICKERS.values():
            if tenor not in us:
                continue
            cn = max(us[tenor] - CN_SPREAD_PCT[tenor] / 100.0, 0.0001)
            hk = us[tenor] + HK_SPREAD_PCT[tenor] / 100.0
            rows.append((day, "CN_TREAS", tenor, days, cn, "YFINANCE"))
            rows.append((day, "HKGOV", tenor, days, hk, "YFINANCE"))
    return rows


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    close = _close_frame()
    rows = build_rows(close)
    if not rows:
        raise SystemExit("no treasury yield rows downloaded")

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()
    schema = (
        Path(__file__).resolve().parents[3]
        / "1_datastorage"
        / "postgres"
        / "schema"
        / "029_treasury_curve_campisi.sql"
    )
    cur.execute(schema.read_text(encoding="utf-8"))
    cur.execute(
        """
        DELETE FROM fsi.mktdata_yield_curve_quotes
        WHERE curve_id IN ('US_TREAS', 'CN_TREAS', 'HKGOV')
          AND rate_date BETWEEN %s AND %s
          AND data_source = 'YFINANCE'
        """,
        (START, END),
    )
    execute_values(
        cur,
        """
        INSERT INTO fsi.mktdata_yield_curve_quotes (
            rate_date, curve_id, tenor, tenor_days, rate, data_source
        ) VALUES %s
        ON CONFLICT (rate_date, curve_id, tenor) DO UPDATE
        SET tenor_days = EXCLUDED.tenor_days,
            rate = EXCLUDED.rate,
            data_source = EXCLUDED.data_source,
            loaded_at = NOW()
        """,
        rows,
    )
    conn.commit()
    cur.execute(
        """
        SELECT curve_id, COUNT(*), MIN(rate_date), MAX(rate_date),
               MIN(rate), MAX(rate)
        FROM fsi.mktdata_yield_curve_quotes
        WHERE curve_id IN ('US_TREAS', 'CN_TREAS', 'HKGOV')
        GROUP BY 1
        ORDER BY 1
        """
    )
    print("seeded", cur.fetchall())
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
