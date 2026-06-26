"""
run_report.py  MMF 報表執行器
=====================================
對應原始系統：SmartReport 每個數字子文件夾 = 一張報表
  · 每個報表目錄有一個 Excel 模版（Template.xlsx / .xlsm）
  · 多個 .sql 查詢結果分別填入模版的不同 Sheet（或同一 Sheet 的不同列位）
  · 輸出：複製模版 → 填數據 → 另存為結果文件

report_config.json 結構：
  - excel_template: 模版文件名（相對於報表目錄）
  - queries[]: 每個查詢
      - sql: SQL 文件名
      - sheet: 填入哪個 Sheet
      - start_cell: 起始單元格（如 A3、I3）
      - header: 是否輸出列名行

用法：
  python run_report.py --report report_06 --port BHMMF001,BHMMF002 --date 2026-06-25
  python run_report.py --report report_03 --date 2026-06-25
  python run_report.py --all --date 2026-06-25
  python run_report.py --report report_03 --query 03_17 --date 2026-06-25
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORTS = {
    "report_03": BASE_DIR / "report_03",
    "report_06": BASE_DIR / "report_06",
}


# ── DB ───────────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(
        host     = os.getenv("POSTGRES_HOST", "localhost"),
        port     = int(os.getenv("POSTGRES_PORT", "5432")),
        dbname   = os.getenv("POSTGRES_DB", "fsi_risk"),
        user     = os.getenv("POSTGRES_USER", "fsi_user"),
        password = os.getenv("POSTGRES_PASSWORD", "change_me"),
    )


def last_trade_date() -> date:
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


# ── SQL 執行 ─────────────────────────────────────────────────
def run_sql(conn, sql_path: Path, params: dict) -> tuple[list, list]:
    import re
    sql = sql_path.read_text(encoding="utf-8")

    eval_date = params.get("evaluate_date")
    port_ids  = params.get("port_ids")

    eval_date  = params.get("evaluate_date", "2026-06-25")
    port_ids   = params.get("port_ids") or []
    trade_days = params.get("trade_days_ahead", 5)
    shock_bps  = params.get("rate_shock_bps", 50)

    # ── 步驟1：替換 params CTE 定義中的佔位值（'YYYY-MM-DD'::DATE / ARRAY[...]）
    sql = re.sub(r"'\d{4}-\d{2}-\d{2}'::DATE", f"'{eval_date}'::DATE", sql)
    if port_ids:
        arr = ", ".join(f"'{p}'" for p in port_ids)
        sql = re.sub(r"ARRAY\[.*?\]::TEXT\[\]", f"ARRAY[{arr}]::TEXT[]", sql)

    # ── 步驟2：把所有 params.xxx 引用替換為字面量（處理沒有 FROM params 的情況）
    if port_ids:
        arr = ", ".join(f"'{p}'" for p in port_ids)
        sql = sql.replace("params.port_ids",         f"ARRAY[{arr}]::TEXT[]")
    sql = sql.replace("params.evaluate_date",         f"'{eval_date}'::DATE")
    sql = sql.replace("params.trade_days_ahead",      str(trade_days))
    sql = sql.replace("params.rate_shock_bps",        str(shock_bps))

    # ── 步驟3：移除殘留的 ", params" FROM 引用（params 已內聯，不需要 FROM）
    sql = re.sub(r",\s*params\b", "", sql)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        try:
            cur.execute(sql)
        except Exception:
            conn.rollback()
            raise
        rows    = cur.fetchall() if cur.description else []
        columns = [d[0] for d in cur.description] if cur.description else []
    return columns, [dict(r) for r in rows]


# ── Excel Sheet 填充 ─────────────────────────────────────────
def fill_sheet(wb, sheet_name: str, start_cell: str,
               columns: list, rows: list, include_header: bool):
    """在已打開的 workbook 中，向指定 Sheet 的起始位置填充數據。"""
    if sheet_name not in wb.sheetnames:
        logger.warning(f"  Sheet '{sheet_name}' 不存在，跳過")
        return

    ws = wb[sheet_name]
    col_letter = ''.join(c for c in start_cell if c.isalpha())
    row_num    = int(''.join(c for c in start_cell if c.isdigit()))
    col_idx    = column_index_from_string(col_letter)
    cur_row    = row_num

    if include_header:
        for ci, col in enumerate(columns, col_idx):
            cell = ws.cell(row=cur_row, column=ci)
            if cell.__class__.__name__ != "MergedCell":
                cell.value = col
        cur_row += 1

    for row in rows:
        for ci, col in enumerate(columns, col_idx):
            cell = ws.cell(row=cur_row, column=ci)
            if cell.__class__.__name__ != "MergedCell":
                cell.value = row.get(col)
        cur_row += 1

    logger.info(f"    Sheet [{sheet_name}] {start_cell}: {len(rows)} rows × {len(columns)} cols")


# ── 單個報表目錄執行 ─────────────────────────────────────────
def run_report_dir(report_dir: Path, params: dict,
                   query_filter: str | None, conn) -> Path | None:
    cfg          = json.loads((report_dir / "report_config.json").read_text(encoding="utf-8"))
    report_id    = cfg["report_id"]
    tmpl_name    = cfg.get("excel_template", "Template.xlsx")
    tmpl_path    = report_dir / tmpl_name
    out_subdir   = OUTPUT_DIR / report_id
    out_subdir.mkdir(parents=True, exist_ok=True)

    if not tmpl_path.exists():
        logger.error(f"模版文件不存在：{tmpl_path}")
        return None

    # 生成輸出文件名
    date_str = params["evaluate_date"].strftime("%Y%m%d")
    port_ids = params.get("port_ids") or []
    port_str = "_".join(port_ids) if port_ids else "all"
    # 輸出文件固定為 .xlsx（純數據結果，不帶宏）
    out_name = f"{report_id}_{port_str}_{date_str}.xlsx"
    out_path = out_subdir / out_name

    # 臨時文件：保持模版原格式讀入（xlsm 需 keep_vba 才能讀取 Sheet 結構）
    tmp_path = out_subdir / f"_tmp_{Path(tmpl_name).name}"
    shutil.copy2(tmpl_path, tmp_path)
    logger.info(f"Template → {out_name}")

    keep_vba = tmpl_name.endswith(".xlsm")
    wb = load_workbook(tmp_path, keep_vba=keep_vba)

    queries = cfg["queries"]
    if query_filter:
        queries = [q for q in queries if q["id"] == query_filter]
        if not queries:
            logger.error(f"查詢 {query_filter} 在 {report_id} 中不存在")
            return None

    for q in queries:
        sql_path = report_dir / q["sql"]
        logger.info(f"  [{q['id']}] {q['name']}")
        try:
            cols, rows = run_sql(conn, sql_path, params)
            fill_sheet(wb, q["sheet"], q["start_cell"],
                       cols, rows, q.get("header", False))
        except Exception as e:
            logger.error(f"    ERROR: {e}")

    # 另存為純 xlsx（去掉宏，作為結果文件交付）
    wb.save(out_path)
    tmp_path.unlink(missing_ok=True)   # 刪除臨時文件
    logger.info(f"  → 輸出: {out_path}")
    return out_path


# ── 入口 ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MMF SmartReport 執行器")
    parser.add_argument("--report", help="報表目錄：report_03 或 report_06")
    parser.add_argument("--all",    action="store_true", help="執行全部報表")
    parser.add_argument("--query",  help="只執行指定查詢 ID（如 06_01）")
    parser.add_argument("--port",   help="組合ID，逗號分隔（report_06 必填）")
    parser.add_argument("--date",   help="估值日期 YYYY-MM-DD，默認昨個交易日")
    args = parser.parse_args()

    eval_date = date.fromisoformat(args.date) if args.date else last_trade_date()
    port_ids  = [p.strip() for p in args.port.split(",")] if args.port else []

    params = {
        "evaluate_date":    eval_date,
        "port_ids":         port_ids or None,
        "trade_days_ahead": 5,
        "rate_shock_bps":   50,
    }

    if args.all:
        targets = list(REPORTS.items())
    elif args.report:
        if args.report not in REPORTS:
            raise ValueError(f"未知報表: {args.report}，可選: {list(REPORTS.keys())}")
        targets = [(args.report, REPORTS[args.report])]
    else:
        parser.print_help()
        return

    logger.info(f"估值日期: {eval_date}  組合: {port_ids or '全部MMF'}")

    conn = get_conn()
    try:
        for r_id, r_dir in targets:
            logger.info(f"\n{'='*55}\n報表: {r_id} ({r_dir.name})")
            run_report_dir(r_dir, params, args.query, conn)
    finally:
        conn.close()

    logger.info(f"\n完成。輸出目錄: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
