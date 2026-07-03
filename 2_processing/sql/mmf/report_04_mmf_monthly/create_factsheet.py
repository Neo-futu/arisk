"""
create_factsheet.py — 讀取 outputdata.json + ref_layout.json → 生成 PDF
用法：python create_factsheet.py --data outputdata_20260625_博匯港元貨幣市場基金I.json

工作流：
  1. extract_data.py   → outputdata.json  （資料庫數值）
  2. ref_layout.json   → PDF 模版結構     （坐標/字型/顏色）
  3. create_factsheet  → 最終 PDF         （模版 + 數值合併）
"""
import sys, os, io, json, argparse
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date, timedelta
from pathlib import Path

BASE_DIR    = Path(__file__).parent
LAYOUT_FILE = BASE_DIR / 'ref_layout.json'
OUTPUT_DIR  = BASE_DIR.parent / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 依賴 ─────────────────────────────────────────────────
try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import Color
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
except ImportError:
    print('pip install reportlab'); sys.exit(1)

try:
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt, matplotlib.font_manager as fm
    for _fp in ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf']:
        if os.path.exists(_fp):
            plt.rcParams.update({'font.family': [fm.FontProperties(fname=_fp).get_name(), 'sans-serif'],
                                 'axes.unicode_minus': False})
            break
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

W, H = A4   # 595.92 × 841.92

# ══════════════════════════════════════════════════════════
# 字型
# ══════════════════════════════════════════════════════════
def _setup_fonts():
    reg = {'cjk': 'Helvetica', 'arial': 'Helvetica', 'arialb': 'Helvetica-Bold'}
    for path, name in [('C:/Windows/Fonts/msyh.ttc', 'MYH'),
                       ('C:/Windows/Fonts/simhei.ttf', 'SHH')]:
        if os.path.exists(path) and reg['cjk'] == 'Helvetica':
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                addMapping(name, 0, 0, name); addMapping(name, 1, 0, name)
                reg['cjk'] = name; break
            except: pass
    for path, name in [('C:/Windows/Fonts/arial.ttf', 'ARL')]:
        if os.path.exists(path) and reg['arial'] == 'Helvetica':
            try: pdfmetrics.registerFont(TTFont(name, path)); reg['arial'] = name; break
            except: pass
    for path, name in [('C:/Windows/Fonts/arialbd.ttf', 'ARLB')]:
        if os.path.exists(path) and reg['arialb'] == 'Helvetica-Bold':
            try: pdfmetrics.registerFont(TTFont(name, path)); reg['arialb'] = name; break
            except: pass
    return reg

FONTS = _setup_fonts()

def _font(ref_name):
    r = ref_name.lower()
    if ('bold' in r) and any(k in r for k in ('yahe', 'hei', 'sun')): return FONTS['cjk']
    if any(k in r for k in ('yahe', 'hei', 'sun')): return FONTS['cjk']
    if 'bold' in r: return FONTS['arialb']
    return FONTS['arial']

def _color(int_color):
    return Color((int_color >> 16 & 0xFF) / 255,
                 (int_color >> 8  & 0xFF) / 255,
                 (int_color       & 0xFF) / 255)

# ══════════════════════════════════════════════════════════
# 圖表
# ══════════════════════════════════════════════════════════
PIE_COLORS = ['#2E75B6','#70AD47','#ED7D31','#FFC000','#5B9BD5','#7030A0','#FF0000','#00B0F0']

def _pie_png(labels, values, w_pt, h_pt, dpi=150):
    if not HAVE_MPL or not values: return None
    fig, ax = plt.subplots(figsize=(w_pt/72, h_pt/72), dpi=dpi)
    wedges, _, ats = ax.pie(values, labels=None,
        colors=PIE_COLORS[:len(values)],
        autopct=lambda p: f'{p:.1f}%' if p >= 3 else '',
        startangle=90, pctdistance=0.72,
        wedgeprops={'linewidth': 0.4, 'edgecolor': 'white'})
    for at in ats: at.set_fontsize(6.5)
    ax.legend(wedges, [f'{l}  {v:.1f}%' for l, v in zip(labels, values)],
              loc='lower center', bbox_to_anchor=(0.5, -0.35),
              ncol=2, fontsize=6, frameon=False, handlelength=0.8)
    ax.set_aspect('equal'); plt.tight_layout(pad=0.1)
    buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight', dpi=dpi)
    plt.close(); buf.seek(0); return buf.read()

