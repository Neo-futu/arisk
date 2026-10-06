"""
update_template_layout.py — report_06 Template 版面升級
=====================================
按 2026-10-05 需求調整：
  1. 各「原始」sheet 列頭增加組合名稱/代碼列（與 SQL 輸出對齊）：
     · 資產分佈原始 R2：A=组合名称, B=组合代码（原 A=代码，右移）
     · 銀行存款交易對手原始 R2：同上
     · 剩餘期限結構原始 R2：A=组合名称, B=组合代码（原 A=代码，右移）
     · 資產變現原始 R1 / 信用債及質押債原始 R1 / 十全每日運作簡報原始 R1 /
       T+1日可用流動性原始 R1：A=组合名称, B=组合代码
  2. 「影子定价偏离度原始」→ 改名「基金原始成本影子定价偏离度原始」，
     列頭去掉偏離度 4 列（VNAV 無攤余成本偏離），保留成本/影子價值/久期
  3. 展示層公式引用列偏移（插列後 B→C、C→D…）
  4. 「T+1日可用流動性预估」列頭單位標注（億元）
  5. 目錄只保留 PART11/12/13（SFC 三表）

用法：cd arisk && python 2_processing/tools/mmf/report_06/update_template_layout.py
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

BASE = Path(__file__).resolve().parents[4]
TMPL = BASE / "2_processing" / "sql" / "mmf" / "report_06" / "Template.xlsx"

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
CENTER = Alignment(horizontal="center", vertical="center")


def shift_formulas_in_sheet(wb, sheet_name: str, ref_sheet: str, min_col_letter: str) -> None:
    """把 sheet_name 中引用 ref_sheet 且列字母 >= min_col 的公式右移一列。"""
    from openpyxl.utils import column_index_from_string, get_column_letter
    min_col = column_index_from_string(min_col_letter)
    ws = wb[sheet_name]
    import re
    pattern = re.compile(
        r"(" + re.escape(ref_sheet) + r"!?)(\$?)([A-Z]{1,2})(\$?)(\d+)"
    )
    for row in ws.iter_rows():
        for c in row:
            v = c.value
            if not (isinstance(v, str) and v.startswith("=") and ref_sheet in v):
                continue
            def repl(m: re.Match) -> str:
                col_letters = m.group(3)
                idx = column_index_from_string(col_letters)
                if idx >= min_col:
                    return f"{m.group(1)}{m.group(2)}{get_column_letter(idx + 1)}{m.group(4)}{m.group(5)}"
                return m.group(0)
            c.value = pattern.sub(repl, v)


def main() -> None:
    wb = load_workbook(TMPL)

    # ── 1. 原始 sheet 列頭：A=组合名称，B=组合代码 ──────────────
    # 這些 sheet 的數據從第 3 行起（R2 為列頭），SQL 寫入 A3 起
    for sheet, hdr_row in [
        ("资产分布原始", 2),
        ("银行存款交易对手原始", 2),
        ("剩余期限结构原始", 2),
    ]:
        ws = wb[sheet]
        ws.insert_cols(1)  # 預留 A=組合名稱
        c = ws.cell(row=hdr_row, column=1, value="组合名称")
        c.fill, c.font, c.alignment = HDR_FILL, HDR_FONT, CENTER
        # 原 A 列（組合代碼）已右移到 B；改列頭文字確認
        b = ws.cell(row=hdr_row, column=2)
        if b.value in ("组合代码", "组合代码", None):
            b.value = "组合代码"

    # 這些 sheet 無標題行，R1 即列頭，SQL 寫入 A2 起
    for sheet in ["资产变现原始", "信用债及质押债原始", "十全每日运作简报原始", "T+1日可用流动性原始"]:
        ws = wb[sheet]
        ws.insert_cols(1)
        c = ws.cell(row=1, column=1, value="组合名称")
        c.fill, c.font, c.alignment = HDR_FILL, HDR_FONT, CENTER
        b = ws.cell(row=1, column=2)
        if b.value in ("组合代码", None):
            b.value = "组合代码"

    # ── 2. 影子定价偏离度原始 → 基金原始成本影子定价偏离度原始 ──
    if "影子定价偏离度原始" in wb.sheetnames:
        ws = wb["影子定价偏离度原始"]
        # 插入 A=組合名稱、B=組合代碼（原 R1 無名稱/代碼列）
        ws.insert_cols(1)
        ws.insert_cols(2)
        c = ws.cell(row=1, column=1, value="组合名称")
        c.fill, c.font, c.alignment = HDR_FILL, HDR_FONT, CENTER
        c = ws.cell(row=1, column=2, value="组合代码")
        c.fill, c.font, c.alignment = HDR_FILL, HDR_FONT, CENTER
        # 刪除偏離度 4 列（現 D~G：目前偏離度/輕度/中度/重度）
        ws.delete_cols(4, 4)
        # 改名
        ws.title = "基金原始成本影子定价偏离度原始"

    # ── 3. 展示層公式偏移（插 1 列後 B→C, C→D…）───────────────
    # 這些展示層引用的原始 sheet 各插了 1 列
    for disp, ref in [
        ("资产分布情况表", "资产分布原始"),
        ("银行存款交易对手敞口数据", "银行存款交易对手原始"),
        ("投资组合剩余期限结构日报表", "剩余期限结构原始"),
        ("资产变现情况表", "资产变现原始"),
        ("信用债及质押债发行人关注清单", "信用债及质押债原始"),
        ("十全每日运作简报", "十全每日运作简报原始"),
        ("T+1日可用流动性预估", "T+1日可用流动性原始"),
    ]:
        shift_formulas_in_sheet(wb, disp, ref, "B")  # B 及以右 +1

    # ── 4. T+1 預估列頭單位標注 ────────────────────────────────
    ws = wb["T+1日可用流动性预估"]
    if ws["A1"].value and "单位" not in str(ws["A1"].value):
        ws["A1"] = str(ws["A1"].value) + " — 單位：億元（金額），非天數/百分比"

    # ── 5. 目錄只保留 PART11/12/13 ────────────────────────────
    ws_toc = wb["目录"]
    # 清空舊條目
    for row in ws_toc.iter_rows(min_row=3, max_row=ws_toc.max_row):
        for c in row:
            if c.value is not None:
                c.value = None
    toc_items = [
        "PART11.  SFC壓力測試（流動性壓力測試綜述）",
        "PART12.  SFC流動性分層（口徑A：變現天數歸桶）",
        "PART13.  SFC_DLA_WLA合規（口徑B：ADTV約束覆蓋能力）",
    ]
    r = 3
    for item in toc_items:
        ws_toc.cell(row=r, column=2, value=item)
        r += 1

    wb.save(TMPL)
    print(f"Template updated: {TMPL}")
    print("Sheets:", wb.sheetnames)


if __name__ == "__main__":
    main()
