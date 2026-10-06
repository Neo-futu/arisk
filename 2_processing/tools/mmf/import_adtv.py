"""
import_adtv.py — SFC ADTV 行情導入工具（Excel / yfinance / OpenBB / Wind 四源統一入口）
=====================================
流程：原始行情 → fsi.mktdata_security_quotes（按 source 分源存儲）
      → fsi.fn_compute_adtv_30d() 聚合 → fsi.mktdata_adtv（data_source='MARKET'）
      → fsi.mktdata_adtv_import_log 留痕

用法：
  # Excel 手工導入（先生成模板，填好後導入）
  python import_adtv.py --source excel --make-template adtv.xlsx
  python import_adtv.py --source excel --file adtv.xlsx --date 2026-06-25

  # yfinance 抓取（公開行情，港股/ETF；證券代碼映射 fsi.para_security_alias）
  python import_adtv.py --source yfinance --date 2026-06-25

  # OpenBB 抓取（provider=yfinance，備用通道）
  python import_adtv.py --source openbb --date 2026-05-15 --to 2026-06-25

  # Wind 導入（4_mcp wind_get_price 工具；債券/CD 專業源）
  python import_adtv.py --source wind --date 2026-06-25

  # 聚合 ADTV（從原始表算 30 日平均寫入 mktdata_adtv，覆蓋 PROXY 代理值）
  python import_adtv.py --aggregate --date 2026-06-25
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]  # arisk/
SQL_DIR = REPO_ROOT / "2_processing" / "sql" / "mmf" / "report_06"


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "fsi_risk"),
        user=os.getenv("POSTGRES_USER", "fsi_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def ensure_alias_table(cur) -> None:
    """創建 fsi.para_security_alias（冪等）：security_code ↔ Yahoo/Wind ticker 映射。"""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fsi.para_security_alias (
            security_code   VARCHAR(32) NOT NULL,
            source          VARCHAR(16) NOT NULL,
            alias_code      VARCHAR(32) NOT NULL,
            note            VARCHAR(200),
            loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (security_code, source)
        );
        COMMENT ON TABLE fsi.para_security_alias IS '證券代碼別名映射：security_code ↔ yfinance/wind ticker';
        """
    )


def get_alias_map(cur, source: str) -> dict[str, str]:
    """security_code → alias_code（如 4701.HK → Yahoo ticker）。"""
    cur.execute(
        "SELECT security_code, alias_code FROM fsi.para_security_alias WHERE source = %s",
        (source,),
    )
    return dict(cur.fetchall())


