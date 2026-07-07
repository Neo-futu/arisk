from pathlib import Path
from openpyxl import load_workbook

local = Path(r'd:\vsproject\arisk\2_processing\sql\mmf\report_06\Template.xlsx')
external = Path(r'd:\riskpy\amc\SQLServer\Script\SmartReport\06\Template.xlsx')
print('LOCAL exists', local.exists())
print('EXT exists', external.exists())
wb_local = load_workbook(local, data_only=False)
wb_ext = load_workbook(external, data_only=False)
print('LOCAL sheets:', wb_local.sheetnames)
print('EXT sheets:', wb_ext.sheetnames)
common = [s for s in wb_local.sheetnames if s in wb_ext.sheetnames]
print('common:', common)
for sheet in common:
    ws_l = wb_local[sheet]
    ws_e = wb_ext[sheet]
    maxr = min(50, max(ws_l.max_row, ws_e.max_row))
    maxc = min(30, max(ws_l.max_column, ws_e.max_column))
    diffs = []
    for r in range(1, maxr + 1):
        for c in range(1, maxc + 1):
            cl = ws_l.cell(row=r, column=c)
            ce = ws_e.cell(row=r, column=c)
            vl = cl.value
            ve = ce.value
            if cl.data_type == 'f' or ce.data_type == 'f':
                fl = cl.value if cl.data_type == 'f' else None
                fe = ce.value if ce.data_type == 'f' else None
                if fl != fe:
                    diffs.append((r, c, 'formula', fl, fe))
            else:
                if vl is None and ve is None:
                    continue
                if str(vl).strip() != str(ve).strip():
                    diffs.append((r, c, 'value', vl, ve))
    print(f'-- SHEET {sheet}: diffs {len(diffs)}')
    for x in diffs[:100]:
        print(x)
    if len(diffs) > 100:
        print('  ...', len(diffs) - 100, 'more')
