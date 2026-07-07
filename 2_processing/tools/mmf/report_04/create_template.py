"""
create_template.py  —  生成 report_04_mmf_monthly/Template.xlsx
執行：python 2_processing/sql/mmf/report_04_mmf_monthly/create_template.py

月報 XLSX 模版，對應 ChinaAMC Select MMF Factsheet 格式：
  01_基金資料    基金基本資訊（規模、WAM/WAL、7日年化）
  02_各類別NAV   各股份類別每股淨值
  03_累積表現    1M/3M/6M/1Y/自成立/年化/7日年化
  04_年度表現    2021-本年至今年度業績
  05_組合特點    WAM/WAL/YTM/持倉數
  06_資產配置    資產類別佔NAV%
  07_到期分佈    到期日區間佔NAV%
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from pathlib import Path

# ── 顏色主題（仿 ChinaAMC 藍色系）──────────────────────────
DEEP_BLUE  = PatternFill('solid', fgColor='1F3864')   # 深藍（主標題）
MID_BLUE   = PatternFill('solid', fgColor='2E75B6')   # 中藍（表頭）
LIGHT_BLUE = PatternFill('solid', fgColor='D9E2F3')   # 淺藍（交替行）
YELLOW     = PatternFill('solid', fgColor='FFF2CC')   # 黃（數據區）
WHITE      = PatternFill('solid', fgColor='FFFFFF')   # 白
TAB_BLUE   = '2E75B6'
TAB_GREEN  = '70AD47'
TAB_ORANGE = 'ED7D31'

_TH = Side(border_style='thin')
_MD = Side(border_style='medium')

def _bd(t=None, b=None, l=None, r=None):
    return Border(top=t, bottom=b, left=l, right=r)

def hdr(ws, row, col, text, fill=MID_BLUE, font_color='FFFFFF'):
    c = ws.cell(row=row, column=col, value=text)
    c.fill = fill
    c.font = Font(bold=True, size=9, color=font_color)
    c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    c.border = _bd(t=_TH, b=_TH, l=_TH, r=_TH)
    return c

def title(ws, row, col, text, span=1):
    c = ws.cell(row=row, column=col, value=text)
    c.fill = DEEP_BLUE
    c.font = Font(bold=True, size=11, color='FFFFFF')
    c.alignment = Alignment(horizontal='left', vertical='center')
    if span > 1:
        ws.merge_cells(start_row=row, start_column=col,
                       end_row=row, end_column=col + span - 1)
    return c

def yell(ws, r1, c1, r2, c2):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(row=r, column=c).fill = YELLOW


wb = Workbook()
wb.remove(wb.active)

# ══════════════════════════════════════════════════════════
# Sheet 1：01_基金資料
# ══════════════════════════════════════════════════════════
ws1 = wb.create_sheet('01_基金資料')
ws1.sheet_properties.tabColor = TAB_BLUE
title(ws1, 1, 1, '基金基本資料  ←  01_fund_info.sql', 7)
h1 = ['組合名稱', '基礎貨幣', '基金規模(億)', 'WAM(天)', 'WAL(天)', '7日年化(%)', '估值日期']
for i, h in enumerate(h1, 1):
    hdr(ws1, 2, i, h)
yell(ws1, 3, 1, 20, len(h1))
for col in range(1, len(h1) + 1):
    ws1.column_dimensions[get_column_letter(col)].width = 16
ws1.freeze_panes = 'A3'

# ══════════════════════════════════════════════════════════
# Sheet 2：02_各類別NAV
# ══════════════════════════════════════════════════════════
ws2 = wb.create_sheet('02_各類別NAV')
ws2.sheet_properties.tabColor = TAB_BLUE
title(ws2, 1, 1, '各股份類別每股淨值  ←  02_nav_by_class.sql', 8)
h2 = ['組合名稱', '類別代碼', '類別名稱', '每股淨值', '類別資產淨值(元)', '發行單位數', '成立日期', '估值日期']
for i, h in enumerate(h2, 1):
    hdr(ws2, 2, i, h)
yell(ws2, 3, 1, 20, len(h2))
for col in range(1, len(h2) + 1):
    ws2.column_dimensions[get_column_letter(col)].width = 16
ws2.freeze_panes = 'A3'

# ══════════════════════════════════════════════════════════
# Sheet 3：03_累積表現
# ══════════════════════════════════════════════════════════
ws3 = wb.create_sheet('03_累積表現')
ws3.sheet_properties.tabColor = TAB_GREEN
title(ws3, 1, 1, '累積業績表現  ←  03_performance.sql', 13)
h3 = ['組合名稱', '類別', '近1個月(%)', '近3個月(%)', '近6個月(%)',
      '近1年(%)', '自成立(%)', '年化(%)', '7日年化(%)',
      '成立日期', '本年至今(%)', '估值日期', '成立年數']
for i, h in enumerate(h3, 1):
    hdr(ws3, 2, i, h)
yell(ws3, 3, 1, 20, len(h3))
for col in range(1, len(h3) + 1):
    ws3.column_dimensions[get_column_letter(col)].width = 14
ws3.freeze_panes = 'A3'

# ══════════════════════════════════════════════════════════
# Sheet 4：04_年度表現
# ══════════════════════════════════════════════════════════
ws4 = wb.create_sheet('04_年度表現')
ws4.sheet_properties.tabColor = TAB_GREEN
title(ws4, 1, 1, '年度業績表現  ←  04_annual_performance.sql', 6)
h4 = ['組合名稱', '類別', '年份', '年度表現(%)', '年初淨值', '年末淨值']
for i, h in enumerate(h4, 1):
    hdr(ws4, 2, i, h)
yell(ws4, 3, 1, 50, len(h4))
for col in range(1, len(h4) + 1):
    ws4.column_dimensions[get_column_letter(col)].width = 16
ws4.freeze_panes = 'A3'

# ══════════════════════════════════════════════════════════
# Sheet 5：05_組合特點
# ══════════════════════════════════════════════════════════
ws5 = wb.create_sheet('05_組合特點')
ws5.sheet_properties.tabColor = TAB_ORANGE
title(ws5, 1, 1, '投資組合特點  ←  05_portfolio_chars.sql', 6)
h5 = ['組合名稱', 'WAM(天)', 'WAL(天)', '加權平均YTM(%)', '基金規模(億)', '持倉數量']
for i, h in enumerate(h5, 1):
    hdr(ws5, 2, i, h)
yell(ws5, 3, 1, 20, len(h5))
for col in range(1, len(h5) + 1):
    ws5.column_dimensions[get_column_letter(col)].width = 18
ws5.freeze_panes = 'A3'

# ══════════════════════════════════════════════════════════
# Sheet 6：06_資產配置
# ══════════════════════════════════════════════════════════
ws6 = wb.create_sheet('06_資產配置')
ws6.sheet_properties.tabColor = TAB_ORANGE
title(ws6, 1, 1, '資產類別分佈  ←  06_asset_allocation.sql', 5)
h6 = ['組合名稱', '資產類別代碼', '資產類別（中文）', '市值(億)', '佔NAV比例(%)']
for i, h in enumerate(h6, 1):
    hdr(ws6, 2, i, h)
yell(ws6, 3, 1, 40, len(h6))
for col in range(1, len(h6) + 1):
    ws6.column_dimensions[get_column_letter(col)].width = 20
ws6.freeze_panes = 'A3'

# ══════════════════════════════════════════════════════════
# Sheet 7：07_到期分佈
# ══════════════════════════════════════════════════════════
ws7 = wb.create_sheet('07_到期分佈')
ws7.sheet_properties.tabColor = TAB_ORANGE
title(ws7, 1, 1, '到期日分佈  ←  07_maturity_dist.sql', 5)
h7 = ['組合名稱', '排序', '到期區間', '市值(億)', '佔NAV比例(%)']
for i, h in enumerate(h7, 1):
    hdr(ws7, 2, i, h)
yell(ws7, 3, 1, 40, len(h7))
for col in range(1, len(h7) + 1):
    ws7.column_dimensions[get_column_letter(col)].width = 16
ws7.freeze_panes = 'A3'

# ══════════════════════════════════════════════════════════
# 保存
# ══════════════════════════════════════════════════════════
dest = Path('D:/vsproject/arisk/2_processing/sql/mmf/report_04_mmf_monthly/Template.xlsx')
wb.save(dest)
print(f'已創建: {dest}')
for name in wb.sheetnames:
    print(f'  • {name}')
