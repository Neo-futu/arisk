from openpyxl import load_workbook
from pathlib import Path

local = Path('2_processing/sql/mmf/report_06/Template.xlsx')
external = Path(r'D:\riskpy\amc\SQLServer\Script\SmartReport\06\Template.xlsx')
output = Path('2_processing/sql/mmf/output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx')

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

for name, path in [('local', local), ('external', external), ('output', output)]:
    wb = load_workbook(path, data_only=True)
    print('===' * 20)
    print(name, path)
    for sheet in sheets:
        if sheet not in wb.sheetnames:
            print('MISSING', sheet)
            continue
        ws = wb[sheet]
        row1 = [ws.cell(row=1, column=c).value for c in range(1, 60)]
        row2 = [ws.cell(row=2, column=c).value for c in range(1, 60)]
        row1_len = max((c for c, v in enumerate(row1, start=1) if v is not None), default=0)
        row2_len = max((c for c, v in enumerate(row2, start=1) if v is not None), default=0)
        print(sheet, 'row1_len', row1_len, 'row2_len', row2_len)
        if row1_len < row2_len:
            print('  warning row2 longer than row1')
        print('  row1', row1[:row1_len+2])
        print('  row2', row2[:row2_len+2])
        print()