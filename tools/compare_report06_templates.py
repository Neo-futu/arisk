from openpyxl import load_workbook
from pathlib import Path
import sys

local = Path('2_processing/sql/mmf/report_06/Template.xlsx')
external = Path(r'D:\riskpy\amc\SQLServer\Script\SmartReport\06\Template.xlsx')

if not local.exists():
    print('LOCAL_MISSING', local)
    sys.exit(2)
if not external.exists():
    print('EXTERNAL_MISSING', external)
    sys.exit(3)

wb_local = load_workbook(local, data_only=True)
wb_ext = load_workbook(external, data_only=True)

sheets_local = wb_local.sheetnames
sheets_ext = wb_ext.sheetnames

print('LOCAL_SHEETS', len(sheets_local))
print('EXTERNAL_SHEETS', len(sheets_ext))

only_local = [s for s in sheets_local if s not in sheets_ext]
only_ext = [s for s in sheets_ext if s not in sheets_local]

print('ONLY_LOCAL_SHEETS', only_local)
print('ONLY_EXTERNAL_SHEETS', only_ext)

# For common sheets compare first 10 rows x 30 cols
MAX_ROWS = 10
MAX_COLS = 30
mismatches = {}
for s in sheets_local:
    if s not in sheets_ext:
        continue
    ws_l = wb_local[s]
    ws_e = wb_ext[s]
    sheet_mis = []
    for r in range(1, MAX_ROWS+1):
        for c in range(1, MAX_COLS+1):
            v1 = ws_l.cell(row=r, column=c).value
            v2 = ws_e.cell(row=r, column=c).value
            if v1 is None and v2 is None:
                continue
            # normalize to string for comparison
            s1 = str(v1).strip() if v1 is not None else ''
            s2 = str(v2).strip() if v2 is not None else ''
            if s1 != s2:
                sheet_mis.append({'row': r, 'col': c, 'local': s1, 'external': s2})
    if sheet_mis:
        mismatches[s] = sheet_mis

print('MISMATCH_SHEETS_COUNT', len(mismatches))
# Print a sample of mismatches per sheet (up to 10)
for s, diffs in mismatches.items():
    print('--- SHEET', s, 'DIFFS', len(diffs))
    for d in diffs[:10]:
        print(f"R{d['row']}C{d['col']}: local='{d['local']}' | external='{d['external']}'")

# Exit 0 if no mismatches and sheet lists match; else exit 1
if not only_local and not only_ext and not mismatches:
    print('TEMPLATES_MATCH')
    sys.exit(0)
else:
    print('TEMPLATES_DIFFER')
    sys.exit(1)
