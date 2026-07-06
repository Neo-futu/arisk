from openpyxl import load_workbook
from pathlib import Path
import sys

LOCAL_ROOT = Path('2_processing/sql/mmf/report_06')
EXTERNAL_ROOT = Path(r'D:\riskpy\amc\SQLServer\Script\SmartReport\06')

# parameters
MAX_ROWS = 20
MAX_COLS = 50
HEADER_ROWS = 5

pairs = []
# gather local xlsx files under LOCAL_ROOT
local_files = list(LOCAL_ROOT.rglob('*.xlsx'))
# build map by filename lower -> paths
local_map = {}
for p in local_files:
    local_map.setdefault(p.name.lower(), []).append(p)

external_files = list(EXTERNAL_ROOT.rglob('*.xlsx'))
external_map = {}
for p in external_files:
    external_map.setdefault(p.name.lower(), []).append(p)

all_names = sorted(set(list(local_map.keys()) + list(external_map.keys())))

results = []

for name in all_names:
    locals = local_map.get(name, [])
    exts = external_map.get(name, [])
    if not locals:
        results.append({'file': name, 'status': 'MISSING_LOCAL', 'detail': [str(x) for x in exts]})
        continue
    if not exts:
        results.append({'file': name, 'status': 'MISSING_EXTERNAL', 'detail': [str(x) for x in locals]})
        continue
    # if multiple, compare first pair by path order
    lpath = locals[0]
    epath = exts[0]
    wb_l = load_workbook(lpath, data_only=True)
    wb_e = load_workbook(epath, data_only=True)
    sheets_e = wb_e.sheetnames
    sheets_l = wb_l.sheetnames
    file_report = {'file': name, 'status': 'OK', 'missing_sheets': [], 'header_mismatch': [], 'missing_content': []}
    # check all external sheets exist locally
    for s in sheets_e:
        if s not in sheets_l:
            file_report['missing_sheets'].append(s)
            file_report['status'] = 'DIFFER'
    # for common sheets check header equality and content presence
    for s in sheets_e:
        if s not in sheets_l:
            continue
        ws_e = wb_e[s]
        ws_l = wb_l[s]
        # header check: first HEADER_ROWS x MAX_COLS exact match
        for r in range(1, HEADER_ROWS+1):
            for c in range(1, MAX_COLS+1):
                ve = ws_e.cell(row=r, column=c).value
                vl = ws_l.cell(row=r, column=c).value
                if (ve is None or str(ve).strip()=="") and (vl is None or str(vl).strip()==""):
                    continue
                se = str(ve).strip() if ve is not None else ''
                sl = str(vl).strip() if vl is not None else ''
                if se != sl:
                    file_report['header_mismatch'].append({'sheet': s, 'row': r, 'col': c, 'external': se, 'local': sl})
                    file_report['status'] = 'DIFFER'
        # content presence: for region MAX_ROWS x MAX_COLS, any non-empty in external must be non-empty in local
        for r in range(1, MAX_ROWS+1):
            for c in range(1, MAX_COLS+1):
                ve = ws_e.cell(row=r, column=c).value
                if ve is None or str(ve).strip()=='' :
                    continue
                vl = ws_l.cell(row=r, column=c).value
                if vl is None or str(vl).strip()=='' :
                    file_report['missing_content'].append({'sheet': s, 'row': r, 'col': c, 'external': str(ve).strip()})
                    file_report['status'] = 'DIFFER'
    results.append(file_report)

# print summary
ok = True
for r in results:
    if r['status'] == 'OK':
        print('OK:', r['file'])
    else:
        ok = False
        print('DIFFER:', r['file'])
        if r.get('missing_sheets'):
            print('  MISSING_SHEETS:', r['missing_sheets'])
        if r.get('header_mismatch'):
            print('  HEADER_MISMATCH_COUNT:', len(r['header_mismatch']))
            for m in r['header_mismatch'][:10]:
                print(f"    {m['sheet']} R{m['row']}C{m['col']}: ext='{m['external']}' | loc='{m['local']}'")
        if r.get('missing_content'):
            print('  MISSING_CONTENT_COUNT:', len(r['missing_content']))
            for m in r['missing_content'][:10]:
                print(f"    {m['sheet']} R{m['row']}C{m['col']}: external='{m['external']}'")

if ok:
    print('ALL_TEMPLATES_MATCH')
    sys.exit(0)
else:
    print('TEMPLATES_DIFFER')
    sys.exit(1)
