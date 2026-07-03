"""
create_word_report.py — 讀取 outputdata.json + 圖表 PNG → 填充 Word 模版 → 輸出 .docx
用法：python create_word_report.py --all

前置步驟：
  1. python extract_data.py --date 2026-06-25
  2. python create_charts.py --all
  3. python create_word_report.py --all
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date
from pathlib import Path

BASE_DIR   = Path(__file__).parent
TEMPLATE   = BASE_DIR / 'Template_Factsheet.docx'
OUTPUT_DIR = BASE_DIR.parent / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    from docxtpl import DocxTemplate, InlineImage
    from docx.shared import Cm
except ImportError:
    print('pip install docxtpl python-docx'); sys.exit(1)


def _f(v, dec=2, suffix='%'):
    """格式化數值：None → '—'"""
    if v is None: return '—'
    try: return f'{float(v):.{dec}f}{suffix}'
    except: return str(v)

def _fv(v, dec=2):
    """格式化純數字（不加%）：None → '—'"""
    if v is None: return '—'
    try: return f'{float(v):.{dec}f}'
    except: return str(v)


def build_context(data: dict, tpl: DocxTemplate, pie_path, bar_path) -> dict:
    ev  = date.fromisoformat(data['eval_date'])
    p   = data['performance']
    cls = data['nav_classes']
    ann = data['annual_performance']
    ccy = data['base_currency']

    # ── 基本資料 ──────────────────────────────────────
    ctx = {
        'fund_name':           data['fund_name'],
        'eval_year':           str(ev.year),
        'eval_month':          f'{ev.month:02d}',
        'eval_day':            f'{ev.day:02d}',
        'base_currency':       ccy,
        'nav_millions':        f"{data['nav_millions']:,.2f}",
        'wam_days':            _fv(data['wam_days'], 2),
        'ytm_pct':             _fv(data['ytm_pct'], 2),
        'investment_manager':  data.get('investment_manager', '—'),
        'trustee':             data.get('trustee', '—'),
        'custodian':           data.get('custodian', '—'),
        'legal_structure':     '香港傘子式單位信託基金',
        'non_base_currency':   '美元',
        'trading_freq':        '每日',
        'investment_objective': (
            f'本基金旨在提供與通行貨幣市場利率相若的回報，以資本安全及流動性為首要考慮，'
            f'將本基金資產淨值的不少於70%投資於以{ccy}計價的短期存款及高質量貨幣市場工具。'),
        'contact_phone': '(852) XXXX XXXX',
        'contact_web':   'www.example.com.hk',
        'contact_email': 'fund@example.com.hk',
    }

    # ── NAV 類別（4行）─────────────────────────────────
    for i in range(4):
        if i < len(cls):
            c2 = cls[i]
            ctx[f'nav_cls_{i}_id']   = str(c2.get('class_id', '—'))
            ctx[f'nav_cls_{i}_date'] = str(c2.get('issue_date', '—'))
            ctx[f'nav_cls_{i}_nav']  = _fv(c2.get('nav_per_unit'), 4)
            ctx[f'nav_cls_{i}_bb']   = '—'
            ctx[f'nav_cls_{i}_isin'] = '—'
        else:
            for k in ['id', 'date', 'nav', 'bb', 'isin']:
                ctx[f'nav_cls_{i}_{k}'] = '—'

    # ── 費用表（沿用參考 PDF 費率結構）───────────────
    fee_defaults = [
        ('I', '0.05%', '1,000,000'),
        ('A', '0.15%', '1,000'),
        ('F', '0.60%', '無'),
        ('B', '0.30%', '10,000'),
    ]
    for i, (cls_id, mgmt, mini) in enumerate(fee_defaults):
        ctx[f'fee_{i}_cls']  = cls[i]['class_id'] if i < len(cls) else cls_id
        ctx[f'fee_{i}_mgmt'] = mgmt
        ctx[f'fee_{i}_min']  = mini

    # ── 累積業績（4行×7個數值）────────────────────────
    perf_keys = ['ret_1m', 'ret_3m', 'ret_6m', 'ret_1y',
                 'ret_since_inception', 'ret_ann_since_inception', 'ret_7d_ann']
    for i in range(4):
        ctx[f'perf_{i}_cls'] = cls[i]['class_id'] if i < len(cls) else '—'
        for k in perf_keys:
            ctx[f'perf_{i}_{k}'] = _f(p.get(k)) if i == 0 else '—'

    # ── 年度業績（4行×6年）────────────────────────────
    years    = ['2021', '2022', '2023', '2024', '2025', 'ytd']
    ann_map  = {a['year']: a['return_pct'] for a in ann}
    ytd_val  = ann_map.get('本年至今')
    year_val = {
        '2021': ann_map.get('2021'),
        '2022': ann_map.get('2022'),
        '2023': ann_map.get('2023'),
        '2024': ann_map.get('2024'),
        '2025': ann_map.get('2025'),
        'ytd':  ytd_val,
    }
    for i in range(4):
        ctx[f'ann_{i}_cls'] = cls[i]['class_id'] if i < len(cls) else '—'
        for y in years:
            ctx[f'ann_{i}_{y}'] = _f(year_val.get(y)) if i == 0 else '—'

    # ── 圖表圖片（讀取預生成 PNG）──────────────────────
    if pie_path and Path(pie_path).exists():
        ctx['pie_chart'] = InlineImage(tpl, str(pie_path), width=Cm(9.6))
    else:
        ctx['pie_chart'] = '（無資產配置數據）'

    if bar_path and Path(bar_path).exists():
        ctx['bar_chart'] = InlineImage(tpl, str(bar_path), width=Cm(9.6))
    else:
        ctx['bar_chart'] = '（無到期分佈數據）'

    return ctx


def process_one(json_path: Path):
    if not TEMPLATE.exists():
        print(f'✗ 找不到 Word 模版，請先執行 create_word_template.py'); return

    data = json.load(open(json_path, encoding='utf-8'))
    ev_s = data['eval_date'].replace('-', '')
    safe = data['fund_name'].replace('/', '-').replace(' ', '_')

    # 查找圖表 PNG（由 create_charts.py 生成）
    pie_path = OUTPUT_DIR / f'pie_chart_{ev_s}_{safe}.png'
    bar_path = OUTPUT_DIR / f'bar_chart_{ev_s}_{safe}.png'
    if not pie_path.exists() or not bar_path.exists():
        print(f'  ⚠ 找不到圖表 PNG，請先執行 create_charts.py')
        print(f'    缺少：{pie_path.name if not pie_path.exists() else bar_path.name}')

    tpl = DocxTemplate(str(TEMPLATE))
    ctx = build_context(data, tpl, pie_path, bar_path)
    tpl.render(ctx)

    out = OUTPUT_DIR / f'MMF_Factsheet_{ev_s}_{safe}.docx'
    tpl.save(str(out))
    print(f'  ✅ {out.name}')


def main():
    ap = argparse.ArgumentParser(description='outputdata.json → Word Factsheet (.docx)')
    ap.add_argument('--data', default=None, help='指定 outputdata JSON 文件')
    ap.add_argument('--date', default=None, help='估值日期（搭配 --all）')
    ap.add_argument('--all',  action='store_true', help='處理 output 目錄中所有 outputdata 文件')
    args = ap.parse_args()

    if args.data:
        json_files = [Path(args.data)]
    elif args.all or args.date:
        pat = f'outputdata_{args.date.replace("-","")}_*.json' if args.date else 'outputdata_*.json'
        json_files = sorted(OUTPUT_DIR.glob(pat))
    else:
        json_files = sorted(OUTPUT_DIR.glob('outputdata_*.json'))
        json_files = [json_files[-1]] if json_files else []

    if not json_files:
        print('✗ 找不到 outputdata 文件，請先執行 extract_data.py'); return

    print(f'[create_word_report] 處理 {len(json_files)} 個文件')
    for jf in json_files:
        print(f'  讀取：{jf.name}')
        process_one(jf)


if __name__ == '__main__':
    main()
