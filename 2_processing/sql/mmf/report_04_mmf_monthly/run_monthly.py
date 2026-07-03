"""
run_monthly.py — 一鍵生成 MMF 月報 XLSX + PDF Factsheet
執行：python 2_processing/sql/mmf/report_04_mmf_monthly/run_monthly.py --date 2026-06-25
"""
import sys, argparse, shutil
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date
from pathlib import Path

BASE_DIR   = Path(__file__).parent
MMF_DIR    = BASE_DIR.parent
OUTPUT_DIR = MMF_DIR / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_xlsx(eval_date: date) -> Path:
    """調用 run_report.py 生成 XLSX"""
    import importlib.util, sys, os
    spec = importlib.util.spec_from_file_location('run_report', MMF_DIR / 'run_report.py')
    rr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rr)

    params = {
        'evaluate_date': eval_date,
        'port_ids': [],
        'trade_days_ahead': 5,
        'rate_shock_bps': 50,
    }
    import os
    rr.OUTPUT_DIR = OUTPUT_DIR
    out = rr.generate_report(BASE_DIR, params, None, rr.get_db_conn())
    return out


def run_pdf(eval_date: date) -> Path:
    """調用 create_factsheet.py 生成 PDF"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'create_factsheet', BASE_DIR / 'create_factsheet.py')
    cf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cf)
    cf.OUTPUT_DIR = OUTPUT_DIR
    pdf_path = OUTPUT_DIR / f'MMF_Factsheet_{eval_date.strftime("%Y%m%d")}_TC.pdf'
    data = cf.load_data(eval_date)
    cf.build_pdf(data, eval_date, pdf_path)
    return pdf_path


def main():
    parser = argparse.ArgumentParser(description='MMF月報 XLSX + PDF 一鍵生成')
    parser.add_argument('--date', default=date.today().isoformat(),
                        help='估值日期 YYYY-MM-DD')
    parser.add_argument('--xlsx-only', action='store_true', help='僅生成 XLSX')
    parser.add_argument('--pdf-only',  action='store_true', help='僅生成 PDF')
    args = parser.parse_args()
    eval_date = date.fromisoformat(args.date)

    print(f'\n{"="*55}')
    print(f'  MMF 月報生成  |  估值日期：{eval_date}')
    print(f'{"="*55}')

    results = {}

    if not args.pdf_only:
        print('\n[1/2] 生成 XLSX 月報數據表...')
        try:
            xlsx_path = run_xlsx(eval_date)
            results['xlsx'] = xlsx_path
            print(f'  ✅ XLSX：{xlsx_path}')
        except Exception as e:
            print(f'  ⚠ XLSX 生成失敗：{e}')

    if not args.xlsx_only:
        print('\n[2/2] 生成 PDF Factsheet...')
        try:
            pdf_path = run_pdf(eval_date)
            results['pdf'] = pdf_path
            print(f'  ✅ PDF ：{pdf_path}')
        except Exception as e:
            print(f'  ⚠ PDF 生成失敗：{e}')
            import traceback; traceback.print_exc()

    print(f'\n{"="*55}')
    print(f'  完成！輸出目錄：{OUTPUT_DIR}')
    for k, v in results.items():
        print(f'    {k.upper()} → {Path(v).name}')
    print(f'{"="*55}\n')


if __name__ == '__main__':
    main()
