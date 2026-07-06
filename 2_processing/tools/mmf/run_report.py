"""
run_report.py  MMF 報表執行器
=====================================
功能：讀取 SQL → 按 report_config.json 配置 → 寫入 Excel 模版 → 生成結果文件

模塊結構：
  1. CONFIG   — 報表目錄、參數默認值
  2. DATABASE — 數據庫連接、SQL 執行
  3. EXCEL    — 模版複製、Sheet 填充
  4. REPORT   — 單份報表生成（SQL → Excel）
  5. MAIN     — 命令行入口

用法：
  python run_report.py --report report_03 --date 2026-06-25
  python run_report.py --report report_06 --port BHMMF001,BHMMF002 --date 2026-06-25
  python run_report.py --all --date 2026-06-25
  python run_report.py --report report_03 --query 03_01 --date 2026-06-25
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
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


# ══════════════════════════════════════════════════════════════
# 1. CONFIG — 報表目錄與參數
# ══════════════════════════════════════════════════════════════

SQL_DIR    = Path(__file__).parent.parent.parent / "sql" / "mmf"
OUTPUT_DIR = SQL_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 可用報表目錄：report_id → SQL 目錄路徑
REPORTS = {
    "report_03":             SQL_DIR / "report_03",
    "report_03_mmf":         SQL_DIR / "report_03_mmf",
    "report_04_mmf_monthly": SQL_DIR / "report_04_mmf_monthly",
    "report_06":             SQL_DIR / "report_06",
}

# SQL 參數默認值（可被命令行覆蓋）
DEFAULT_PARAMS = {
    "trade_days_ahead": 5,    # 用於 05_assets_5y.sql
    "rate_shock_bps":   50,   # 用於壓力測試 SQL（+50bp）
}


# ══════════════════════════════════════════════════════════════
# 2. DATABASE — 連接與 SQL 執行
# ══════════════════════════════════════════════════════════════

def get_db_conn():
    """從環境變量創建 PostgreSQL 連接。"""
    return psycopg2.connect(
        host     = os.getenv("POSTGRES_HOST", "localhost"),
        port     = int(os.getenv("POSTGRES_PORT", "5432")),
        dbname   = os.getenv("POSTGRES_DB",   "fsi_risk"),
        user     = os.getenv("POSTGRES_USER", "fsi_user"),
        password = os.getenv("POSTGRES_PASSWORD", "change_me"),
    )


def execute_sql(conn, sql_path: Path, params: dict) -> tuple[list, list]:
    """
    讀取 SQL 文件，注入運行參數，執行並返回 (columns, rows)。

    SQL 文件頭部有 WITH params AS (...) 佔位值，執行前替換為實際參數：
      '2026-06-25'::DATE  → 實際估值日期
      ARRAY[...]::TEXT[]  → 實際組合ID列表
    """
    sql        = sql_path.read_text(encoding="utf-8")
    eval_date  = params.get("evaluate_date", date.today())
    port_ids   = params.get("port_ids") or []
    trade_days = params.get("trade_days_ahead", DEFAULT_PARAMS["trade_days_ahead"])
    shock_bps  = params.get("rate_shock_bps",   DEFAULT_PARAMS["rate_shock_bps"])

    # 替換日期佔位（'YYYY-MM-DD'::DATE）
    sql = re.sub(r"'\d{4}-\d{2}-\d{2}'::DATE", f"'{eval_date}'::DATE", sql)

    # 替換組合ID陣列佔位（ARRAY[...]::TEXT[]）
    if port_ids:
        arr = ", ".join(f"'{p}'" for p in port_ids)
        sql = re.sub(r"ARRAY\[.*?\]::TEXT\[\]", f"ARRAY[{arr}]::TEXT[]", sql)
        sql = sql.replace("params.port_ids", f"ARRAY[{arr}]::TEXT[]")

    # 替換其他 params.xxx 字面量引用
    sql = sql.replace("params.evaluate_date",    f"'{eval_date}'::DATE")
    sql = sql.replace("params.trade_days_ahead", str(trade_days))
    sql = sql.replace("params.rate_shock_bps",   str(shock_bps))

    # 移除殘留的 ", params" FROM 引用（params 已內聯）
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


# ══════════════════════════════════════════════════════════════
# 3. EXCEL — 模版處理與 Sheet 填充
# ══════════════════════════════════════════════════════════════

def open_template(tmpl_path: Path, out_path: Path):
    """複製模版到輸出路徑並打開 workbook（保留 VBA/Wind 公式）。"""
    shutil.copy2(tmpl_path, out_path)
    keep_vba = tmpl_path.suffix == ".xlsm"
    return load_workbook(out_path, keep_vba=keep_vba)


def write_sheet(wb, sheet_name: str, start_cell: str,
                columns: list, rows: list, include_header: bool = False):
    """
    將查詢結果寫入 workbook 指定 Sheet 的起始位置。
    自動跳過合併儲存格（MergedCell）。
    """
    if sheet_name not in wb.sheetnames:
        logger.warning(f"    Sheet '{sheet_name}' 不存在，跳過")
        return

    ws      = wb[sheet_name]
    col_idx = column_index_from_string(''.join(c for c in start_cell if c.isalpha()))
    cur_row = int(''.join(c for c in start_cell if c.isdigit()))

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

    logger.info(f"    → Sheet[{sheet_name}] {start_cell}: {len(rows)} rows × {len(columns)} cols")


# ══════════════════════════════════════════════════════════════
# 4. REPORT — 報表生成（SQL → Excel）
# ══════════════════════════════════════════════════════════════

def load_report_config(report_dir: Path) -> dict:
    """讀取 report_config.json，包含模版路徑和查詢映射列表。"""
    return json.loads((report_dir / "report_config.json").read_text(encoding="utf-8"))


def make_output_path(cfg: dict, out_dir: Path, params: dict) -> Path:
    """生成輸出文件路徑，格式與模版一致（.xlsm → .xlsm，.xlsx → .xlsx）。"""
    date_str = params["evaluate_date"].strftime("%Y%m%d")
    port_str = "_".join(params.get("port_ids") or []) or "all"
    suffix   = Path(cfg["excel_template"]).suffix
    return out_dir / f"{cfg['report_id']}_{port_str}_{date_str}{suffix}"


def generate_report(report_dir: Path, params: dict,
                    query_filter: str | None, conn) -> Path | None:
    """
    生成單份報表：
      1. 讀取 report_config.json（模版路徑、查詢映射）
      2. 複製模版 → 打開 workbook
      3. 依次執行每個 SQL → 結果寫入對應 Sheet
      4. 保存輸出文件
    """
    cfg       = load_report_config(report_dir)
    tmpl_path = report_dir / cfg["excel_template"]
    out_dir   = OUTPUT_DIR / cfg["report_id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    if not tmpl_path.exists():
        logger.error(f"模版不存在：{tmpl_path}")
        return None

    out_path = make_output_path(cfg, out_dir, params)
    wb       = open_template(tmpl_path, out_path)
    logger.info(f"  模版: {tmpl_path.name}  →  輸出: {out_path.name}")

    # 篩選要執行的查詢（無過濾則全部執行）
    queries = cfg["queries"]
    if query_filter:
        queries = [q for q in queries if q["id"] == query_filter]
        if not queries:
            logger.warning(f"  查詢 {query_filter} 不存在")
            return None

    # 依次執行 SQL → 寫入 Sheet
    for q in queries:
        logger.info(f"  [{q['id']}] {q['name']}")
        try:
            cols, rows = execute_sql(conn, report_dir / q["sql"], params)
            write_sheet(wb, q["sheet"], q["start_cell"],
                        cols, rows, q.get("header", False))
        except Exception as e:
            logger.error(f"    ERROR: {e}")

    wb.save(out_path)
    return out_path


# ══════════════════════════════════════════════════════════════
# 5. MAIN — 命令行入口
# ══════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="MMF SmartReport 執行器")
    p.add_argument("--report", choices=list(REPORTS), help="指定報表：report_03 / report_06")
    p.add_argument("--all",    action="store_true",   help="執行全部報表")
    p.add_argument("--query",  help="只執行指定查詢 ID（如 03_01）")
    p.add_argument("--port",   help="組合ID，多個用逗號分隔（report_06 必填）")
    p.add_argument("--date",   help="估值日期 YYYY-MM-DD（默認昨個交易日）")
    return p.parse_args()


def last_trade_date() -> date:
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def main():
    args = parse_args()

    params = {
        "evaluate_date":    date.fromisoformat(args.date) if args.date else last_trade_date(),
        "port_ids":         [p.strip() for p in args.port.split(",")] if args.port else [],
        **DEFAULT_PARAMS,
    }

    if args.all:
        targets = list(REPORTS.items())
    elif args.report:
        targets = [(args.report, REPORTS[args.report])]
    else:
        print("請指定 --report 或 --all")
        return

    logger.info(f"估值日期: {params['evaluate_date']}  組合: {params['port_ids'] or '全部'}")

    conn = get_db_conn()
    try:
        for r_id, r_dir in targets:
            logger.info(f"\n{'─'*50}\n報表: {r_id}")
            out = generate_report(r_dir, params, args.query, conn)
            if out:
                logger.info(f"完成: {out}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
