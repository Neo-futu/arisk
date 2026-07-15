from pathlib import Path
from openpyxl import load_workbook

local_template = Path('2_processing/sql/mmf/report_06/Template.xlsx')
output_file = Path('2_processing/sql/mmf/output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx')

print('Local template:')
wb = load_workbook(local_template, data_only=True)
ws = wb['银行存款交易对手原始']
print('header row 2:', [ws.cell(row=2, column=c).value for c in range(1, 12)])
print('rows 3-12:')
for r in range(3, 12):
    print(r, [ws.cell(row=r, column=c).value for c in range(1, 12)])

print('\nOutput file:')
wb2 = load_workbook(output_file, data_only=True)
ws2 = wb2['银行存款交易对手原始']
print('header row 2:', [ws2.cell(row=2, column=c).value for c in range(1, 12)])
print('rows 3-12:')
for r in range(3, 15):
    print(r, [ws2.cell(row=r, column=c).value for c in range(1, 12)])
