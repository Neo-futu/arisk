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

BASE_DIR = Path(__file__).parent
MMF_DIR  = BASE_DIR.parent

def run(cmd, desc):
    print(f'\n{"─"*55}')
    print(f'  {desc}')
    print(f'{"─"*55}')
    result = subprocess.run(cmd, shell=True, text=True, encoding='utf-8',
                            capture_output=False)
    return result.returncode == 0

def main():
    ap = argparse.ArgumentParser(description='MMF 月報一鍵生成')
    ap.add_argument('--date', default=date.today().isoformat(), help='估值日期 YYYY-MM-DD')
    ap.add_argument('--fund', default=None, help='指定基金名稱（缺省=全部）')
    ap.add_argument('--xlsx-only', action='store_true')
    ap.add_argument('--pdf-only',  action='store_true')
    args = ap.parse_args()

    fund_flag = f'--fund "{args.fund}"' if args.fund else ''
    ev = args.date

    print(f'\n{"═"*55}')
    print(f'  MMF 月報生成  |  估值日期：{ev}')
    if args.fund: print(f'  基金：{args.fund}')
    print(f'{"═"*55}')

    ok = True

    # Step 1: XLSX
    if not args.pdf_only:
        ok &= run(
            f'python "{MMF_DIR / "run_report.py"}" --report report_04_mmf_monthly --date {ev}',
            'Step 1/3  生成 XLSX 數據表')

    # Step 2: outputdata.json
    if not args.xlsx_only:
        ok &= run(
            f'python "{BASE_DIR / "extract_data.py"}" --date {ev} {fund_flag}',
            'Step 2/4  提取資料庫數據 → outputdata.json')

    # Step 3: 圖表 PNG
    if not args.xlsx_only and ok:
        ok &= run(
            f'python "{BASE_DIR / "create_charts.py"}" --all',
            'Step 3/4  生成圖表 PNG（餅圖 + 柱狀圖）')

    # Step 4a: PDF
    if not args.xlsx_only and ok:
        ok &= run(
            f'python "{BASE_DIR / "create_factsheet.py"}" --date {ev} --all',
            'Step 4a/4  生成 PDF Factsheet')

    # Step 4b: Word
    if not args.xlsx_only and ok:
        run(
            f'python "{BASE_DIR / "create_word_report.py"}" --all',
            'Step 4b/4  生成 Word Factsheet（可編輯 .docx）')

    print(f'\n{"═"*55}')
    out = MMF_DIR / 'output' / 'report_04_mmf_monthly'
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
