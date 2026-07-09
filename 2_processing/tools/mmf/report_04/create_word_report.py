"""
create_word_report.py — outputdata.json + 圖表PNG → Word Factsheet (.docx)
採用扁平結構（無嵌套表格），確保所有數據100%正確顯示。
用法：python create_word_report.py --all
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date
from pathlib import Path

SQL_MMF    = Path(__file__).parent.parent.parent.parent / "sql" / "mmf"
OUTPUT_DIR = SQL_MMF / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Twips, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
except ImportError:
    print('pip install python-docx'); sys.exit(1)

# ── 色彩常量 ─────────────────────────────────────────────
RED   = RGBColor(191, 0, 8)
BLACK = RGBColor(0, 0, 0)
WHITE = RGBColor(255, 255, 255)
GREY  = RGBColor(100, 100, 100)
CJK   = '微软雅黑'
MONO  = 'Arial'


# ══════════════════════════════════════════════════════════
# 底層工具（不產生副作用、冪等操作）
# ══════════════════════════════════════════════════════════
def _shd(cell, hex6):
    """設定儲存格背景色"""
    tcp = cell._tc.get_or_add_tcPr()
    for old in tcp.findall(qn('w:shd')): tcp.remove(old)
    s = OxmlElement('w:shd')
    s.set(qn('w:val'),'clear'); s.set(qn('w:color'),'auto')
    s.set(qn('w:fill'), hex6); tcp.append(s)

def _pad(cell, t=20, b=20, l=70, r=70):
    """設定儲存格內邊距（twips，20twips=1pt）"""
    tcp = cell._tc.get_or_add_tcPr()
    for old in tcp.findall(qn('w:tcMar')): tcp.remove(old)
    m = OxmlElement('w:tcMar')
    for side, v in [('top',t),('bottom',b),('left',l),('right',r)]:
        e = OxmlElement(f'w:{side}')
        e.set(qn('w:w'), str(v)); e.set(qn('w:type'),'dxa')
        m.append(e)
    tcp.append(m)

def _no_border(cell):
    """移除儲存格邊框"""
    tcp = cell._tc.get_or_add_tcPr()
    for old in tcp.findall(qn('w:tcBorders')): tcp.remove(old)
    b = OxmlElement('w:tcBorders')
    for s in ['top','bottom','left','right','insideH','insideV']:
        e = OxmlElement(f'w:{s}')
        e.set(qn('w:val'),'none'); e.set(qn('w:sz'),'0')
        e.set(qn('w:color'),'auto'); b.append(e)
    tcp.append(b)


def _border(cell, color='BF0008', sz='4'):
    """設定儲存格四周邊框"""
    tcp = cell._tc.get_or_add_tcPr()
    for old in tcp.findall(qn('w:tcBorders')): tcp.remove(old)
    b = OxmlElement('w:tcBorders')
    for s in ['top','bottom','left','right']:
        e = OxmlElement(f'w:{s}')
        e.set(qn('w:val'),'single'); e.set(qn('w:sz'), sz)
        e.set(qn('w:color'), color); b.append(e)
    tcp.append(b)


def _image_box(cell, width_cm, border_color='BF0008', border_sz='4'):
    """建立四周邊框圖片容器，避免圖片排版錯亂"""
    t = _new_tbl(cell, 1, 1, [width_cm], border=False)
    c = t.rows[0].cells[0]
    _border(c, color=border_color, sz=border_sz)
    _pad(c, t=18, b=18, l=18, r=18)
    _clear_cell(c)
    return c


def _anchor_image_run(run):
    """將圖片從 inline 轉為 anchor，使頁面和表格中的圖形顯示更穩定。"""
    inline = run._element.findall('.//' + qn('wp:inline'))
    if not inline:
        return
    inline = inline[0]
    inline.tag = qn('wp:anchor')
    inline.set('distT', '0')
    inline.set('distB', '0')
    inline.set('distL', '114300')
    inline.set('distR', '114300')
    inline.set('simplePos', '0')
    inline.set('relativeHeight', '251658240')
    inline.set('behindDoc', '0')
    inline.set('locked', '0')
    inline.set('layoutInCell', '1')
    inline.set('allowOverlap', '1')

    simple_pos = OxmlElement('wp:simplePos')
    simple_pos.set('x', '0'); simple_pos.set('y', '0')
    pos_h = OxmlElement('wp:positionH')
    pos_h.set('relativeFrom', 'column')
    pos_offset_h = OxmlElement('wp:posOffset')
    pos_offset_h.text = '0'
    pos_h.append(pos_offset_h)
    pos_v = OxmlElement('wp:positionV')
    pos_v.set('relativeFrom', 'paragraph')
    pos_offset_v = OxmlElement('wp:posOffset')
    pos_offset_v.text = '0'
    pos_v.append(pos_offset_v)
    effect = OxmlElement('wp:effectExtent')
    effect.set('l', '0'); effect.set('t', '0'); effect.set('r', '6985'); effect.set('b', '0')
    wrap = OxmlElement('wp:wrapSquare')
    wrap.set('wrapText', 'bothSides')

    inline.insert(0, simple_pos)
    inline.insert(1, pos_h)
    inline.insert(2, pos_v)
    # extent already exists as child 3 now
    # insert effectExtent and wrapSquare after extent
    inline.insert(4, effect)
    inline.insert(5, wrap)


def _row_h(row, pt, rule='exact'):
    """設定精確行高"""
    tr = row._tr; tp = tr.get_or_add_trPr()
    for old in tp.findall(qn('w:trHeight')): tp.remove(old)
    h = OxmlElement('w:trHeight')
    h.set(qn('w:val'), str(int(pt * 20)))
    h.set(qn('w:hRule'), rule)
    tp.append(h)

def _col_w(cell, cm):
    """設定儲存格欄寬"""
    tc = cell._tc; tcp = tc.get_or_add_tcPr()
    for old in tcp.findall(qn('w:tcW')): tcp.remove(old)
    w = OxmlElement('w:tcW')
    w.set(qn('w:w'), str(int(cm * 567))); w.set(qn('w:type'),'dxa')
    tcp.append(w); cell.width = Cm(cm)

def _clear_cell(cell):
    """清空儲存格（保留一個空段落）"""
    tc = cell._tc
    for p in tc.findall(qn('w:p')): tc.remove(p)
    for t in tc.findall(qn('w:tbl')): tc.remove(t)
    tc.append(OxmlElement('w:p'))


# ══════════════════════════════════════════════════════════
# 段落與文字工具
# ══════════════════════════════════════════════════════════
def _p(cell_or_row, sz=7, before=0, after=0, align=WD_ALIGN_PARAGRAPH.LEFT, ls=None):
    """新增格式化段落"""
    p = cell_or_row.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before); pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(ls if ls else sz * 1.35)
    return p

def _r(para, text, fn=CJK, sz=7, bold=False, clr=BLACK):
    """向段落新增文字"""
    if text is None or str(text).strip() == '': return
    r = para.add_run(str(text))
    r.font.name = fn; r.font.size = Pt(sz)
    r.font.bold = bold; r.font.color.rgb = clr
    r._element.rPr.rFonts.set(qn('w:eastAsia'), fn)

def _fmt(v, dec=2):
    if v is None: return '—'
    try: return f'{float(v):.{dec}f}%'
    except: return '—'

def _fmtv(v, dec=2):
    if v is None: return '—'
    try: return f'{float(v):.{dec}f}'
    except: return '—'

def _section_h(cell, text):
    """節標題（紅色 ■ + 粗體）"""
    p = _p(cell, 9, before=4, after=2, ls=12)
    _r(p, '■ ', MONO, 8.5, clr=RED)
    _r(p, text, CJK, 9, bold=True, clr=RED)


# ══════════════════════════════════════════════════════════
# 表格工具（扁平，無嵌套）
# ══════════════════════════════════════════════════════════
def _new_tbl(doc, rows, cols, col_widths_cm, border=False, style='Table Grid'):
    """在 doc 中建立扁平表格"""
    t = doc.add_table(rows=rows, cols=cols)
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    try: t.style = style
    except: pass
    for row in t.rows:
        for i, cell in enumerate(row.cells):
            if i < len(col_widths_cm): _col_w(cell, col_widths_cm[i])
            if not border: _no_border(cell)
            _pad(cell, t=14, b=14, l=60, r=60)
    return t

def _set_cell_text(cell, text, fn=CJK, sz=6.5, bold=False,
                   clr=BLACK, bg=None, align=WD_ALIGN_PARAGRAPH.LEFT,
                   pad_l=50, pad_r=50):
    """設定儲存格文字（清空後重寫）"""
    _clear_cell(cell)
    if bg: _shd(cell, bg)
    _pad(cell, t=12, b=12, l=pad_l, r=pad_r)
    # 直接使用 cell.paragraphs[0]（避免 add_paragraph 重複）
    p = cell.paragraphs[0]
    p.clear()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(0); pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(sz * 1.35)
    if text is not None and str(text).strip():
        r = p.add_run(str(text))
        r.font.name = fn; r.font.size = Pt(sz)
        r.font.bold = bold; r.font.color.rgb = clr
        r._element.rPr.rFonts.set(qn('w:eastAsia'), fn)


# ══════════════════════════════════════════════════════════
# ── 頁首（兩頁共用）
# ══════════════════════════════════════════════════════════
def _add_header(doc, data):
    ev = date.fromisoformat(data['eval_date'])
    fn = data['fund_name']

    # 行1：基金名稱（左）+ 「新資本」徽章（右）
    t = _new_tbl(doc, 2, 2, [13.0, 5.0])
    _clear_cell(t.rows[0].cells[0])
    p = _p(t.rows[0].cells[0], 14, before=0, after=1, ls=18)
    _r(p, fn, CJK, 14, bold=True)
    _clear_cell(t.rows[0].cells[1])
    p2 = _p(t.rows[0].cells[1], 5.5, before=2, ls=7.5, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _r(p2, '「新資本投資者入境計劃」合資格基金', CJK, 5.5, clr=RED)

    # 行2：月報/日期（左）+ AAAmf（右）
    _clear_cell(t.rows[1].cells[0])
    p3 = _p(t.rows[1].cells[0], 8, before=0, after=0, ls=11)
    _r(p3, '基金月報    截至  ', CJK, 8, bold=True)
    _r(p3, f'{ev.year}', MONO, 8, bold=True)
    _r(p3, f'年{ev.month:02d}月{ev.day:02d}日', CJK, 8, bold=True)
    _clear_cell(t.rows[1].cells[1])
    p4 = _p(t.rows[1].cells[1], 7, before=0, ls=9, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _r(p4, 'AAAmf*', MONO, 7, bold=True, clr=RED)

    # 品牌紅橫條
    bar = _new_tbl(doc, 1, 2, [5.5, 12.5])
    _shd(bar.rows[0].cells[0], 'BF0008')
    _shd(bar.rows[0].cells[1], '000000')
    _row_h(bar.rows[0], 5)
    for c in bar.rows[0].cells:
        _clear_cell(c); _pad(c, t=3, b=3, l=20, r=20)


# ══════════════════════════════════════════════════════════
# ── P1 全寬風險說明
# ══════════════════════════════════════════════════════════
def _add_risk_block(doc, data):
    fn  = data['fund_name']
    t   = _new_tbl(doc, 1, 1, [18.0])
    c   = t.rows[0].cells[0]
    _clear_cell(c); _pad(c, t=30, b=20, l=70, r=70)

    p0 = _p(c, 6, before=2, after=1, ls=8)
    _r(p0, '投資涉及風險，包括損失本金。基金單位價格可升亦可跌，基金過往業績並不表示將來的回報。'
       '投資者應在投資於基金前，閱讀有關基金之銷售說明書及產品資料概要，以了解基金詳情及風險因素。'
       '閣下不應僅依賴本資料而作出任何投資決定。投資者須注意：', CJK, 6)

    bullets = [
        f'{fn}尋求實現與通行貨幣市場利率相若的長期回報，主要考慮資本安全及流動性，'
        '將本基金資產淨值的不少於70%投資於由全球政府、準政府、國際組織和金融機構所發行的港幣及美元計價和結算的短期存款和優質貨幣市場工具。',
        '基金是投資基金而非銀行存款。',
        '投資於貨幣市場工具涉及波動性及流動性風險、信貸風險、利率風險、信貸評級風險、估值風險、評級下調風險及主權債務風險。',
        '投資於短期存款面臨提供及作為該等存款交易對手方的金融機構的信貸風險。',
        '本基金可能為對沖目的而購入金融衍生工具，其價格可以十分波動，且涉及對手方風險。',
        '本基金的基金經理或會於任何一個交易日對本基金設置贖回限制。',
        '本基金可能酌情從本基金的資本中支付分派，任何該等分派可導致基金的每單位資產淨值即時減少。',
    ]
    for b in bullets:
        p = _p(c, 6, before=0, after=0, ls=7.8)
        p.paragraph_format.left_indent  = Cm(0.3)
        p.paragraph_format.first_line_indent = Cm(-0.3)
        _r(p, '• ', MONO, 6); _r(p, b, CJK, 6)


# ══════════════════════════════════════════════════════════
# ── P1 主體（扁平雙欄：用多列大表格）
# ══════════════════════════════════════════════════════════
def _add_p1_main(doc, data):
    """
    P1 主體：用一個 2欄大表格實現雙欄佈局
    左欄(7.8cm)包含所有基金資料內容
    右欄(10.2cm)包含所有業績表格
    ── 關鍵：在大表格的單個儲存格中直接用段落格式模擬表格行
    """
    ccy = data['base_currency']
    ev  = date.fromisoformat(data['eval_date'])
    cls = data.get('nav_classes', [])
    perf = data.get('performance', {})
    ann  = data.get('annual_performance', [])

    # ── 大表（1行2欄）────────────────────────────────────
    main = _new_tbl(doc, 1, 2, [7.8, 10.2])
    lc = main.rows[0].cells[0]   # 左欄
    rc = main.rows[0].cells[1]   # 右欄
    _pad(lc, t=15, b=15, l=55, r=35)
    _pad(rc, t=15, b=15, l=35, r=35)
    _clear_cell(lc); _clear_cell(rc)

    # ══ 左欄內容 ══════════════════════════════════════════

    # 投資目標
    _section_h(lc, '投資目標')
    p = lc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0); pf.space_after = Pt(4)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY; pf.line_spacing = Pt(8.5)
    _r(p, data.get('investment_objective',
        f'本基金旨在提供與通行貨幣市場利率相若的回報，以資本安全及流動性為首要考慮，'
        f'將本基金資產淨值的不少於70%投資於以{ccy}計價的短期存款及高質量貨幣市場工具。'), CJK, 6.5)

    # 基金資料（Key-Value 格式段落模擬表格）
    _section_h(lc, '基金資料')
    fi_rows = [
        ('法律結構', '香港傘子式單位信託基金'),
        ('投資經理', data.get('investment_manager','博匯投資管理有限公司')),
        ('受託人',   data.get('trustee','博匯保誠信託有限公司')),
        ('託管人',   data.get('custodian','中國銀行（香港）有限公司')),
        ('基礎貨幣', ccy),
        ('基金規模', f'{ccy} {data.get("nav_millions",0):,.2f} 百萬'),
        ('非基礎貨幣股份類別', '美元'),
        ('交易頻率', '每日'),
    ]
    # 用嵌入式表格格式：在左欄 cell 內新增一個小表格
    fi_tbl = lc.add_table(rows=len(fi_rows), cols=2)
    fi_tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    try: fi_tbl.style = 'Table Grid'
    except: pass
    for i, (k, v) in enumerate(fi_rows):
        row = fi_tbl.rows[i]; bg = 'FFFFFF' if i%2==0 else 'F5F5F5'
        _row_h(row, 9)
        for j, cell in enumerate(row.cells):
            _no_border(cell); _shd(cell, bg)
            _pad(cell, t=10, b=10, l=50, r=20)
            _col_w(cell, 3.0 if j==0 else 4.6)
        _set_cell_text(row.cells[0], k, sz=6.5, clr=GREY, bg='FFFFFF' if i%2==0 else 'F5F5F5')
        _set_cell_text(row.cells[1], v, sz=6.5, bg='FFFFFF' if i%2==0 else 'F5F5F5')

    # 基金單位類別
    p_gap = lc.add_paragraph()
    p_gap.paragraph_format.space_before = Pt(2); p_gap.paragraph_format.space_after = Pt(1)
    p_gap.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p_gap.paragraph_format.line_spacing = Pt(3)
    _section_h(lc, '基金單位類別')

    cls_hdrs = ['類別', '發行日期', '每股資產淨值', '彭博編碼', 'ISIN編碼']
    cls_ws   = [2.2, 1.4, 1.7, 1.2, 1.2]
    cls_tbl  = lc.add_table(rows=5, cols=5)
    cls_tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    try: cls_tbl.style = 'Table Grid'
    except: pass
    _row_h(cls_tbl.rows[0], 9)
    for j, (h, w) in enumerate(zip(cls_hdrs, cls_ws)):
        c = cls_tbl.rows[0].cells[j]
        _col_w(c, w); _no_border(c); _shd(c, 'D0D0D0')
        _pad(c, t=10, b=10, l=40, r=20)
        _set_cell_text(c, h, sz=6, bold=True, clr=BLACK, bg='D0D0D0')
    for i in range(1, 5):
        row = cls_tbl.rows[i]; idx = i-1; bg = 'FFFFFF' if i%2==1 else 'F5F5F5'
        _row_h(row, 9)
        for j, w in enumerate(cls_ws):
            _col_w(row.cells[j], w); _no_border(row.cells[j])
        if idx < len(cls):
            c2 = cls[idx]
            vals = [f"{c2.get('class_id','—')} 類", str(c2.get('issue_date','—')),
                    f"{ccy} {_fmtv(c2.get('nav_per_unit'),4)}", '—', '—']
        else:
            vals = ['—','—','—','—','—']
        for j, v in enumerate(vals):
            _set_cell_text(row.cells[j], v, fn=CJK if j==0 else MONO, sz=6, bg=bg)

    # 數據來源
    ps = lc.add_paragraph()
    ps.paragraph_format.space_before = Pt(2); ps.paragraph_format.space_after = Pt(2)
    ps.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    ps.paragraph_format.line_spacing = Pt(7.5)
    _r(ps, f'數據來源：彭博  截至 {ev.year}年{ev.month:02d}月{ev.day:02d}日，除非另有說明。', CJK, 5.5, clr=GREY)

    # 費用表
    fee_defaults = [
        ('I',  '無',     '0.05%', f'{ccy} 1,000,000'),
        ('A',  '最高 5%', '0.15%', f'{ccy} 1,000'),
        ('F',  '最高 5%', '0.60%', '無'),
        ('B',  '最高 5%', '0.30%', f'{ccy} 10,000'),
    ]
    fee_hdrs = ['類別', '認購費', '投資管理費', '最低認購額']
    fee_ws   = [2.2, 1.3, 1.7, 2.5]
    fee_tbl  = lc.add_table(rows=5, cols=4)
    fee_tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    try: fee_tbl.style = 'Table Grid'
    except: pass
    _row_h(fee_tbl.rows[0], 9)
    for j, (h, w) in enumerate(zip(fee_hdrs, fee_ws)):
        c = fee_tbl.rows[0].cells[j]
        _col_w(c, w); _no_border(c)
        _set_cell_text(c, h, sz=6, bold=True, clr=BLACK, bg='D0D0D0')
    for i, (cls_id, sub, mgmt, mini) in enumerate(fee_defaults):
        row = fee_tbl.rows[i+1]; bg = 'FFFFFF' if i%2==0 else 'F5F5F5'
        _row_h(row, 9)
        for j, w in enumerate(fee_ws):
            _col_w(row.cells[j], w); _no_border(row.cells[j])
        actual_cls = cls[i]['class_id'] if i < len(cls) else cls_id
        vals = [f'{actual_cls} 類', sub, mgmt, mini]
        for j, v in enumerate(vals):
            _set_cell_text(row.cells[j], v, fn=CJK if j==0 else MONO, sz=6, bg=bg)

    # ══ 右欄內容 ══════════════════════════════════════════

    ph = rc.add_paragraph()
    ph.paragraph_format.space_before = Pt(0); ph.paragraph_format.space_after = Pt(2)
    ph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    ph.paragraph_format.line_spacing = Pt(12)
    _r(ph, '基金表現', CJK, 9.5, bold=True, clr=RED)
    _r(ph, ' ²', MONO, 7, clr=RED)

    # 累積業績
    pc = rc.add_paragraph()
    pc.paragraph_format.space_before = Pt(2); pc.paragraph_format.space_after = Pt(1)
    pc.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pc.paragraph_format.line_spacing = Pt(11)
    _r(pc, '累積表現 (%)', CJK, 8.5, bold=True, clr=RED)
    _r(pc, '  ²', MONO, 6.5, clr=RED)

    c_hdrs = ['類別', '一個月', '三個月', '六個月', '一年', '自成立起', '年化\n(自成立)', '7日年化⁴']
    c_ws   = [2.9, 0.9, 0.9, 0.9, 0.9, 0.9, 1.1, 0.9]
    perf_keys = ['ret_1m','ret_3m','ret_6m','ret_1y',
                 'ret_since_inception','ret_ann_since_inception','ret_7d_ann']
    ct = rc.add_table(rows=5, cols=8)
    ct.alignment = WD_TABLE_ALIGNMENT.LEFT
    try: ct.style = 'Table Grid'
    except: pass
    _row_h(ct.rows[0], 11)
    for j, (h, w) in enumerate(zip(c_hdrs, c_ws)):
        c = ct.rows[0].cells[j]; _col_w(c, w); _no_border(c)
        _set_cell_text(c, h, sz=6, bold=True, clr=WHITE, bg='BF0008',
                       align=WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT)
    for i in range(1, 5):
        row = ct.rows[i]; idx = i-1; bg = 'FFFFFF' if i%2==1 else 'F5F5F5'
        _row_h(row, 9)
        for j, w in enumerate(c_ws): _col_w(row.cells[j], w); _no_border(row.cells[j])
        cls_lbl = f"{cls[idx]['class_id']} 類" if idx < len(cls) else '—'
        vals = [cls_lbl] + [_fmt(perf.get(k)) if i==1 else '—' for k in perf_keys]
        for j, v in enumerate(vals):
            _set_cell_text(row.cells[j], v,
                           fn=CJK if j==0 else MONO, sz=6.5, bg=bg,
                           align=WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT)

    # 年度業績
    pa = rc.add_paragraph()
    pa.paragraph_format.space_before = Pt(5); pa.paragraph_format.space_after = Pt(1)
    pa.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pa.paragraph_format.line_spacing = Pt(11)
    _r(pa, '年度表現 (%)', CJK, 8.5, bold=True, clr=RED)
    _r(pa, '  ²', MONO, 6.5, clr=RED)

    ann_map  = {a['year']: a['return_pct'] for a in ann}
    a_years  = ['2021','2022','2023','2024','2025','本年至今']
    a_ws     = [2.9, 0.9, 0.9, 0.9, 0.9, 0.9, 1.1]
    at = rc.add_table(rows=5, cols=7)
    at.alignment = WD_TABLE_ALIGNMENT.LEFT
    try: at.style = 'Table Grid'
    except: pass
    _row_h(at.rows[0], 11)
    a_hdrs = ['類別'] + a_years
    for j, (h, w) in enumerate(zip(a_hdrs, a_ws)):
        c = at.rows[0].cells[j]; _col_w(c, w); _no_border(c)
        _set_cell_text(c, h, fn=CJK if j==0 else MONO, sz=6, bold=True,
                       clr=WHITE, bg='BF0008',
                       align=WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT)
    for i in range(1, 5):
        row = at.rows[i]; idx = i-1; bg = 'FFFFFF' if i%2==1 else 'F5F5F5'
        _row_h(row, 9)
        for j, w in enumerate(a_ws): _col_w(row.cells[j], w); _no_border(row.cells[j])
        cls_lbl = f"{cls[idx]['class_id']} 類" if idx < len(cls) else '—'
        vals = [cls_lbl] + [_fmt(ann_map.get(y)) if i==1 else '—' for y in a_years]
        for j, v in enumerate(vals):
            _set_cell_text(row.cells[j], v,
                           fn=CJK if j==0 else MONO, sz=6.5, bg=bg,
                           align=WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT)


# ══════════════════════════════════════════════════════════
# ── P1 全寬腳注
# ══════════════════════════════════════════════════════════
def _add_p1_footnotes(doc, data):
    ev = date.fromisoformat(data['eval_date'])
    t  = _new_tbl(doc, 1, 1, [18.0])
    c  = t.rows[0].cells[0]
    _clear_cell(c); _pad(c, t=25, b=15, l=70, r=70)

    for txt in [
        '* 相關評級機構已授予本基金貨幣市場基金評級。',
        '¹ 關於基金詳情（包括費用）請參考基金說明書。',
        '² 過往表現並不代表未來業績。業績以資產淨值對資產淨值計算，並已計入股息再投資（如屬派息類別，則不計入股息再投資）。',
        '³ 自各類別成立日期起計算，成立日期請參考本文「基金單位類別」部分。',
        '⁴ 根據七天（七個日曆天）的週期進行年化計算。此數據是根據基金過去七天的表現假設計算，並不代表實際一年的回報。',
        f'除非另有說明，資料來源均來自本公司及彭博。截至 {ev.year}年{ev.month:02d}月{ev.day:02d}日。',
    ]:
        p = c.add_paragraph()
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(0.8)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p.paragraph_format.line_spacing = Pt(7.5)
        _r(p, txt, CJK, 5.8, clr=GREY)

    disc = c.add_paragraph()
    disc.paragraph_format.space_before = Pt(4); disc.paragraph_format.space_after = Pt(0)
    disc.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    disc.paragraph_format.line_spacing = Pt(7.5)
    _r(disc, '投資涉及風險，包括損失本金。基金單位價格可升亦可跌，過往業績並不代表未來回報。'
       '本基金是投資基金而非銀行存款。本資料之發行人為本公司管理人。此資料並未獲香港證監會所審閱。',
       CJK, 5.8, clr=GREY)


# ══════════════════════════════════════════════════════════
# ── P2 主體（投資組合特點 + 圖表）
# ══════════════════════════════════════════════════════════
def _add_p2_main(doc, data, pie_path, bar_path):
    wam = data.get('wam_days', 0)
    ytm = data.get('ytm_pct',  0)

    main2 = _new_tbl(doc, 1, 2, [7.8, 10.2])
    lc    = main2.rows[0].cells[0]
    rc    = main2.rows[0].cells[1]
    _pad(lc, t=15, b=15, l=55, r=35); _pad(rc, t=15, b=15, l=35, r=35)
    _clear_cell(lc); _clear_cell(rc)

    # ── 左欄：投資組合特點 ──────────────────────────────
    _section_h(lc, '投資組合特點')

    p1 = lc.add_paragraph()
    p1.paragraph_format.space_before = Pt(10); p1.paragraph_format.space_after = Pt(2)
    p1.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p1.paragraph_format.line_spacing = Pt(9.5)
    _r(p1, '加權平均到期日', CJK, 8)

    p2 = lc.add_paragraph()
    p2.paragraph_format.space_before = Pt(2); p2.paragraph_format.space_after = Pt(12)
    p2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p2.paragraph_format.line_spacing = Pt(26)
    _r(p2, f'{_fmtv(wam, 2)}', MONO, 22, bold=True, clr=RED)
    _r(p2, '  天', CJK, 12)

    p3 = lc.add_paragraph()
    p3.paragraph_format.space_before = Pt(5); p3.paragraph_format.space_after = Pt(2)
    p3.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p3.paragraph_format.line_spacing = Pt(9.5)
    _r(p3, '加權平均到期收益率', CJK, 8)
    _r(p3, ' ¹', MONO, 6.5)

    p4 = lc.add_paragraph()
    p4.paragraph_format.space_before = Pt(2); p4.paragraph_format.space_after = Pt(5)
    p4.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p4.paragraph_format.line_spacing = Pt(26)
    _r(p4, f'{_fmtv(ytm, 2)}%', MONO, 22, bold=True, clr=RED)

    # ── 右欄：圖表 ──────────────────────────────────────
    # 資產類別分佈標題
    pt1 = rc.add_paragraph()
    pt1.paragraph_format.space_before = Pt(0); pt1.paragraph_format.space_after = Pt(2)
    pt1.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pt1.paragraph_format.line_spacing = Pt(11)
    _r(pt1, '資產類別分佈 (%)', CJK, 8.5, bold=True, clr=RED)

    # 嵌入餅圖
    if pie_path and Path(pie_path).exists():
        img_cell = _image_box(rc, 10.0)
        p_pie = img_cell.add_paragraph()
        p_pie.paragraph_format.space_before = Pt(0); p_pie.paragraph_format.space_after = Pt(0)
        p_pie.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p_pie.paragraph_format.line_spacing = Pt(1)
        p_pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_pie = p_pie.add_run()
        run_pie.add_picture(str(pie_path), width=Cm(9.4))
        _anchor_image_run(run_pie)
    else:
        p_na = rc.add_paragraph(); p_na.paragraph_format.space_after = Pt(5)
        _r(p_na, '（請先執行 create_charts.py）', CJK, 7, clr=GREY)

    # 到期日分佈標題
    pt2 = rc.add_paragraph()
    pt2.paragraph_format.space_before = Pt(4); pt2.paragraph_format.space_after = Pt(2)
    pt2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pt2.paragraph_format.line_spacing = Pt(11)
    _r(pt2, '到期日分佈 (%)', CJK, 8.5, bold=True, clr=RED)

    # 嵌入柱狀圖
    if bar_path and Path(bar_path).exists():
        img_cell = _image_box(rc, 10.0)
        p_bar = img_cell.add_paragraph()
        p_bar.paragraph_format.space_before = Pt(0); p_bar.paragraph_format.space_after = Pt(0)
        p_bar.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p_bar.paragraph_format.line_spacing = Pt(1)
        p_bar.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_bar = p_bar.add_run()
        run_bar.add_picture(str(bar_path), width=Cm(9.4))
        _anchor_image_run(run_bar)
    else:
        p_na2 = rc.add_paragraph(); p_na2.paragraph_format.space_after = Pt(0)
        _r(p_na2, '（請先執行 create_charts.py）', CJK, 7, clr=GREY)


# ══════════════════════════════════════════════════════════
# ── P2 底部免責聲明
# ══════════════════════════════════════════════════════════
def _add_p2_footer(doc, data):
    ev = date.fromisoformat(data['eval_date'])
    t  = _new_tbl(doc, 1, 1, [18.0])
    c  = t.rows[0].cells[0]
    _clear_cell(c); _pad(c, t=25, b=15, l=70, r=70)

    for txt in [
        '¹ 使用基金中每個持倉的加權平均到期收益率計算。',
        f'數據來源：除非另有說明，資料來源均來自本公司。截至 {ev.year}年{ev.month:02d}月{ev.day:02d}日。',
    ]:
        p = c.add_paragraph()
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p.paragraph_format.line_spacing = Pt(7.5)
        _r(p, txt, CJK, 5.8, clr=GREY)

    disc = c.add_paragraph()
    disc.paragraph_format.space_before = Pt(5); disc.paragraph_format.space_after = Pt(5)
    disc.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    disc.paragraph_format.line_spacing = Pt(7.5)
    _r(disc, '重要聲明：投資涉及風險。基金股價可升亦可跌，過往業績並不表示將來基金回報，未來回報不能被保證。'
       '閣下亦可能損失所投資之本金。本資料並不構成對於任何證券或基金的買賣或進行任何交易之邀約或任何投資建議。'
       '本文件只供閣下參考之用。本資料之發行人為本公司。此資料並未獲香港證監會所審閱。', CJK, 5.8, clr=GREY)

    cont = c.add_paragraph()
    cont.paragraph_format.space_before = Pt(6); cont.paragraph_format.space_after = Pt(0)
    cont.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    cont.paragraph_format.line_spacing = Pt(11)
    _r(cont, f"服務熱線：{data.get('contact_phone','(852) XXXX XXXX')}    "
             f"網站：{data.get('contact_web','www.example.com.hk')}    "
             f"電郵：{data.get('contact_email','fund@example.com.hk')}", CJK, 8)


# ══════════════════════════════════════════════════════════
# 主函數：組裝 2 頁 Word 文件
# ══════════════════════════════════════════════════════════
def build_word(data, pie_path, bar_path, out_path: Path):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width   = Cm(21.0); sec.page_height  = Cm(29.7)
    sec.top_margin   = Cm(1.0);  sec.bottom_margin = Cm(0.8)
    sec.left_margin  = Cm(1.5);  sec.right_margin  = Cm(1.5)

    # Page 1
    _add_header(doc, data)
    _add_risk_block(doc, data)
    _add_p1_main(doc, data)
    _add_p1_footnotes(doc, data)

    # Page 2
    doc.add_page_break()
    _add_header(doc, data)
    _add_p2_main(doc, data, pie_path, bar_path)
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
        print('  ⚠ 圖表 PNG 不存在，請先執行 create_charts.py')

    out = OUTPUT_DIR / f'MMF_Factsheet_{ev_s}_{safe}.docx'
    build_word(data, pie_path, bar_path, out)


PORT_ID_MAP = {
    "BHMMF001": "博匯港元貨幣市場基金I",
    "BHMMF002": "博匯港元貨幣市場基金II",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data',    default=None, help='指定單個 outputdata.json 文件路徑')
    ap.add_argument('--date',    default=None, help='按日期過濾（YYYY-MM-DD）')
    ap.add_argument('--all',     action='store_true')
    ap.add_argument('--port-id', default=None, dest='port_id',
                    help='僅處理指定基金（如 BHMMF001），精確匹配，避免 I/II 混淆')
    args = ap.parse_args()

    if args.data:
        json_files = [Path(args.data)]
    else:
        pat = f'outputdata_{args.date.replace("-","")}_*.json' if args.date else 'outputdata_*.json'
        all_files = sorted(OUTPUT_DIR.glob(pat))
        if args.port_id:
            fund_name = PORT_ID_MAP.get(args.port_id, "")
            # 精確匹配：文件名必須包含完整基金名，且下一字符不是中文字（避免 I 命中 II）
            json_files = [
                f for f in all_files
                if fund_name and (
                    f.stem.endswith(fund_name) or
                    f'_{fund_name}_' in f.stem or
                    f.stem.endswith(fund_name.replace(' ', '_'))
                )
            ]
        elif args.all or args.date:
            json_files = all_files
        else:
            json_files = [all_files[-1]] if all_files else []

    if not json_files:
        print('✗ 找不到 outputdata 文件')
        return
    print(f'[create_word_report] 處理 {len(json_files)} 個文件')
    for jf in json_files:
        print(f'  讀取：{jf.name}')
        process_one(jf)


if __name__ == '__main__':
    main()
