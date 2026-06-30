"""
create_template.py  —  全新建立 report_03_mmf/Template.xlsx
執行：python 2_processing/sql/mmf/report_03_mmf/create_template.py
"""
import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.styles.colors import Color
from openpyxl.utils import get_column_letter
from pathlib import Path

# ── 儲存格填充色 ──────────────────────────────────────────
YELLOW = PatternFill('solid', fgColor='FFFF99')   # SQL 數據區
BLUE_H = PatternFill('solid', fgColor='BDD7EE')   # 表頭
GREY_L = PatternFill('solid', fgColor='EEEEEE')   # 區段標籤

# ── Sheet Tab 顏色 ─────────────────────────────────────────
TAB_YELLOW = 'FFD700'   # 源 SQL 輸出 sheet（黃）
TAB_RED    = 'FF4C4C'   # 計算過程 sheet（紅）
TAB_BLUE   = '4472C4'   # 彙總展示 sheet（藍）


def hdr(ws, row, col, text, fill=BLUE_H):
    c = ws.cell(row=row, column=col, value=text)
    c.fill = fill
    c.font = Font(bold=True, size=9)
    c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    return c


def lbl(ws, row, col, text):
    c = ws.cell(row=row, column=col, value=text)
    c.fill = GREY_L
    c.font = Font(bold=True, size=9, color='595959')
    return c


def yell(ws, r1, c1, r2, c2):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(row=r, column=c).fill = YELLOW


def set_col_width(ws, col_widths):
    for col, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


wb = Workbook()
wb.remove(wb.active)

# ══════════════════════════════════════════════════════════
# 1. 日报-表格汇总
# ══════════════════════════════════════════════════════════
ws = wb.create_sheet('日报-表格汇总')
ws.sheet_properties.tabColor = TAB_BLUE
ws['A1'] = '【日報 - 表格彙總】'
ws['A1'].font = Font(bold=True, size=14)
ws['A2'] = '此頁由使用者自行設計，引用「日报-sql导入数据」的數據'
ws['A2'].font = Font(color='808080', size=10)
ws.column_dimensions['A'].width = 60

# ══════════════════════════════════════════════════════════
# 2. 日报-sql导入数据
# ══════════════════════════════════════════════════════════
ws2 = wb.create_sheet('日报-sql导入数据')
ws2.sheet_properties.tabColor = TAB_YELLOW

# 01 NAV → A6
lbl(ws2, 3, 1, '01_nav_deviation.sql  →  A6')
# row 4 空白，row 5 標題行，row 6 數據起始（start_cell=A6）
h01 = ['组合名称', '净资产(元)', '偏离度(bp)', '偏离金额(元)',
       '每万份收益', '7日年化(%)', 'WAM(天)', 'WAL(天)']
for i, h in enumerate(h01, 1):
    hdr(ws2, 5, i, h)
yell(ws2, 6, 1, 12, len(h01))

# 02 流动性 → I6
lbl(ws2, 3, 9, '02_liquidity_1m.sql  →  I6')
for i, h in enumerate(['组合名称', '现金(亿)', '1M内利率债(亿)'], 9):
    hdr(ws2, 5, i, h)
yell(ws2, 6, 9, 12, 11)

# 07 受限 → L6
lbl(ws2, 3, 12, '07_restricted_liquidity.sql  →  L6')
for i, h in enumerate(['组合名称', '受限资产(亿)'], 12):
    hdr(ws2, 5, i, h)
yell(ws2, 6, 12, 12, 13)

# 08 久期结构 → A26
lbl(ws2, 23, 1, '08_duration_structure.sql  →  A26')
for i, h in enumerate(['组合名称', '评级类别', '加权平均久期(年)'], 1):
    hdr(ws2, 25, i, h)
yell(ws2, 26, 1, 32, 3)

# 04 持有人 → D26
lbl(ws2, 23, 4, '04_top_holders.sql  →  D26')
for i, h in enumerate(['组合名称', '机构占比(%)', '前1大(%)', '前5大(%)', '前10大(%)'], 4):
    hdr(ws2, 25, i, h)
yell(ws2, 26, 4, 32, 8)

# 05 T+N → I26
lbl(ws2, 23, 9, '05_assets_5y.sql  →  I26')
for i, h in enumerate(['组合名称', 'T+1(亿)', 'T+2', 'T+3', 'T+4', 'T+5', 'T1~5合计(亿)'], 9):
    hdr(ws2, 25, i, h)
