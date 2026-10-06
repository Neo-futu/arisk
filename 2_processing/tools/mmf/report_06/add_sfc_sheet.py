"""
add_sfc_sheet.py — 在 report_06/Template.xlsx 中新增/更新 SFC 壓力測試 sheets（v3：雙表格版式）
=====================================
「SFC壓力測試」綜述 sheet 版式（兩個獨立表格塊）：
  表格1 流動性分層（口徑A）  — 標題 R4 / 表頭 R5 / 數據 R6 起（11_sfc_bucket_summary.sql，7列）
  表格2 DLA/WLA 合規（口徑B）— 標題 R12 / 表頭 R13 / 數據 R14 起（14_sfc_dla_wla_summary.sql，5列）
  說明區 R20 起（Note i-iv + LMT + 方法論）

其他 sheets：
  「SFC壓力測試原始」（10_sfc_stress.sql，28列明細）
  「SFC流動性分層」（12_sfc_bucket_profile.sql，7列，口徑A詳表）
  「SFC_DLA_WLA合規」（13_sfc_dla_wla.sql，9列，口徑B詳表）

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

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(bold=True, size=14)
NOTE_FONT = Font(italic=True, size=9, color="666666")
SECTION_FONT = Font(bold=True, size=11)
THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")

DETAIL_HEADERS = [
    "组合名称", "组合代码", "证券代码", "证券名称", "资产类别", "场景",
    "当前市值(元)", "有效久期(年)", "利率冲击(bp)", "压力市值(元)", "压力损失(元)",
    "30日ADTV(元)", "市场参与率", "ADTV折扣", "日可变现规模(元)",
    "1日可变现额(元)", "5日可变现额(元)", "变现时间桶", "变现天数",
    "1日可变现%NAV", "5日可变现%NAV", "市值%NAV(分桶)", "买卖价差成本(元)",
    "净变现额(元)", "变现系数", "修正压力损失(元)", "组合NAV(元)", "ADTV来源",
]

BUCKET_HDRS = ["组合 / 场景", "1 Day", "2-7 Days", "8-30 Days", "31-90 Days", "> 90 Days", "合計%"]
DLA_HDRS = ["组合 / 场景", "DLA%（SFC下限≥7.5%）", "DLA狀態", "WLA%（SFC下限≥15%）", "WLA狀態"]


def build_detail_sheet(ws) -> None:
    for ci, h in enumerate(DETAIL_HEADERS, start=1):
        c = ws.cell(row=1, column=ci, value=h)
        c.fill, c.font, c.alignment, c.border = HDR_FILL, HDR_FONT, CENTER, BORDER
    widths = {"A": 22, "B": 12, "C": 18, "D": 26, "E": 11, "F": 11}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    for ci in range(7, len(DETAIL_HEADERS) + 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = 15
    ws.freeze_panes = "A2"


def build_bucket_profile_sheet(ws) -> None:
    """口徑 A 詳表：12_sfc_bucket_profile.sql 數據寫入 A5 起（R4 表頭）。"""
    ws["A1"] = "SFC 流動性分層（口徑 A）— Indicative Liquidity Profile"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = ("每筆持倉全額市值按「完全變現所需天數」歸入 5 檔非累計時間桶；每場景合計 = 組合資產 100%。"
                "變現天數 = ⌈市值 ÷ 日可變現規模⌉；日可變現規模 = ADTV × 10% 參與率 × (1 − 場景折扣)；"
                "Stressed：ADTV 50% haircut + 定期存款零早破。")
    ws["A2"].font = NOTE_FONT
    for ci, h in enumerate(["组合名称", "场景", "时间桶", "市值(元)", "佔組合資產%", "組合資產合計(元)"], start=1):
        c = ws.cell(row=4, column=ci, value=h)
        c.fill, c.font, c.alignment, c.border = HDR_FILL, HDR_FONT, CENTER, BORDER
    for col, w in {"A": 24, "B": 17, "C": 10, "D": 18, "E": 14, "F": 18}.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"


def build_dla_wla_sheet(ws) -> None:
    """口徑 B 詳表：13_sfc_dla_wla.sql 數據寫入 A5 起（R4 表頭）。"""
    ws["A1"] = "SFC DLA/WLA 流動性覆蓋能力（口徑 B）— 贖回壓力測試"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = ("1 日/5 交易日內 ADTV 約束下真實可變現額對 NAV 的覆蓋率。"
                "DLA% = Σ MIN(市值, ADTV×10%×(1−折扣)) + 現金/隔夜/1日到期 ÷ NAV；WLA% 同理（5 日）。"
                "SFC UT Code §8.2(n)：雙場景均須 DLA ≥ 7.5%、WLA ≥ 15%。每場景末行「合規匯總」。")
    ws["A2"].font = NOTE_FONT
    for ci, h in enumerate(["组合名称", "场景", "资产类别", "市值(元)",
                            "1日可变现额(元)", "佔DLA%", "5日可变现额(元)", "佔WLA%"], start=1):
        c = ws.cell(row=4, column=ci, value=h)
        c.fill, c.font, c.alignment, c.border = HDR_FILL, HDR_FONT, CENTER, BORDER
    for col, w in {"A": 24, "B": 17, "C": 14, "D": 18, "E": 18, "F": 12, "G": 18, "H": 12}.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"


def build_summary_sheet(ws) -> None:
    """綜述頁 v3：兩個獨立表格塊（分層表 + DLA/WLA 表）+ 說明區。"""
    ws["A1"] = "SFC 壓力測試 — Indicative Liquidity Profile（指示性流動性概況）"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "依據：lmt-mmf-test-sfc.docx · SFC《單位信託及互惠基金守則》§8.2 · 通函 24EC64"
    ws["A2"].font = NOTE_FONT

    # ── 表格1：流動性分層（口徑A）— R4 標題 / R5 表頭 / R6 數據（11_sfc_bucket_summary.sql）──
    ws["A4"] = "表一：流動性分層（非累計時間桶，每場景五檔合計 = 組合資產 100%）"
    ws["A4"].font = SECTION_FONT
    for ci, h in enumerate(BUCKET_HDRS, start=1):
        c = ws.cell(row=5, column=ci, value=h)
        c.fill, c.font, c.alignment, c.border = HDR_FILL, HDR_FONT, CENTER, BORDER

    # ── 表格2：DLA/WLA 合規（口徑B）— R12 標題 / R13 表頭 / R14 數據（14_sfc_dla_wla_summary.sql）──
    ws["A12"] = "表二：DLA/WLA 合規指標（UT Code §8.2(n)：正常與壓力情景均須滿足）"
    ws["A12"].font = SECTION_FONT
    for ci, h in enumerate(DLA_HDRS, start=1):
        c = ws.cell(row=13, column=ci, value=h)
        c.fill, c.font, c.alignment, c.border = HDR_FILL, HDR_FONT, CENTER, BORDER

    # ── LMT 聲明 ──
    ws["A19"] = "流動性管理工具（LMT）與治理"
    ws["A19"].font = SECTION_FONT
    ws["A20"] = ("如出現極端贖回壓力，將考慮運用章程允許並已在發售文件/KFS 披露的 LMT"
                 "（贖回限制/反稀釋機制/公允估值）以保障投資者利益。（SFC 文檔 §2(b)）")
    ws["A20"].font = NOTE_FONT

    # ── 說明區（SFC 文檔 Note i-iv + 方法論）──
    notes = [
        "注：",
        "(i) 百分比為非累計時間桶，各場景五檔合計 = 組合資產端 100%（見表一；明細見「SFC流動性分層」sheet）。",
        "(ii) DLA ≥ 7.5% / WLA ≥ 15% 為 ADTV 約束下可覆蓋額口徑（見表二；明細見「SFC_DLA_WLA合規」sheet）。",
        "(iii) 變現規模為在給定時間內以合理成本變現（無重大市場衝擊或過度交易成本）的組合部分估計值。",
        "(iv) 壓力情景假設：二級市場 ADTV 50% 折扣、買賣價差擴大、定期存款零提前支取（嚴格按合約到期變現）、極端市況下的潛在結算/匯款延遲。",
        "",
        "方法論（Basis of Liquidity Classification 摘要）：",
        "· 合約現金流：按剩餘期限與結算週期（T+0/T+1）分類，桶內合約到期視為到期現金。",
        "· 二級市場變現（到期前賣出）：按過去 30 日 ADTV 的 10% 最大市場參與率估算變現能力。",
        "· 買賣價差與交易成本：以交易商可執行報價評估；壓力下需較高折扣/衝擊成本的工具下調至更長桶。",
        "· 提前支取/贖回成本：定期存款計入提前終止條款與罰息成本（壓力下為零早破）。",
        "· 定性因素：交易對手信用、市場基礎設施與 FX/結算、二級市場深度、流動性管理工具（LMT）治理。",
    ]
    for ri, note in enumerate(notes, start=22):
        ws.cell(row=ri, column=1, value=note).font = NOTE_FONT

    for col, w in {"A": 34, "B": 14, "C": 14, "D": 14, "E": 14, "F": 14, "G": 12,
                   "H": 20, "I": 12, "J": 20, "K": 12}.items():
        ws.column_dimensions[col].width = w


def main() -> None:
    wb = load_workbook(TMPL_PATH)

    builders = {
        "SFC壓力測試原始": build_detail_sheet,
        "SFC流動性分層": build_bucket_profile_sheet,
        "SFC_DLA_WLA合規": build_dla_wla_sheet,
        "SFC壓力測試": build_summary_sheet,
    }
    for name, builder in builders.items():
        if name in wb.sheetnames:
            del wb[name]
        ws = wb.create_sheet(name)
        builder(ws)

    wb.save(TMPL_PATH)
    print(f"Template updated: {TMPL_PATH}")

    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in cfg["queries"]}

    def upsert(qid, **kw):
        if qid in by_id:
            by_id[qid].update(kw)
        else:
            cfg["queries"].append({"id": qid, **kw})

    upsert("06_10", name="SFC壓力測試持倉明細", sql="10_sfc_stress.sql",
           sheet="SFC壓力測試原始", start_cell="A2", header=False,
           description="SFC壓力測試：雙場景持倉明細，含ADTV/利率衝擊/5檔時間桶，落庫sfc_liquidity_stress/compliance，A1=表頭，數據A2起")
    upsert("06_11", name="SFC流動性分層表（綜述·表一）", sql="11_sfc_bucket_summary.sql",
           sheet="SFC壓力測試", start_cell="A6", header=False,
           description="綜述表一：5檔分層×雙場景(合計=100%)，寫入A6起（R5表頭），7列（前置：06_10）")
    upsert("06_12", name="SFC流動性分層（口徑A詳表）", sql="12_sfc_bucket_profile.sql",
           sheet="SFC流動性分層", start_cell="A5", header=False,
           description="口徑A詳表：全額市值按完全變現天數歸5檔桶，A4=表頭，數據A5起（前置：06_10）")
    upsert("06_13", name="SFC DLA/WLA覆蓋能力（口徑B詳表）", sql="13_sfc_dla_wla.sql",
           sheet="SFC_DLA_WLA合規", start_cell="A5", header=False,
           description="口徑B詳表：資產類別貢獻拆分+合規匯總，A4=表頭，數據A5起（前置：06_10）")
    upsert("06_14", name="SFC DLA/WLA合規表（綜述·表二）", sql="14_sfc_dla_wla_summary.sql",
           sheet="SFC壓力測試", start_cell="A14", header=False,
           description="綜述表二：DLA/WLA%+合規狀態×雙場景，寫入A14起（R13表頭），5列（前置：06_10）")

    # 依賴順序：10 → 11 → 12 → 13 → 14（10 落庫，11/12/13/14 讀庫）
    cfg["queries"] = sorted(cfg["queries"], key=lambda q: int(q["id"].split("_")[1]))
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"config updated: {CONFIG_PATH} ({len(cfg['queries'])} queries)")


if __name__ == "__main__":
    main()
