from pathlib import Path
from openpyxl import load_workbook

local = Path(r'd:\vsproject\arisk\2_processing\sql\mmf\report_06\Template.xlsx')
external = Path(r'd:\riskpy\amc\SQLServer\Script\SmartReport\06\Template.xlsx')
wb_local = load_workbook(local, data_only=False)
wb_ext = load_workbook(external, data_only=False)
print('local count', len(wb_local.sheetnames))
print('external count', len(wb_ext.sheetnames))
local_names = set(wb_local.sheetnames)
external_names = set(wb_ext.sheetnames)
print('same set?', local_names == external_names)
print('local-only', sorted(local_names - external_names))
print('external-only', sorted(external_names - local_names))
for name in sorted(local_names & external_names):
    print('common', repr(name))
