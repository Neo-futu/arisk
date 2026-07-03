"""
create_word_report.py — 讀取 outputdata.json → 填充 Word 模版 → 生成 .docx
用法：python create_word_report.py --data outputdata_20260625_博匯港元貨幣市場基金I.json

工作流：
  create_word_template.py  →  Template_Factsheet.docx  （結構模版）
  extract_data.py          →  outputdata.json           （資料庫數值）
  create_word_report.py    →  MMF_Factsheet_YYYYMMDD.docx（最終可編輯 Word）
"""
import sys, os, io, json, argparse, copy
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date, timedelta
from pathlib import Path

BASE_DIR    = Path(__file__).parent
TEMPLATE    = BASE_DIR / 'Template_Factsheet.docx'
OUTPUT_DIR  = BASE_DIR.parent / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    from docxtpl import DocxTemplate, InlineImage
    from docx.shared import Cm
except ImportError:
    print('pip install docxtpl python-docx'); sys.exit(1)

try:
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt, matplotlib.font_manager as fm
    for _fp in ['C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/simhei.ttf']:
        if os.path.exists(_fp):
            plt.rcParams.update({'font.family':[fm.FontProperties(fname=_fp).get_name(),'sans-serif'],
                                 'axes.unicode_minus': False})
            break
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

# ── 顏色常量 ─────────────────────────────────────────────
PIE_COLORS = ['#2E75B6','#70AD47','#ED7D31','#FFC000',
              '#5B9BD5','#7030A0','#FF0000','#00B0F0']

# ══════════════════════════════════════════════════════════
# 圖表生成
# ══════════════════════════════════════════════════════════
def _make_pie_file(labels, values, dpi=150) -> str | None:
    if not HAVE_MPL or not values: return None
    fig, ax = plt.subplots(figsize=(5.5, 3.8), dpi=dpi)
    wedges, _, ats = ax.pie(
        values, labels=None, colors=PIE_COLORS[:len(values)],
        autopct=lambda p: f'{p:.1f}%' if p >= 3 else '',
        startangle=90, pctdistance=0.72,
        wedgeprops={'linewidth': 0.5, 'edgecolor': 'white'})
    for at in ats: at.set_fontsize(7.5)
    ax.legend(wedges, [f'{l}  {v:.1f}%' for l, v in zip(labels, values)],
              loc='lower center', bbox_to_anchor=(0.5, -0.28),
              ncol=2, fontsize=7, frameon=False, handlelength=1.0)
    ax.set_aspect('equal')
    plt.tight_layout(pad=0.3)
    path = str(OUTPUT_DIR / '_tmp_pie.png')
    plt.savefig(path, format='png', bbox_inches='tight', dpi=dpi); plt.close()
    return path

def _make_bar_file(labels, values, dpi=150) -> str | None:
    if not HAVE_MPL or not values: return None
    fig, ax = plt.subplots(figsize=(5.5, 3.2), dpi=dpi)
    ax.bar(range(len(labels)), values, color='#2E75B6', width=0.6, edgecolor='white')
    for i, v in enumerate(values):
        if v > 0.5:
            ax.text(i, v + 0.3, f'{v:.1f}%', ha='center', va='bottom', fontsize=7)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7.5, rotation=30, ha='right')
    ax.set_ylabel('%', fontsize=8); ax.yaxis.set_tick_params(labelsize=7.5)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.set_ylim(0, max(values) * 1.3 if values else 100)
    plt.tight_layout(pad=0.3)
    path = str(OUTPUT_DIR / '_tmp_bar.png')
    plt.savefig(path, format='png', bbox_inches='tight', dpi=dpi); plt.close()
    return path

# ══════════════════════════════════════════════════════════
# 數值格式化
# ══════════════════════════════════════════════════════════
def _f(v, dec=2):
    """格式化業績數字：None → '—'"""
    if v is None: return '—'
    try: return f'{float(v):.{dec}f}%'
    except: return str(v)

def _fv(v, dec=2):
    """格式化純數字：None → '—'"""
    if v is None: return '—'
    try: return f'{float(v):.{dec}f}'
    except: return str(v)

