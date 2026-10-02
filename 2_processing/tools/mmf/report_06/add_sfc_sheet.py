"""
add_sfc_sheet.py — 在 report_06/Template.xlsx 中新增 SFC 壓力測試 sheets
=====================================
新增：
  1. 「SFC壓力測試原始」sheet — 10_sfc_stress.sql 明細數據層（A1 表頭，A2 起數據）
  2. 「SFC壓力測試」sheet — SFC 文檔 §1 Indicative Liquidity Profile 展示層
     （11_sfc_compliance_summary.sql 寫入 B4:G5 區域：Normal/Stressed × 5 檔）
  3. 更新「目录」sheet 增加 PART11
  4. 更新 report_config.json 增加 06_10 / 06_11 查詢映射

用法：cd arisk && python 2_processing/tools/mmf/report_06/add_sfc_sheet.py
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

BASE = Path(__file__).resolve().parents[4]  # arisk/
TMPL_PATH = BASE / "2_processing" / "sql" / "mmf" / "report_06" / "Template.xlsx"
CONFIG_PATH = BASE / "2_processing" / "sql" / "mmf" / "report_06" / "report_config.json"

# ── 樣式 ────────────────────────────────────────────────────
HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(bold=True, size=12)
NOTE_FONT = Font(italic=True, size=9, color="666666")
SECTION_FONT = Font(bold=True, size=11)
THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)

# ── 1. 明細數據層表頭（10_sfc_stress.sql 輸出欄位，25 列）───
DETAIL_HEADERS = [
    "组合名称", "组合代码", "证券代码", "证券名称", "资产类别", "场景",
    "当前市值(元)", "有效久期(年)", "利率冲击(bp)", "压力市值(元)", "压力损失(元)",
    "30日ADTV(元)", "市场参与率", "ADTV折扣", "日可变现规模(元)",
    "1日可变现额(元)", "5日可变现额(元)", "变现时间桶", "变现天数",
    "1日可变现%NAV", "5日可变现%NAV", "市值%NAV(分桶)", "买卖价差成本(元)",
    "净变现额(元)", "变现系数", "修正压力损失(元)", "组合NAV(元)", "ADTV来源",
]

# ── 2. 展示層（SFC 文檔表格）────────────────────────────────
def build_display_sheet(ws) -> None:
    """SFC 文檔 §1 Indicative Liquidity Profile 版式。"""
    ws["A1"] = "SFC 壓力測試 — Indicative Liquidity Profile（指示性流動性概況）"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "依據：lmt-mmf-test-sfc.docx · SFC《單位信託及互惠基金守則》§8.2 · 通函 24EC64"
    ws["A2"].font = NOTE_FONT

    # ── 表1：5 檔分層（數據從 11_sfc_compliance_summary.sql 寫入 A6 起）──
    ws["A4"] = "1. 流動性分層（非累計時間桶，每場景合計=組合資產 100%）"
    ws["A4"].font = SECTION_FONT
    headers = ["组合 / 场景", "1 Day", "2-7 Days", "8-30 Days", "31-90 Days", "> 90 Days", "合計%",
               "DLA%（≥7.5%）", "DLA狀態", "WLA%（≥15%）", "WLA狀態"]
    for ci, h in enumerate(headers, start=1):
        c = ws.cell(row=5, column=ci, value=h)
        c.fill, c.font, c.alignment, c.border = HDR_FILL, HDR_FONT, CENTER, BORDER
    # 數據行由 run_report.py 寫入 A6 起（11_sfc_compliance_summary.sql → 每組合 2 行）
    # 每行：組合名/場景 | 5 檔% | 合計% | DLA%/狀態 | WLA%/狀態（A~L 列一次寫入）

    ws["A9"] = "2. 流動性管理工具（LMT）與治理"
    ws["A9"].font = SECTION_FONT
    ws["A10"] = "如出現極端贖回壓力，將考慮運用章程允許並已在發售文件/KFS 披露的 LMT（贖回限制/反稀釋機制/公允估值）以保障投資者利益。（SFC 文檔 §2(b)）"
    ws["A10"].font = NOTE_FONT

    # ── 說明（SFC 文檔 Note i-iv）────────────────────────────
    notes = [
        "注：",
        "(i) 百分比為非累計時間桶，各場景五檔合計 = 組合資產端 100%（明細持倉覆蓋率見明細表 coverage_pct）。",
        "(ii) 任何情況下嚴格遵守《單位信託及互惠基金守則》§8.2 流動性要求：每日流動資產 ≥ 7.5%、每週流動資產 ≥ 15%（正常與壓力情景均適用）。",
        "(iii) 變現規模為在給定時間內以合理成本變現（無重大市場衝擊或過度交易成本）的組合部分估計值。",
        "(iv) 壓力情景假設：二級市場 ADTV 50% 折扣、買賣價差擴大、定期存款零提前支取（嚴格按合約到期變現）、極端市況下的潛在結算/匯款延遲。",
        "",
        "方法論（Basis of Liquidity Classification 摘要）：",
        "· 合約現金流：按剩餘期限與結算週期（T+0/T+1）分類，桶內合約到期視為到期現金。",
        "· 二級市場變現（到期前賣出）：按過去 30 日 ADTV 的 10% 最大市場參與率估算變現能力。",
        "· 買賣價差與交易成本：以交易商可執行報價評估；壓力下需較高折扣/衝擊成本的工具下調至更長桶。",
        "· 提前支取/贖回成本：定期存款計入提前終止條款與罰息成本（壓力下為零早破）。",
        "· 定性因素：交易對手信用、市場基礎設施與 FX/結算（境內中國資產經 Bond Connect/QFI）、二級市場深度、流動性管理工具（LMT）治理。",
    ]
    for ri, note in enumerate(notes, start=12):
        ws.cell(row=ri, column=1, value=note).font = NOTE_FONT

    # 列寬
    widths = {"A": 34, "B": 13, "C": 13, "D": 13, "E": 13, "F": 13, "G": 12,
              "H": 14, "I": 13, "J": 13, "K": 14, "L": 13}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def build_detail_sheet(ws) -> None:
    """明細數據層：10_sfc_stress.sql 輸出，A1 表頭，A2 起數據。"""
    for ci, h in enumerate(DETAIL_HEADERS, start=1):
        c = ws.cell(row=1, column=ci, value=h)
        c.fill, c.font, c.alignment, c.border = HDR_FILL, HDR_FONT, CENTER, BORDER
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 26
    for col in ("E", "F"):
        ws.column_dimensions[col].width = 11
    for ci in range(7, len(DETAIL_HEADERS) + 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = 15
    ws.freeze_panes = "A2"


def main() -> None:
    wb = load_workbook(TMPL_PATH)

    # 明細層
    if "SFC壓力測試原始" in wb.sheetnames:
        del wb["SFC壓力測試原始"]
    ws_detail = wb.create_sheet("SFC壓力測試原始")
    build_detail_sheet(ws_detail)

    # 展示層
    if "SFC壓力測試" in wb.sheetnames:
        del wb["SFC壓力測試"]
    ws_disp = wb.create_sheet("SFC壓力測試")
    build_display_sheet(ws_disp)

    # 移動到「十全每日运作简报原始」之後，保持在原始/展示成對區
    if "T+1日可用流动性原始" in wb.sheetnames:
        wb.move_sheet("SFC壓力測試原始", offset=len(wb.sheetnames))
        wb.move_sheet("SFC壓力測試", offset=len(wb.sheetnames))

    # 目錄更新
    ws_toc = wb["目录"]
    next_part = ws_toc.max_row + 1
    ws_toc.cell(row=next_part, column=2, value="PART11.                                     SFC壓力測試（流動性壓力測試）  ")

    wb.save(TMPL_PATH)
    print(f"Template updated: {TMPL_PATH}")
    print(f"Sheets: {wb.sheetnames}")

    # ── 更新 report_config.json ─────────────────────────────
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    ids = {q["id"] for q in cfg["queries"]}
    if "06_10" not in ids:
        cfg["queries"].append({
            "id": "06_10",
            "name": "SFC壓力測試持倉明細",
            "sql": "10_sfc_stress.sql",
            "sheet": "SFC壓力測試原始",
            "start_cell": "A2",
            "header": False,
            "description": "SFC MMF壓力測試：雙場景(Normal/Stressed)持倉明細，含ADTV變現係數/利率衝擊/5檔時間桶，落庫sfc_liquidity_stress/compliance，A1=表頭，數據A2起",
        })
    if "06_11" not in ids:
        cfg["queries"].append({
            "id": "06_11",
            "name": "SFC流動性分層與合規",
            "sql": "11_sfc_compliance_summary.sql",
            "sheet": "SFC壓力測試",
            "start_cell": "A6",
            "header": False,
            "description": "SFC文檔§1 Indicative Liquidity Profile：5檔分層(1D/2-7D/8-30D/31-90D/>90D)×雙場景 + DLA≥7.5%/WLA≥15%合規，寫入B6起（前置：06_10）",
        })
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"config updated: {CONFIG_PATH} ({len(cfg['queries'])} queries)")


if __name__ == "__main__":
    main()
