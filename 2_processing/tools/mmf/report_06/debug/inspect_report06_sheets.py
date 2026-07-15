from openpyxl import load_workbook
from pathlib import Path

paths = [
    Path('2_processing/sql/mmf/report_06/Template.xlsx'),
    Path('2_processing/sql/mmf/output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx'),
]
for path in paths:
    print('FILE', path)
    if not path.exists():
        print('MISSING', path)
        continue
    wb = load_workbook(path, data_only=True)
    for name in ['资产分布原始', 'T+1日可用流动性原始']:
        print('SHEET', name)
        if name not in wb.sheetnames:
            print('MISS SHEET', name)
            continue
        ws = wb[name]
        for r in range(1, 8):
            vals = [ws.cell(row=r, column=c).value for c in range(1, 13)]
            print(r, vals)
        print('---')