def load_security_aliases_sql() -> str:
    """讀取 023a 種子 SQL（含 yfinance ticker 映射的初始記錄）。"""
    path = REPO_ROOT / "1_datastorage" / "postgres" / "schema" / "023a_security_alias_seed.sql"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def log_import(cur, source, as_of, rows, securities, adtv_total, file_name, status, message):
    cur.execute(
        """
        INSERT INTO fsi.mktdata_adtv_import_log
            (source, as_of_date, rows_upserted, securities_cnt, adtv_total, file_name, status, message)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (source, as_of, rows, securities, adtv_total, file_name, status, message),
    )


# ══════════════════════════════════════════════════════════════
# 1. Excel 手工導入（含模板生成）
# ══════════════════════════════════════════════════════════════

def cmd_make_template(args) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    as_of = date.fromisoformat(args.date) if args.date else date.today()
    out_path = Path(args.file)
    wb = Workbook()
    ws = wb.active
    ws.title = "ADTV導入"

    HDR_FILL = PatternFill("solid", fgColor="1F4E78")
    HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
    THIN = Side(style="thin", color="999999")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    ws["A1"] = ("SFC ADTV 手工導入模板 — A1 説明行，第 3 行表頭，第 4 行起數據（勿改列順序）。"
                "證券代碼與 balance_bond/cd.security_code 對齊；B 日成交額(元)；"
                "ADTV = 過去 30 日 B 列算術平均（聚合時與其他源按優先級取高）。")
    ws["A1"].font = Font(italic=True, size=9, color="666666")

    headers = ["證券代碼", "證券名稱(備註,可留空)", "日成交額(元,必填)", "市場(HKEX/IB/CIBM/OTC)", "幣種", "日期(YYYY-MM-DD)"]
    for ci, h in enumerate(headers, start=1):
        c = ws.cell(row=3, column=ci, value=h)
        c.fill, c.font, c.alignment, c.border = HDR_FILL, HDR_FONT, Alignment(horizontal="center"), BORDER

    # 預填當前 MMF 持倉的證券清單 + 默認日期（成交額留空待填）
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT ON (t.security_code) t.security_code, t.security_name, t.asset_category
        FROM (
            SELECT b.security_code, b.security_name,
                   CASE WHEN COALESCE(b.coupon_type,'FIXED')='FLOAT' THEN 'BOND_FLOAT'
                        ELSE b.asset_subtype::TEXT END AS asset_category
            FROM fsi.balance_bond b
            JOIN fsi.para_portfolio p ON p.port_id = b.port_id
            WHERE p.is_mmf = TRUE AND p.is_active = TRUE AND b.quantity > 0
            UNION ALL
            SELECT c.security_code, c.security_name, 'CD' FROM fsi.balance_cd c
            JOIN fsi.para_portfolio p ON p.port_id = c.port_id
            WHERE p.is_mmf = TRUE AND p.is_active = TRUE
        ) t ORDER BY t.security_code
        """
    )
    r = 4
    for code, name, cat in cur.fetchall():
        ws.cell(row=r, column=1, value=code)
        ws.cell(row=r, column=2, value=name)  # 備註名稱（可留空）
        ws.cell(row=r, column=3, value="")    # 日成交額留空待填
        ws.cell(row=r, column=4, value="HKEX")
        ws.cell(row=r, column=5, value="HKD")
        ws.cell(row=r, column=6, value=as_of.isoformat())
        r += 1
    conn.close()

    for col, w in {"A": 20, "B": 30, "C": 14, "D": 22, "E": 8, "F": 16}.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A4"

    wb.save(out_path)
    logger.info(f"模板已生成: {out_path}（{r-4} 個證券預填，待填 B 列日成交額）")


def cmd_import_excel_daily(args) -> None:
    """逐日行情文件導入（Bloomberg/FINRA 網頁導出格式）。

    模板列（第 3 行表頭，第 4 行起數據）：
      A 證券代碼(CUSIP/ISIN/代碼) | B 證券名稱 | C 收盤價 | D 成交量 | E 幣種 | F 日期
    每行一個證券一個交易日；ADTV 由 fn_compute_adtv_30d 聚合（≥5 日樣本）。
    成交量留空時，按『已平均 ADTV 估計值』處理 → 直寫 mktdata_adtv (EXCEL 源)。
    """
    from openpyxl import load_workbook

    as_of = date.fromisoformat(args.date) if args.date else date.today()
    wb = load_workbook(args.file, data_only=True)
    ws = wb.active
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    rows_upserted = 0
    securities_seen = set()
    skipped = []

    for row in ws.iter_rows(min_row=4, values_only=True):
        code = row[0]
        if not code:
            continue
        code = str(code).strip()
        close = row[2] if len(row) > 2 else None
        volume = row[3] if len(row) > 3 else None
        ccy = (row[4] if len(row) > 4 and row[4] else "USD")[:3]
        qd = row[5] if len(row) > 5 and row[5] else as_of
        if isinstance(qd, datetime):
            qd = qd.date()
        elif isinstance(qd, str):
            qd = date.fromisoformat(qd)

        try:
            close_f = float(close) if close is not None else None
            vol_f = float(volume) if volume is not None else None
        except (TypeError, ValueError):
            skipped.append((code, "invalid close/volume"))
            continue

        if close_f is None:
            skipped.append((code, "missing close"))
            continue

        if vol_f is None or vol_f <= 0:
            # 無成交量：Bloomberg 導出價格 but 無量 → 記價格，量待補
            skipped.append((code, f"{qd} no volume"))
            continue

        cur.execute(
            """
            INSERT INTO fsi.mktdata_security_quotes
                (quote_date, security_code, market_id, close_price, volume, turnover, source, currency)
            VALUES (%s, %s, 'OTC', %s, %s, %s, 'EXCEL', %s)
            ON CONFLICT (quote_date, security_code, source) DO UPDATE
            SET close_price = EXCLUDED.close_price, volume = EXCLUDED.volume,
                turnover = EXCLUDED.turnover, loaded_at = NOW()
            """,
            (qd, code, close_f, vol_f, close_f * vol_f, ccy),
        )
        rows_upserted += 1
        securities_seen.add(code)

    # EXCEL 逐日行情 ≥5 日樣本 → fn_compute_adtv_30d 聚合為 MARKET
    # （與 WIND/YFINANCE/OPENBB 同等待遇，真實逐日數據優先於估計值）
    cur.execute("SELECT fsi.fn_compute_adtv_30d(%s, 30)", (as_of,))
    log_import(cur, "EXCEL_DAILY", as_of, rows_upserted, len(securities_seen),
               None, Path(args.file).name, "OK" if not skipped else "WARN",
               f"skipped={skipped[:5]}")
    conn.close()
    logger.info(f"逐日行情導入完成: {rows_upserted} 行, {len(securities_seen)} 證券, skipped={len(skipped)}")


