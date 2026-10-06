"""
fix_toc_v2.py — 目录补两个 SFC 详表 + 修复基金影子定價公式断链
=====================================
1. 目录追加：
   B14  PART11. SFC壓力測試（綜述）
   B15  SFC流動性分層（口徑A詳表）        ← 新增，与前面格式一致
   B16  SFC_DLA_WLA合規（口徑B詳表）       ← 新增，与前面格式一致
2. 修复「基金影子定價」sheet 公式引用：旧名「基金原始成本影子定价偏离度原始」→ 新名「基金原始成本影子价值原始」
"""
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import Font

BASE = Path(__file__).resolve().parents[4]
TMPL = BASE / "2_processing" / "sql" / "mmf" / "report_06" / "Template.xlsx"
LINK_FONT = Font(color="0563C1", underline="single")

OLD_NAME = "基金原始成本影子定价偏离度原始"
NEW_NAME = "基金原始成本影子价值原始"


def main():
    wb = load_workbook(TMPL)

    # ── 1. 修复基金影子定價 sheet 公式断链 ──
    fixed = 0
    for ws_name in ("基金影子定價",):
        if ws_name not in wb.sheetnames:
            continue
        ws = wb[ws_name]
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and OLD_NAME in c.value:
                    c.value = c.value.replace(OLD_NAME, NEW_NAME)
                    fixed += 1
    print(f"✓ 基金影子定價 公式断链修复: {fixed} 处 → 引用 '{NEW_NAME}'")

    # ── 2. 目录追加两个 SFC 详表链接 ──
    ws_toc = wb["目录"]
    # B14 应是 PART11（已有），B15/B16 追加两个详表
    extra = [
        (15, "SFC流動性分層（口徑A詳表：變現天數歸5檔桶）"),
        (16, "SFC_DLA_WLA合規（口徑B詳表：DLA/WLA資產類別貢獻拆分）"),
    ]
    for r, label in extra:
        sheet = label.split("（")[0]
        c = ws_toc.cell(row=r, column=2, value=label)
        c.font = LINK_FONT
        c.hyperlink = f"#'{sheet}'!A1"
    print(f"✓ 目录追加: B15 SFC流動性分層 / B16 SFC_DLA_WLA合規")

    wb.save(TMPL)
    print()
    print("目录最终内容:")
    ws = wb["目录"]
    for r in range(2, 18):
        v = ws.cell(row=r, column=2).value
        if v:
            print(f"  B{r}: {v}")

    # 验证修复后公式
    ws2 = wb["基金影子定價"]
    print()
    print("基金影子定價 R2 公式修复后:")
    for c in ws2[2][:4]:
        print(f"  {c.coordinate}: {c.value}")


if __name__ == "__main__":
    main()
