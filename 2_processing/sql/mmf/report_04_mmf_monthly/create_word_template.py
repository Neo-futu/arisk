"""
create_word_template.py — 生成 Word 模版 Template_Factsheet.docx
執行：python create_word_template.py

模版結構（仿參考 PDF 雙欄格式）：
  P1 頁首：基金名稱 + 日期 + 品牌紅橫條
  P1 左欄：投資目標、基金資料、基金單位類別、費用
  P1 右欄：基金表現、累積業績表、年度業績表
  P2 左欄：投資組合特點（WAM/YTM）
  P2 右欄：資產配置圓餅圖、到期分佈柱狀圖
  P2 底部：重要聲明、聯絡資料

可變字段使用 {{var}} 佔位符（Jinja2 格式），由 create_word_report.py 填充。
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from copy import deepcopy

BASE_DIR = Path(__file__).parent
OUT_PATH = BASE_DIR / 'Template_Factsheet.docx'

# ── 品牌色 ───────────────────────────────────────────────
RED    = RGBColor(191, 0, 8)      # #BF0008 品牌紅
BLACK  = RGBColor(0, 0, 0)
WHITE  = RGBColor(255, 255, 255)
LGREY  = RGBColor(242, 242, 242)  # 淺灰背景

# ── 字型 ─────────────────────────────────────────────────
CJK   = '微软雅黑'   # Microsoft YaHei
ARIAL = 'Arial'

# ══════════════════════════════════════════════════════════
# 底層 XML 輔助
# ══════════════════════════════════════════════════════════
def _set_cell_bg(cell, hex_color: str):
    """設定表格儲存格背景色"""
    tc  = cell._tc
    tcp = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcp.append(shd)

def _set_cell_border(cell, sides=None, color='BFBFBF', sz='4'):
    """設定儲存格邊框"""
    tc  = cell._tc
    tcp = tc.get_or_add_tcPr()
    tcb = OxmlElement('w:tcBorders')
    for side in (sides or ['top','bottom','left','right']):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), sz)
        el.set(qn('w:color'), color)
        tcb.append(el)
    tcp.append(tcb)

def _set_row_height(row, height_cm, exact=True):
    """設定行高"""
    tr   = row._tr
    trpr = tr.get_or_add_trPr()
    trh  = OxmlElement('w:trHeight')
    trh.set(qn('w:val'), str(int(height_cm * 914400 / 2.54 / 914400 * 1440)))
    trh.set(qn('w:hRule'), 'exact' if exact else 'atLeast')
    trpr.append(trh)

def _para(cell_or_doc, text='', font_name=CJK, size_pt=7.5, bold=False,
          color=BLACK, align=WD_ALIGN_PARAGRAPH.LEFT, space_after=0):
    """在 cell 或 doc 中新增格式化段落"""
    p = cell_or_doc.add_paragraph() if hasattr(cell_or_doc,'add_paragraph') else None
    if p is None: return
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(0); pf.space_after = Pt(space_after)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(size_pt * 1.25)
    if text:
        run = p.add_run(text)
        run.font.name  = font_name; run.font.size  = Pt(size_pt)
        run.font.bold  = bold;      run.font.color.rgb = color
        run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    return p

def _add_run(para, text, font_name=CJK, size_pt=7.5, bold=False, color=BLACK):
    run = para.add_run(text)
    run.font.name  = font_name; run.font.size  = Pt(size_pt)
    run.font.bold  = bold;      run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    return run

def _clear_cell(cell):
    """清空儲存格既有段落"""
    for p in cell.paragraphs:
        p.clear()

# ══════════════════════════════════════════════════════════
# 表格建立輔助
# ══════════════════════════════════════════════════════════
def _make_table(doc, rows, cols, col_widths_cm, style='Table Grid'):
    """建立表格並設定欄寬"""
    tbl = doc.add_table(rows=rows, cols=cols)
    tbl.style = doc.styles['Table Grid'] if style == 'Table Grid' else doc.styles.get(style) or tbl.style
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    for i, w in enumerate(col_widths_cm):
        for row in tbl.rows:
            cell = row.cells[i]
            cell.width = Cm(w)
    return tbl

def _merge_row(row, start=0):
    """合併一行所有儲存格"""
    cells = row.cells
    if len(cells) > 1:
        cells[start].merge(cells[-1])
    return cells[start]

# ══════════════════════════════════════════════════════════
# 頁首（品牌紅橫條 + 基金名稱）
# ══════════════════════════════════════════════════════════
def _build_header(doc, is_p2=False):
    """建立頁首區塊（兩列：基金名稱區 | 評級徽章區）"""
    # 外層大表（全寬，無邊框）
    hdr = _make_table(doc, 2, 2, [12.5, 5.5], style='Table Grid')
    # 去除表格外框
    for row in hdr.rows:
        for cell in row.cells:
            _set_cell_border(cell, color='FFFFFF', sz='0')

    # Row 0：基金名稱 + 徽章
    r0 = hdr.rows[0]
    c0, c1 = r0.cells[0], r0.cells[1]
    _clear_cell(c0)
    p = c0.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after  = Pt(2)
    _add_run(p, '{{fund_name}}', CJK, 14, bold=True, color=BLACK)
    _clear_cell(c1)
    p1 = c1.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_run(p1, '「新資本投資者入境計劃」合資格基金', CJK, 5.5, color=RED)

    # Row 1：副標題（月報/日期）+ AAAmf
    r1 = hdr.rows[1]
    c0b, c1b = r1.cells[0], r1.cells[1]
    _clear_cell(c0b)
    p2 = c0b.paragraphs[0]
    p2.paragraph_format.space_before = Pt(0)
    p2.paragraph_format.space_after  = Pt(0)
    _add_run(p2, '基金月報    截至  ', CJK, 8, bold=True, color=BLACK)
    _add_run(p2, '{{eval_year}}', ARIAL, 8, bold=True, color=BLACK)
    _add_run(p2, '年', CJK, 8, bold=True, color=BLACK)
    _add_run(p2, '{{eval_month}}', ARIAL, 8, bold=True, color=BLACK)
    _add_run(p2, '月', CJK, 8, bold=True, color=BLACK)
    _add_run(p2, '{{eval_day}}', ARIAL, 8, bold=True, color=BLACK)
    _add_run(p2, '日', CJK, 8, bold=True, color=BLACK)
    _clear_cell(c1b)
    p3 = c1b.paragraphs[0]
    p3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_run(p3, 'AAAmf*', ARIAL, 7, bold=True, color=RED)

    # 紅色分隔條（全寬，高0.35cm）
    div = _make_table(doc, 1, 1, [18.0])
    _merge_row(div.rows[0])
    _set_cell_bg(div.rows[0].cells[0], 'BF0008')
    div.rows[0].height = Cm(0.35)
    _clear_cell(div.rows[0].cells[0])
    div.rows[0].cells[0].add_paragraph()

    return hdr, div


# ══════════════════════════════════════════════════════════
# 節標題（紅色小方塊 + 粗體文字）
# ══════════════════════════════════════════════════════════
def _section_head(cell, title_text):
    """在儲存格中加入節標題（仿 PDF 格式：■ 標題文字）"""
    p = cell.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after  = Pt(2)
    # 紅色方塊用 Unicode 實心方塊 ■ 模擬
    r1 = p.add_run('■ ')
    r1.font.name = ARIAL; r1.font.size = Pt(8); r1.font.color.rgb = RED
    r2 = p.add_run(title_text)
    r2.font.name = CJK;   r2.font.size = Pt(9); r2.font.bold = True
    r2.font.color.rgb = RED
    r2._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    return p


# ══════════════════════════════════════════════════════════
# 基金資料鍵值表
# ══════════════════════════════════════════════════════════
def _fund_info_table(cell):
    """在儲存格中建立基金資料鍵值表"""
    rows_def = [
        ('法律結構', '{{legal_structure}}'),
        ('投資經理', '{{investment_manager}}'),
        ('受託人',   '{{trustee}}'),
        ('託管人',   '{{custodian}}'),
        ('基礎貨幣', '{{base_currency}}'),
        ('基金規模', '{{base_currency}} {{nav_millions}} 百萬'),
        ('非基礎貨幣股份類別', '{{non_base_currency}}'),
        ('交易頻率', '{{trading_freq}}'),
    ]
    tbl = cell.add_table(rows=len(rows_def), cols=2)
    tbl.style = cell._tc.document.styles['Table Grid'] if hasattr(cell._tc,'document') else None
    for i, (k, v) in enumerate(rows_def):
        row = tbl.rows[i]
        row.cells[0].width = Cm(3.2)
        row.cells[1].width = Cm(4.5)
        bg = 'FFFFFF' if i%2==0 else 'F2F2F2'
        for c in row.cells: _set_cell_bg(c, bg)
        _clear_cell(row.cells[0])
        pk = row.cells[0].add_paragraph()
        pk.paragraph_format.space_before = Pt(1); pk.paragraph_format.space_after = Pt(1)
        rk = pk.add_run(k)
        rk.font.name = CJK; rk.font.size = Pt(6.5); rk.font.color.rgb = RGBColor(100,100,100)
        rk._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
        _clear_cell(row.cells[1])
        pv = row.cells[1].add_paragraph()
        pv.paragraph_format.space_before = Pt(1); pv.paragraph_format.space_after = Pt(1)
        rv = pv.add_run(v)
        rv.font.name = CJK; rv.font.size = Pt(6.5)
        rv._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)


# ══════════════════════════════════════════════════════════
# NAV 類別表
# ══════════════════════════════════════════════════════════
def _nav_class_table(cell):
    hdrs = ['類別', '發行日期', '每股資產淨值', '彭博編碼', 'ISIN編碼']
    widths = [2.2, 1.6, 2.0, 1.8, 1.8]
    tbl = cell.add_table(rows=5, cols=5)  # 1 header + 4 data rows
    for i, (h, w) in enumerate(zip(hdrs, widths)):
        for row in tbl.rows: row.cells[i].width = Cm(w)
        c = tbl.rows[0].cells[i]
        _set_cell_bg(c, 'D9D9D9')
        _clear_cell(c)
        p = c.add_paragraph()
        p.paragraph_format.space_before = Pt(1); p.paragraph_format.space_after = Pt(1)
        r = p.add_run(h)
        r.font.name = CJK; r.font.size = Pt(6.5); r.font.bold = True
        r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    # 4 data rows
    for i in range(1, 5):
        row = tbl.rows[i]
        idx = i - 1
        vals = [
            f'{{{{nav_cls_{idx}_id}}}}',
            f'{{{{nav_cls_{idx}_date}}}}',
            f'{{{{nav_cls_{idx}_nav}}}}',
            f'{{{{nav_cls_{idx}_bb}}}}',
            f'{{{{nav_cls_{idx}_isin}}}}',
        ]
        bg = 'FFFFFF' if i%2==1 else 'F2F2F2'
        for j, v in enumerate(vals):
            _set_cell_bg(row.cells[j], bg)
            _clear_cell(row.cells[j])
            p = row.cells[j].add_paragraph()
            p.paragraph_format.space_before = Pt(1); p.paragraph_format.space_after = Pt(1)
            r = p.add_run(v)
            r.font.name = ARIAL; r.font.size = Pt(6.5)


# ══════════════════════════════════════════════════════════
# 費用表
# ══════════════════════════════════════════════════════════
def _fee_table(cell):
    hdrs = ['類別', '認購費', '投資管理費', '最低認購額']
    widths = [2.2, 1.4, 1.8, 2.0]
    tbl = cell.add_table(rows=5, cols=4)
    for i, (h, w) in enumerate(zip(hdrs, widths)):
        for row in tbl.rows: row.cells[i].width = Cm(w)
        c = tbl.rows[0].cells[i]
        _set_cell_bg(c, 'D9D9D9')
        _clear_cell(c)
        p = c.add_paragraph()
        p.paragraph_format.space_before = Pt(1); p.paragraph_format.space_after = Pt(1)
        r = p.add_run(h)
        r.font.name = CJK; r.font.size = Pt(6.5); r.font.bold = True
        r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    fee_placeholders = [
        ('{{fee_cls_0_id}}類', '{{fee_cls_0_sub}}', '{{fee_cls_0_mgmt}}', '{{fee_cls_0_min}}'),
        ('{{fee_cls_1_id}}類', '{{fee_cls_1_sub}}', '{{fee_cls_1_mgmt}}', '{{fee_cls_1_min}}'),
        ('{{fee_cls_2_id}}類', '{{fee_cls_2_sub}}', '{{fee_cls_2_mgmt}}', '{{fee_cls_2_min}}'),
        ('{{fee_cls_3_id}}類', '{{fee_cls_3_sub}}', '{{fee_cls_3_mgmt}}', '{{fee_cls_3_min}}'),
    ]
    for i, vals in enumerate(fee_placeholders):
        row = tbl.rows[i+1]
        bg = 'FFFFFF' if i%2==0 else 'F2F2F2'
        for j, v in enumerate(vals):
            _set_cell_bg(row.cells[j], bg)
            _clear_cell(row.cells[j])
            p = row.cells[j].add_paragraph()
            p.paragraph_format.space_before = Pt(1); p.paragraph_format.space_after = Pt(1)
            r = p.add_run(v)
            r.font.name = ARIAL; r.font.size = Pt(6.5)


# ══════════════════════════════════════════════════════════
# 業績表（累積 + 年度）
# ══════════════════════════════════════════════════════════
def _perf_table(cell):
    """累積業績表（含列標題）"""
    hdrs    = ['類別', '一個月', '三個月', '六個月', '一年', '自成立', '年化表現\n(自成立)', '7日\n年化']
    widths  = [3.0, 0.9, 0.9, 0.9, 0.9, 0.9, 1.2, 0.9]
    n_rows  = 5   # 1 header + 4 data
    tbl = cell.add_table(rows=n_rows, cols=8)
    for i, (h, w) in enumerate(zip(hdrs, widths)):
        for row in tbl.rows: row.cells[i].width = Cm(w)
        c = tbl.rows[0].cells[i]
        _set_cell_bg(c, 'BF0008')
        _clear_cell(c)
        p = c.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(1); p.paragraph_format.space_after = Pt(1)
        r = p.add_run(h)
        r.font.name = CJK; r.font.size = Pt(6.5); r.font.bold = True; r.font.color.rgb = WHITE
        r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    keys = ['ret_1m','ret_3m','ret_6m','ret_1y','ret_since_inception','ret_ann_since_inception','ret_7d_ann']
    for i in range(1, n_rows):
        row = tbl.rows[i]; bg = 'FFFFFF' if i%2==1 else 'F2F2F2'
        idx = i - 1
        vals = [f'{{{{perf_{idx}_cls}}}}'] + [f'{{{{perf_{idx}_{k}}}}}' for k in keys]
        for j, v in enumerate(vals):
            _set_cell_bg(row.cells[j], bg); _clear_cell(row.cells[j])
            p = row.cells[j].add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(1); p.paragraph_format.space_after = Pt(1)
            r = p.add_run(v)
            r.font.name = ARIAL if j>0 else CJK; r.font.size = Pt(6.5)
            if j == 0: r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)

def _annual_table(cell):
    """年度業績表"""
    hdrs   = ['類別', '2021', '2022', '2023', '2024', '2025', '本年至今']
    widths = [3.0, 0.9, 0.9, 0.9, 0.9, 0.9, 1.1]
    tbl = cell.add_table(rows=5, cols=7)
    for i, (h, w) in enumerate(zip(hdrs, widths)):
        for row in tbl.rows: row.cells[i].width = Cm(w)
        c = tbl.rows[0].cells[i]
        _set_cell_bg(c, 'BF0008'); _clear_cell(c)
        p = c.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(1); p.paragraph_format.space_after = Pt(1)
        r = p.add_run(h)
        r.font.name = CJK if i==0 else ARIAL
        r.font.size = Pt(6.5); r.font.bold = True; r.font.color.rgb = WHITE
        if i == 0: r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    years = ['2021','2022','2023','2024','2025','ytd']
    for i in range(1, 5):
        row = tbl.rows[i]; bg = 'FFFFFF' if i%2==1 else 'F2F2F2'; idx = i-1
        vals = [f'{{{{ann_{idx}_cls}}}}'] + [f'{{{{ann_{idx}_{y}}}}}' for y in years]
        for j, v in enumerate(vals):
            _set_cell_bg(row.cells[j], bg); _clear_cell(row.cells[j])
            p = row.cells[j].add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if j>0 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(1); p.paragraph_format.space_after = Pt(1)
            r = p.add_run(v)
            r.font.name = ARIAL if j>0 else CJK; r.font.size = Pt(6.5)
            if j == 0: r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)


# ══════════════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════════════
def build_template():
    doc = Document()

    # ── 頁面設定（A4，窄邊距）───────────────────────────
    sec = doc.sections[0]
    sec.page_width  = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin  = Cm(1.2); sec.bottom_margin = Cm(1.0)
    sec.left_margin = Cm(1.5); sec.right_margin  = Cm(1.5)

    # ── Page 1 ──────────────────────────────────────────
    _build_header(doc)
    doc.add_paragraph()  # 小間距

    # 主內容大表（左欄 + 右欄）
    main = _make_table(doc, 1, 2, [8.0, 10.0])
    for row in main.rows:
        for cell in row.cells:
            _set_cell_border(cell, color='FFFFFF', sz='0')
    lc = main.rows[0].cells[0]   # 左欄
    rc = main.rows[0].cells[1]   # 右欄

    # ── 左欄 ────────────────────────────────────────────
    _section_head(lc, '投資目標')
    p_obj = lc.add_paragraph()
    p_obj.paragraph_format.space_before = Pt(1); p_obj.paragraph_format.space_after = Pt(4)
    r = p_obj.add_run('{{investment_objective}}')
    r.font.name = CJK; r.font.size = Pt(6.5)
    r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)

    _section_head(lc, '基金資料')
    _fund_info_table(lc)
    lc.add_paragraph()

    _section_head(lc, '基金單位類別')
    _nav_class_table(lc)
    p_src = lc.add_paragraph()
    p_src.paragraph_format.space_before = Pt(2)
    r = p_src.add_run('數據來源：本公司。截至 {{eval_year}}年{{eval_month}}月{{eval_day}}日，除非另有說明。')
    r.font.name = CJK; r.font.size = Pt(6); r.font.color.rgb = RGBColor(100,100,100)
    r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    lc.add_paragraph()

    _section_head(lc, '費用')
    _fee_table(lc)

    # ── 右欄 ────────────────────────────────────────────
    p_head = rc.add_paragraph()
    p_head.paragraph_format.space_before = Pt(0); p_head.paragraph_format.space_after = Pt(3)
    r1 = p_head.add_run('基金表現'); r1.font.name = CJK; r1.font.size = Pt(9)
    r1.font.bold = True; r1.font.color.rgb = RED; r1._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    r2 = p_head.add_run(' ²'); r2.font.name = ARIAL; r2.font.size = Pt(7); r2.font.color.rgb = RED

    p_cs = rc.add_paragraph()
    p_cs.paragraph_format.space_before = Pt(2); p_cs.paragraph_format.space_after = Pt(1)
    r3 = p_cs.add_run('累積表現 (%)'); r3.font.name = CJK; r3.font.size = Pt(8)
    r3.font.bold = True; r3.font.color.rgb = RED; r3._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    _perf_table(rc)
    rc.add_paragraph()

    p_ay = rc.add_paragraph()
    p_ay.paragraph_format.space_before = Pt(4); p_ay.paragraph_format.space_after = Pt(1)
    r4 = p_ay.add_run('年度表現 (%)'); r4.font.name = CJK; r4.font.size = Pt(8)
    r4.font.bold = True; r4.font.color.rgb = RED; r4._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    _annual_table(rc)

    # ── P1 底部：腳注 + 免責聲明 ─────────────────────────
    doc.add_paragraph()
    fn_tbl = _make_table(doc, 1, 1, [18.0])
    _set_cell_bg(fn_tbl.rows[0].cells[0], 'FFFFFF')
    fc = fn_tbl.rows[0].cells[0]
    for fn_text in [
        '* 聯合評級國際有限公司授予本基金"AAAmf" 貨幣市場基金評級。',
        '¹ 關於基金詳情（包括費用）請參考基金說明書。',
        '² 過往表現並不代表未來業績。業績以資產淨值對資產淨值計算，並已計入股息再投資。',
        '³ 自各類別成立日期起計算。',
        '⁴ 根據七天（七個日曆天）的週期進行年化計算。',
        '除非另有說明，資料來源均來自本公司及彭博。截至 {{eval_year}}年{{eval_month}}月{{eval_day}}日。',
    ]:
        p = fc.add_paragraph()
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(1)
        r = p.add_run(fn_text)
        r.font.name = CJK; r.font.size = Pt(5.5); r.font.color.rgb = RGBColor(80,80,80)
        r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)

    # 免責聲明
    disc_p = fc.add_paragraph()
    disc_p.paragraph_format.space_before = Pt(4)
    r = disc_p.add_run('投資涉及風險，包括損失本金。基金單位價格可升亦可跌，過往業績並不代表未來回報。本基金是投資基金而非銀行存款。'
                        '投資者應細閱基金銷售文件，了解基金詳情及風險因素。如有需要，應諮詢獨立專業意見。'
                        '本資料並未獲香港證監會所審閱。')
    r.font.name = CJK; r.font.size = Pt(5.5); r.font.color.rgb = RGBColor(80,80,80)
    r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)

    # ── Page 2 ─────────────────────────────────────────
    doc.add_page_break()
    _build_header(doc, is_p2=True)
    doc.add_paragraph()

    main2 = _make_table(doc, 1, 2, [8.0, 10.0])
    for row in main2.rows:
        for cell in row.cells:
            _set_cell_border(cell, color='FFFFFF', sz='0')
    lc2 = main2.rows[0].cells[0]
    rc2 = main2.rows[0].cells[1]

    # ── P2 左欄：組合特點 ─────────────────────────────
    _section_head(lc2, '投資組合特點')
    # WAM 大字
    p_wam = lc2.add_paragraph()
    p_wam.paragraph_format.space_before = Pt(6)
    r5 = p_wam.add_run('加權平均到期日         ')
    r5.font.name = CJK; r5.font.size = Pt(7.5); r5._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    r6 = p_wam.add_run('{{wam_days}}')
    r6.font.name = ARIAL; r6.font.size = Pt(16); r6.font.bold = True; r6.font.color.rgb = RED
    r7 = p_wam.add_run('  天')
    r7.font.name = CJK; r7.font.size = Pt(9); r7._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    # YTM 大字
    p_ytm = lc2.add_paragraph()
    p_ytm.paragraph_format.space_before = Pt(6)
    r8 = p_ytm.add_run('加權平均到期收益率 ¹  ')
    r8.font.name = CJK; r8.font.size = Pt(7.5); r8._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    r9 = p_ytm.add_run('{{ytm_pct}}%')
    r9.font.name = ARIAL; r9.font.size = Pt(16); r9.font.bold = True; r9.font.color.rgb = RED

    # ── P2 右欄：圖表佔位符 ───────────────────────────
    ph_p = rc2.add_paragraph()
    ph_p.paragraph_format.space_before = Pt(0)
    r = ph_p.add_run('資產類別分佈 (%)')
    r.font.name = CJK; r.font.size = Pt(8); r.font.bold = True; r.font.color.rgb = RED
    r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    # 圖表圖片佔位
    rc2.add_paragraph('{{pie_chart_image}}')
    rc2.add_paragraph()
    ph_b = rc2.add_paragraph()
    r = ph_b.add_run('到期日分佈 (%)')
    r.font.name = CJK; r.font.size = Pt(8); r.font.bold = True; r.font.color.rgb = RED
    r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    rc2.add_paragraph('{{bar_chart_image}}')

    # ── P2 底部：重要聲明 + 聯絡 ────────────────────────
    doc.add_paragraph()
    d2_tbl = _make_table(doc, 1, 1, [18.0])
    dc = d2_tbl.rows[0].cells[0]
    _set_cell_bg(dc, 'FFFFFF')
    disc2 = dc.add_paragraph()
    disc2.paragraph_format.space_before = Pt(4)
    r = disc2.add_run('¹ 使用基金中每個持倉的加權平均到期收益率計算。\n'
                      '數據來源：除非另有說明，資料來源均來自本公司。截至 {{eval_year}}年{{eval_month}}月{{eval_day}}日。')
    r.font.name = CJK; r.font.size = Pt(5.5); r.font.color.rgb = RGBColor(80,80,80)
    r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    imp_p = dc.add_paragraph()
    imp_p.paragraph_format.space_before = Pt(4)
    r = imp_p.add_run('重要聲明：投資涉及風險。基金股價可升亦可跌，過往業績並不表示將來基金回報，未來回報不能被保證。'
                      '閣下亦可能損失所投資之本金。本資料並不構成對於任何證券或基金的買賣邀約或任何投資建議。'
                      '本文件只供閣下參考之用，閣下不應依賴本文件作任何投資決定。'
                      '本資料之發行人為本公司。此資料並未獲香港證監會所審閱。')
    r.font.name = CJK; r.font.size = Pt(5.5); r.font.color.rgb = RGBColor(80,80,80)
    r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)
    cont_p = dc.add_paragraph()
    cont_p.paragraph_format.space_before = Pt(6)
    r = cont_p.add_run('服務熱線：{{contact_phone}}    網站：{{contact_web}}    電郵：{{contact_email}}')
    r.font.name = CJK; r.font.size = Pt(8)
    r._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)

    doc.save(str(OUT_PATH))
    print(f'✅ Word 模版已建立：{OUT_PATH}')

if __name__ == '__main__':
    build_template()
