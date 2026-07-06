from pathlib import Path
from openpyxl import load_workbook

path = Path('2_processing/sql/mmf/output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx')
wb = load_workbook(path, data_only=True)
for sheet_name in ['剩余期限结构原始', 'T+1日可用流动性原始']:
    print('SHEET', sheet_name)
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(min_row=1, max_row=8, min_col=1, max_col=35, values_only=True))
    for r, row in enumerate(rows, start=1):
        print(r, row)
    print('\n')