yell(ws2, 26, 9, 32, 15)

# 06 资产组合 → A44
lbl(ws2, 41, 1, '06_asset_portfolio.sql  →  A44')
h06 = ['组合', '估值日', '净资产(亿)', '现金', '债券', '存款', 'CD',
       '逆回购', '正回购', '利率债', '信用债', '其他债', '存款利率', 'CD利率', '组合利率']
for i, h in enumerate(h06, 1):
    hdr(ws2, 43, i, h)
yell(ws2, 44, 1, 54, len(h06))

# 09 AAA以下合计 → A62
lbl(ws2, 59, 1, '09_sub_aaa_total.sql  →  A62')
for i, h in enumerate(['组合名称', 'AAA以下市值(亿)', '占NAV比(%)'], 1):
    hdr(ws2, 61, i, h)
yell(ws2, 62, 1, 68, 3)

# 11 单一AAA以下最大 → D62
lbl(ws2, 59, 4, '11_sub_aaa_single_max.sql  →  D62')
for i, h in enumerate(['组合名称', '单一最大比率(%)'], 4):
    hdr(ws2, 61, i, h)
yell(ws2, 62, 4, 68, 5)

# 40 AAA以下明细 → F62
lbl(ws2, 59, 6, '40_sub_aaa_detail.sql  →  F62')
for i, h in enumerate(['组合名称', '发行人', '品种', '比率(%)', '市值(元)'], 6):
    hdr(ws2, 61, i, h)
yell(ws2, 62, 6, 80, 10)

# 13 利差损 → A80
lbl(ws2, 77, 1, '13_deposit_rate_loss.sql  →  A80')
for i, h in enumerate(['组合名称', '组合代码', '最大利差损金额(元)'], 1):
    hdr(ws2, 79, i, h)
yell(ws2, 80, 1, 86, 3)

# 10 申赎 → A96
lbl(ws2, 93, 1, '10_sub_redeem_3d.sql  →  A96')
for i, h in enumerate(['组合名称', '明日确认(亿)', '当日&昨日(亿)', 'T-2净值(亿)'], 1):
    hdr(ws2, 95, i, h)
yell(ws2, 96, 1, 102, 4)

# 12 T+1~T+5 → E96
lbl(ws2, 93, 5, '12_maturity_t1t5.sql  →  E96')
for i, h in enumerate(['组合名称', 'T+1到期', 'T+2', 'T+3', 'T+4', 'T+5'], 5):
    hdr(ws2, 95, i, h)
yell(ws2, 96, 5, 102, 10)

# 16 月季年末 → K96
lbl(ws2, 93, 11, '16_maturity_buckets.sql  →  K96')
for i, h in enumerate(['组合', 'T+14', 'T+30', '月末', '季末', '年末', '明年末', '后年末+'], 11):
    hdr(ws2, 95, i, h)
yell(ws2, 96, 11, 102, 18)

# 03 偏差拆分 → A118
lbl(ws2, 115, 1, '03_deviation_breakdown.sql  →  A118')
h03 = ['组合名称', 'CD偏差(万)', '企业债偏差(万)', '政府债偏差(万)',
       'CD市值(亿)', '企业债(亿)', '政府债(亿)', '存款(亿)',
       'CD利率', '企债利率', '政债利率', '组合平均利率']
for i, h in enumerate(h03, 1):
    hdr(ws2, 117, i, h)
yell(ws2, 118, 1, 125, len(h03))

for col in range(1, 22):
    ws2.column_dimensions[get_column_letter(col)].width = 15
ws2.freeze_panes = 'A2'
ws2.row_dimensions[1].height = 20

# ══════════════════════════════════════════════════════════
# 3. 持仓数据  (17_stress_test.sql → A2)
# ══════════════════════════════════════════════════════════
ws10 = wb.create_sheet('持仓数据')
ws10.sheet_properties.tabColor = TAB_YELLOW
h17 = ['组合名称', '证券类型', '证券代码', '证券名称', '数量', '成本',
       '市值净价', '成本全价', '影价偏离度', '市值占净值比(%)',
       '偏离金额(万元)', '到期日', '利率类型', '久期', '评级', '是否当季到期']