def cmd_import_excel(args) -> None:
    from openpyxl import load_workbook

    as_of = date.fromisoformat(args.date) if args.date else date.today()
    wb = load_workbook(args.file, data_only=True)
    ws = wb.active
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    rows_upserted = 0
    securities_seen = set()
    skipped = []
    adtv_total = 0.0

    # Excel 手工錄入的是「已平均的 ADTV 估計值」（通常無逐日報價），
    # 直接入庫 mktdata_adtv（data_source='EXCEL'）；MARKET 真實行情（≥5 日樣本
    # 聚合）會覆蓋同證券的 EXCEL 值，PROXY 代理值優先級最低。
    for row in ws.iter_rows(min_row=4, values_only=True):
        code, _name, turnover = row[0], row[1], row[2]
        if not code or turnover is None:
            continue
        code = str(code).strip()
        try:
            tv = float(turnover)
        except (TypeError, ValueError):
            skipped.append((code, "invalid turnover"))
            continue
        if tv <= 0:
            continue
        qd = row[5] if len(row) > 5 and row[5] else as_of
        if isinstance(qd, datetime):
            qd = qd.date()
        elif isinstance(qd, str):
            qd = date.fromisoformat(qd)
        market_id = row[3] if len(row) > 3 and row[3] else "HKEX"
        ccy = (row[4] if len(row) > 4 and row[4] else "HKD")[:3]
        cur.execute(
            """
            INSERT INTO fsi.mktdata_adtv
                (adtv_date, security_code, market_id, adtv_30d, sample_days, data_source)
            VALUES (%s, %s, %s, %s, 1, 'EXCEL')
            ON CONFLICT (adtv_date, security_code) DO UPDATE
            SET adtv_30d = EXCLUDED.adtv_30d,
                market_id = EXCLUDED.market_id,
                sample_days = 1,
                data_source = 'EXCEL',
                loaded_at = NOW()
            """,
            (qd, code, market_id, tv),
        )
        rows_upserted += 1
        securities_seen.add(code)
        adtv_total += tv

    log_import(cur, "EXCEL", as_of, rows_upserted, len(securities_seen),
               adtv_total, Path(args.file).name, "OK" if not skipped else "WARN",
               f"skipped={skipped[:5]}" if skipped else "manual ADTV estimates")
    # MARKET 行情若存在則覆蓋同證券 EXCEL 值
    cur.execute("SELECT fsi.fn_compute_adtv_30d(%s, 30)", (as_of,))
    conn.close()
    logger.info(f"Excel 導入完成: {rows_upserted} 行, {len(securities_seen)} 證券, "
                f"合計 {adtv_total:.0f} 元, skipped={len(skipped)}（MARKET 行情自動覆蓋）")


