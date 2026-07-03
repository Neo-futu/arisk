"""
create_word_template.py — 生成 Word 模版 Template_Factsheet.docx（2頁，仿 PDF 精確佈局）

正確頁面結構（源自參考 PDF 分析）：
  P1: 頁首 → 紅條 → [全寬風險說明] → [雙欄：左=基金資料|右=業績表] → [全寬腳注]
  P2: 頁首 → 紅條 → [雙欄：左=組合特點|右=圖表] → [全寬免責聲明+聯絡]
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE_DIR = Path(__file__).parent
OUT_PATH = BASE_DIR / 'Template_Factsheet.docx'

# 品牌紅
RED   = RGBColor(191, 0, 8)
BLACK = RGBColor(0, 0, 0)
WHITE = RGBColor(255, 255, 255)
DGREY = RGBColor(80, 80, 80)
LGREY = RGBColor(245, 245, 245)

CJK   = '微软雅黑'
ARIAL = 'Arial'

# ══════════════════════════════════════════════════════════
# 底層 XML 工具
# ══════════════════════════════════════════════════════════
def _shd(cell, hex_color):
    tcp = cell._tc.get_or_add_tcPr()
    s = OxmlElement('w:shd')
    s.set(qn('w:val'), 'clear'); s.set(qn('w:color'), 'auto')
    s.set(qn('w:fill'), hex_color); tcp.append(s)

def _cell_margins(cell, top=20, bottom=20, left=60, right=60):
    """設定儲存格內邊距（twips，1pt=20twips）"""
    tcp = cell._tc.get_or_add_tcPr()
    m = OxmlElement('w:tcMar')
    for side, val in [('top',top),('bottom',bottom),('left',left),('right',right)]:
        e = OxmlElement(f'w:{side}')
        e.set(qn('w:w'), str(val)); e.set(qn('w:type'), 'dxa')
        m.append(e)
    tcp.append(m)

def _no_border(cell):
    tcp = cell._tc.get_or_add_tcPr()
    b = OxmlElement('w:tcBorders')
    for side in ['top','bottom','left','right','insideH','insideV']:
        e = OxmlElement(f'w:{side}')
        e.set(qn('w:val'),'none'); e.set(qn('w:sz'),'0')
        e.set(qn('w:color'),'FFFFFF'); b.append(e)
    tcp.append(b)

def _border(cell, sides=None, color='BF0008', sz='4'):
    tcp = cell._tc.get_or_add_tcPr()
    b = OxmlElement('w:tcBorders')
    for side in (sides or ['top','bottom','left','right']):
        e = OxmlElement(f'w:{side}')
        e.set(qn('w:val'),'single'); e.set(qn('w:sz'),sz)
        e.set(qn('w:color'),color); b.append(e)
    tcp.append(b)

def _row_exact_height(row, height_pt):
    tr = row._tr; tp = tr.get_or_add_trPr()
    h = OxmlElement('w:trHeight')
    h.set(qn('w:val'), str(int(height_pt * 20)))
    h.set(qn('w:hRule'), 'exact'); tp.append(h)

def _set_col_width(cell, cm):
    tc = cell._tc; tcp = tc.get_or_add_tcPr()
    tcw = OxmlElement('w:tcW')
    tcw.set(qn('w:w'), str(int(cm * 567))); tcw.set(qn('w:type'), 'dxa')
    tcp.append(tcw)
    cell.width = Cm(cm)

# ══════════════════════════════════════════════════════════
# 段落工具
# ══════════════════════════════════════════════════════════
def _clear(cell):
    for p in cell.paragraphs: p.clear()

def _p(cell, text='', fn=CJK, sz=6.5, bold=False, clr=BLACK,
       align=WD_ALIGN_PARAGRAPH.LEFT, before=0, after=0, line_spacing_pt=None):
    """在 cell 中新增段落"""
    p = cell.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before); pf.space_after = Pt(after)
    if line_spacing_pt:
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(line_spacing_pt)
    else:
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(sz * 1.35)
    if text:
        r = p.add_run(text)
        r.font.name = fn; r.font.size = Pt(sz)
        r.font.bold = bold; r.font.color.rgb = clr
        r._element.rPr.rFonts.set(qn('w:eastAsia'), fn)
    return p

def _run(para, text, fn=CJK, sz=6.5, bold=False, clr=BLACK):
    r = para.add_run(text)
    r.font.name = fn; r.font.size = Pt(sz)
    r.font.bold = bold; r.font.color.rgb = clr
    r._element.rPr.rFonts.set(qn('w:eastAsia'), fn)
    return r

# ══════════════════════════════════════════════════════════
# 表格工具
# ══════════════════════════════════════════════════════════
def _table(doc_or_cell, rows, cols, col_widths_cm, no_border=True):
    """在 doc 或 cell 中建立緊湊表格"""
    if hasattr(doc_or_cell, 'add_table'):
        tbl = doc_or_cell.add_table(rows=rows, cols=cols)
    else:
        tbl = doc_or_cell.add_table(rows=rows, cols=cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    # 移除表格自帶邊框
    tbl.style = 'Table Grid'
    for row in tbl.rows:
        for i, (cell, w) in enumerate(zip(row.cells, col_widths_cm)):
            _set_col_width(cell, w)
            if no_border: _no_border(cell)
            _cell_margins(cell, top=15, bottom=15, left=50, right=50)
    return tbl


def _image_box(cell, width_cm, border_color='BF0008', border_sz='6'):
    """建立四周邊框的圖片容器"""
    tbl = _table(cell, 1, 1, [width_cm], no_border=True)
    c = tbl.rows[0].cells[0]
    _border(c, color=border_color, sz=border_sz)
    _cell_margins(c, top=80, bottom=80, left=80, right=80)
    _clear(c)
    return c


def _section_head(cell, text):
    """節標題（■ 紅色文字）"""
    p = cell.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(3); pf.space_after = Pt(1.5)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY; pf.line_spacing = Pt(11)
    r1 = p.add_run('■ ')
    r1.font.name = ARIAL; r1.font.size = Pt(8); r1.font.color.rgb = RED
    r2 = p.add_run(text)
    r2.font.name = CJK; r2.font.size = Pt(9)
    r2.font.bold = True; r2.font.color.rgb = RED
    r2._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)

# ══════════════════════════════════════════════════════════
# P1 頁首（共用）
# ══════════════════════════════════════════════════════════
def _add_header(doc):
    """頁首：基金名稱/日期 + 品牌紅橫條"""
    # 行1：基金名稱（左）+ 新資本計劃（右）
    h = _table(doc, 2, 2, [13.5, 4.5], no_border=True)
    r0 = h.rows[0]
    _clear(r0.cells[0])
    p = r0.cells[0].add_paragraph()
    p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p.paragraph_format.line_spacing = Pt(17)
    _run(p, '{{fund_name}}', CJK, 14, bold=True)
    _clear(r0.cells[1])
    p2 = r0.cells[1].add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p2.paragraph_format.space_before = Pt(2)
    p2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p2.paragraph_format.line_spacing = Pt(8)
    _run(p2, '「新資本投資者入境計劃」合資格基金', CJK, 5.5, clr=RED)

    # 行2：月報/日期（左）+ AAAmf（右）
    r1 = h.rows[1]
    _clear(r1.cells[0])
    p3 = r1.cells[0].add_paragraph()
    p3.paragraph_format.space_before = Pt(0); p3.paragraph_format.space_after = Pt(0)
    p3.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p3.paragraph_format.line_spacing = Pt(10.5)
    _run(p3, '基金月報    截至  ', CJK, 8, bold=True)
    _run(p3, '{{eval_year}}', ARIAL, 8, bold=True)
    _run(p3, '年', CJK, 8, bold=True)
    _run(p3, '{{eval_month}}', ARIAL, 8, bold=True)
    _run(p3, '月', CJK, 8, bold=True)
    _run(p3, '{{eval_day}}', ARIAL, 8, bold=True)
    _run(p3, '日', CJK, 8, bold=True)
    _clear(r1.cells[1])
    p4 = r1.cells[1].add_paragraph()
    p4.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(p4, 'AAAmf*  ', ARIAL, 7, bold=True, clr=RED)

    # 品牌紅橫條
    bar = _table(doc, 1, 1, [18.0], no_border=True)
    _shd(bar.rows[0].cells[0], 'BF0008')
    _row_exact_height(bar.rows[0], 6)
    _clear(bar.rows[0].cells[0])
    p5 = bar.rows[0].cells[0].add_paragraph()
    p5.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p5.paragraph_format.line_spacing = Pt(6)

    return h, bar

# ══════════════════════════════════════════════════════════
# P1 全寬風險說明區
# ══════════════════════════════════════════════════════════
def _add_disclaimer_block(doc):
    """全寬風險說明（源自 PDF y=79-211，佔約 3.5cm）"""
    tbl = _table(doc, 1, 1, [18.0], no_border=True)
    c = tbl.rows[0].cells[0]
    _cell_margins(c, top=30, bottom=20, left=60, right=60)
    _clear(c)

    intro = c.add_paragraph()
    intro.paragraph_format.space_before = Pt(2); intro.paragraph_format.space_after = Pt(1)
    intro.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    intro.paragraph_format.line_spacing = Pt(8)
    _run(intro, '投資涉及風險，包括損失本金。基金單位價格可升亦可跌，基金過往業績並不表示將來的回報。'
         '基金的價值可能會非常波動，並可能於短時間內大幅下跌。投資者應在投資於基金前，'
         '閱讀有關基金之銷售說明書及產品資料概要，以了解基金詳情及風險因素。'
         '閣下不應僅依賴本資料而作出任何投資決定。投資者須注意：', CJK, 6)

    bullets = [
        '{{fund_name}}（「本基金」）尋求實現與通行貨幣市場利率相若的長期回報，主要考慮資本安全及流動性，'
        '將本基金資產淨值的不少於70%投資於由全球政府、準政府、國際組織和金融機構所發行的港幣及美元計價和結算的短期存款和優質貨幣市場工具。',
        '基金是投資基金而非銀行存款。',
        '投資於貨幣市場工具涉及波動性及流動性風險、信貸風險、利率風險、信貸評級風險、估值風險、評級下調風險及主權債務風險。',
        '投資於短期存款面臨提供及作為該等存款交易對手方的金融機構的信貸風險。',
        '本基金可能為對沖目的而購入金融衍生工具。衍生工具的價格可以十分波動，且涉及對手方風險。',
        '本基金的基金經理或會於任何一個交易日對本基金設置贖回限制。',
        '本基金可能酌情從本基金的資本中支付分派。任何該等分派可導致基金的每單位資產淨值即時減少。',
    ]
    for b in bullets:
        p = c.add_paragraph()
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p.paragraph_format.line_spacing = Pt(7.8)
        p.paragraph_format.left_indent = Cm(0.3)
        p.paragraph_format.first_line_indent = Cm(-0.3)
        _run(p, '• ', ARIAL, 6, clr=BLACK)
        _run(p, b, CJK, 6)

# ══════════════════════════════════════════════════════════
# P1 左欄內容
# ══════════════════════════════════════════════════════════
def _build_left_p1(cell):
    """投資目標 + 基金資料表 + NAV類別表 + 費用表"""
    _clear(cell)

    # 投資目標
    _section_head(cell, '投資目標')
    p = cell.add_paragraph()
    p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p.paragraph_format.line_spacing = Pt(8)
    _run(p, '{{investment_objective}}', CJK, 6)

    # 基金資料
    _section_head(cell, '基金資料')
    # 用小表格模擬鍵值對
    fi_rows = [
        ('法律結構', '{{legal_structure}}'),
        ('投資經理', '{{investment_manager}}'),
        ('受託人',   '{{trustee}}'),
        ('託管人',   '{{custodian}}'),
        ('基礎貨幣', '{{base_currency}}'),
        ('基金規模', '{{base_currency}} {{nav_millions}} 百萬'),
        ('非基礎貨幣股份類別', '{{non_base_currency}}'),
        ('交易頻率', '{{trading_freq}}'),
    ]
    fi = _table(cell, len(fi_rows), 2, [3.0, 4.7])
    for i, (k, v) in enumerate(fi_rows):
        r = fi.rows[i]
        bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
        _shd(r.cells[0], bg); _shd(r.cells[1], bg)
        _cell_margins(r.cells[0], top=12, bottom=12, left=50, right=30)
        _cell_margins(r.cells[1], top=12, bottom=12, left=30, right=50)
        _row_exact_height(r, 9)
        _clear(r.cells[0])
        pk = r.cells[0].add_paragraph()
        pk.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pk.paragraph_format.line_spacing = Pt(7.5)
        _run(pk, k, CJK, 6, clr=DGREY)
        _clear(r.cells[1])
        pv = r.cells[1].add_paragraph()
        pv.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pv.paragraph_format.line_spacing = Pt(7.5)
        _run(pv, v, CJK, 6)

    # 基金單位類別
    cell.add_paragraph().paragraph_format.space_after = Pt(2)
    _section_head(cell, '基金單位類別')
    hdrs = ['類別', '發行日期', '每股資產淨值', '彭博編碼', 'ISIN編碼']
    ws   = [2.3, 1.5, 1.8, 1.5, 1.6]
    cls_t = _table(cell, 5, 5, ws)
    for j, (h, w) in enumerate(zip(hdrs, ws)):
        c2 = cls_t.rows[0].cells[j]
        _shd(c2, 'D9D9D9'); _cell_margins(c2, top=10, bottom=10, left=40, right=20)
        _row_exact_height(cls_t.rows[0], 8.5)
        _clear(c2)
        ph = c2.add_paragraph()
        ph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        ph.paragraph_format.line_spacing = Pt(7)
        _run(ph, h, CJK, 6, bold=True)
    for i in range(1, 5):
        idx = i - 1
        bg = 'FFFFFF' if i % 2 == 1 else 'F5F5F5'
        vals = [f'{{{{nav_cls_{idx}_id}}}} 類',
                f'{{{{nav_cls_{idx}_date}}}}',
                f'{{{{base_currency}}}} {{{{nav_cls_{idx}_nav}}}}',
                f'{{{{nav_cls_{idx}_bb}}}}',
                f'{{{{nav_cls_{idx}_isin}}}}']
        row = cls_t.rows[i]; _row_exact_height(row, 8.5)
        for j, v in enumerate(vals):
            _shd(row.cells[j], bg)
            _cell_margins(row.cells[j], top=10, bottom=10, left=40, right=20)
            _clear(row.cells[j])
            pv = row.cells[j].add_paragraph()
            pv.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pv.paragraph_format.line_spacing = Pt(7)
            _run(pv, v, CJK if j == 0 else ARIAL, 6)

    # 數據來源
    ps = cell.add_paragraph()
    ps.paragraph_format.space_before = Pt(1.5); ps.paragraph_format.space_after = Pt(2)
    ps.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    ps.paragraph_format.line_spacing = Pt(7.5)
    _run(ps, '數據來源：彭博  截至 {{eval_year}}年{{eval_month}}月{{eval_day}}日，除非另有說明。',
         CJK, 5.5, clr=DGREY)

    # 費用表（無節標題，直接跟 NAV 表）
    fee_hdrs = ['類別', '認購費', '投資管理費', '最低認購額']
    fee_ws   = [2.3, 1.5, 1.8, 3.1]
    fee_t = _table(cell, 5, 4, fee_ws)
    for j, (h, w) in enumerate(zip(fee_hdrs, fee_ws)):
        c3 = fee_t.rows[0].cells[j]
        _shd(c3, 'D9D9D9'); _cell_margins(c3, top=10, bottom=10, left=40, right=20)
        _row_exact_height(fee_t.rows[0], 8.5)
        _clear(c3)
        pf2 = c3.add_paragraph()
        pf2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf2.paragraph_format.line_spacing = Pt(7)
        _run(pf2, h, CJK, 6, bold=True)
    fee_ph = [
        ('{{fee_0_cls}}類', '無', '每年 {{fee_0_mgmt}}', '{{base_currency}} {{fee_0_min}}'),
        ('{{fee_1_cls}}類', '最高 5%', '每年 {{fee_1_mgmt}}', '{{base_currency}} {{fee_1_min}}'),
        ('{{fee_2_cls}}類', '最高 5%', '每年 {{fee_2_mgmt}}', '無'),
        ('{{fee_3_cls}}類', '最高 5%', '每年 {{fee_3_mgmt}}', '{{base_currency}} {{fee_3_min}}'),
    ]
    for i, vals in enumerate(fee_ph):
        row = fee_t.rows[i + 1]; bg = 'FFFFFF' if i % 2 == 0 else 'F5F5F5'
        _row_exact_height(row, 8.5)
        for j, v in enumerate(vals):
            _shd(row.cells[j], bg)
            _cell_margins(row.cells[j], top=10, bottom=10, left=40, right=20)
            _clear(row.cells[j])
            pv = row.cells[j].add_paragraph()
            pv.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pv.paragraph_format.line_spacing = Pt(7)
            _run(pv, v, CJK if j == 0 else ARIAL, 6)


# ══════════════════════════════════════════════════════════
# P1 右欄內容
# ══════════════════════════════════════════════════════════
def _build_right_p1(cell):
    """基金表現 + 累積業績表 + 年度業績表"""
    _clear(cell)

    # 大標題「基金表現²」
    ph = cell.add_paragraph()
    ph.paragraph_format.space_before = Pt(0); ph.paragraph_format.space_after = Pt(2)
    ph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    ph.paragraph_format.line_spacing = Pt(12)
    _run(ph, '基金表現', CJK, 9, bold=True, clr=RED)
    _run(ph, ' ²', ARIAL, 6.5, clr=RED)

    # 累積業績
    cp = cell.add_paragraph()
    cp.paragraph_format.space_before = Pt(2); cp.paragraph_format.space_after = Pt(1)
    cp.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    cp.paragraph_format.line_spacing = Pt(10)
    _run(cp, '累積表現', CJK, 8, bold=True, clr=RED)
    _run(cp, ' (%)', ARIAL, 8, bold=True, clr=RED)
    _run(cp, ' ²', ARIAL, 6, clr=RED)

    # 累積業績表（4行×8列）
    c_hdrs = ['類別', '一個月', '三個月', '六個月', '一年', '自成立起', '年化表現\n(自成立起)³', '7日\n年化表現⁴']
    c_ws   = [3.2, 0.88, 0.88, 0.88, 0.88, 0.88, 1.16, 0.88]
    ct = _table(cell, 5, 8, c_ws)
    for j, (h, w) in enumerate(zip(c_hdrs, c_ws)):
        c4 = ct.rows[0].cells[j]
        _shd(c4, 'BF0008'); _cell_margins(c4, top=10, bottom=10, left=30, right=20)
        _row_exact_height(ct.rows[0], 10.5)
        _clear(c4)
        ph2 = c4.add_paragraph()
        ph2.alignment = WD_ALIGN_PARAGRAPH.CENTER if j > 0 else WD_ALIGN_PARAGRAPH.LEFT
        ph2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        ph2.paragraph_format.line_spacing = Pt(7)
        _run(ph2, h, CJK, 5.8, bold=True, clr=WHITE)

    perf_keys = ['ret_1m','ret_3m','ret_6m','ret_1y',
                 'ret_since_inception','ret_ann_since_inception','ret_7d_ann']
    for i in range(1, 5):
        row = ct.rows[i]; idx = i - 1; bg = 'FFFFFF' if i%2==1 else 'F5F5F5'
        _row_exact_height(row, 8.5)
        vals = [f'{{{{perf_{idx}_cls}}}}類'] + [f'{{{{perf_{idx}_{k}}}}}' for k in perf_keys]
        for j, v in enumerate(vals):
            _shd(row.cells[j], bg); _cell_margins(row.cells[j], top=10, bottom=10, left=30, right=20)
            _clear(row.cells[j])
            pv = row.cells[j].add_paragraph()
            pv.alignment = WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT
            pv.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pv.paragraph_format.line_spacing = Pt(7)
            _run(pv, v, CJK if j==0 else ARIAL, 6)

    # 年度業績
    ap = cell.add_paragraph()
    ap.paragraph_format.space_before = Pt(4); ap.paragraph_format.space_after = Pt(1)
    ap.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    ap.paragraph_format.line_spacing = Pt(10)
    _run(ap, '年度表現', CJK, 8, bold=True, clr=RED)
    _run(ap, ' (%)', ARIAL, 8, bold=True, clr=RED)
    _run(ap, ' ²', ARIAL, 6, clr=RED)

    a_hdrs = ['類別', '2021', '2022', '2023', '2024', '2025', '2026\n本年至今']
    a_ws   = [3.2, 0.93, 0.93, 0.93, 0.93, 0.93, 1.09]
    at = _table(cell, 5, 7, a_ws)
    for j, (h, w) in enumerate(zip(a_hdrs, a_ws)):
        c5 = at.rows[0].cells[j]
        _shd(c5, 'BF0008'); _cell_margins(c5, top=10, bottom=10, left=30, right=20)
        _row_exact_height(at.rows[0], 10.5)
        _clear(c5)
        ph3 = c5.add_paragraph()
        ph3.alignment = WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT
        ph3.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        ph3.paragraph_format.line_spacing = Pt(7)
        _run(ph3, h, CJK if j==0 else ARIAL, 5.8, bold=True, clr=WHITE)
    years = ['2021','2022','2023','2024','2025','ytd']
    for i in range(1, 5):
        row = at.rows[i]; idx = i-1; bg = 'FFFFFF' if i%2==1 else 'F5F5F5'
        _row_exact_height(row, 8.5)
        vals = [f'{{{{ann_{idx}_cls}}}}類'] + [f'{{{{ann_{idx}_{y}}}}}' for y in years]
        for j, v in enumerate(vals):
            _shd(row.cells[j], bg); _cell_margins(row.cells[j], top=10, bottom=10, left=30, right=20)
            _clear(row.cells[j])
            pv = row.cells[j].add_paragraph()
            pv.alignment = WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT
            pv.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pv.paragraph_format.line_spacing = Pt(7)
            _run(pv, v, CJK if j==0 else ARIAL, 6)


# ══════════════════════════════════════════════════════════
# P1 全寬腳注
# ══════════════════════════════════════════════════════════
def _add_p1_footnotes(doc):
    tbl = _table(doc, 1, 1, [18.0])
    c = tbl.rows[0].cells[0]
    _cell_margins(c, top=30, bottom=20, left=60, right=60)
    _shd(c, 'FFFFFF'); _clear(c)

    fn_lines = [
        '* 相關評級機構已授予本基金貨幣市場基金評級。',
        '¹ 關於基金詳情（包括費用）請參考基金說明書。',
        '² 過往表現並不代表未來業績。業績以資產淨值對資產淨值計算，並已計入股息再投資（如屬派息類別，則不計入股息再投資）。',
        '³ 自各類別成立日期起計算，成立日期請參考本文「基金單位類別」部分。',
        '⁴ 根據七天（七個日曆天）的週期進行年化計算。此數據是根據基金過去七天的表現假設計算，並不代表實際一年的回報。',
        '除非另有說明，資料來源均來自本公司及彭博。截至 {{eval_year}}年{{eval_month}}月{{eval_day}}日。',
    ]
    for t in fn_lines:
        p = c.add_paragraph()
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(0.5)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p.paragraph_format.line_spacing = Pt(7.5)
        _run(p, t, CJK, 5.5, clr=DGREY)


# ══════════════════════════════════════════════════════════
# P2 左欄（投資組合特點）
# ══════════════════════════════════════════════════════════
def _build_left_p2(cell):
    _clear(cell)
    _section_head(cell, '投資組合特點')

    p1 = cell.add_paragraph()
    p1.paragraph_format.space_before = Pt(8); p1.paragraph_format.space_after = Pt(4)
    p1.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p1.paragraph_format.line_spacing = Pt(9)
    _run(p1, '加權平均到期日', CJK, 7.5)

    p2 = cell.add_paragraph()
    p2.paragraph_format.space_before = Pt(2); p2.paragraph_format.space_after = Pt(10)
    p2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p2.paragraph_format.line_spacing = Pt(22)
    _run(p2, '{{wam_days}}', ARIAL, 20, bold=True, clr=RED)
    _run(p2, '  天', CJK, 11)

    p3 = cell.add_paragraph()
    p3.paragraph_format.space_before = Pt(4); p3.paragraph_format.space_after = Pt(4)
    p3.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p3.paragraph_format.line_spacing = Pt(9)
    _run(p3, '加權平均到期收益率', CJK, 7.5)
    _run(p3, ' ¹', ARIAL, 6)

    p4 = cell.add_paragraph()
    p4.paragraph_format.space_before = Pt(2); p4.paragraph_format.space_after = Pt(4)
    p4.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p4.paragraph_format.line_spacing = Pt(22)
    _run(p4, '{{ytm_pct}}%', ARIAL, 20, bold=True, clr=RED)


# ══════════════════════════════════════════════════════════
# P2 右欄（圖表）
# ══════════════════════════════════════════════════════════
def _build_right_p2(cell):
    _clear(cell)

    ph1 = cell.add_paragraph()
    ph1.paragraph_format.space_before = Pt(0); ph1.paragraph_format.space_after = Pt(1)
    ph1.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    ph1.paragraph_format.line_spacing = Pt(10)
    _run(ph1, '資產類別分佈 (%)', CJK, 7.5, bold=True, clr=RED)

    # 圖片佔位符（docxtpl InlineImage 格式）
    pie_box = _image_box(cell, 9.8)
    p_pie = pie_box.add_paragraph()
    p_pie.paragraph_format.space_before = Pt(1); p_pie.paragraph_format.space_after = Pt(3)
    p_pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p_pie, '{{pie_chart}}', ARIAL, 7)

    ph2 = cell.add_paragraph()
    ph2.paragraph_format.space_before = Pt(3); ph2.paragraph_format.space_after = Pt(1)
    ph2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    ph2.paragraph_format.line_spacing = Pt(10)
    _run(ph2, '到期日分佈 (%)', CJK, 7.5, bold=True, clr=RED)

    bar_box = _image_box(cell, 9.8)
    p_bar = bar_box.add_paragraph()
    p_bar.paragraph_format.space_before = Pt(1); p_bar.paragraph_format.space_after = Pt(0)
    p_bar.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p_bar, '{{bar_chart}}', ARIAL, 7)


# ══════════════════════════════════════════════════════════
# P2 底部免責聲明 + 聯絡
# ══════════════════════════════════════════════════════════
def _add_p2_footer(doc):
    tbl = _table(doc, 1, 1, [18.0])
    c = tbl.rows[0].cells[0]
    _cell_margins(c, top=25, bottom=20, left=60, right=60)
    _shd(c, 'FFFFFF'); _clear(c)

    fn_lines = [
        '¹ 使用基金中每個持倉的中位到期收益率加權平均計算。',
        '數據來源：除非另有說明，資料來源均來自本公司及彭博。截至 {{eval_year}}年{{eval_month}}月{{eval_day}}日。',
    ]
    for t in fn_lines:
        p = c.add_paragraph()
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p.paragraph_format.line_spacing = Pt(7.5)
        _run(p, t, CJK, 5.5, clr=DGREY)

    disc = c.add_paragraph()
    disc.paragraph_format.space_before = Pt(4); disc.paragraph_format.space_after = Pt(4)
    disc.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    disc.paragraph_format.line_spacing = Pt(7.5)
    _run(disc, '重要聲明：投資涉及風險。基金股價可升亦可跌，過往業績並不表示將來基金回報，未來回報不能被保證。'
         '閣下亦可能損失所投資之本金。本資料並不構成對於任何證券或基金的買賣或進行任何交易之邀約或任何投資建議。'
         '本文件只供閣下參考之用，閣下不應依賴本文件作任何投資決定。'
         '本文所載之部份資料或數據是從第三方取得的，本公司確保準確地再製造該等數據或資料，但並不保證其準確性及完整性。'
         '閣下不應僅依賴本資料而作出任何投資決定，應細閱基金銷售文件，了解基金詳情及風險因素。'
         '如有需要，應諮詢獨立專業意見。本資料之發行人為本公司。此資料並未獲香港證監會所審閱。',
         CJK, 5.5, clr=DGREY)

    cont = c.add_paragraph()
    cont.paragraph_format.space_before = Pt(5)
    cont.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    cont.paragraph_format.line_spacing = Pt(10)
    _run(cont, '服務熱線：{{contact_phone}}    網站：{{contact_web}}    電郵：{{contact_email}}',
         CJK, 8)


# ══════════════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════════════
def build_template():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width   = Cm(21.0); sec.page_height  = Cm(29.7)
    sec.top_margin   = Cm(1.0);  sec.bottom_margin = Cm(0.8)
    sec.left_margin  = Cm(1.5);  sec.right_margin  = Cm(1.5)

    # ── Page 1 ──────────────────────────────────────────
    _add_header(doc)

    _add_disclaimer_block(doc)  # 全寬風險說明（PDF y=79-211）

    # 主雙欄表（左8cm + 右10cm）
    main = _table(doc, 1, 2, [7.85, 10.15])
    _build_left_p1(main.rows[0].cells[0])
    _build_right_p1(main.rows[0].cells[1])

    _add_p1_footnotes(doc)     # 全寬腳注（PDF y=723-841）

    # ── Page 2 ──────────────────────────────────────────
    doc.add_page_break()
    _add_header(doc)

    main2 = _table(doc, 1, 2, [7.85, 10.15])
    _build_left_p2(main2.rows[0].cells[0])
    _build_right_p2(main2.rows[0].cells[1])

    _add_p2_footer(doc)

    doc.save(str(OUT_PATH))
    print(f'✅ Word 模版已建立（2頁）：{OUT_PATH}')

if __name__ == '__main__':
    build_template()
