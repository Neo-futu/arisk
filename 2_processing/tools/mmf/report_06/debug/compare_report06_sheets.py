from openpyxl import load_workbook
from pathlib import Path

def sheet_info(wb, sheet_name, max_cols=40):
    ws = wb[sheet_name]
    header = [ws.cell(row=1, column=c).value for c in range(1, max_cols+1)]
    first_data = [ws.cell(row=2, column=c).value for c in range(1, max_cols+1)]
    last_col = max((c for c, v in enumerate(header, start=1) if v is not None), default=0)
    data_cols = max((c for c, v in enumerate(first_data, start=1) if v is not None), default=0)
    return {
        'header_values': header,
        'first_data_values': first_data,
        'header_last_col': last_col,
        'first_data_last_col': data_cols,
    }

local_template = Path('2_processing/sql/mmf/report_06/Template.xlsx')
output_file = Path('2_processing/sql/mmf/output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx')

query_sheets = [
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

print('REPORT 06 sheet compare')
print('local_template=', local_template)
print('output_file=', output_file)

wb_local = load_workbook(local_template, data_only=True)
wb_out = load_workbook(output_file, data_only=True)

for sheet in query_sheets:
    print('='*80)
    print('SHEET', sheet)
    if sheet not in wb_local.sheetnames:
        print('  missing in template')
        continue
    if sheet not in wb_out.sheetnames:
        print('  missing in output')
        continue
    li = sheet_info(wb_local, sheet, max_cols=40)
    oi = sheet_info(wb_out, sheet, max_cols=40)
    print('  header_last_col', li['header_last_col'], 'output_first_data_last_col', oi['first_data_last_col'])
    print('  template headers:', li['header_values'][:max(li['header_last_col'], 10)])
    print('  output first row:', oi['first_data_values'][:max(oi['first_data_last_col'], 10)])
    if oi['first_data_last_col'] > li['header_last_col']:
        print('  WARNING: output has more populated cols than template headers')
    if oi['first_data_last_col'] < li['header_last_col']:
        print('  NOTE: output has fewer non-empty cols than template headers')
    print()
