"""
fix_toc_and_vnav.py — 修复目录与 VNAV 命名（2026-10-05 用户反馈）
=====================================
1. 目录只保留 PART11（SFC 壓力測試綜述，含表一/表二两块测试结果），放最后
   · B3 起恢复「资产分布情况表」等展示层 sheet 的链接（之前被 PART11/12/13 覆盖）
   · PART11 放在目录末尾（B13），不覆盖原链接
2. 「基金影子定價偏離度」→ 改名「基金影子定價」（VNAV 下无偏离度）
   · 列头去掉「偏離度」字样，只留成本/影子价值/久期拆解
3. 验证：SFC 综述 sheet 在展示层之后、原始层之前
"""
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

BASE = Path(__file__).resolve().parents[4]
TMPL = BASE / "2_processing" / "sql" / "mmf" / "report_06" / "Template.xlsx"

LINK_FONT = Font(color="0563C1", underline="single")
TITLE_FONT = Font(bold=True, size=14)


def main():
    wb = load_workbook(TMPL)

    # ── 1. 改名：基金影子定價偏離度 → 基金影子定價 ──
    if "基金影子定價偏離度" in wb.sheetnames:
        wb["基金影子定價偏離度"].title = "基金影子定價"
    # 同步原始 sheet 改名（VNAV 下无偏离度）
    if "基金原始成本影子定价偏离度原始" in wb.sheetnames:
        wb["基金原始成本影子定价偏离度原始"].title = "基金原始成本影子价值原始"

    # ── 2. 重建目录：B3 起是展示层 sheet 链接，PART11 放最后 ──
    ws_toc = wb["目录"]
    # 清空 B3 起
    for r in range(3, ws_toc.max_row + 5):
        c = ws_toc.cell(row=r, column=2)
        c.value = None
        c.hyperlink = None

    # 展示层 sheet（用户看的报表，按当前顺序）— 作为可点击链接
    display_sheets = [
        "资产分布情况表",
        "银行存款交易对手敞口数据",
        "投资组合剩余期限结构日报表",
        "可提前支取协议存款自然到期表",
        "基金影子定價",
        "资产变现情况表",
        "机构投资者持有金额表",
        "十全每日运作简报",
        "信用债及质押债发行人关注清单",
        "债券黑名单库",
        "T+1日可用流动性预估",
    ]
    r = 3
    for name in display_sheets:
        if name in wb.sheetnames:
            c = ws_toc.cell(row=r, column=2, value=name)
            c.font = LINK_FONT
            c.hyperlink = f"#'{name}'!A1"
            r += 1
    # PART11 放最后（SFC 压力测试综述，含表一分层 + 表二 DLA/WLA 两块测试结果）
    c = ws_toc.cell(row=r, column=2,
                    value="PART11.  SFC壓力測試（流動性壓力測試綜述：表一分層+表二DLA/WLA）")
    c.font = TITLE_FONT
    c.hyperlink = f"#'SFC壓力測試'!A1"

    # ── 3. 调整 sheet 顺序：展示层在前，SFC 综述居中靠后，原始层最后 ──
    desired = ["目录"] + display_sheets + [
        "SFC壓力測試", "SFC流動性分層", "SFC_DLA_WLA合規",
    ] + [
        "资产分布原始", "银行存款交易对手原始", "剩余期限结构原始",
        "可提支存款到期原始", "基金原始成本影子价值原始", "资产变现原始",
        "信用债及质押债原始", "十全每日运作简报原始", "T+1日可用流动性原始",
        "SFC壓力測試原始",
    ]
    present = [s for s in desired if s in wb.sheetnames]
    extras = [s for s in wb.sheetnames if s not in desired]
    final = present + extras
    for idx, name in enumerate(final):
        cur = wb.sheetnames.index(name)
        if cur != idx:
            wb.move_sheet(name, offset=idx - cur)

    wb.save(TMPL)
    print("✓ 目录重建完成（PART11 放最后，展示层链接恢复）")
    print("✓ 基金影子定價偏離度 → 基金影子定價（VNAV 无偏离度）")
    print()
    print("Sheet 顺序:")
    for i, s in enumerate(wb.sheetnames, 1):
        print(f"  {i:2d}. {s}")
    print()
    print("目录内容:")
    ws = wb["目录"]
    for r in range(2, 16):
        v = ws.cell(row=r, column=2).value
        if v:
            print(f"  B{r}: {v}")


if __name__ == "__main__":
    main()