for i, h in enumerate(h17, 1):
    hdr(ws10, 1, i, h)
yell(ws10, 2, 1, 300, len(h17))
for col in range(1, len(h17) + 1):
    ws10.column_dimensions[get_column_letter(col)].width = 14
ws10.freeze_panes = 'A2'

# ══════════════════════════════════════════════════════════
# 4. 回购明细  (15_overnight_repo.sql → A2)
# ══════════════════════════════════════════════════════════
ws11 = wb.create_sheet('回购明细')
ws11.sheet_properties.tabColor = TAB_YELLOW
h15 = ['组合代码', '组合名称', '市场', '资产负债',
       '证券代码', '成本', '利率', '起息日', '到期日', '占净值比', '交易对手']
for i, h in enumerate(h15, 1):
    hdr(ws11, 1, i, h)
yell(ws11, 2, 1, 200, len(h15))
for col in range(1, len(h15) + 1):
    ws11.column_dimensions[get_column_letter(col)].width = 16
ws11.freeze_panes = 'A2'

# ══════════════════════════════════════════════════════════
# 5. 其他监控-sql导入数据
# ══════════════════════════════════════════════════════════
ws9 = wb.create_sheet('其他监控-sql导入数据')
ws9.sheet_properties.tabColor = TAB_YELLOW

# 18 → A4
lbl(ws9, 2, 1, '18_online_channel.sql  →  A4')
for i, h in enumerate(['组合名称', '网商渠道存量(亿份)'], 1):
    hdr(ws9, 3, i, h)
yell(ws9, 4, 1, 10, 2)

# 19 → D4
lbl(ws9, 2, 4, '19_wam_detail.sql  →  D4')
for i, h in enumerate(['组合名称', '加权平均剩余期限(天)'], 4):
    hdr(ws9, 3, i, h)
yell(ws9, 4, 4, 10, 5)

# 39 → A16
lbl(ws9, 14, 1, '39_ib_overnight_repo.sql  →  A16')
h39 = ['组合名称', '估值日', '到期日', '交易对手', '本金', '占净值比']
for i, h in enumerate(h39, 1):
    hdr(ws9, 15, i, h)
yell(ws9, 16, 1, 24, len(h39))

# 41 → A27
lbl(ws9, 25, 1, '41_bank_deposit_dist.sql  →  A27')
h41 = ['组合名称', '银行/发行人', '3月以内(亿)', '3~6月(亿)',
       '6月~1年(亿)', '1年以上(亿)', '存款小计(亿)', '存单小计(亿)', '合计(亿)']
for i, h in enumerate(h41, 1):
    hdr(ws9, 26, i, h)
yell(ws9, 27, 1, 45, len(h41))

for col in range(1, 15):
    ws9.column_dimensions[get_column_letter(col)].width = 16

# ══════════════════════════════════════════════════════════
# 6. shibor债定价  (留空供 Wind 公式)
# ══════════════════════════════════════════════════════════
ws13 = wb.create_sheet('shibor债定价')
ws13.sheet_properties.tabColor = TAB_RED
ws13['A1'] = ('【shibor 債定價】浮息債壓力定價 '
              '— 需在 Wind 環境填入 b_dq_close / b_anal_yield_cnbd / b_calc_price 公式')
ws13['A1'].font = Font(color='808080', size=9)
ws13.column_dimensions['A'].width = 80

# ══════════════════════════════════════════════════════════
# 7. 计算过程  (全新，輔助計算中間層)
# ══════════════════════════════════════════════════════════
wsc = wb.create_sheet('计算过程')
wsc.sheet_properties.tabColor = TAB_RED

# 說明區
wsc['A1'] = '【計算過程】中間計算輔助層'
wsc['A1'].font = Font(bold=True, size=12)
wsc['A2'] = '供壓力測試、WAM/WAL 等中間計算使用，引用持仓数据，結果供债券及存单新引用'
wsc['A2'].font = Font(color='808080', size=9)

# ── 區塊 A：WAM / WAL 加權計算（行 5 起）─────────────────
lbl(wsc, 4, 1, 'WAM / WAL 計算區')
h_wam = ['组合名称', '证券代码', '市值', '占净值比(%)', '剩余天数', 'WAM贡献(天)', 'WAL贡献(天)']
for i, h in enumerate(h_wam, 1):
    hdr(wsc, 5, i, h)
