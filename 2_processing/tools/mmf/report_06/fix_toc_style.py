"""
fix_toc_style.py — 目錄 B13~B16 樣式對齊 B3/B4（2026-10-06）
=====================================
原樣式（B3~B12）：
  · 字體：默認字體，藍色 0563C1，單下劃線
  · 填充：奇數行 FF55B9FF（淺藍）/ 偶數行 theme=8 tint≈0.8（主題淺色）交替
  · 邊框：底部 thin
  · 行高 33，垂直居中
將 B13~B16（T+1預估 / PART11 / 口徑A詳表 / 口徑B詳表）統一為該樣式。
"""
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Border, Color, Font, PatternFill, Side
from openpyxl.styles.colors import COLOR_INDEX

BASE = Path(__file__).resolve().parents[4]
TMPL = BASE / "2_processing" / "sql" / "mmf" / "report_06" / "Template.xlsx"

ODD_FILL = PatternFill("solid", fgColor="FF55B9FF")
# 偶數行為主題色填充（theme=8, tint≈0.8），用 Color 對象複刻
EVEN_FILL = PatternFill("solid", fgColor=Color(theme=8, tint=0.7999816888943144))
LINK_FONT = Font(color="000563C1", underline="single")
BOTTOM_BORDER = Border(bottom=Side(style="thin"))
ROW_H = 33.0


def main():
    wb = load_workbook(TMPL)
    ws = wb["目录"]

    # 樣式參照行：B3（奇數模板）、B4（偶數模板）
    for r in range(13, 17):
        c = ws.cell(row=r, column=2)
        c.font = LINK_FONT
        c.fill = ODD_FILL if (r % 2 == 1) else EVEN_FILL
        c.border = BOTTOM_BORDER
        c.alignment = ws.cell(row=3, column=2).alignment.copy()
        ws.row_dimensions[r].height = ROW_H
        print(f"B{r}: 樣式已對齊（fill={'奇' if r % 2 == 1 else '偶'}, font=藍色下劃線, border=thin, 行高=33）")

    wb.save(TMPL)
    print("✓ 目錄 B13~B16 樣式統一完成")


if __name__ == "__main__":
    main()
