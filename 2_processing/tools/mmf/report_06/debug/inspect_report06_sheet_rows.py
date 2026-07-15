from openpyxl import load_workbook
from pathlib import Path

local_template = Path('2_processing/sql/mmf/report_06/Template.xlsx')
output_file = Path('2_processing/sql/mmf/output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx')

sheets = [
    '资产分布原始',
    '银行存款交易对手原始',
    '剩余期限结构原始',
    '可提支存款到期原始',
    '影子定价偏离度原始',
    '资产变现原始',
    '信用债及质押债原始',
    '十全每日运作简报原始',
    'T+1日可用流动性原始',
]

wb_local = load_workbook(local_template, data_only=True)
wb_output = load_workbook(output_file, data_only=True)

for sheet in sheets:
    print('='*80)
    print('SHEET:', sheet)
    if sheet not in wb_local.sheetnames:
        print('  missing in local template')
    else:
        ws = wb_local[sheet]
        print('  local template rows 1-6:')
        for r in range(1, 7):
            print('   ', r, [ws.cell(row=r, column=c).value for c in range(1, 21)])
    if sheet not in wb_output.sheetnames:
        print('  missing in output')
    else:
        ws = wb_output[sheet]
        print('  output rows 1-8:')
        for r in range(1, 9):
            print('   ', r, [ws.cell(row=r, column=c).value for c in range(1, 21)])
    print()