# ══════════════════════════════════════════════════════════════
# 2. yfinance 抓取
# ══════════════════════════════════════════════════════════════

def fetch_yfinance(tickers: list[str], start: date, end: date) -> dict[str, list[dict]]:
    import yfinance as yf
    result: dict[str, list[dict]] = {}
    for tk in tickers:
        try:
            h = yf.Ticker(tk).history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat())
            if h.empty:
                continue
            result[tk] = [
                {"date": idx.date(), "close": float(r["Close"]), "volume": float(r["Volume"])}
                for idx, r in h.iterrows()
            ]
        except Exception as e:
            logger.warning(f"yfinance {tk}: {e}")
    return result


def cmd_import_yfinance(args) -> None:
    as_of = date.fromisoformat(args.date)
    end = date.fromisoformat(args.to) if args.to else as_of
    start = end - timedelta(days=45)  # 取 45 天保證 ≥30 個交易日樣本

    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    ensure_alias_table(cur)
    seed = load_security_aliases_sql()
    if seed:
        cur.execute(seed)  # 寫入 yfinance ticker 映射
    alias_map = get_alias_map(cur, "YFINANCE")
    if not alias_map:
        conn.close()
        logger.error("無 yfinance alias 映射，請先維護 fsi.para_security_alias")
        return
    data = fetch_yfinance(list(alias_map.values()), start, end)
    rows_upserted = 0
    securities_seen = set()
    # 反向：alias → security_code
    inv = {v: k for k, v in alias_map.items()}
    for tk, rows in data.items():
        sc = inv.get(tk)
        if not sc:
            continue
        for r in rows:
            cur.execute(
                """
                INSERT INTO fsi.mktdata_security_quotes
                    (quote_date, security_code, market_id, close_price, volume, turnover, source, currency)
                VALUES (%s, %s, 'HKEX', %s, %s, %s, 'YFINANCE', 'HKD')
                ON CONFLICT (quote_date, security_code, source) DO UPDATE
                SET close_price = EXCLUDED.close_price, volume = EXCLUDED.volume,
                    turnover = EXCLUDED.turnover, loaded_at = NOW()
                """,
                (r["date"], sc, r["close"], r["volume"], r["close"] * r["volume"]),
            )
            rows_upserted += 1
        securities_seen.add(sc)
    log_import(cur, "YFINANCE", as_of, rows_upserted, len(securities_seen),
               None, None, "OK", f"tickers={len(alias_map)}, fetched={len(data)}")
    conn.close()
    logger.info(f"yfinance 導入完成: {rows_upserted} 行, {len(securities_seen)} 證券")
    if not args.no_aggregate:
        aggregate(cur=None, conn=None, as_of=as_of)


# ══════════════════════════════════════════════════════════════
# 3. OpenBB 抓取
# ══════════════════════════════════════════════════════════════

