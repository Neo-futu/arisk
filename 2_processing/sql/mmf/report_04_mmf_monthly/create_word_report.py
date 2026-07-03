"""
create_word_report.py — outputdata.json + 图表PNG → Word Factsheet (.docx)
直接编程生成，不依赖模板文件，数据100%可靠填充。
用法：python create_word_report.py --all
前置：python extract_data.py && python create_charts.py
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date
from pathlib import Path

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR.parent / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Twips
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
except ImportError:
    print('pip install python-docx'); sys.exit(1)

# ── 品牌色 ─────────────────────────────────────────────
RED   = RGBColor(191, 0, 8)
BLACK = RGBColor(0, 0, 0)
WHITE = RGBColor(255, 255, 255)
GREY  = RGBColor(90, 90, 90)
LGREY = RGBColor(245, 245, 245)

CJK  = '微软雅黑'
MONO = 'Arial'


# ══════════════════════════════════════════════════════════
# XML 工具（仅供内部使用）
# ══════════════════════════════════════════════════════════
def _shd(cell, hex6):
    tcp = cell._tc.get_or_add_tcPr()
    s = OxmlElement('w:shd')
    s.set(qn('w:val'),'clear'); s.set(qn('w:color'),'auto')
    s.set(qn('w:fill'), hex6); tcp.append(s)

def _cell_pad(cell, t=15, b=15, l=60, r=60):
    tcp = cell._tc.get_or_add_tcPr()
    m = OxmlElement('w:tcMar')
    for side, v in [('top',t),('bottom',b),('left',l),('right',r)]:
        e = OxmlElement(f'w:{side}')
        e.set(qn('w:w'), str(v)); e.set(qn('w:type'),'dxa')
        m.append(e)
    tcp.append(m)

def _no_border(cell):
    tcp = cell._tc.get_or_add_tcPr()
    b = OxmlElement('w:tcBorders')
    for s in ['top','bottom','left','right','insideH','insideV']:
        e = OxmlElement(f'w:{s}')
        e.set(qn('w:val'),'none'); e.set(qn('w:sz'),'0'); e.set(qn('w:color'),'FFFFFF')
        b.append(e)
    tcp.append(b)

def _exact_row(row, pt):
    tr = row._tr; tp = tr.get_or_add_trPr()
    h = OxmlElement('w:trHeight')
    h.set(qn('w:val'), str(int(pt*20))); h.set(qn('w:hRule'),'exact')
    tp.append(h)

def _col_w(cell, cm):
    tc = cell._tc; tcp = tc.get_or_add_tcPr()
    w = OxmlElement('w:tcW')
    w.set(qn('w:w'), str(int(cm*567))); w.set(qn('w:type'),'dxa')
    tcp.append(w); cell.width = Cm(cm)


# ══════════════════════════════════════════════════════════
# 段落 / 文字工具
# ══════════════════════════════════════════════════════════
def _clear(cell):
    for p in cell.paragraphs: p.clear()

def _para(container, sz=6.5, before=0, after=0, ls=None, align=WD_ALIGN_PARAGRAPH.LEFT):
    p = container.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before); pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(ls or sz*1.35)
    return p

def _run(p, text, fn=CJK, sz=6.5, bold=False, clr=BLACK):
    if not str(text).strip(): return
    r = p.add_run(str(text))
    r.font.name = fn; r.font.size = Pt(sz)
    r.font.bold = bold; r.font.color.rgb = clr
    r._element.rPr.rFonts.set(qn('w:eastAsia'), fn)
    return r

def _tbl(container, rows, cols, ws):
    if hasattr(container, 'add_table'):
        t = container.add_table(rows=rows, cols=cols)
    else:
        t = container.add_table(rows=rows, cols=cols)
    t.style = 'Table Grid'; t.alignment = WD_TABLE_ALIGNMENT.LEFT
    for row in t.rows:
        for i, (cell, w) in enumerate(zip(row.cells, ws)):
            _col_w(cell, w); _no_border(cell); _cell_pad(cell)
    return t

def _fmt(v, dec=2):
    if v is None: return '—'
    try: return f'{float(v):.{dec}f}%'
    except: return '—'

def _fmtv(v, dec=2):
    if v is None: return '—'
    try: return f'{float(v):.{dec}f}'
    except: return '—'

def _section_title(cell, text):
    p = _para(cell, 9, before=3, after=2, ls=11)
    _run(p, '■ ', MONO, 8, clr=RED)
    _run(p, text, CJK, 9, bold=True, clr=RED)

def _hdr_cell(cell, text, bg='BF0008', sz=6, bold=True, fn=CJK, align=WD_ALIGN_PARAGRAPH.LEFT):
    _shd(cell, bg); _clear(cell)
    _cell_pad(cell, t=10, b=10, l=40, r=20)
    p = _para(cell, sz, ls=7.5, align=align)
    _run(p, text, fn, sz, bold, WHITE)

def _data_cell(cell, text, bg='FFFFFF', sz=6, fn=CJK, align=WD_ALIGN_PARAGRAPH.LEFT):
    _shd(cell, bg); _clear(cell)
    _cell_pad(cell, t=10, b=10, l=40, r=20)
    p = _para(cell, sz, ls=7.5, align=align)
    _run(p, str(text) if text is not None else '—', fn, sz, clr=BLACK)


# ══════════════════════════════════════════════════════════
# 页首（两页共用）
# ══════════════════════════════════════════════════════════
def _add_header(doc, data):
    ev = date.fromisoformat(data['eval_date'])
    fn = data['fund_name']

    # 基金名称 + 徽章
    t = _tbl(doc, 2, 2, [13.2, 4.8])
    # 行0: 基金名称 | 新资本计划
    r0 = t.rows[0]
    _clear(r0.cells[0])
    p = _para(r0.cells[0], 14, before=0, after=1, ls=17)
    _run(p, fn, CJK, 14, bold=True)
    _clear(r0.cells[1])
    p2 = _para(r0.cells[1], 5.5, before=2, ls=7.5, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _run(p2, '「新資本投資者入境計劃」合資格基金', CJK, 5.5, clr=RED)
    # 行1: 月报/日期 | AAAmf
    r1 = t.rows[1]
    _clear(r1.cells[0])
    p3 = _para(r1.cells[0], 8, before=0, after=0, ls=10.5)
    _run(p3, '基金月報    截至  ', CJK, 8, bold=True)
    _run(p3, f'{ev.year}', MONO, 8, bold=True)
    _run(p3, '年', CJK, 8, bold=True)
    _run(p3, f'{ev.month:02d}', MONO, 8, bold=True)
    _run(p3, '月', CJK, 8, bold=True)
    _run(p3, f'{ev.day:02d}', MONO, 8, bold=True)
    _run(p3, '日', CJK, 8, bold=True)
    _clear(r1.cells[1])
    p4 = _para(r1.cells[1], 7, before=0, ls=8.5, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _run(p4, 'AAAmf*', MONO, 7, bold=True, clr=RED)

    # 红条（左红右黑）
    bar = _tbl(doc, 1, 2, [5.8, 12.2])
    _shd(bar.rows[0].cells[0], 'BF0008'); _shd(bar.rows[0].cells[1], '000000')
    _exact_row(bar.rows[0], 5.5)
    for c in bar.rows[0].cells:
        _clear(c); _cell_pad(c, t=5, b=5, l=20, r=20)
        _para(c, 5.5, ls=5.5)


# ══════════════════════════════════════════════════════════
# P1 全宽风险说明（对应 PDF y=79-211）
# ══════════════════════════════════════════════════════════
def _add_risk_disclaimer(doc, data):
    fn = data['fund_name']
    t = _tbl(doc, 1, 1, [18.0])
    c = t.rows[0].cells[0]; _clear(c)
    _cell_pad(c, t=30, b=20, l=60, r=60)

    p0 = _para(c, 6, before=2, after=1, ls=7.8)
    _run(p0, '投資涉及風險，包括損失本金。基金單位價格可升亦可跌，基金過往業績並不表示將來的回報。'
         '基金的價值可能會非常波動，並可能於短時間內大幅下跌。投資者應在投資於基金前，'
         '閱讀有關基金之銷售說明書及產品資料概要，以了解基金詳情及風險因素。'
         '閣下不應僅依賴本資料而作出任何投資決定。投資者須注意：', CJK, 6)

    bullets = [
        f'{fn}（「本基金」）尋求實現與通行貨幣市場利率相若的長期回報，主要考慮資本安全及流動性，'
        '將本基金資產淨值的不少於70%投資於由全球政府、準政府、國際組織和金融機構所發行的港幣及美元計價和結算的短期存款和優質貨幣市場工具。',
        '基金是投資基金而非銀行存款。',
        '投資於貨幣市場工具涉及波動性及流動性風險、信貸風險、利率風險、信貸評級風險、估值風險、評級下調風險及主權債務風險。',
        '投資於短期存款面臨提供及作為該等存款交易對手方的金融機構的信貸風險。',
        '本基金可能為對沖目的而購入金融衍生工具。衍生工具的價格可以十分波動，且涉及對手方風險。於市況逆轉時，該等對沖可能變得無效，且本基金可能承受重大虧損。',
        '本基金的基金經理或會於任何一個交易日對本基金設置贖回限制。',
        '本基金可能酌情從本基金的資本中或實際從資本中支付分派，任何該等分派可導致基金的每單位資產淨值即時減少。',
    ]
    for b in bullets:
        p = _para(c, 6, before=0, after=0, ls=7.8)
        p.paragraph_format.left_indent  = Cm(0.3)
        p.paragraph_format.first_line_indent = Cm(-0.3)
        _run(p, '• ', MONO, 6); _run(p, b, CJK, 6)


# ══════════════════════════════════════════════════════════
# P1 左栏
# ══════════════════════════════════════════════════════════
def _build_left_p1(cell, data):
    ccy = data['base_currency']
    ev  = date.fromisoformat(data['eval_date'])
    cls = data.get('nav_classes', [])

    _clear(cell)
    _cell_pad(cell, t=15, b=15, l=50, r=30)

    # 投資目標
    _section_title(cell, '投資目標')
    p = _para(cell, 6, before=0, after=4, ls=8)
    _run(p, data.get('investment_objective',
         f'本基金旨在提供與通行貨幣市場利率相若的回報，以資本安全及流動性為首要考慮，'
         f'將本基金資產淨值的不少於70%投資於以{ccy}計價的短期存款及高質量貨幣市場工具。'), CJK, 6)

    # 基金資料
    _section_title(cell, '基金資料')
    fi_rows = [
        ('法律結構', '香港傘子式單位信託基金'),
        ('投資經理', data.get('investment_manager','—')),
        ('受託人',   data.get('trustee','—')),
        ('託管人',   data.get('custodian','—')),
        ('基礎貨幣', ccy),
        ('基金規模', f'{ccy} {data.get("nav_millions",0):,.2f} 百萬'),
        ('非基礎貨幣股份類別', '美元'),
        ('交易頻率', '每日'),
    ]
    fi = _tbl(cell, len(fi_rows), 2, [3.0, 4.6])
    for i, (k, v) in enumerate(fi_rows):
        r = fi.rows[i]; bg = 'FFFFFF' if i%2==0 else 'F5F5F5'
        _exact_row(r, 9)
        for c2 in r.cells: _shd(c2, bg)
        _cell_pad(r.cells[0], t=12, b=12, l=50, r=20)
        _cell_pad(r.cells[1], t=12, b=12, l=20, r=40)
        _clear(r.cells[0]); p2 = _para(r.cells[0], 6, ls=7); _run(p2, k, CJK, 6, clr=GREY)
        _clear(r.cells[1]); p3 = _para(r.cells[1], 6, ls=7); _run(p3, v, CJK, 6)

    # 基金單位類別
    pa = _para(cell, 6, before=2, after=1, ls=7); _run(pa, '', CJK, 6)
    _section_title(cell, '基金單位類別')
    cls_hdrs = ['類別', '發行日期', '每股資產淨值', '彭博編碼', 'ISIN編碼']
    cls_ws   = [2.3, 1.5, 1.9, 1.5, 1.5]
    ct = _tbl(cell, 5, 5, cls_ws)
    # 表头
    _exact_row(ct.rows[0], 8.5)
    for j, h in enumerate(cls_hdrs):
        _clear(ct.rows[0].cells[j])
        _shd(ct.rows[0].cells[j], 'D9D9D9')
        _cell_pad(ct.rows[0].cells[j], t=10, b=10, l=40, r=20)
        ph = _para(ct.rows[0].cells[j], 6, ls=7)
        _run(ph, h, CJK, 6, bold=True, clr=BLACK)
    # 数据行（最多4行）
    for i in range(1, 5):
        row = ct.rows[i]; idx = i-1; bg = 'FFFFFF' if i%2==1 else 'F5F5F5'
        _exact_row(row, 8.5)
        if idx < len(cls):
            c2 = cls[idx]
            vals = [f"{c2.get('class_id','—')} 類",
                    str(c2.get('issue_date','—')),
                    f"{ccy} {_fmtv(c2.get('nav_per_unit'),4)}",
                    '—', '—']
        else:
            vals = ['—','—','—','—','—']
        for j, v in enumerate(vals):
            _data_cell(row.cells[j], v, bg=bg, sz=6, fn=CJK if j==0 else MONO)

    # 数据来源
    ps = _para(cell, 5.5, before=2, after=3, ls=7)
    _run(ps, f'數據來源：彭博  截至 {ev.year}年{ev.month:02d}月{ev.day:02d}日，除非另有說明。', CJK, 5.5, clr=GREY)

    # 費用表（无节标题，直接跟）
    fee_hdrs = ['類別', '認購費', '投資管理費', '最低認購額']
    fee_ws   = [2.3, 1.4, 1.8, 3.2]
    fee_defaults = [
        ('I',  '無',     '0.05%', f'{ccy} 1,000,000'),
        ('A',  '最高5%', '0.15%', f'{ccy} 1,000'),
        ('F',  '最高5%', '0.60%', '無'),
        ('B',  '最高5%', '0.30%', f'{ccy} 10,000'),
    ]
    ft = _tbl(cell, 5, 4, fee_ws)
    _exact_row(ft.rows[0], 8.5)
    for j, h in enumerate(fee_hdrs):
        _clear(ft.rows[0].cells[j]); _shd(ft.rows[0].cells[j], 'D9D9D9')
        _cell_pad(ft.rows[0].cells[j], t=10, b=10, l=40, r=20)
        ph2 = _para(ft.rows[0].cells[j], 6, ls=7)
        _run(ph2, h, CJK, 6, bold=True, clr=BLACK)
    for i, (cls_id, sub, mgmt, mini) in enumerate(fee_defaults):
        row = ft.rows[i+1]; bg = 'FFFFFF' if i%2==0 else 'F5F5F5'
        _exact_row(row, 8.5)
        # 类别ID: 用实际类别名（如有）
        actual_cls = cls[i]['class_id'] if i < len(cls) else cls_id
        vals = [f'{actual_cls} 類', sub, mgmt, mini]
        for j, v in enumerate(vals):
            _data_cell(row.cells[j], v, bg=bg, sz=6, fn=CJK if j==0 else MONO)


# ══════════════════════════════════════════════════════════
# P1 右栏
# ══════════════════════════════════════════════════════════
def _build_right_p1(cell, data):
    cls  = data.get('nav_classes', [])
    p    = data.get('performance', {})
    ann  = data.get('annual_performance', [])
    _clear(cell); _cell_pad(cell, t=15, b=15, l=30, r=30)

    # 大标题
    ph = _para(cell, 9, before=0, after=2, ls=12)
    _run(ph, '基金表現', CJK, 9, bold=True, clr=RED)
    _run(ph, ' ²', MONO, 6.5, clr=RED)

    # ── 累積表現 ────────────────────────────────────────
    pc = _para(cell, 8, before=2, after=1, ls=10)
    _run(pc, '累積表現 (%)  ', CJK, 8, bold=True, clr=RED)
    _run(pc, '²', MONO, 6, clr=RED)

    c_hdrs = ['類別', '一個月', '三個月', '六個月', '一年', '自成立起', '年化\n(自成立)', '7日年化⁴']
    c_ws   = [3.1, 0.88, 0.88, 0.88, 0.88, 0.88, 1.0, 0.88]
    ct = _tbl(cell, 5, 8, c_ws)
    _exact_row(ct.rows[0], 10.5)
    for j, h in enumerate(c_hdrs):
        _clear(ct.rows[0].cells[j]); _shd(ct.rows[0].cells[j], 'BF0008')
        _cell_pad(ct.rows[0].cells[j], t=10, b=10, l=30, r=20)
        ph2 = _para(ct.rows[0].cells[j], 5.8, ls=7, align=WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT)
        _run(ph2, h, CJK, 5.8, bold=True, clr=WHITE)

    perf_keys = ['ret_1m','ret_3m','ret_6m','ret_1y','ret_since_inception','ret_ann_since_inception','ret_7d_ann']
    for i in range(1, 5):
        row = ct.rows[i]; idx = i-1; bg = 'FFFFFF' if i%2==1 else 'F5F5F5'
        _exact_row(row, 8.5)
        cls_lbl = f"{cls[idx]['class_id']} 類" if idx < len(cls) else '—'
        vals = [cls_lbl] + [_fmt(p.get(k)) if i==1 else '—' for k in perf_keys]
        for j, v in enumerate(vals):
            _clear(row.cells[j]); _shd(row.cells[j], bg)
            _cell_pad(row.cells[j], t=10, b=10, l=30, r=20)
            pa2 = _para(row.cells[j], 6, ls=7.5, align=WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT)
            _run(pa2, v, CJK if j==0 else MONO, 6)

    # ── 年度表現 ────────────────────────────────────────
    py = _para(cell, 8, before=4, after=1, ls=10)
    _run(py, '年度表現 (%)  ', CJK, 8, bold=True, clr=RED)
    _run(py, '²', MONO, 6, clr=RED)

    # 构建年度数据映射
    ann_map = {a['year']: a['return_pct'] for a in ann}
    a_years = ['2021','2022','2023','2024','2025','本年至今']
    a_hdrs  = ['類別'] + a_years
    a_ws    = [3.1, 0.93, 0.93, 0.93, 0.93, 0.93, 1.18]
    at = _tbl(cell, 5, 7, a_ws)
    _exact_row(at.rows[0], 10.5)
    for j, h in enumerate(a_hdrs):
        _clear(at.rows[0].cells[j]); _shd(at.rows[0].cells[j], 'BF0008')
        _cell_pad(at.rows[0].cells[j], t=10, b=10, l=30, r=20)
        ph3 = _para(at.rows[0].cells[j], 5.8, ls=7, align=WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT)
        _run(ph3, h, CJK if j==0 else MONO, 5.8, bold=True, clr=WHITE)
    for i in range(1, 5):
        row = at.rows[i]; idx = i-1; bg = 'FFFFFF' if i%2==1 else 'F5F5F5'
        _exact_row(row, 8.5)
        cls_lbl = f"{cls[idx]['class_id']} 類" if idx < len(cls) else '—'
        vals = [cls_lbl] + [_fmt(ann_map.get(y)) if i==1 else '—' for y in a_years]
        for j, v in enumerate(vals):
            _clear(row.cells[j]); _shd(row.cells[j], bg)
            _cell_pad(row.cells[j], t=10, b=10, l=30, r=20)
            pa3 = _para(row.cells[j], 6, ls=7.5, align=WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT)
            _run(pa3, v, CJK if j==0 else MONO, 6)


# ══════════════════════════════════════════════════════════
# P1 全宽脚注
# ══════════════════════════════════════════════════════════
def _add_p1_footnotes(doc, data):
    ev = date.fromisoformat(data['eval_date'])
    t = _tbl(doc, 1, 1, [18.0]); c = t.rows[0].cells[0]
    _cell_pad(c, t=25, b=15, l=60, r=60); _shd(c, 'FFFFFF'); _clear(c)

    lines = [
        '* 相關評級機構已授予本基金貨幣市場基金評級。',
        '¹ 關於基金詳情（包括費用）請參考基金說明書。',
        '² 過往表現並不代表未來業績。業績以資產淨值對資產淨值計算，並已計入股息再投資（如屬派息類別，則不計入股息再投資）。如基金的所有單位已全部被贖回，則每日資產淨值顯示為零。',
        '³ 自各類別成立日期起計算，成立日期請參考本文「基金單位類別」部分。',
        '⁴ 根據七天（七個日曆天）的週期進行年化計算。此數據是根據基金過去七天的表現假設計算，並不代表實際一年的回報。',
        f'除非另有說明，資料來源均來自本公司及彭博。截至 {ev.year}年{ev.month:02d}月{ev.day:02d}日。',
    ]
    for txt in lines:
        p = _para(c, 5.5, before=0, after=0.5, ls=7.5)
        _run(p, txt, CJK, 5.5, clr=GREY)

    disc = _para(c, 5.5, before=5, after=0, ls=7.5)
    _run(disc, '投資涉及風險，包括損失本金。基金單位價格可升亦可跌，過往業績並不代表未來回報。'
         '本基金是投資基金而非銀行存款。閣下應細閱基金銷售文件，了解基金詳情及風險因素。'
         '如有需要，應諮詢獨立專業意見。本資料之發行人為本公司管理人。此資料並未獲香港證監會所審閱。',
         CJK, 5.5, clr=GREY)


# ══════════════════════════════════════════════════════════
# P2 左栏（組合特點）
# ══════════════════════════════════════════════════════════
def _build_left_p2(cell, data):
    _clear(cell); _cell_pad(cell, t=15, b=15, l=50, r=30)
    _section_title(cell, '投資組合特點')

    p1 = _para(cell, 7.5, before=8, after=3, ls=9)
    _run(p1, '加權平均到期日', CJK, 7.5)

    p2 = _para(cell, 20, before=2, after=10, ls=23)
    _run(p2, _fmtv(data.get('wam_days'), 2), MONO, 20, bold=True, clr=RED)
    _run(p2, '  天', CJK, 11)

    p3 = _para(cell, 7.5, before=3, after=3, ls=9)
    _run(p3, '加權平均到期收益率', CJK, 7.5)
    _run(p3, ' ¹', MONO, 6)

    p4 = _para(cell, 20, before=2, after=3, ls=23)
    _run(p4, f"{_fmtv(data.get('ytm_pct'), 2)}%", MONO, 20, bold=True, clr=RED)


# ══════════════════════════════════════════════════════════
# P2 右栏（圖表）
# ══════════════════════════════════════════════════════════
def _build_right_p2(cell, data, pie_path, bar_path):
    try:
        from docx.shared import Cm as _Cm
    except: pass
    _clear(cell); _cell_pad(cell, t=15, b=15, l=30, r=30)

    p1 = _para(cell, 8, before=0, after=1, ls=10)
    _run(p1, '資產類別分佈 (%)', CJK, 8, bold=True, clr=RED)

    # 嵌入饼图
    if pie_path and Path(pie_path).exists():
        p_img = _para(cell, 0, before=1, after=3, ls=1)
        p_img.add_run().add_picture(str(pie_path), width=Cm(9.5))
    else:
        p_na = _para(cell, 6, before=1, after=3, ls=8)
        _run(p_na, '（請先執行 create_charts.py 生成圖表）', CJK, 6, clr=GREY)

    p2 = _para(cell, 8, before=3, after=1, ls=10)
    _run(p2, '到期日分佈 (%)', CJK, 8, bold=True, clr=RED)

    # 嵌入柱状图
    if bar_path and Path(bar_path).exists():
        p_img2 = _para(cell, 0, before=1, after=0, ls=1)
        p_img2.add_run().add_picture(str(bar_path), width=Cm(9.5))
    else:
        p_na2 = _para(cell, 6, before=1, after=0, ls=8)
        _run(p_na2, '（請先執行 create_charts.py 生成圖表）', CJK, 6, clr=GREY)


# ══════════════════════════════════════════════════════════
# P2 底部免责声明
# ══════════════════════════════════════════════════════════
def _add_p2_footer(doc, data):
    ev = date.fromisoformat(data['eval_date'])
    t = _tbl(doc, 1, 1, [18.0]); c = t.rows[0].cells[0]
    _cell_pad(c, t=25, b=15, l=60, r=60); _shd(c, 'FFFFFF'); _clear(c)

    for txt in [
        '¹ 使用基金中每個持倉的加權平均到期收益率計算。',
        f'數據來源：除非另有說明，資料來源均來自本公司。截至 {ev.year}年{ev.month:02d}月{ev.day:02d}日。',
    ]:
        p = _para(c, 5.5, before=0, after=1, ls=7.5)
        _run(p, txt, CJK, 5.5, clr=GREY)

    disc = _para(c, 5.5, before=5, after=4, ls=7.5)
    _run(disc, '重要聲明：投資涉及風險。基金股價可升亦可跌，過往業績並不表示將來基金回報，未來回報不能被保證。'
         '閣下亦可能損失所投資之本金。本資料並不構成對於任何證券或基金的買賣或進行任何交易之邀約或任何投資建議。'
         '本文件只供閣下參考之用，閣下不應依賴本文件作任何投資決定。'
         '本資料之發行人為本公司。此資料並未獲香港證監會所審閱。',
         CJK, 5.5, clr=GREY)

    cont = _para(c, 8, before=5, after=0, ls=10)
    _run(cont, f"服務熱線：{data.get('contact_phone','(852) XXXX XXXX')}    "
               f"網站：{data.get('contact_web','www.example.com.hk')}    "
               f"電郵：{data.get('contact_email','fund@example.com.hk')}", CJK, 8)


# ══════════════════════════════════════════════════════════
# 主函数：组装完整2页 Word 文档
# ══════════════════════════════════════════════════════════
def build_word(data: dict, pie_path, bar_path, out_path: Path):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0); sec.page_height = Cm(29.7)
    sec.top_margin = Cm(1.0);  sec.bottom_margin = Cm(0.8)
    sec.left_margin = Cm(1.5); sec.right_margin  = Cm(1.5)

    # ── Page 1 ─────────────────────────────────────────
    _add_header(doc, data)
    _add_risk_disclaimer(doc, data)

    # 双栏主内容
    main = _tbl(doc, 1, 2, [7.8, 10.2])
    _build_left_p1(main.rows[0].cells[0], data)
    _build_right_p1(main.rows[0].cells[1], data)

    _add_p1_footnotes(doc, data)

    # ── Page 2 ─────────────────────────────────────────
    doc.add_page_break()
    _add_header(doc, data)

    main2 = _tbl(doc, 1, 2, [7.8, 10.2])
    _build_left_p2(main2.rows[0].cells[0], data)
    _build_right_p2(main2.rows[0].cells[1], data, pie_path, bar_path)

    _add_p2_footer(doc, data)

    doc.save(str(out_path))
    print(f'  ✅ {out_path.name}')


# ══════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════
def process_one(json_path: Path):
    data = json.load(open(json_path, encoding='utf-8'))
    ev_s = data['eval_date'].replace('-', '')
    safe = data['fund_name'].replace('/', '-').replace(' ', '_')

    pie_path = OUTPUT_DIR / f'pie_chart_{ev_s}_{safe}.png'
    bar_path = OUTPUT_DIR / f'bar_chart_{ev_s}_{safe}.png'
    if not pie_path.exists() or not bar_path.exists():
        print(f'  ⚠ 找不到圖表 PNG，部分圖表將顯示提示文字。請執行 create_charts.py')

    out = OUTPUT_DIR / f'MMF_Factsheet_{ev_s}_{safe}.docx'
    build_word(data, pie_path, bar_path, out)


def main():
    ap = argparse.ArgumentParser(description='outputdata.json + 圖表PNG → .docx')
    ap.add_argument('--data', default=None)
    ap.add_argument('--date', default=None)
    ap.add_argument('--all',  action='store_true')
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
        print('✗ 找不到 outputdata 文件'); return

    print(f'[create_word_report] 處理 {len(json_files)} 個文件')
    for jf in json_files:
        print(f'  讀取：{jf.name}')
        process_one(jf)


if __name__ == '__main__':
    main()
