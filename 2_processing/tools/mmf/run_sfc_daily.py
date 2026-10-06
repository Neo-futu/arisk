"""
run_sfc_daily.py — SFC 壓力測試日度總控腳本（一鍵完整流程）
=====================================
封裝日度全流程，直接可用：
  步骤0  環境自檢（DB 連通、持倉數據、ADTV 三源狀態）
  步骤1  OpenBB 行情更新（交易所掛牌品種：ETF/股票，多 provider fallback + 並發）
  步骤2  Bloomberg 導出逐日行情導入（單只債券/CD，--source excel-daily；文件可選）
  步骤3  生成 report_06（run_report.py --report report_06，14 查詢 → 25 sheet）
  步骤4  自動自檢（分層合計=100%、DLA/WLA 合規、SFC §1(iv) 假設生效）

用法：
  python run_sfc_daily.py --date 2026-06-25                       # 標準日度流程
  python run_sfc_daily.py --date 2026-06-25 --skip-openbb         # 跳過 OpenBB（行情無更新日）
  python run_sfc_daily.py --date 2026-06-25 --bloomberg-file x.xlsx  # 指定 Bloomberg 導出文件
  python run_sfc_daily.py --date 2026-06-25 --ports BHMMF001      # 只跑單組合
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[3]  # arisk/
TOOLS_DIR = BASE / "2_processing" / "tools" / "mmf"
OUT_DIR = BASE / "2_processing" / "sql" / "mmf" / "output" / "report_06"

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STEP_BAR = "─" * 64


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "fsi_risk"),
        user=os.getenv("POSTGRES_USER", "fsi_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def run_step(n: int, title: str) -> None:
    logger.info("")
    logger.info(STEP_BAR)
    logger.info(f"  步骤{n}: {title}")
    logger.info(STEP_BAR)


def step0_preflight(eval_date: date) -> bool:
    """環境自檢：DB 連通、持倉/NAV/行情可用性。"""
    run_step(0, "環境自檢（DB / 持倉 / ADTV 三源）")
    try:
        conn = get_conn()
    except Exception as e:
        logger.error(f"  ✗ DB 連接失敗: {e}")
        return False
    cur = conn.cursor()
    ok = True

    def q(sql, label, fail_on_zero=True):
        nonlocal ok
        try:
            cur.execute(sql, {"d": eval_date})
            cnt = cur.fetchone()[0]
            if cnt == 0 and fail_on_zero:
                logger.warning(f"  ⚠ {label}: 0 行（該日期無數據，報表將出空表）")
                ok = False
            else:
                logger.info(f"  ✓ {label}: {cnt} 行")
        except Exception as e:
            logger.error(f"  ✗ {label}: {e}")
            ok = False

    q("SELECT COUNT(*) FROM fsi.balance_portfolio_nav WHERE evaluate_date=%(d)s AND class_id IS NULL", "NAV 快照")
    q("SELECT COUNT(*) FROM fsi.balance_bond WHERE evaluate_date=%(d)s AND quantity>0", "債券持倉")
    q("SELECT COUNT(*) FROM fsi.balance_cd WHERE evaluate_date=%(d)s", "CD 持倉")
    q("SELECT COUNT(*) FROM fsi.balance_deposit WHERE evaluate_date=%(d)s", "存款持倉")
    q("SELECT COUNT(*) FROM fsi.balance_cash WHERE evaluate_date=%(d)s", "現金持倉")
    q("SELECT COUNT(*) FROM fsi.mktdata_adtv WHERE adtv_date=%(d)s AND data_source='MARKET'", "ADTV(MARKET 真實行情)")
    q("SELECT COUNT(*) FROM fsi.mktdata_adtv WHERE adtv_date=%(d)s AND data_source IN ('EXCEL','PROXY')", "ADTV(EXCEL/PROXY 兜底)", fail_on_zero=False)

    # 參數配置表
    cur.execute("SELECT COUNT(*) FROM fsi.sfc_liquidity_bucket_def")
    logger.info(f"  ✓ SFC 壓力參數配置: {cur.fetchone()[0]} 行（8類×2場景）")
    conn.close()
    return ok


def step1_openbb(eval_date: date) -> bool:
    """OpenBB 行情更新（可跳過）。"""
    run_step(1, "OpenBB 行情更新（交易所掛牌品種）")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "import_adtv.py", "--source", "openbb",
         "--date", eval_date.isoformat(), "--to", eval_date.isoformat()],
        cwd=TOOLS_DIR,
    )
    return r.returncode == 0


def step2_bloomberg(eval_date: date, file: str | None) -> None:
    """Bloomberg 導出逐日行情導入（可選）。"""
    run_step(2, "Bloomberg 導出逐日行情導入（單只債券/CD）")
    if not file:
        logger.info("  - 未指定 --bloomberg-file，跳過（單債行情沿用上次導入）")
        return
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "import_adtv.py", "--source", "excel-daily",
         "--file", file, "--date", eval_date.isoformat()],
        cwd=TOOLS_DIR,
    )
    if r.returncode != 0:
        logger.warning("  ⚠ Bloomberg 導入返回非零，繼續（可用 EXCEL/PROXY 兜底）")


def step3_generate_report(eval_date: date, ports: list[str]) -> Path | None:
    """生成 report_06。"""
    run_step(3, f"生成 report_06（{','.join(ports)} @ {eval_date}）")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "run_report.py", "--report", "report_06",
         "--port", ",".join(ports), "--date", eval_date.isoformat()],
        cwd=TOOLS_DIR,
    )
    if r.returncode != 0:
        logger.error("  ✗ run_report.py 失敗")
        return None
    date_str = eval_date.strftime("%Y%m%d")
    out = OUT_DIR / f"report_06_{'_'.join(ports)}_{date_str}.xlsx"
    if not out.exists():
        logger.error(f"  ✗ 輸出文件未找到: {out}")
        return None
    logger.info(f"  ✓ 輸出: {out}")
    return out


def step4_verify(out_path: Path) -> bool:
    """自動自檢：SFC 三表核心斷言。"""
    run_step(4, "自動自檢（SFC 報表核心斷言）")
    from openpyxl import load_workbook
    wb = load_workbook(out_path)
    ok = True

    # ── 斷言1：綜述表一（分層）每行五檔求和=100% ──
    ws = wb["SFC壓力測試"]
    layers = []
    r = 6
    while True:
        label = ws.cell(row=r, column=1).value
        if label is None:
            break
        # 命中表二標題（R12）則停
        if str(label).startswith("表二"):
            break
        vals = [ws.cell(row=r, column=c).value for c in range(2, 8)]
        if all(v is None for v in vals):
            break
        layers.append((label, vals))
        r += 1
    for label, vals in layers:
        total = sum(v or 0 for v in vals[:5])
        status = "✓" if abs(total - (vals[5] or 0)) < 0.01 else "✗"
        if status == "✗":
            ok = False
        logger.info(f"  {status} 分層合計: {str(label)[:34]} → {total:.2f}%（表值 {(vals[5] or 0):.2f}%）")

    # ── 斷言2：綜述表二（DLA/WLA）雙場景合規 ──
    r = 14
    while ws.cell(row=r, column=1).value:
        label = ws.cell(row=r, column=1).value
        dla_pct, dla_st = ws.cell(row=r, column=2).value, ws.cell(row=r, column=3).value
        wla_pct, wla_st = ws.cell(row=r, column=4).value, ws.cell(row=r, column=5).value
        s1 = "✓" if (dla_st == "合規" and dla_pct >= 7.5) else "✗"
        s2 = "✓" if (wla_st == "合規" and wla_pct >= 15) else "✗"
        if s1 == "✗" or s2 == "✗":
            ok = False
        logger.info(f"  {s1}{s2} 合規: {label[:34]} → DLA={dla_pct:.2f}({dla_st}) WLA={wla_pct:.2f}({wla_st})")
        r += 1

    # ── 斷言3：口徑A詳表雙場景合計=100% ──
    ws2 = wb["SFC流動性分層"]
    pct_sum: dict[tuple, float] = {}
    for row in ws2.iter_rows(min_row=5, values_only=True):
        if row[0] and row[1]:
            pct_sum[(row[0], row[1])] = pct_sum.get((row[0], row[1]), 0) + (row[4] or 0)
    for (port, scen), total in pct_sum.items():
        status = "✓" if abs(total - 100) < 0.05 else "✗"
        if status == "✗":
            ok = False
        logger.info(f"  {status} 口徑A詳表合計: {port[:14]} {scen} → {total:.2f}%")

    # ── 斷言4：口徑B詳表 Stressed DLA ≤ Normal DLA（壓力收緊方向性）──
    ws3 = wb["SFC_DLA_WLA合規"]
    dla_by = {}
    for row in ws3.iter_rows(min_row=5, values_only=True):
        if row[0] and row[2] == "合規匯總":
            dla_by[(row[0], row[1])] = row[5]
    for (port, _), _v in list(dla_by.items()):
        if (port, "Normal scenario") in dla_by and (port, "Stressed scenario") in dla_by:
            n, s = dla_by[(port, "Normal scenario")], dla_by[(port, "Stressed scenario")]
            status = "✓" if s < n else "✗"
            if status == "✗":
                ok = False
            logger.info(f"  {status} 壓力收緊: {port[:14]} Stressed DLA {s:.2f}% < Normal {n:.2f}%")

    return ok


def main():
    ap = argparse.ArgumentParser(description="SFC 壓力測試日度總控（一鍵完整流程）")
    ap.add_argument("--date", required=True, help="估值日 YYYY-MM-DD")
    ap.add_argument("--ports", default="BHMMF001,BHMMF002", help="組合ID，逗號分隔")
    ap.add_argument("--skip-openbb", action="store_true", help="跳過 OpenBB 行情更新")
    ap.add_argument("--bloomberg-file", help="Bloomberg 導出逐日行情文件（可選）")
    ap.add_argument("--skip-verify", action="store_true", help="跳過自動自檢")
    args = ap.parse_args()

    eval_date = date.fromisoformat(args.date)
    ports = [p.strip() for p in args.ports.split(",") if p.strip()]

    t0 = datetime.now()
    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║  SFC 壓力測試 · 日度總控（ARISK report_06）  ║")
    logger.info("╚══════════════════════════════════════════════╝")

    if not step0_preflight(eval_date):
        logger.error("前置檢查未通過（見上），中止。")
        sys.exit(2)

    s1 = True if args.skip_openbb else step1_openbb(eval_date)
    step2_bloomberg(eval_date, args.bloomberg_file)
    out = step3_generate_report(eval_date, ports)
    if out is None:
        sys.exit(1)

    verified = True
    if not args.skip_verify:
        verified = step4_verify(out)

    elapsed = (datetime.now() - t0).total_seconds()
    logger.info("")
    logger.info(STEP_BAR)
    if verified:
        logger.info(f"  ✓ 完成：{out.name}（耗時 {elapsed:.0f}s）— 全部自檢通過")
    else:
        logger.warning(f"  ⚠ 完成（含告警）：{out.name}（耗時 {elapsed:.0f}s）— 存在未通過斷言，請人工復核")
    logger.info(STEP_BAR)


if __name__ == "__main__":
    main()
