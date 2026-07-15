from pathlib import Path
from openpyxl import load_workbook

LOCAL = Path('2_processing/sql/mmf/report_06/Template.xlsx')
EXTERNAL = Path(r'D:\riskpy\amc\SQLServer\Script\SmartReport\06\Template.xlsx')

if not LOCAL.exists() or not EXTERNAL.exists():
    raise FileNotFoundError(f'Local: {LOCAL.exists()}, External: {EXTERNAL.exists()}')

wb_local = load_workbook(LOCAL)
wb_ext = load_workbook(EXTERNAL)

changed = False
for sheet_name in wb_ext.sheetnames:
    if sheet_name not in wb_local.sheetnames:
        wb_local.create_sheet(sheet_name)
        ws_local = wb_local[sheet_name]
        ws_ext = wb_ext[sheet_name]
        for row in ws_ext.iter_rows(values_only=False):
            for cell in row:
                ws_local[cell.coordinate].value = cell.value
                changed = True
        continue
    ws_ext = wb_ext[sheet_name]
    ws_local = wb_local[sheet_name]
    max_row = max(ws_ext.max_row, ws_local.max_row)
    max_col = max(ws_ext.max_column, ws_local.max_column)
    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            v_ext = ws_ext.cell(row=r, column=c).value
            v_loc = ws_local.cell(row=r, column=c).value
            if v_ext is None:
                continue
            if v_loc is None or str(v_loc).strip() == '':
                ws_local.cell(row=r, column=c).value = v_ext
                changed = True

if changed:
    wb_local.save(LOCAL)
    print('PATCHED')
else:
    print('NO_CHANGES')