wsc['A6'] = '← 從持仓数据引用數據，公式填入後自動計算'
wsc['A6'].font = Font(color='808080', size=9, italic=True)
yell(wsc, 7, 1, 50, len(h_wam))

# WAM/WAL 匯總
lbl(wsc, 52, 1, 'WAM / WAL 匯總')
for i, h in enumerate(['组合名称', '加权平均期限WAM(天)', '加权平均存续期WAL(天)',
                        'WAM是否超限(60天)', 'WAL是否超限(120天)'], 1):
    hdr(wsc, 53, i, h)
yell(wsc, 54, 1, 58, 5)

# ── 區塊 B：流動性計算（行 61 起）───────────────────────
lbl(wsc, 60, 1, '日/週流動性計算區')
h_liq = ['组合名称', '证券代码', '证券类型', '到期日', '剩余天数',
          '市值(元)', '占NAV比(%)', '计入日流动', '计入周流动']
for i, h in enumerate(h_liq, 1):
    hdr(wsc, 61, i, h)
yell(wsc, 62, 1, 110, len(h_liq))

# 流動性匯總
lbl(wsc, 112, 1, '流動性比率匯總')
for i, h in enumerate(['组合名称', '净资产(NAV)', '日流动资产', '日流动比率(%)',
                        '是否达标(≥7.5%)', '周流动资产', '周流动比率(%)', '是否达标(≥15%)'], 1):
    hdr(wsc, 113, i, h)
yell(wsc, 114, 1, 118, 8)

# ── 區塊 C：壓力測試中間值（行 121 起）──────────────────
lbl(wsc, 120, 1, '壓力測試中間計算區（+50bp）')
h_st = ['组合名称', '证券代码', '利率类型', '市值(元)', '久期(年)',
        '压力市值(元)', '压力损失(元)', '占NAV比(%)']
for i, h in enumerate(h_st, 1):
    hdr(wsc, 121, i, h)
wsc['A122'] = '← 引用持仓数据 + 参数sheet 中的 shock_50bp，公式：市值×(1-久期×0.005)'
wsc['A122'].font = Font(color='808080', size=9, italic=True)
yell(wsc, 123, 1, 200, len(h_st))

# 壓力測試匯總
lbl(wsc, 202, 1, '壓力測試匯總')
for i, h in enumerate(['组合名称', '净资产(NAV)', '压力总损失(元)',
                        '占NAV比(%)', '是否超偏差警戒(0.5%)'], 1):
    hdr(wsc, 203, i, h)
yell(wsc, 204, 1, 208, 5)

for col in range(1, 12):
    wsc.column_dimensions[get_column_letter(col)].width = 16
wsc.freeze_panes = 'A3'

# ══════════════════════════════════════════════════════════
# 8. 组合
# ══════════════════════════════════════════════════════════
ws14 = wb.create_sheet('组合')
ws14.sheet_properties.tabColor = TAB_RED
ws14['A1'] = '【组合】組合參數與彙總，使用者自行設計'
ws14['A1'].font = Font(color='808080', size=9)
ws14.column_dimensions['A'].width = 50

# ══════════════════════════════════════════════════════════
# 8. 债券及存单新  (壓力測試計算層，按 Template 精確生成)
# ══════════════════════════════════════════════════════════
ws15 = wb.create_sheet('债券及存单新')
ws15.sheet_properties.tabColor = TAB_RED

YEL      = PatternFill('solid', fgColor='FFFF00')
YEL_ARGB = PatternFill('solid', fgColor='FFFF00')          # Row 1 黃
THEME9   = PatternFill('solid', fgColor=Color(theme=9))    # Row 2 A-P 主題色9
NFMT     = '0.00_ '
MAX_ROWS = 5570
_THIN        = Side(border_style='thin')
_BORDER_THIN = Border(top=_THIN, bottom=_THIN, left=_THIN, right=_THIN)
_ALIGN_CTR   = Alignment(horizontal='center', vertical='center', wrap_text=True)
_ALIGN_H_CTR = Alignment(horizontal='center')   # 水平置中，無垂直設定

# ── Row 1：參數行 ─────────────────────────────────────────
ws15.row_dimensions[1].height = 14.5
# A1: Arial bold 紅色; B1/M1/N1: Arial bold; Q1: 宋体 bold
ws15['A1'].value          = '=TDaysOffset(TODAY(),"Offset=-1")'
ws15['A1'].number_format  = 'yyyy\\-mm\\-dd'
ws15['A1'].fill           = YEL
ws15['A1'].font           = Font(name='Arial', size=10, bold=True, color='FF0000')

