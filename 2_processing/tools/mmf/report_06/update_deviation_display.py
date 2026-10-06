"""
update_deviation_display.py — 「影子定价偏离度」展示層 VNAV 改造（v2 需求第2/5點）
=====================================
· 改名「基金影子定價偏離度」（VNAV 下保留成本/影子價值監控，去偏離度 BP）
· 列頭去偏離度 4 列（目前/輕度/中度/重度）
· 公式引用改「基金原始成本影子定价偏离度原始」（改名後的原始表）
· 列對齊 SQL 輸出（A 組合名稱 B 組合代碼 + 15 數據列）
"""
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

BASE = Path(__file__).resolve().parents[4]
TMPL = BASE / "2_processing" / "sql" / "mmf" / "report_06" / "Template.xlsx"

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
CENTER = Alignment(horizontal="center", vertical="center")

# SQL 輸出（05_deviation_analysis.sql）：A 名稱 B 代碼 + 5組×(成本/影子價值/久期)
HEADERS = [
    "日期", "组合名称", "组合代码",
    "利率债成本合计(亿)", "利率债影子价值合计(亿)", "利率债平均久期(年)",
    "AAA级信用债成本合计(亿)", "AAA级信用债影子价值合计(亿)", "AAA级信用债平均久期(年)",
    "AAA级存单成本合计(亿)", "AAA级存单影子价值合计(亿)", "AAA级存单平均久期(亿)",
    "AA+级信用债成本合计(亿)", "AA+级信用债影子价值合计(亿)", "AA+级信用债平均久期(年)",
    "AA+级存单成本合计(亿)", "AA+级存单影子价值合计(亿)", "AA+级存单平均久期(年)",
]

def main() -> None:
    wb = load_workbook(TMPL)

    if "影子定价偏离度" in wb.sheetnames:
        del wb["影子定价偏离度"]
    ws = wb.create_sheet("基金影子定價偏離度", 14)  # 插到「可提前支取协议存款自然到期表」後
    for ci, h in enumerate(HEADERS, start=1):
        c = ws.cell(row=1, column=ci, value=h)
        c.fill, c.font, c.alignment = HDR_FILL, HDR_FONT, CENTER
    # 數據行公式：引用改名後的原始 sheet（06_05 SQL 寫入 A2 起，每組合 1 行）
    # R2 起：A=日期(TODAY-1) B=組合名稱 C=組合代碼 D~R=數據
    # 原始 sheet：A 名稱 B 代碼 C~Q 15 數據列
    raw_cols = {"利率债": "C", "AAA信": "F", "AAA存": "I", "AA+信": "L", "AA+存": "O"}
    for i in range(2, 4):  # 預置 2 組合公式行
        ws.cell(row=i, column=1, value='=TEXT(TODAY()-1,"yyyymmdd")')
        # B/C: 組合名稱/代碼直接引用原始表 A/B 列
        ws.cell(row=i, column=2, value=f"='基金原始成本影子定价偏离度原始'!A{i}")
        ws.cell(row=i, column=3, value=f"='基金原始成本影子定价偏离度原始'!B{i}")
        # D~R: 15 數據列 = 原始表 C~Q（久期列 ROUND 2 位）
        for j, data_col in enumerate(range(3, 18)):  # raw C..Q
            disp_col = 4 + j
            raw_letter = ws.cell(row=1, column=disp_col).column_letter
            from openpyxl.utils import get_column_letter
            raw_l = get_column_letter(data_col)
            val = f"='基金原始成本影子定价偏离度原始'!{raw_l}{i}"
            if (disp_col - 3) % 3 == 2:  # 久期列（第3列 of each group）
                val = f"=ROUND('基金原始成本影子定价偏离度原始'!{raw_l}{i},2)"
            ws.cell(row=i, column=disp_col, value=val)
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 12
    for ci in range(4, 19):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = 16

    wb.save(TMPL)
    print("display sheet rebuilt: 基金影子定價偏離度")
    print("Sheets:", wb.sheetnames)


if __name__ == "__main__":
    main()
