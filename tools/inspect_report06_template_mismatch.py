from openpyxl import load_workbook
from pathlib import Path

local = Path('2_processing/sql/mmf/report_06/Template.xlsx')
external = Path(r'D:\riskpy\amc\SQLServer\Script\SmartReport\06\Template.xlsx')
output = Path('2_processing/sql/mmf/output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx')

def inspect(path, sheetname, rows=6, cols=16):
    print('='*80)
    print('PATH', path)
    wb = load_workbook(path, data_only=True)
    if sheetname not in wb.sheetnames:
        print('MISS', sheetname)
        return
    ws = wb[sheetname]
    print('MERGED RANGES:', ws.merged_cells.ranges)
    for r in range(1, rows+1):
        vals = [ws.cell(row=r, column=c).value for c in range(1, cols+1)]
        print(f'R{r}:', vals)
    print()

for p in [local, external, output]:
    inspect(p, '剩余期限结构原始', rows=7, cols=32)
    inspect(p, 'T+1日可用流动性原始', rows=6, cols=10)
