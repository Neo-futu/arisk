"""
create_template.py  —  全新建立 report_03_mmf/Template.xlsx
執行：python 2_processing/sql/mmf/report_03_mmf/create_template.py
"""
import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
from datetime import date

# HKEX 交易日曆（2026-07-01 至 2026-12-15，從 Wind TDays 取得後靜態固化）
HKEX_TRADING_DAYS = [
    date(2026,7,1),  date(2026,7,2),  date(2026,7,3),  date(2026,7,6),
    date(2026,7,7),  date(2026,7,8),  date(2026,7,9),  date(2026,7,10),
    date(2026,7,13), date(2026,7,14), date(2026,7,15), date(2026,7,16),
    date(2026,7,17), date(2026,7,20), date(2026,7,21), date(2026,7,22),
    date(2026,7,23), date(2026,7,24), date(2026,7,27), date(2026,7,28),
    date(2026,7,29), date(2026,7,30), date(2026,7,31), date(2026,8,3),
    date(2026,8,4),  date(2026,8,5),  date(2026,8,6),  date(2026,8,7),
    date(2026,8,10), date(2026,8,11), date(2026,8,12), date(2026,8,13),
    date(2026,8,14), date(2026,8,17), date(2026,8,18), date(2026,8,19),
    date(2026,8,20), date(2026,8,21), date(2026,8,24), date(2026,8,25),
    date(2026,8,26), date(2026,8,27), date(2026,8,28), date(2026,8,31),
    date(2026,9,1),  date(2026,9,2),  date(2026,9,3),  date(2026,9,4),
    date(2026,9,7),  date(2026,9,8),  date(2026,9,9),  date(2026,9,10),
    date(2026,9,11), date(2026,9,14), date(2026,9,15), date(2026,9,16),
    date(2026,9,17), date(2026,9,18), date(2026,9,21), date(2026,9,22),
    date(2026,9,23), date(2026,9,24), date(2026,9,28), date(2026,9,29),
    date(2026,9,30), date(2026,10,8), date(2026,10,9), date(2026,10,12),
    date(2026,10,13),date(2026,10,14),date(2026,10,15),date(2026,10,16),
    date(2026,10,19),date(2026,10,20),date(2026,10,21),date(2026,10,22),
    date(2026,10,23),date(2026,10,26),date(2026,10,27),date(2026,10,28),
    date(2026,10,29),date(2026,10,30),date(2026,11,2), date(2026,11,3),
    date(2026,11,4), date(2026,11,5), date(2026,11,6), date(2026,11,9),
    date(2026,11,10),date(2026,11,11),date(2026,11,12),date(2026,11,13),
    date(2026,11,16),date(2026,11,17),date(2026,11,18),date(2026,11,19),
    date(2026,11,20),date(2026,11,23),date(2026,11,24),date(2026,11,25),
    date(2026,11,26),date(2026,11,27),date(2026,11,30),date(2026,12,1),
    date(2026,12,2), date(2026,12,3), date(2026,12,4), date(2026,12,7),
    date(2026,12,8), date(2026,12,9), date(2026,12,10),date(2026,12,11),
    date(2026,12,14),date(2026,12,15),
]

from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
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
# 8. 债券及存单新
# ══════════════════════════════════════════════════════════
ws15 = wb.create_sheet('债券及存单新')
ws15.sheet_properties.tabColor = TAB_RED
ws15['A1'] = '【債券及存單新】壓力測試計算層 — 引用「持仓数据」sheet，使用者填入公式'
ws15['A1'].font = Font(color='808080', size=9)
ws15.column_dimensions['A'].width = 60

# ══════════════════════════════════════════════════════════
# 9. 债券及存单新程序结果NEW
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

# ── A~C：基礎參數 ──────────────────────────────────────
for i, h in enumerate(['参数名称', '参数值', '说明'], 1):
    hdr(ws17, 1, i, h)
base_params = [
    ('rate_shock_bps',  50,       '利率衝擊幅度（基點），壓力測試用'),
    ('evaluate_date',   '',       '估值日期，由 run_report.py 注入'),
    ('coupon_type_fi',  'FIXED',  '固定利率類型代碼'),
    ('coupon_type_fl',  'FLOAT',  '浮息類型代碼'),
    ('coupon_type_zc',  'ZERO',   '零息/貼現券類型代碼'),
    ('shock_50bp',      0.005,    '+50bp（小數），= rate_shock_bps / 10000'),
]
for row, (name, val, desc) in enumerate(base_params, 2):
    ws17.cell(row=row, column=1, value=name)
    ws17.cell(row=row, column=2, value=val)
    ws17.cell(row=row, column=3, value=desc)

# ── F：當月倒數第5交易日 ───────────────────────────────
ws17['F1'] = '当前日期所在月倒数第5个交易日'
ws17['F1'].font = Font(bold=True, size=9)
ws17['F2'] = ('=IF(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1)-1'
              '=WORKDAY(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1),-1),'
              'WORKDAY(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1)-1,-4),'
              'WORKDAY(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1)-1,-5))')

# ── K~N：今日 / 5交易日後 / HKEX 交易日曆 ─────────────
ws17['K1'] = '今天'
ws17['K1'].font = Font(bold=True, size=9)
ws17['K2'] = '5个交易日后'
ws17['K2'].font = Font(bold=True, size=9)
ws17['L1'] = '=TODAY()'
ws17['L2'] = '=N5'
ws17['M1'] = '=TODAY()'
ws17['N1'] = '=[1]!TDays(G1,"2026-12-15","HKEX","cols=1;rows=115")'
# N2:N115 靜態 HKEX 交易日（Wind 取得後固化）
for i, d in enumerate(HKEX_TRADING_DAYS, 2):
    c = ws17.cell(row=i, column=14, value=d)
    c.number_format = 'YYYY-MM-DD'

ws17.column_dimensions['A'].width = 20
ws17.column_dimensions['B'].width = 12
ws17.column_dimensions['C'].width = 40
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