def _bar_png(labels, values, w_pt, h_pt, dpi=150):
    if not HAVE_MPL or not values: return None
    fig, ax = plt.subplots(figsize=(w_pt/72, h_pt/72), dpi=dpi)
    ax.bar(range(len(labels)), values, color='#2E75B6', width=0.6, edgecolor='white')
    for i, v in enumerate(values):
        if v > 0.5: ax.text(i, v + 0.3, f'{v:.1f}%', ha='center', va='bottom', fontsize=6.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7, rotation=30, ha='right')
    ax.set_ylabel('%', fontsize=7); ax.yaxis.set_tick_params(labelsize=7)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.set_ylim(0, max(values) * 1.25 if values else 100)
    plt.tight_layout(pad=0.3)
    buf = io.BytesIO(); plt.savefig(buf, format='png', bbox_inches='tight', dpi=dpi)
    plt.close(); buf.seek(0); return buf.read()

# ══════════════════════════════════════════════════════════
# 可變字段替換表（key = (round(y), round(x))）
# 精確對應 ref_layout.json 解析出的 span 坐標
# ══════════════════════════════════════════════════════════
def build_replacements(data: dict) -> dict:
    fn  = data['fund_name']
    ccy = data['base_currency']
    ev  = date.fromisoformat(data['eval_date'])
    p   = data['performance']
    cls = data['nav_classes']      # list of {class_id, nav_per_unit, issue_date}
    ann = data['annual_performance']  # list of {year, return_pct}

    def fmt(v, dec=2):
        """格式化數值：None → '—'"""
        if v is None: return '—'
        return f'{float(v):.{dec}f}'

    R = {}
    def add(y, x, t): R[(round(y), round(x))] = str(t)

    # ── P1 頁首 ──────────────────────────────────────
    add(18.9, 15.3, fn)                            # 基金名稱
    add(41.3, 79.8,  str(ev.year))                 # 年
    add(41.3, 112.3, f'{ev.month:02d}')            # 月
    add(41.3, 130.5, f'{ev.day:02d}')              # 日

    # ── P1 左欄：基金資料 ─────────────────────────────
    add(309.1, 217.9, data.get('investment_manager', '—'))   # 投資經理
    add(316.4, 205.7, data.get('trustee', '—'))              # 受託人
    # 託管人（原 PDF 拆成多個 span：中國銀行 + （香港）+ 有限公司）
    custodian = data.get('custodian', '中國銀行（香港）有限公司')
    add(324.4, 226.1, custodian.split('（')[0])               # "中國銀行" 部分
    add(324.4, 252.7, '（')
    add(324.4, 254.7, custodian.split('（')[1].split('）')[0] if '（' in custodian else '')
    add(325.3, 265.0, '）')
    add(324.4, 267.1, '有限公司')
    add(331.8, 279.3, ccy)                                    # 基礎貨幣（右欄值）
    # 基金規模
    add(339.8, 236.3, ccy)
    add(340.7, 248.6, f"{data['nav_millions']:,.2f}")
    add(339.8, 279.3, '百萬')
    add(347.1, 279.3, '—')                                    # 非基礎貨幣股份類別

    # ── P1 左欄：基金單位類別 NAV 表（4行）────────────
    # 每行 (y_num, y_cjk, x_date, x_ccy, x_nav, x_bb, x_isin)
    nav_rows = [
        (399.6, 398.7, 113.8, 159.2, 171.5, 204.7, 248.9),
        (408.8, 407.9, 114.2, 159.2, 171.5, 200.6, 248.9),
        (418.1, 417.1, 113.8, 159.2, 171.5, 200.6, 248.9),
        (427.2, 426.3, 113.8, 159.2, 171.5, 199.9, 248.9),
    ]
    nav_label_x = [(15.3, 17.1), (15.3, 19.4), (15.3, 19.1), (15.3, 19.4)]
    nav_prefix  = ['I', 'A', 'F', 'B']   # 原參考 PDF 的前綴字母（保持格式）
    for i, (yn, yt2, xdt, xccy, xnav, xbb, xisin) in enumerate(nav_rows):
        xnum, xcjk = nav_label_x[i]
        if i < len(cls):
            c2 = cls[i]
            add(yn,  xnum, c2['class_id'])
            add(yt2, xcjk, '類基金單位')
            add(yn,  xdt,  str(c2.get('issue_date', '—')))
            add(yt2, xccy, ccy)
            add(yn,  xnav, fmt(c2['nav_per_unit'], 4))
            add(yn,  xbb,  '—')     # Bloomberg 代碼（暫無）
            add(yn,  xisin,'—')     # ISIN（暫無）
        else:
            add(yn, xnum, '—'); add(yt2, xcjk, '')
            add(yn, xdt, ''); add(yt2, xccy, '')
            add(yn, xnav, ''); add(yn, xbb, ''); add(yn, xisin, '')

    # ── P1 左欄：費用表（4行，類別名稱對應 NAV 類別）────
    fee_rows = [(466.5,465.6),(475.8,474.8),(485.0,484.0),(494.2,493.2)]
    for i, (yn, yt2) in enumerate(fee_rows):
        if i < len(cls):
            add(yn, 15.3, cls[i]['class_id']); add(yt2, 17.1, '類基金單位')
        else:
            add(yn, 15.3, '—'); add(yt2, 17.1, '')

    # ── P1 左欄：數據來源日期 ─────────────────────────
    add(438.3, 72.3,  str(ev.year))
    add(438.3, 93.8,  f'{ev.month:02d}')
    add(438.3, 106.8, f'{ev.day:02d}')

    # ── P1 右欄：累積業績表（4行×7列）─────────────────
    # 參考 PDF 行坐標 + 7列 x 坐標
    perf_rows = [
        (456.7, 455.8),  # I 類
        (465.9, 465.0),  # A 類
        (475.1, 474.2),  # F 類
        (484.4, 483.4),  # B 類
    ]
    perf_xs = [385.9, 410.7, 435.6, 460.5, 493.0, 532.3, 568.2]  # 7列 x 坐標
    perf_keys = ['ret_1m','ret_3m','ret_6m','ret_1y',
                 'ret_since_inception','ret_ann_since_inception','ret_7d_ann']
    for i, (yn, yt2) in enumerate(perf_rows):
        add(yn,  303.9, cls[i]['class_id'] if i < len(cls) else '—')
        add(yt2, 305.6, '類基金單位' if i < len(cls) else '')
        for j, (x, key) in enumerate(zip(perf_xs, perf_keys)):
            v = p.get(key) if i == 0 else None   # 只有第1行顯示真實數據
            add(yn, x, fmt(v))

    # ── P1 右欄：年度業績表（4行×6列）──────────────────
    ann_rows = [
        (537.8, 536.8),
        (547.0, 546.0),
        (556.2, 555.2),
        (565.4, 564.5),
    ]
    ann_xs = [430.1, 457.7, 485.3, 513.0, 540.6, 568.2]   # 2021/22/23/24/25/本年至今
    for i, (yn, yt2) in enumerate(ann_rows):
        add(yn,  303.9, cls[i]['class_id'] if i < len(cls) else '—')
        add(yt2, 305.6, '類基金單位' if i < len(cls) else '')
        for j, x in enumerate(ann_xs):
            v = ann[j]['return_pct'] if (i == 0 and j < len(ann)) else None
            add(yn, x, fmt(v))

    # ── P2：投資組合特點 ──────────────────────────────
    add(94.8,  268.4, fmt(data['wam_days'], 2))    # 加權平均到期日（天）
    add(104.9, 274.2, f"{data['ytm_pct']:.2f}%")  # 加權平均到期收益率

    # ── P2：腳注4 日期（7日前 ~ 估值日）─────────────
    d7 = ev - timedelta(days=7)
    add(796.8, 156.2, str(ev.year));  add(796.8, 176.0, f'{ev.month:02d}')
    add(796.8, 189.0, f'{d7.day:02d}')
    add(796.8, 208.2, str(ev.year));  add(796.8, 228.1, f'{ev.month:02d}')
    add(796.8, 241.1, f'{ev.day:02d}')

    return R