ws15['B1'].value          = '=参数!L2'
ws15['B1'].number_format  = 'mm-dd-yy'
ws15['B1'].fill           = YEL
ws15['B1'].font           = Font(name='Arial', size=10, bold=True)

ws15['M1'].value          = 'FIXED'   # 對應 SQL 輸出 coupon_type=FIXED
ws15['M1'].fill           = YEL
ws15['M1'].font           = Font(name='Arial', size=10, bold=True)

ws15['N1'].value          = '0.005'
ws15['N1'].number_format  = '0.00%'
ws15['N1'].fill           = YEL
ws15['N1'].font           = Font(name='Arial', size=10, bold=True)

ws15['Q1'].value          = '公式列'
ws15['Q1'].number_format  = '0.0000_ '
ws15['Q1'].font           = Font(name='宋体', size=10, bold=True)
ws15['Q1'].border         = _BORDER_THIN

# ── Row 2：表頭（thin 四邊框 + center/wrap + size=10）────
# A-P: Microsoft Sans Serif；Q-Y: 宋体
ws15.row_dimensions[2].height = 48.0
_H2 = [
    # (col, text, fmt, fill, font_name)
    # A-P: theme color 9；Q-Y: 黃色 FFFF00
    ('A','组合名称',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('B','证券类型',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('C','证券代码',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('D','证券名称',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('E','数量',                         NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('F','成本',                         NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('G','市值净价',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('H','成本全价',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('I','影价偏离度',                   NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('J','市值占净值比（%）',            NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('K','偏离金额（万元）',             NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('L','到期日',                       NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('M','利率类型',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('N','久期',                         NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('O','评级',                         NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('P','是否当季到期',                 NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('Q','压力情景净价(亿元)',           '0.0000_ ', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('R','压力情景全价(亿元)',           '0.0000_ ', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('S','压力情景偏离金额(万元)',       '#,##0.00', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('T','压力情景偏离金额绝对值(万元)', '#,##0.00', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('U','债券类别',                     NFMT,       PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('V','变现系数',                     NFMT,       PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('W','压力情景全价修正(亿元)',       '0.0000_ ', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('X','压力情景偏离金额修正(万元)',   NFMT,       PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('Y','需变现偏离资产金额（亿元）',   NFMT,       PatternFill('solid', fgColor='FFFF00'), '宋体'),
]
for col, text, fmt, fill, font_name in _H2:
    c = ws15[col + '2']
    c.value = text; c.number_format = fmt
    c.font      = Font(name=font_name, size=10, bold=True)
    c.border    = _BORDER_THIN
    c.alignment = _ALIGN_CTR
    c.fill      = fill

# ── AA 欄：組合名稱參考列表 ───────────────────────────────
_AA = ['组合名称','薪金宝','现金增利','现金宝','沃利货币',
       '天利货币','收益宝','快线货币','惠利货币','华夏货币','财富宝','保证金货币']
for i, v in enumerate(_AA, 3):
    c = ws15.cell(row=i, column=27, value=v)
    c.number_format = NFMT
    c.border        = _BORDER_THIN
    c.alignment     = _ALIGN_CTR

# ── Q 欄公式模板（Row n，n >= 3）────────────────────────
_Q = (
    '=IF(M{n}=$M$1,G{n}-$N$1*N{n}*G{n},'
    'IF(C{n}="160309",VLOOKUP($A$1,shibor债定价!$A:$F,6,FALSE)*E{n},'
    'IF(C{n}="130208",VLOOKUP($A$1,shibor债定价!$AQ:$BC,6,FALSE)*E{n},'
    'IF(C{n}="160305",VLOOKUP($A$1,shibor债定价!$O:$T,6,FALSE)*E{n},'
    'IF(C{n}="110236",VLOOKUP($A$1,shibor债定价!#REF!,6,FALSE)*E{n},'
    'IF(C{n}="160202",VLOOKUP($A$1,shibor债定价!$AC:$AO,6,FALSE)*E{n},'
    'IF(C{n}="110236",VLOOKUP($A$1,shibor债定价!#REF!,6,FALSE)*E{n},'
    'IF(C{n}="150315",VLOOKUP($A$1,shibor债定价!$AQ:$AZ,6,FALSE)*E{n},'
    'IF(C{n}="130235",VLOOKUP($A$1,shibor债定价!$BE:$BN,6,FALSE)*E{n},'
    '0)))))))))/10^8'
)
_DATA_COLS = list('ABCDEFGHIJKLMNOP')

# ── Rows 3~MAX_ROWS：公式行 ───────────────────────────────
# 每欄的格式設定（col索引, fmt, alignment）
# A-P(1-16): General, center水平; Q/R(17-18): 0.0000_, 無align;
# S/T(19-20): #,##0.00, 無align; U/V(21-22): General, center;
# W(23): 0.0000_, center; X(24): 0.00_, center; Y(25): 0.00, center
_COL_CFG = {
    **{ci: ('General',   _ALIGN_H_CTR) for ci in range(1, 17)},   # A-P
    17: ('0.0000_ ',  None),          # Q
    18: ('0.0000_ ',  None),          # R
    19: ('#,##0.00',  None),          # S
    20: ('#,##0.00',  None),          # T
    21: ('General',   _ALIGN_H_CTR),  # U
    22: ('General',   _ALIGN_H_CTR),  # V
    23: ('0.0000_ ',  _ALIGN_H_CTR),  # W
    24: ('0.00_ ',    _ALIGN_H_CTR),  # X
    25: ('0.00',      _ALIGN_H_CTR),  # Y
}

print('  生成 债券及存单新 公式行...')
for row in range(3, MAX_ROWS + 1):
    src = row - 1
    n   = row
    # A:P — 引用持仓数据（宋体 size=10）
    for ci, cl in enumerate(_DATA_COLS, 1):
        c = ws15.cell(row=row, column=ci, value=f'=持仓数据!{cl}{src}')
        c.font      = Font(name='宋体', size=10)
        c.border    = _BORDER_THIN
        c.alignment = _ALIGN_H_CTR

    # Q~X — VLOOKUP 引用 压力测试结果 sheet（組合鍵 = port_name | security_code）
    # 压力测试结果 欄位：A=key, B=port, C=sec_code, ...,
    #   I(9)=stressed_mv_100m, J(10)=stressed_loss, K(11)=abs,
    #   L(12)=bond_category, M(13)=liq_ratio, N(14)=stressed_mv_adj_100m, O(15)=stressed_loss_adj
    _key = f'A{n}&"|"&C{n}'
    _lkp = lambda col: f'=IFERROR(VLOOKUP({_key},压力测试结果!$A:$O,{col},0),0)'

    def _qcell(ws_col, src_col, fmt=None, align=None):
        c = ws15.cell(row=row, column=ws_col, value=_lkp(src_col))
        c.font   = Font(name='宋体', size=11)
        c.border = _BORDER_THIN
        if fmt:   c.number_format = fmt
        if align: c.alignment     = align

    _qcell(17,  9, '0.0000_ ')                  # Q: 压力情景净价(亿元)
    _qcell(18,  9, '0.0000_ ')                  # R: 压力情景全价(亿元) ≈ Q
    _qcell(19, 10, '#,##0.00')                  # S: 压力偏离金额(万元)
    _qcell(20, 11, '#,##0.00')                  # T: 偏离绝对值(万元)
    _qcell(21, 12, 'General', _ALIGN_H_CTR)     # U: 债券类别
    _qcell(22, 13, 'General', _ALIGN_H_CTR)     # V: 变现系数
    _qcell(23, 14, '0.0000_ ', _ALIGN_H_CTR)   # W: 全价修正(亿元)
    _qcell(24, 15, NFMT,       _ALIGN_H_CTR)   # X: 偏离修正(万元)

    if row % 1000 == 0:
        print(f'    {row}/{MAX_ROWS}')

# ── 欄寬 ──────────────────────────────────────────────────
_CW = {'A':13.18,'B':10.36,'C':16.18,'E':11.0,
       'F':15.36,'G':15.09,'H':14.27,'I':11.45,'J':9.82,
       'L':16.45,'M':9.82,'P':10.91,
       'Q':12.36,'R':9.82,'S':10.36,'T':9.82,
       'W':9.82,'X':11.0,'Y':11.45}
for col, w in _CW.items():
    ws15.column_dimensions[col].width = w

# ══════════════════════════════════════════════════════════
# 9. 压力测试结果  (42_stress_result.sql → A2，SQL 直接計算)
# ══════════════════════════════════════════════════════════
ws42 = wb.create_sheet('压力测试结果')
ws42.sheet_properties.tabColor = TAB_BLUE
_H42 = ['组合名称','证券代码','证券名称','资产类型','利率类型',
        '当前市值(元)','有效久期(年)','压力市值(元)',
        '压力损失(万元)','债券类别','变现系数','压力损失修正(万元)']
for i, h in enumerate(_H42, 1):
    hdr(ws42, 1, i, h)
yell(ws42, 2, 1, 200, len(_H42))
for col in range(1, len(_H42) + 1):
    ws42.column_dimensions[get_column_letter(col)].width = 16
ws42.freeze_panes = 'A2'

# ══════════════════════════════════════════════════════════
# 10. 债券及存单新程序结果NEW
# ══════════════════════════════════════════════════════════
ws16 = wb.create_sheet('债券及存单新程序结果NEW')
ws16.sheet_properties.tabColor = TAB_BLUE
ws16['A1'] = '【債券及存單新程序結果 NEW】新版壓力測試結果，使用者自行設計'
ws16['A1'].font = Font(color='808080', size=9)
ws16.column_dimensions['A'].width = 60

# ══════════════════════════════════════════════════════════
# 10. 参数
# ══════════════════════════════════════════════════════════
ws17 = wb.create_sheet('参数')
ws17.sheet_properties.tabColor = TAB_RED
for i, h in enumerate(['参数名称', '参数值', '说明'], 1):
    hdr(ws17, 1, i, h)
params = [
    ('rate_shock_bps',  50,       '利率衝擊幅度（基點），壓力測試用'),
    ('evaluate_date',   '',       '估值日期，由 run_report.py 注入'),
    ('coupon_type_fi',  'FIXED',  '固定利率類型代碼'),
    ('coupon_type_fl',  'FLOAT',  '浮息類型代碼'),
    ('coupon_type_zc',  'ZERO',   '零息/貼現券類型代碼'),
    ('shock_50bp',      0.005,    '+50bp（小數），= rate_shock_bps / 10000'),
]
for row, (name, val, desc) in enumerate(params, 2):
    ws17.cell(row=row, column=1, value=name)
    ws17.cell(row=row, column=2, value=val)
    ws17.cell(row=row, column=3, value=desc)
ws17.column_dimensions['A'].width = 20
ws17.column_dimensions['B'].width = 12
ws17.column_dimensions['C'].width = 40

# ── F1:N1 行 ─────────────────────────────────────────────
ws17['F1'] = '当前日期所在月倒数第5个交易日'
ws17['K1'] = '今天'
ws17['L1'].value         = '=TODAY()'
ws17['L1'].number_format = 'mm-dd-yy'
ws17['M1'].value         = '=TODAY()'
ws17['M1'].number_format = 'mm-dd-yy'
ws17['N1'] = '=TDays(G1,"2026-12-15","TradingCalendar=HKEX")'

# ── F2:L2 行 ─────────────────────────────────────────────
BLUE_CELL = PatternFill('solid', fgColor='00B0F0')
ws17['F2'].value         = ('=IF(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1)-1'
                             '=WORKDAY(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1),-1),'
                             'WORKDAY(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1)-1,-4),'
                             'WORKDAY(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1)-1,-5))')
ws17['F2'].fill          = BLUE_CELL
ws17['F2'].number_format = 'mm-dd-yy'
ws17['K2'] = '5个交易日后'
ws17['L2'].value         = '=N5'
ws17['L2'].number_format = 'mm-dd-yy'

ws17.column_dimensions['F'].width = 30
ws17.column_dimensions['K'].width = 14
ws17.column_dimensions['L'].width = 14
ws17.column_dimensions['M'].width = 14
ws17.column_dimensions['N'].width = 14

# ── 保存 ─────────────────────────────────────────────────
dest = Path('D:/vsproject/fsi-risk-platform/2_processing/sql/mmf/report_03_mmf/Template.xlsx')
wb.save(dest)
print(f'已創建: {dest}')
print(f'Sheets ({len(wb.sheetnames)}):')
for name in wb.sheetnames:
    print(f'  • {name}')