def cmd_import_openbb(args) -> None:
    """生產級 OpenBB 抓取：多 provider 鏈 fallback + 重試 + 並發 + 覆蓋報告。"""
    import json as _json
    from openbb_fetcher import fetch_batch, health_check, coverage_report

    as_of = date.fromisoformat(args.date)
    end = date.fromisoformat(args.to) if args.to else as_of
    start = end - timedelta(days=45)

    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    ensure_alias_table(cur)
    seed = load_security_aliases_sql()
    if seed:
        cur.execute(seed)
    alias_map = get_alias_map(cur, "OPENBB")
    if not alias_map:
        conn.close()
        logger.error("無 OPENBB alias 映射（請先維護 fsi.para_security_alias）")
        return

    # 1. provider 健康檢查
    health = health_check()
    logger.info("OpenBB provider 健康: " + ", ".join(
        f"{p}={'OK' if i['ok'] else 'FAIL'}" for p, i in health.items()))

    # 2. 並發抓取（多 provider fallback）
    results = fetch_batch(alias_map, start, end, max_workers=args.workers)
    cov = coverage_report(results)
    logger.info(f"OpenBB 覆蓋: {cov['summary']}")

    # 3. 入庫（成功的寫 mktdata_security_quotes；失敗的留給 EXCEL/PROXY 兜底）
    rows_upserted = 0
    securities_seen = set()
    for r in results:
        if r.status != "ok":
            continue
        securities_seen.add(r.security_code)
        # 市場按代碼後綴判斷：HK→HKEX, US→NYSE/NASDAQ
        market_id = "HKEX" if r.alias.endswith(".HK") else "US"
        ccy = "HKD" if r.alias.endswith(".HK") else "USD"
        for row in r.rows:
            cur.execute(
                """
                INSERT INTO fsi.mktdata_security_quotes
                    (quote_date, security_code, market_id, close_price, volume, turnover, source, currency)
                VALUES (%s, %s, %s, %s, %s, %s, 'OPENBB', %s)
                ON CONFLICT (quote_date, security_code, source) DO UPDATE
                SET close_price = EXCLUDED.close_price, volume = EXCLUDED.volume,
                    turnover = EXCLUDED.turnover, loaded_at = NOW()
                """,
                (row["date"], r.security_code, market_id,
                 row["close"], row["volume"], row["turnover"], ccy),
            )
            rows_upserted += 1

    # 4. 審計日誌（含覆蓋報告，便於排查缺口）
    msg = _json.dumps(cov, ensure_ascii=False)
    log_import(cur, "OPENBB", as_of, rows_upserted, len(securities_seen),
               None, None,
               "OK" if cov["summary"]["ok"] > 0 else "WARN",
               f"providers={list(health.keys())}; coverage={cov['summary']}; details={msg[:500]}")
    conn.close()
    logger.info(f"OpenBB 導入完成: {rows_upserted} 行, {len(securities_seen)}/{len(alias_map)} 證券成功; "
                f"缺口 {len(cov['no_data'])+len(cov['errored'])} 個（走 EXCEL/PROXY 兜底）")
    if not args.no_aggregate:
        aggregate(cur=None, conn=None, as_of=as_of)


# ══════════════════════════════════════════════════════════════
# 4. Wind MCP 抓取
# ══════════════════════════════════════════════════════════════