# ══════════════════════════════════════════════════════════
# PDF 渲染（逐元素克隆參考 PDF，可變字段用替換表覆蓋）
# ══════════════════════════════════════════════════════════
def _render_page(c, page_data: dict, repl: dict, charts=None):
    """
    渲染一頁：
      1. 填充矩形（brand red + 黑色背景條/分隔線）
      2. 所有文字 span（字型/顏色/大小精確對應參考 PDF）
      3. 嵌入圖表 PNG（僅 P2）
    """
    RED = Color(191/255, 0, 8/255)    # 品牌紅 #BF0008

    # ① 填充矩形
    for r in page_data.get('rects', []):
        f = r.get('fill')
        if not f: continue
        x0, y0, x1, y1 = r['rect']
        if x1 <= x0 or y1 <= y0: continue
        c.setFillColor(Color(f[0], f[1], f[2]))
        c.rect(x0, H - y1, x1 - x0, y1 - y0, fill=1, stroke=0)

    # ② 固定黑色元素（頁首右側橫條 + 欄間垂直線 + 水平分隔線）
    c.setFillColor(Color(0, 0, 0))
    c.rect(192.16, H - 69.37, 580.15 - 192.16, 9.21, fill=1, stroke=0)   # 黑色橫條
    c.setStrokeColor(Color(0, 0, 0)); c.setLineWidth(0.4)
    c.line(297.75, H - 221.62, 297.75, H - 600)                           # 垂直分隔線
    for hy in [300.21, 388.0, 436.5, 236.36, 735.09]:                     # 水平分隔線
        c.line(15.35, H - hy, 291.61, H - hy)
    for hy in [435.88, 516.92, 236.36]:                                    # 右欄水平線
        c.line(303.89, H - hy, 580.15, H - hy)

    # ③ 文字（克隆 + 替換）
    for span in page_data.get('texts', []):
        y0s, x0s = span['y'], span['x']
        key  = (round(y0s), round(x0s))
        text = repl.get(key, span['text'])
        if not text or not str(text).strip(): continue
        font_name = _font(span['font'])
        color     = _color(span['color'])
        size      = span['size']
        y_rl      = H - span['y1'] + 0.5   # baseline ≈ bbox 底部 + 微調
        c.setFont(font_name, size)
        c.setFillColor(color)
        c.drawString(x0s, y_rl, str(text))

    # ④ 圖表圖片（僅 P2）
    if charts:
        for (bx0, by0, bx1, by1), img_bytes in charts:
            if img_bytes:
                c.drawImage(ImageReader(io.BytesIO(img_bytes)),
                            bx0, H - by1, bx1 - bx0, by1 - by0)


