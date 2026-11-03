"""补齐归因区间的指数行情、个券行情，并倒推每日成分权重。

成分没有供应商对接。每日入选个券后，在接近等权的前提下，
把权重调到组合收益尽量等于当日指数收益。
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import numpy as np
import psycopg2
import yfinance as yf
from dotenv import load_dotenv
from psycopg2.extras import execute_values

START = "2026-03-20"
END = "2026-06-26"

HSI_MEMBERS = [
    ("0700.HK", "腾讯控股", "Information Technology", "HKEX", "HKD"),
    ("9988.HK", "阿里巴巴", "Consumer Discretionary", "HKEX", "HKD"),
    ("0005.HK", "汇丰控股", "Financials", "HKEX", "HKD"),
    ("0939.HK", "建设银行", "Financials", "HKEX", "HKD"),
    ("1299.HK", "友邦保险", "Financials", "HKEX", "HKD"),
    ("1398.HK", "工商银行", "Financials", "HKEX", "HKD"),
    ("0388.HK", "香港交易所", "Financials", "HKEX", "HKD"),
    ("2318.HK", "中国平安", "Financials", "HKEX", "HKD"),
    ("3690.HK", "美团", "Consumer Discretionary", "HKEX", "HKD"),
    ("1810.HK", "小米集团", "Information Technology", "HKEX", "HKD"),
    ("0941.HK", "中国移动", "Communication Services", "HKEX", "HKD"),
    ("0883.HK", "中国海洋石油", "Energy", "HKEX", "HKD"),
]
FI_MEMBERS = [
    ("BIL", "iShares 1-3 Month Treasury Bond ETF", "NYSE", "USD"),
    ("SGOV", "iShares 0-3 Month Treasury Bond ETF", "NYSE", "USD"),
    ("LQD", "iShares iBoxx $ IG Corp Bond ETF", "NYSE", "USD"),
    ("VCIT", "Vanguard Intermediate-Term Corp Bond ETF", "NYSE", "USD"),
    ("3141.HK", "ABF HK Bond Index ETF", "HKEX", "HKD"),
]
INDEX_TICKERS = {"HSI": "^HSI", "USD_AGG": "AGG"}


def fit_weights(security_returns: np.ndarray, index_return: float) -> np.ndarray:
    """贴近等权，且组合收益等于指数收益；不可行时退回等权。"""
    count = len(security_returns)
    equal = np.full(count, 1.0 / count)
    low, high = float(security_returns.min()), float(security_returns.max())
    if high - low < 1e-12:
        return equal
    target = min(max(float(index_return), low), high)
    centered = security_returns - security_returns.mean()
    scale = float(centered @ centered)
    if scale < 1e-18:
        return equal
    shift = (target - float(equal @ security_returns)) / scale
    raw = equal + shift * centered
    raw = np.clip(raw, 0.0, None)
    total = float(raw.sum())
    return raw / total if total else equal


def close_frame():
    tickers = [item[0] for item in HSI_MEMBERS] + [item[0] for item in FI_MEMBERS] + list(INDEX_TICKERS.values())
    frame = yf.download(tickers, start=START, end=END, auto_adjust=True, progress=False, threads=False)
    close = frame["Close"]
    if hasattr(close.columns, "levels"):
        close.columns = [str(col) for col in close.columns]
    return close.dropna(how="all").sort_index()


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    prices = close_frame()
    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()
    schema = Path(__file__).resolve().parents[3] / "1_datastorage" / "postgres" / "schema" / "028_attribution_benchmark_market.sql"
    cur.execute(schema.read_text(encoding="utf-8"))

    industry_schema = (
        Path(__file__).resolve().parents[3]
        / "1_datastorage"
        / "postgres"
        / "schema"
        / "030_mktdata_stock_industry.sql"
    )
    cur.execute(industry_schema.read_text(encoding="utf-8"))

    for code, name, sector, market, currency in HSI_MEMBERS:
        cur.execute(
            """
            INSERT INTO fsi.mktdata_stock_static (
                internal_id, security_code, security_name, market_id, currency,
                country, sector_level1, industry_standard, data_source
            ) VALUES (%s,%s,%s,%s,%s,'HK',%s,'GICS','YFINANCE')
            ON CONFLICT (internal_id) DO UPDATE
            SET security_name = EXCLUDED.security_name,
                sector_level1 = EXCLUDED.sector_level1,
                market_id = EXCLUDED.market_id
            """,
            (code, code, name, market, currency, sector),
        )
        industry_code = "".join(ch if ch.isalnum() else "-" for ch in sector.upper()).strip("-")
        cur.execute(
            """
            INSERT INTO fsi.mktdata_stock_industry (
                security_code, internal_id, standard,
                industry_code, industry_name,
                level1_code, level1_name,
                begin_date, end_date, is_primary, data_source
            ) VALUES (%s,%s,'GICS',%s,%s,%s,%s,DATE '1900-01-01',NULL,TRUE,'YFINANCE')
            ON CONFLICT (security_code, standard, industry_code, begin_date) DO UPDATE
            SET industry_name = EXCLUDED.industry_name,
                level1_code = EXCLUDED.level1_code,
                level1_name = EXCLUDED.level1_name,
                is_primary = TRUE,
                loaded_at = NOW()
            """,
            (code, code, industry_code, sector, industry_code, sector),
        )

    quote_rows = []
    index_rows = []
    dates = [idx.date() for idx in prices.index]
    previous: dict[str, float] = {}
    market_of = {item[0]: item[3] for item in HSI_MEMBERS}
    market_of.update({item[0]: item[2] for item in FI_MEMBERS})
    members = list(market_of)
    for day, idx in zip(dates, prices.index):
        for code in members:
            if code not in prices.columns or np.isnan(prices.at[idx, code]):
                continue
            close = float(prices.at[idx, code])
            prev = previous.get(code)
            change = None if not prev else (close / prev - 1.0) * 100.0
            quote_rows.append((day, code, market_of[code], "CLOSE", close, prev, change, "YFINANCE"))
            previous[code] = close
        for index_code, ticker in INDEX_TICKERS.items():
            if ticker not in prices.columns or np.isnan(prices.at[idx, ticker]):
                continue
            close = float(prices.at[idx, ticker])
            prev = previous.get(ticker)
            change = None if not prev else (close / prev - 1.0) * 100.0
            index_rows.append((day, index_code, close, close, close, close, prev, change, "YFINANCE"))
            previous[ticker] = close

    execute_values(
        cur,
        """
        INSERT INTO fsi.mktdata_quotes (
            price_date, security_code, market_id, price_type,
            close_price, prev_close, price_change_pct, data_source
        ) VALUES %s
        ON CONFLICT (price_date, security_code, price_type) DO UPDATE
        SET close_price = EXCLUDED.close_price,
            prev_close = EXCLUDED.prev_close,
            price_change_pct = EXCLUDED.price_change_pct,
            market_id = EXCLUDED.market_id,
            data_source = EXCLUDED.data_source
        """,
        quote_rows,
    )
    execute_values(
        cur,
        """
        INSERT INTO fsi.mktdata_index_quotes (
            price_date, index_code, open_price, high_price, low_price,
            close_price, prev_close, price_change_pct, data_source
        ) VALUES %s
        ON CONFLICT (price_date, index_code) DO UPDATE
        SET close_price = EXCLUDED.close_price,
            open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            prev_close = EXCLUDED.prev_close,
            price_change_pct = EXCLUDED.price_change_pct,
            data_source = EXCLUDED.data_source
        """,
        index_rows,
    )

    hsi_rows = _component_rows(prices, dates, "HSI", "^HSI", [item[0] for item in HSI_MEMBERS])
    fi_rows = _component_rows(prices, dates, "USD_AGG", "AGG", [item[0] for item in FI_MEMBERS])
    cur.execute(
        """
        DELETE FROM fsi.mktdata_index_component
        WHERE index_code IN ('HSI', 'USD_AGG')
          AND rebal_date BETWEEN %s AND %s
        """,
        (date.fromisoformat(START), date.fromisoformat(END)),
    )
    execute_values(
        cur,
        """
        INSERT INTO fsi.mktdata_index_component (
            rebal_date, index_code, security_code, weight_pct, data_source
        ) VALUES %s
        """,
        hsi_rows + fi_rows,
    )
    conn.commit()
    print(f"quotes={len(quote_rows)} index_quotes={len(index_rows)} hsi_components={len(hsi_rows)} fi_components={len(fi_rows)}")
    conn.close()


def _component_rows(prices, dates, index_code: str, ticker: str, members: list[str]) -> list[tuple]:
    rows = []
    prev_index = None
    prev_member: dict[str, float] = {}
    for day, idx in zip(dates, prices.index):
        if ticker not in prices.columns or np.isnan(prices.at[idx, ticker]):
            continue
        index_close = float(prices.at[idx, ticker])
        available = []
        returns = []
        for code in members:
            if code not in prices.columns or np.isnan(prices.at[idx, code]):
                continue
            close = float(prices.at[idx, code])
            if code in prev_member and prev_index:
                available.append(code)
                returns.append(close / prev_member[code] - 1.0)
            prev_member[code] = close
        index_return = None if prev_index is None else index_close / prev_index - 1.0
        prev_index = index_close
        if len(available) < 2 or index_return is None:
            continue
        weights = fit_weights(np.array(returns), index_return)
        for code, weight in zip(available, weights):
            rows.append((day, index_code, code, round(float(weight) * 100.0, 6), "INFERRED"))
    return rows


if __name__ == "__main__":
    main()
