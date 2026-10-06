"""
reorder_sheets.py — report_06 Template sheet 順序整理
=====================================
規則：
  前：目錄 + 結果展示層 sheet（用戶看的報表）
  後：SQL 查詢結果的原始表（數據源，隱藏或置後）

用法：cd arisk && python 2_processing/tools/mmf/report_06/reorder_sheets.py
"""
from pathlib import Path
from openpyxl import load_workbook

BASE = Path(__file__).resolve().parents[4]
TMPL = BASE / "2_processing" / "sql" / "mmf" / "report_06" / "Template.xlsx"

# 期望順序：目錄 + 結果展示層在前，原始表在後
ORDER = [
    # ── 目錄 + 結果展示層（用戶報表）──
    "目录",
    "资产分布情况表",
    "银行存款交易对手敞口数据",
    "投资组合剩余期限结构日报表",
    "可提前支取协议存款自然到期表",
    "基金影子定價偏離度",
    "资产变现情况表",
    "机构投资者持有金额表",
    "十全每日运作简报",
    "信用债及质押债发行人关注清单",
    "债券黑名单库",
    "T+1日可用流动性预估",
    "SFC壓力測試",
    "SFC流動性分層",
    "SFC_DLA_WLA合規",
    # ── SQL 查詢結果原始表（數據源，置後）──
    "资产分布原始",
    "银行存款交易对手原始",
    "剩余期限结构原始",
    "可提支存款到期原始",
    "基金原始成本影子定价偏离度原始",
    "资产变现原始",
    "信用债及质押债原始",
    "十全每日运作简报原始",
    "T+1日可用流动性原始",
    "SFC壓力測試原始",
]


def main() -> None:
    wb = load_workbook(TMPL)
    present = [s for s in ORDER if s in wb.sheetnames]
    extras = [s for s in wb.sheetnames if s not in ORDER]
    final = present + extras

    # openpyxl 的 move_sheet 用 offset；按 final 序逐一移到當前索引
    for idx, name in enumerate(final):
        cur = wb.sheetnames.index(name)
        if cur != idx:
            offset = idx - cur
            wb.move_sheet(name, offset=offset)
    wb.save(TMPL)
    print("Sheet order:")
    for i, s in enumerate(wb.sheetnames, 1):
        print(f"  {i:2d}. {s}")


if __name__ == "__main__":
    main()