def build_pdf(data: dict, layout: dict, out_path: Path):
    ev   = date.fromisoformat(data['eval_date'])
    repl = build_replacements(data)
    c    = rl_canvas.Canvas(str(out_path), pagesize=A4)

    # 第 1 頁
    _render_page(c, layout['p1'], repl)
    c.showPage()

    # 第 2 頁 + 圖表
    alloc = data.get('asset_allocation', [])
    mat   = data.get('maturity_dist', [])
    # 餅圖 bbox 來自 ref_layout 圖片分析：(303.9, 111.7, 580.2, 190.3)
    pie_bytes = _pie_png([a['label'] for a in alloc],
                         [a['pct_of_nav'] for a in alloc],
                         276.3, 78.6) if alloc else None
    # 柱狀圖 bbox：(303.9, 210.0, 580.2, 310.6)
    bar_bytes = _bar_png([m['bucket'] for m in mat],
                         [m['pct_of_nav'] for m in mat],
                         276.3, 100.7) if mat else None
    charts = [
        ((303.89, 111.73, 580.15, 190.31), pie_bytes),
        ((303.89, 209.96, 580.15, 310.64), bar_bytes),
    ]
    _render_page(c, layout['p2'], repl, charts=charts)
    c.save()
    print(f'  ✅  →  {out_path.name}')


# ══════════════════════════════════════════════════════════
# 入口：讀取 outputdata.json 生成 PDF
# ══════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description='讀取 outputdata.json → 生成 Factsheet PDF')
    ap.add_argument('--data', required=False, default=None,
                    help='outputdata JSON 文件路徑（缺省=output 目錄中最新的）')
    ap.add_argument('--date', default=None, help='估值日期（搭配 --all 使用）')
    ap.add_argument('--all', action='store_true', help='處理 output 目錄中所有 outputdata 文件')
    args = ap.parse_args()

    if not LAYOUT_FILE.exists():
        print(f'✗ 找不到 PDF 模版：{LAYOUT_FILE}'); return
    layout = json.load(open(LAYOUT_FILE, encoding='utf-8'))

    # 決定要處理哪些 JSON 文件
    if args.data:
        json_files = [Path(args.data)]
    elif args.all or args.date:
        pattern = f'outputdata_{args.date.replace("-","")}_*.json' if args.date else 'outputdata_*.json'
        json_files = sorted(OUTPUT_DIR.glob(pattern))
        if not json_files:
            print(f'✗ 找不到符合條件的 outputdata 文件（{OUTPUT_DIR}/{pattern}）'); return
    else:
        # 缺省：取最新的
        json_files = sorted(OUTPUT_DIR.glob('outputdata_*.json'))
        if not json_files:
            print('✗ 找不到 outputdata 文件，請先執行 extract_data.py'); return
        json_files = [json_files[-1]]   # 最新

    print(f'[create_factsheet] 處理 {len(json_files)} 個文件')
    for jf in json_files:
        print(f'  讀取：{jf.name}')
        data = json.load(open(jf, encoding='utf-8'))
        safe = data['fund_name'].replace('/', '-').replace(' ', '_')
        ev_s = data['eval_date'].replace('-', '')
        out  = OUTPUT_DIR / f'MMF_Factsheet_{ev_s}_{safe}.pdf'
        build_pdf(data, layout, out)


if __name__ == '__main__':
    main()
