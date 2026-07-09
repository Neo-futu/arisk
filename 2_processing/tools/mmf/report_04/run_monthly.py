"""
run_monthly.py — MMF 月報一鍵生成：XLSX + outputdata.json + PDF
用法：python run_monthly.py --date 2026-06-25

執行順序：
  Step 1: run_report.py     → XLSX 數據表
  Step 2: extract_data.py   → outputdata.json（可審查數據）
  Step 3: create_factsheet  → PDF Factsheet（模版 + 數據合併）

輸出目錄：mmf/output/report_04_mmf_monthly/
"""
import sys, subprocess, argparse
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date
from pathlib import Path

TOOL_DIR  = Path(__file__).parent                                   # tools/mmf/report_04/
SQL_MMF   = TOOL_DIR.parent.parent.parent / "sql" / "mmf"           # 2_processing/sql/mmf/

def run(cmd, desc):
    print(f'\n{"─"*55}')
    print(f'  {desc}')
    print(f'{"─"*55}')
    result = subprocess.run(cmd, shell=True, text=True, encoding='utf-8',
                            capture_output=False)
    return result.returncode == 0

def main():
    ap = argparse.ArgumentParser(description='MMF 月報一鍵生成')
    ap.add_argument('--date',    default=date.today().isoformat(), help='估值日期 YYYY-MM-DD')
    ap.add_argument('--fund',    default=None, help='基金中文名（建議改用 --port-id）')
    ap.add_argument('--port-id', default=None, dest='port_id',
                    help='基金 port_id（ASCII，如 BHMMF001），優先於 --fund')
    ap.add_argument('--xlsx-only', action='store_true')
    ap.add_argument('--pdf-only',  action='store_true')
    args = ap.parse_args()

    # 統一用 --port-id 傳遞（ASCII，避免 Windows shell 中文編碼問題）
    if args.port_id:
        fund_flag = f'--port-id {args.port_id}'
    elif args.fund:
        fund_flag = f'--fund "{args.fund}"'
    else:
        fund_flag = ''
    ev = args.date

    print(f'\n{"═"*55}')
    print(f'  MMF 月報生成  |  估值日期：{ev}')
    if args.fund: print(f'  基金：{args.fund}')
    print(f'{"═"*55}')

    ok = True

    # Step 1: XLSX 數據表（必須成功，後續依賴此步驟）
    if not args.pdf_only:
        ok &= run(
            f'python "{TOOL_DIR.parent / "run_report.py"}" --report report_04_mmf_monthly --date {ev}',
            'Step 1/4  生成 XLSX 數據表')

    # Step 2: outputdata.json（失敗只警告，不阻斷 PDF/Word 生成）
    step2_ok = True
    if not args.xlsx_only:
        step2_ok = run(
            f'python "{TOOL_DIR / "extract_data.py"}" --date {ev} {fund_flag}',
            'Step 2/4  提取資料庫數據 → outputdata.json')
        if not step2_ok:
            print(f'\n  ⚠ Step 2 失敗（資料提取異常或無數據），嘗試繼續生成 PDF/Word...')

    # --port-id 傳遞給圖表/PDF/Word 腳本，確保只處理選定基金（不含其他基金的舊文件）
    port_id_flag = f'--port-id {args.port_id}' if args.port_id else ''

    # --port-id 傳遞給圖表/PDF/Word 腳本，確保只處理選定基金和選定日期
    port_id_flag = f'--port-id {args.port_id}' if args.port_id else ''

    # Step 3: 圖表 PNG（指定日期 + 指定基金）
    if not args.xlsx_only and ok:
        run(
            f'python "{TOOL_DIR / "create_charts.py"}" --date {ev} --all {port_id_flag}',
            'Step 3/4  生成圖表 PNG（餅圖 + 柱狀圖）')

    # Step 4a: PDF Factsheet（指定日期 + 指定基金）
    if not args.xlsx_only and ok:
        ok &= run(
            f'python "{TOOL_DIR / "create_factsheet.py"}" --date {ev} --all {port_id_flag}',
            'Step 4a/4  生成 PDF Factsheet')

    # Step 4b: Word Factsheet（指定日期 + 指定基金）
    if not args.xlsx_only and ok:
        run(
            f'python "{TOOL_DIR / "create_word_report.py"}" --date {ev} --all {port_id_flag}',
            'Step 4b/4  生成 Word Factsheet（可編輯 .docx）')

    print(f'\n{"═"*55}')
    out = SQL_MMF / 'output' / 'report_04_mmf_monthly'
    if ok:
        print(f'  ✅ 全部完成！輸出目錄：\n     {out}')
        import os
        for f in sorted(out.iterdir()):
            sz = f.stat().st_size
            unit = 'KB' if sz < 1e6 else 'MB'
            print(f'     {f.name:55s}  {sz//1024 if sz<1e6 else sz//1048576:.0f} {unit}')
    else:
        print(f'  ⚠ 部分步驟失敗，請查看上方錯誤信息')
    print(f'{"═"*55}\n')

if __name__ == '__main__':
    main()