def cmd_import_wind(args) -> None:
    import asyncio
    import importlib
    sys.path.insert(0, str(REPO_ROOT))
    # 4_mcp 為數字開頭包名，需 importlib 動態導入
    call_mcp_tool = importlib.import_module("4_mcp.client").call_mcp_tool

    as_of = date.fromisoformat(args.date)
    end = date.fromisoformat(args.to) if args.to else as_of
    start = end - timedelta(days=45)

    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    ensure_alias_table(cur)
    seed = load_security_aliases_sql()
    if seed:
        cur.execute(seed)
    alias_map = get_alias_map(cur, "WIND")
    if not alias_map:
        conn.close()
        logger.error("無 WIND alias 映射")
        return
    rows_upserted = 0
    securities_seen = set()
    # Wind 取近 30 日成交額（fields=turnover），按證券代碼批量調用
    codes = list(alias_map.values())
    try:
        result = asyncio.run(call_mcp_tool(
            "wind", "wind_get_price",
            {"codes": codes, "start_date": start.isoformat(), "end_date": end.isoformat(),
             "fields": "turnover,volume,close"},
        ))
    except Exception as e:
        logger.error(f"Wind MCP 調用失敗: {e}")
        log_import(cur, "WIND", as_of, 0, 0, None, None, "ERROR", str(e))
        conn.close()
        return
    # 解析 result（MCP 返回結構 normalized dict）
    inv = {v: k for k, v in alias_map.items()}
    rows_data = result.get("data", result) if isinstance(result, dict) else result
    for tk, rows in (rows_data.items() if isinstance(rows_data, dict) else []):
        sc = inv.get(tk)
        if not sc or not isinstance(rows, list):
            continue
        for r in rows:
            qd = r.get("date") or r.get("DATE")
            if isinstance(qd, str):
                qd = date.fromisoformat(qd[:10])
            elif isinstance(qd, datetime):
                qd = qd.date()
            tv = float(r.get("turnover") or r.get("TURNOVER") or 0)
            if tv <= 0:
                continue
            cur.execute(
                """
                INSERT INTO fsi.mktdata_security_quotes
                    (quote_date, security_code, market_id, turnover, source, currency)
                VALUES (%s, %s, 'IB', %s, 'WIND', 'HKD')
                ON CONFLICT (quote_date, security_code, source) DO UPDATE
                SET turnover = EXCLUDED.turnover, loaded_at = NOW()
                """,
                (qd, sc, tv),
            )
            rows_upserted += 1
        securities_seen.add(sc)
    log_import(cur, "WIND", as_of, rows_upserted, len(securities_seen),
               None, None, "OK", f"codes={len(codes)}")
    conn.close()
    logger.info(f"wind 導入完成: {rows_upserted} 行, {len(securities_seen)} 證券")
    if not args.no_aggregate:
        aggregate(cur=None, conn=None, as_of=as_of)


# ══════════════════════════════════════════════════════════════
# 5. 聚合 ADTV（fn_compute_adtv_30d）
# ══════════════════════════════════════════════════════════════

def aggregate(cur, conn, as_of: date) -> None:
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
        conn.autocommit = True
        cur = conn.cursor()
    cur.execute("SELECT fsi.fn_compute_adtv_30d(%s, 30)", (as_of,))
    cnt = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(adtv_30d),0) FROM fsi.mktdata_adtv WHERE adtv_date=%s AND data_source='MARKET'", (as_of,))
    total = float(cur.fetchone()[0])
    log_import(cur, "MARKET", as_of, cnt, cnt, total, None, "OK", "fn_compute_adtv_30d")
    logger.info(f"聚合 ADTV 完成: {cnt} 證券, 合計 {total:.0f} 元 (data_source=MARKET)")
    if own_conn:
        conn.close()


def cmd_aggregate(args) -> None:
    as_of = date.fromisoformat(args.date)
    aggregate(None, None, as_of)


# ══════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="SFC ADTV 行情導入工具（四源統一）")
    p.add_argument("--source", choices=["excel", "excel-daily", "yfinance", "openbb", "wind"], help="行情來源")
    p.add_argument("--aggregate", action="store_true", help="僅聚合 ADTV（從原始表算 30 日平均）")
    p.add_argument("--make-template", action="store_true", help="（Excel 源）生成導入模板")
    p.add_argument("--file", help="（Excel 源）導入文件路徑")
    p.add_argument("--date", help="估值日 YYYY-MM-DD（ADTV 計算截止日，默認今天）")
    p.add_argument("--to", help="結束日期 YYYY-MM-DD（yfinance/openbb/wind 抓取區間末尾）")
    p.add_argument("--workers", type=int, default=8, help="（openbb）並發抓取線程數，默認 8")
    p.add_argument("--no-aggregate", action="store_true", help="導入後不自動聚合")
    args = p.parse_args()

    if args.make_template:
        cmd_make_template(args)
        return
    if args.aggregate:
        cmd_aggregate(args)
        return
    if not args.source:
        p.error("需指定 --source 或 --aggregate")
    if not args.date:
        args.date = date.today().isoformat()
    {"excel": cmd_import_excel, "excel-daily": cmd_import_excel_daily,
     "yfinance": cmd_import_yfinance, "openbb": cmd_import_openbb,
     "wind": cmd_import_wind}[args.source](args)


if __name__ == "__main__":
    main()