# ══════════════════════════════════════════════════════════
# 構建模版上下文
# ══════════════════════════════════════════════════════════
def build_context(data: dict, tpl: DocxTemplate) -> dict:
    ev  = date.fromisoformat(data['eval_date'])
    p   = data['performance']
    cls = data['nav_classes']         # list of {class_id, nav_per_unit, issue_date}
    ann = data['annual_performance']  # list of {year, return_pct}
    ccy = data['base_currency']

    # ── 基本資料 ──────────────────────────────────────
    ctx = {
        'fund_name':          data['fund_name'],
        'eval_year':          str(ev.year),
        'eval_month':         f'{ev.month:02d}',
        'eval_day':           f'{ev.day:02d}',
        'base_currency':      ccy,
        'nav_millions':       f'{data["nav_millions"]:,.2f}',
        'wam_days':           _fv(data['wam_days'], 2),
        'ytm_pct':            _fv(data['ytm_pct'], 2),
        'investment_manager': data.get('investment_manager', '—'),
        'trustee':            data.get('trustee', '—'),
        'custodian':          data.get('custodian', '—'),
        'legal_structure':    '香港傘子式單位信託基金',
        'non_base_currency':  '美元',
        'trading_freq':       '每日',
        'investment_objective': (
            '本基金旨在提供與通行貨幣市場利率相若的回報，以資本安全及流動性為首要考慮，'
            f'將本基金資產淨值的不少於70%投資於以{ccy}計價的短期存款及高質量貨幣市場工具。'),
        'contact_phone': '(852) XXXX XXXX',
        'contact_web':   'www.example.com.hk',
        'contact_email': 'fund@example.com.hk',
    }

    # ── NAV 類別表（4行，不足用"—"）────────────────────
    for i in range(4):
        if i < len(cls):
            c2 = cls[i]
            ctx[f'nav_cls_{i}_id']   = str(c2.get('class_id', '—'))
            ctx[f'nav_cls_{i}_date'] = str(c2.get('issue_date', '—'))
            ctx[f'nav_cls_{i}_nav']  = f"{ccy} {_fv(c2.get('nav_per_unit'), 4)}"
            ctx[f'nav_cls_{i}_bb']   = '—'
            ctx[f'nav_cls_{i}_isin'] = '—'
        else:
            for k in ['id','date','nav','bb','isin']:
                ctx[f'nav_cls_{i}_{k}'] = '—'

    # ── 費用表（暫用原參考 PDF 的費率結構）──────────────
    fee_defaults = [
        ('I', '無',   '0.05%', f'{ccy} 1,000,000'),
        ('A', '最高5%', '0.15%', f'{ccy} 1,000'),
        ('F', '最高5%', '0.60%', '無'),
        ('B', '最高5%', '0.30%', f'{ccy} 10,000'),
    ]
    for i, (cls_id, sub, mgmt, mini) in enumerate(fee_defaults):
        if i < len(cls):
            ctx[f'fee_cls_{i}_id']   = cls[i].get('class_id', cls_id)
        else:
            ctx[f'fee_cls_{i}_id'] = '—'
        ctx[f'fee_cls_{i}_sub']  = sub
        ctx[f'fee_cls_{i}_mgmt'] = mgmt
        ctx[f'fee_cls_{i}_min']  = mini

    # ── 累積業績（4行）──────────────────────────────────
    perf_keys = ['ret_1m','ret_3m','ret_6m','ret_1y',
                 'ret_since_inception','ret_ann_since_inception','ret_7d_ann']
    for i in range(4):
        cls_lbl = cls[i]['class_id'] if i < len(cls) else '—'
        ctx[f'perf_{i}_cls'] = f'{cls_lbl}類基金單位' if i < len(cls) else '—'
        for k in perf_keys:
            ctx[f'perf_{i}_{k}'] = _f(p.get(k)) if i == 0 else '—'

    # ── 年度業績（4行×2021-2025+YTD）────────────────────
    year_labels = ['2021','2022','2023','2024','2025','ytd']
    # 從 annual_performance 建 year→value 字典
    ann_map = {a['year']: a['return_pct'] for a in ann}
    for i in range(4):
        cls_lbl = cls[i]['class_id'] if i < len(cls) else '—'
        ctx[f'ann_{i}_cls'] = f'{cls_lbl}類基金單位' if i < len(cls) else '—'
        for yr_key in year_labels:
            yr_label = '本年至今' if yr_key == 'ytd' else yr_key
            v = ann_map.get(yr_label) if i == 0 else None
            ctx[f'ann_{i}_{yr_key}'] = _f(v)

    # ── 圖表圖片 ────────────────────────────────────────
    alloc = data.get('asset_allocation', [])
    mat   = data.get('maturity_dist', [])

    pie_path = _make_pie_file([a['label'] for a in alloc],
                              [a['pct_of_nav'] for a in alloc]) if alloc else None
    bar_path = _make_bar_file([m['bucket'] for m in mat],
                              [m['pct_of_nav'] for m in mat]) if mat else None

    if pie_path and Path(pie_path).exists():
        ctx['pie_chart_image'] = InlineImage(tpl, pie_path, width=Cm(9.5))
    else:
        ctx['pie_chart_image'] = '（無資產配置數據）'

    if bar_path and Path(bar_path).exists():
        ctx['bar_chart_image'] = InlineImage(tpl, bar_path, width=Cm(9.5))
    else:
        ctx['bar_chart_image'] = '（無到期分佈數據）'

    return ctx


# ══════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════
def process_one(json_path: Path):
    if not TEMPLATE.exists():
        print(f'✗ 找不到 Word 模版 {TEMPLATE}，請先執行 create_word_template.py'); return

    data = json.load(open(json_path, encoding='utf-8'))
    tpl  = DocxTemplate(str(TEMPLATE))
    ctx  = build_context(data, tpl)
    tpl.render(ctx)

    safe = data['fund_name'].replace('/', '-').replace(' ', '_')
    ev_s = data['eval_date'].replace('-', '')
    out  = OUTPUT_DIR / f'MMF_Factsheet_{ev_s}_{safe}.docx'
    tpl.save(str(out))
    print(f'  ✅ {out.name}')

    # 清理暫存圖片
    for tmp in ['_tmp_pie.png', '_tmp_bar.png']:
        p = OUTPUT_DIR / tmp
        if p.exists(): p.unlink()


def main():
    ap = argparse.ArgumentParser(description='outputdata.json → Word Factsheet')
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
