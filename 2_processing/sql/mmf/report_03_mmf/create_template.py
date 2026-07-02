"""
create_template.py  —  全新建立 report_03_mmf/Template.xlsx
執行：python 2_processing/sql/mmf/report_03_mmf/create_template.py

功能說明
--------
生成貨幣基金（MMF）日報 xlsx 模版，共 12 個工作表：

  日报-表格汇总        匯總報表（6 大業務區塊，VLOOKUP 取數自 SQL 導入表）
  日报-sql导入数据     SQL 原始數據落地區（各 .sql 輸出按固定起始格寫入）
  持仓数据             17_stress_test.sql 壓力測試持倉明細
  回购明细             15_overnight_repo.sql 回購持倉
  其他监控-sql导入数据 18/19/39/41.sql 監控數據
  shibor债定价         浮息債 Wind 公式預留區
  计算过程             WAM/WAL、流動性、壓力測試中間計算輔助層
  组合                 組合參數與匯總（使用者自行設計）
  债券及存单新         壓力測試計算層，含 VLOOKUP 引用 压力测试结果 sheet
  压力测试结果         42_stress_result.sql 輸出（15 列，含 lookup_key）
  债券及存单新程序结果NEW  新版壓力測試結果（使用者自行設計）
  参数                 rate_shock_bps 等運行參數

業務邏輯重點
-----------
1. 偏離度 (bp) = (市場價值 - 攤余成本) / 淨資產 × 10000
   正值：市價 > 成本（債券升值）；負值：市價 < 成本（收益率上行）

2. 壓力測試（+50bp 利率衝擊）
   壓力市值 = 市值 × (1 - 久期 × 0.005)
   壓力損失 = 市值 - 壓力市值
   壓力損失修正 = 壓力損失 × 變現係數（DEPOSIT=0, FLOAT=0.05, BOND_GOVT=CD=0.20, BOND_CORP=0.80）

3. 收益率曲線壓力情景（風險觀察指標表）
   利率上行 X bp 後偏離度 = 當前偏離度 - X × WAM年
   WAM年 = WAM天 / 365（修正久期近似）

4. 偏離度分解 (bp)
   各資產偏離度貢獻 = 該資產佔總偏差比例 × 基金整體偏離度
   來源：03_deviation_breakdown.sql col8-12（cd_pct/scp_pct/mtn_pct/treasury_pct/policy_pct）

5. 06_asset_portfolio.sql 欄位順序（無估值日列）
   col1=port_name, col2=net_asset亿, col3=cash, col4=bond, col5=bond_interest,
   col6=deposit, col7=deposit_interest, col8=cd, col9=rev_repo, col10=repo,
   col11=interest_rate_bond, col12=fl_bond, col13=credit_bond,
   col14=deposit_y(提支罚息), col15=deposit_n

邊框規則
--------
  _pre_thin()：合併前對範圍所有格寫入 thin，使非錨格保有 XML 邊框數據
  _frame()   ：外框 medium，內部 thin，純按位置決定，不保留既有樣式
               合併格用 merge_map 查詢真實 max_col/max_row 判斷外邊界
"""
import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.styles.colors import Color
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
# 1. 日报-表格汇总  (仿 report_03 六大區塊，VLOOKUP 取數)
# ══════════════════════════════════════════════════════════
ws = wb.create_sheet('日报-表格汇总')
ws.sheet_properties.tabColor = TAB_BLUE

# ── 局部樣式（與全局 hdr/lbl/yell 不衝突）──────────────
_MYH12  = Font(name='微软雅黑', size=12, bold=True)
_MYH11H = Font(name='微软雅黑', size=11, bold=True)
_ST10N  = Font(name='宋体', size=10.5)
_ST10BN = Font(name='宋体', size=10.5, bold=True)
_MS     = Side(border_style='medium')
_TS     = Side(border_style='thin')
_CTR_WP = Alignment(horizontal='center', vertical='center', wrap_text=True)
_RT_H   = Alignment(horizontal='right')
_CTR_H2 = Alignment(horizontal='center')
_LT_H2  = Alignment(horizontal='left')

def _bd(t=None, b=None, l=None, r=None):
    return Border(top=t, bottom=b, left=l, right=r)

# ── 從 DB 取 MMF 組合名稱，失敗時降級到預設列表 ─────────
try:
    import os as _os
    import psycopg2 as _pg
    from dotenv import load_dotenv as _ld
    _ld()
    _conn = _pg.connect(
        host     = _os.getenv('POSTGRES_HOST', 'localhost'),
        port     = int(_os.getenv('POSTGRES_PORT', '5432')),
        dbname   = _os.getenv('POSTGRES_DB',   'fsi_risk'),
        user     = _os.getenv('POSTGRES_USER', 'fsi_user'),
        password = _os.getenv('POSTGRES_PASSWORD', 'change_me'),
    )
    with _conn.cursor() as _cur:
        _cur.execute(
            'SELECT port_name FROM fsi.para_portfolio '
            'WHERE is_mmf = TRUE AND is_active = TRUE '
            'ORDER BY port_name'
        )
        FUNDS_S = [row[0] for row in _cur.fetchall()]
    _conn.close()
    print(f'  DB 組合名稱 ({len(FUNDS_S)}): {FUNDS_S}')
except Exception as _e:
    FUNDS_S = ['薪金宝', '现金增利', '现金宝', '沃利货币', '天利货币',
               '收益宝', '快线货币', '惠利货币', '华夏货币', '财富宝', '保证金货币']
    print(f'  警告：DB 取組合名稱失敗，使用預設列表 ({_e})')
N = len(FUNDS_S)

# ── 動態行偏移（各節起始行隨 N 自動計算）────────────────
# 每節：1行大標題 + n_hdr行表頭 + N行數據 + 1行合計 + 1行空白間隔
def _sec(start, n_hdr=2):
    ds = start + 1 + n_hdr          # 數據起始行
    return {
        't':  start,                 # 大標題行
        'h':  start + 1,             # 表頭起始行
        'ds': ds,                    # 數據起始行
        'de': ds + N - 1,            # 數據結束行
        's':  ds + N,                # 合計行
        'nx': ds + N + 2,            # 下一節起始行（+1空行）
    }

# 節順序與 report_03 一致
# S1 風險觀察：3行表頭（頂層組群→中層→葉）；其餘 2行/1行
S1 = _sec(1, n_hdr=3)               # 风险观察指标：3行表頭
S2 = _sec(S1['nx'])                  # 监管指标和内部要求：2行表頭
S3 = _sec(S2['nx'])                  # 压力测试结果：2行表頭
S4 = _sec(S3['nx'], n_hdr=1)        # 偏离度分解：1行表頭
S5 = _sec(S4['nx'])                  # 申赎与流动性分析：2行表頭
S6 = _sec(S5['nx'], n_hdr=1)        # 资产配置情况：1行表頭

_SRC_S = '日报-sql导入数据'
_STR_S = '压力测试结果'

def _pre_thin(r0, c0, rs=1, cs=1):
    """合並前先對範圍內所有格寫入 thin 四邊框。

    openpyxl 合併後非錨格變為 MergedCell 代理，無法再設樣式，
    但合併前寫入的邊框數據仍保留在 xlsx XML 中。
    Excel 渲染相鄰格線時讀取這些數據，因此必須在 merge_cells() 之前呼叫。
    """
    for ri in range(r0, r0 + rs):
        for ci in range(c0, c0 + cs):
            ws.cell(row=ri, column=ci).border = _bd(t=_TS, b=_TS, l=_TS, r=_TS)

def _stitle(row, text, ncols=14):
    _pre_thin(row, 1, cs=ncols)                           # 合併前所有格補 thin
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    c = ws.cell(row=row, column=1, value=text)
    c.font = _MYH12; c.alignment = _LT_H2
    c.border = _bd(b=_MS)                                 # 錨點僅設 bottom（外框由 _frame 補）
    ws.row_dimensions[row].height = 18.75

def _sh(row, col, text, rs=2, cs=1):
    """標準表頭格：rs×cs 合並，medium 上邊框"""
    _pre_thin(row, col, rs=rs, cs=cs)                     # 合併前所有格補 thin
    if rs > 1 or cs > 1:
        ws.merge_cells(start_row=row, start_column=col,
                       end_row=row + rs - 1, end_column=col + cs - 1)
    c = ws.cell(row=row, column=col, value=text)
    c.font = _MYH11H; c.alignment = _CTR_WP
    c.border = _bd(t=_MS, b=_TS, l=_TS, r=_TS)

def _shg(row, col, text, cs=1):
    """頂層組群表頭：medium 上邊框"""
    _pre_thin(row, col, cs=cs)
    if cs > 1:
        ws.merge_cells(start_row=row, start_column=col,
                       end_row=row, end_column=col + cs - 1)
    c = ws.cell(row=row, column=col, value=text)
    c.font = _MYH11H; c.alignment = _CTR_WP
    c.border = _bd(t=_MS, b=_TS, l=_TS, r=_TS)

def _shi(row, col, text, cs=1):
    """中間層表頭（頂層組群之下）：thin 邊框"""
    _pre_thin(row, col, cs=cs)
    if cs > 1:
        ws.merge_cells(start_row=row, start_column=col,
                       end_row=row, end_column=col + cs - 1)
    c = ws.cell(row=row, column=col, value=text)
    c.font = _MYH11H; c.alignment = _CTR_WP
    c.border = _bd(t=_TS, b=_TS, l=_TS, r=_TS)

def _shl(row, col, text):
    """葉節點表頭：thin 邊框"""
    c = ws.cell(row=row, column=col, value=text)
    c.font = _MYH11H; c.alignment = _CTR_WP
    c.border = _bd(t=_TS, b=_TS, l=_TS, r=_TS)

def _d(row, col, val, fmt='General', bold=False, algn='right'):
    c = ws.cell(row=row, column=col, value=val)
    c.font = _ST10BN if bold else _ST10N
    c.number_format = fmt
    c.alignment = Alignment(horizontal=algn)
    c.border = _bd(t=_TS, b=_TS, l=_TS, r=_TS)

def _s(row, col, val, fmt='General'):
    c = ws.cell(row=row, column=col, value=val)
    c.font = _ST10BN; c.number_format = fmt
    c.alignment = _RT_H
    c.border = _bd(t=_TS, b=_MS, l=_TS, r=_TS)

def _sname(row):
    c = ws.cell(row=row, column=1, value='合计')
    c.font = _ST10BN; c.alignment = _CTR_H2
    c.border = _bd(t=_TS, b=_MS, l=_TS, r=_TS)

def vl(ref, rng, col, div=''):
    base = f"VLOOKUP({ref},'{_SRC_S}'!{rng},{col},0)"
    body = f"({base})/{div}" if div else base
    return f"=IFERROR({body},0)"

def si(ref, col_letter):
    return (f"=IFERROR(SUMIF('{_STR_S}'!$B:$B,{ref},"
            f"'{_STR_S}'!${col_letter}:${col_letter}),0)")

# ── 資料源範圍（對應 日报-sql导入数据 各 SQL 佔位）──────
_N   = '$A$6:$H$50'      # 01: port,nav元,dev_bp,dev_元,万份,7日年化,WAM,WAL
_L   = '$I$6:$K$50'      # 02: port,现金亿,1M利率债亿
_RL  = '$L$6:$M$50'      # 07: port,受限资产亿
_TH  = '$D$26:$H$50'     # 04: port,机构%,前1大%,前5大%,前10大%
_AP  = '$A$44:$O$70'     # 06: port(1),净资产亿(2),现金(3),债券(4),债券利息(5),存款(6),存款利息(7),存单CD(8),逆回购(9),正回购(10),利率债(11),浮息债(12),信用债(13),存款提支罚息(14),存款提支不罚息(15)
_A   = '$A$62:$C$100'    # 09: port,AAA以下市值亿,占NAV%
_AM  = '$D$62:$E$100'    # 11: port,单一最大%
_DL  = '$A$80:$C$100'    # 13: port,code,最大利差损(元)
_RD  = '$A$96:$D$120'    # 10: port,明日确认亿,当日&昨日亿,T-2净值亿
_T5  = '$E$96:$J$120'    # 12: port,T+1,T+2,T+3,T+4,T+5 (亿)
_BKT = '$K$96:$R$120'    # 16: port,T+14,T+30,月末,季末,年末,明年末,后年末+ (亿)
_DV  = '$A$118:$L$140'   # 03: port,CD偏差万,企债偏差万,政债偏差万,CD市值亿,企债亿,政债亿,存款亿,利率×4

# ═══ Section 1：风险观察指标 ════════════════════════════
# 三行表頭仿 report_03：
#   行h  : 頂層組群（收益率曲线压力测试 / 流动性监管指标）
#   行h+1: 中間層（收益率上行幅度BP / 现金及1y以内利率债 / 流通受限资产）
#   行h+2: 葉層（偏离度跌至0/-25/-50 / 下限5% / 上限10%）
_stitle(S1['t'], '风险观察指标', 11)
h, h1, h2 = S1['h'], S1['h'] + 1, S1['h'] + 2

# 跨三行的單列表頭
for ci, text in [(1,'组合/指标'), (2,'净值(成本,亿元)'), (3,'偏离度（bp）'),
                  (4,'偏离金额（万元）'), (8,'万份收益'), (9,'七日收益率（%）')]:
    _sh(h, ci, text, rs=3)

# 組群「收益率曲线压力测试」→「利率冲击情景」→ 冲击后偏离度(bp)
# 含义：利率分别上行 0/+25/+50 bp 后，组合偏离度变为多少
# 公式：新偏离度 = 当前偏离度 − 利率冲击(bp) × WAM年
_shg(h,  5, '收益率曲线压力测试', cs=3)
_shi(h1, 5, '利率冲击→偏离度(bp)', cs=3)
_shl(h2, 5, '利率上行+0bp\n(当前状态)')
_shl(h2, 6, '利率上行+25bp\n(警示线)')
_shl(h2, 7, '利率上行+50bp\n(监管线)')

# 組群「流动性监管指标」— SFC UT Code §8.2(n)：DLA≥7.5% / WLA≥15%
# DLA (Daily Liquid Assets)   = 现金 + T+1到期资产（1个交易日内变现）
# WLA (Weekly Liquid Assets)  = 现金 + T+1~T+5到期资产（5个交易日内变现）
_shg(h,  10, '流动性监管指标\n(SFC UT Code §8.2(n))', cs=2)
_shi(h1, 10, '日流动资产DLA')
_shi(h1, 11, '週流动资产WLA')
_shl(h2, 10, '≥7.5% NAV')
_shl(h2, 11, '≥15% NAV')

for i, fund in enumerate(FUNDS_S):
    r = S1['ds'] + i
    _d(r, 1,  fund,                           bold=True, algn='center')
    _d(r, 2,  vl(f'A{r}', _N, 2, '10^8'),    '0.00_ ')   # 净值亿元
    _d(r, 3,  vl(f'A{r}', _N, 3),             '0.00_ ')   # 偏离度bp
    _d(r, 4,  vl(f'A{r}', _N, 4, '10^4'),    '0_ ')       # 偏离金额万元
    # ── 收益率曲線壓力測試（E/F/G 列）────────────────────────
    # 業務含義：利率分別上行 0/+25/+50 bp 後，組合偏離度變為多少
    #
    # 推導：
    #   利率上行 X bp → 市值下跌 ≈ duration × X/10000 × MV
    #   偏離度變化(bp) ≈ −X × duration ≈ −X × WAM年
    #   （MMF 修正久期 ≈ WAM，WAM年 = WAM天/365）
    # 公式：新偏離度 = 當前偏離度 − X × WAM年
    #   X=0  → 基準狀態；X=25 → 警示線；X=50 → 監管壓力情景
    _wam = f"IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_N},7,0)/365,1)"
    _d(r, 5, f'=IFERROR(C{r}-0*({_wam}),0)',    '0.00_ ')   # +0bp：當前偏離度（基準）
    _d(r, 6, f'=IFERROR(C{r}-25*({_wam}),0)',   '0.00_ ')   # +25bp 衝擊後偏離度
    _d(r, 7, f'=IFERROR(C{r}-50*({_wam}),0)',   '0.00_ ')   # +50bp 衝擊後偏離度
    _d(r, 8,  vl(f'A{r}', _N, 5),             '0.0000_ ') # 万份收益
    _d(r, 9,  vl(f'A{r}', _N, 6),             '0.00_ ')   # 7日年化
    # SFC流动性监管指标
    # DLA% = (现金 + T+1到期资产) / NAV × 100  →  须≥7.5%
    _d(r, 10,
       f"=IFERROR((VLOOKUP(A{r},'{_SRC_S}'!{_L},2,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},2,0))/B{r}*100,0)", '0.00_ ')
    # WLA% = (现金 + T+1~T+5到期资产) / NAV × 100  →  须≥15%
    _d(r, 11,
       f"=IFERROR((VLOOKUP(A{r},'{_SRC_S}'!{_L},2,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},2,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},3,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},4,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},5,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},6,0))/B{r}*100,0)", '0.00_ ')

ds1, de1, s1r = S1['ds'], S1['de'], S1['s']
_sname(s1r)
_s(s1r,  2, f'=SUM(B{ds1}:B{de1})',  '0.00_ ')
_s(s1r,  3,
   f'=IFERROR(SUMPRODUCT($C${ds1}:$C${de1},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')
_s(s1r,  4, f'=SUM(D{ds1}:D{de1})',  '0_ ')
# 压力测试合计：NAV加权平均偏离度（各组合利率冲击后的加权偏离度）
_s(s1r,  5, f'=IFERROR(SUMPRODUCT($E${ds1}:$E${de1},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')  # +0bp
_s(s1r,  6, f'=IFERROR(SUMPRODUCT($F${ds1}:$F${de1},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')  # +25bp
_s(s1r,  7, f'=IFERROR(SUMPRODUCT($G${ds1}:$G${de1},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')  # +50bp
_s(s1r,  8,
   f'=IFERROR(SUMPRODUCT($H${ds1}:$H${de1},$B${ds1}:$B${de1})/$B${s1r},0)', '0.0000_ ')
_s(s1r,  9,
   f'=IFERROR(SUMPRODUCT($I${ds1}:$I${de1},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')
_s(s1r, 10,
   f'=IFERROR(SUMPRODUCT($J${ds1}:$J${de1},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')
_s(s1r, 11,
   f'=IFERROR(SUMPRODUCT($K${ds1}:$K${de1},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')

# ═══ Section 2：监管指标和内部要求 ════════════════════════
# 仿 report_03（14列）：机构投资者/前10大投资者/监管指标/内部要求
_stitle(S2['t'], '监管指标和内部要求', 14)
h, h1 = S2['h'], S2['h'] + 1

_sh(h, 1, '基金名称', rs=2)

_shg(h, 2, '机构投资者', cs=2)
_shl(h1, 2, '总占比（%）')
_shl(h1, 3, '单一最大占比（%）')

_shg(h, 4, '前10大投资者', cs=2)
_shl(h1, 4, '总占比（%）')
_shl(h1, 5, '扣除固有资金占比（%）')

# SFC UT Code §8.2 监管指标（6列）：
#   WAM≤60天 / WAL≤120天 / DLA≥7.5% / WLA≥15% / 信用质量 / 集中度
_shg(h, 6, 'SFC监管指标（UT Code §8.2）', cs=6)
_shl(h1, 6,  'WAM（天）\n限≤60天')
_shl(h1, 7,  'WAL（天）\n限≤120天')
_shl(h1, 8,  '日流动资产DLA\n≥7.5% NAV')
_shl(h1, 9,  '週流动资产WLA\n≥15% NAV')
_shl(h1, 10, 'AAA以下机构发行\n金融工具占比(%)')
_shl(h1, 11, '单一AAA以下机构\n最大持仓比率(%)')

# 内部监控（3列）：流动性结构 / 杠杆 / 回购质押品
_shg(h, 12, '内部监控', cs=3)
_shl(h1, 12, '现金及利率债\n占比（%）')
_shl(h1, 13, '杠杆比例\n（%）')
_shl(h1, 14, '回购质押品资产\n/正回购（%）')

for i, fund in enumerate(FUNDS_S):
    r = S2['ds'] + i
    # ── 06_asset_portfolio 欄位映射（注意：SQL 無 估值日 列）────
    # col2=净资产亿, col3=现金, col4=债券, col5=债券利息, col6=存款,
    # col7=存款利息, col8=存单CD, col9=逆回购(融出), col10=正回购(融入),
    # col11=利率债, col12=浮息债, col13=信用债, col14=存款提支罚息
    # 分母統一用 col2（净资产），比例 > 100% 屬正常（基金使用正回購槓桿）
    nav_e2 = f"IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},2,0),1)"   # col2=净资产亿
    t5_sum = (f"IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_T5},2,0)"
              f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},3,0)"
              f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},4,0)"
              f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},5,0)"
              f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},6,0),0)")
    _d(r, 1,  fund, bold=True, algn='center')
    _d(r, 2,  vl(f'A{r}', _TH, 2),             '0.00_ ')  # 机构总占比
    _d(r, 3,  vl(f'A{r}', _TH, 3),             '0.00_ ')  # 单一最大
    _d(r, 4,  vl(f'A{r}', _TH, 5),             '0.00_ ')  # 前10大总占比
    _d(r, 5,  vl(f'A{r}', _TH, 5),             '0.00_ ')  # 扣除固有(近似前10大)
    # SFC UT Code §8.2 监管指标
    _d(r, 6,  vl(f'A{r}', _N,  7), '0_ ')      # WAM（天），SFC上限60天
    _d(r, 7,  vl(f'A{r}', _N,  8), '0_ ')      # WAL（天），SFC上限120天
    # DLA% = (现金 + T+1到期) / NAV × 100，SFC下限7.5%
    _d(r, 8,
       f"=IFERROR((VLOOKUP(A{r},'{_SRC_S}'!{_L},2,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},2,0))/({nav_e2})*100,0)", '0.00_ ')
    # WLA% = (现金 + T+1~T+5到期) / NAV × 100，SFC下限15%
    _wla = (f"IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_L},2,0)"
            f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},2,0)"
            f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},3,0)"
            f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},4,0)"
            f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},5,0)"
            f"+VLOOKUP(A{r},'{_SRC_S}'!{_T5},6,0),0)")
    _d(r, 9,  f'=IFERROR(({_wla})/({nav_e2})*100,0)', '0.00_ ')
    _d(r, 10, vl(f'A{r}', _A,  3), '0.00_ ')  # AAA以下机构金融工具占NAV%（信用质量指标）
    _d(r, 11, vl(f'A{r}', _AM, 2), '0.00_ ')  # 单一AAA以下机构最大持仓%（集中度指标）
    # 现金(col3)+利率债(col11) / 净资产(col2) × 100
    _d(r, 12,
       f"=IFERROR((VLOOKUP(A{r},'{_SRC_S}'!{_AP},3,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_AP},11,0))/({nav_e2})*100,0)", '0.00_ ')
    # 杠杆比例 = (净资产col2 + 正回购col10) / 净资产col2 × 100
    _d(r, 13,
       f"=IFERROR((VLOOKUP(A{r},'{_SRC_S}'!{_AP},2,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_AP},10,0))"
       f"/VLOOKUP(A{r},'{_SRC_S}'!{_AP},2,0)*100,0)", '0.00_ ')
    # 回购质押/正回购 = (债券col4+存单col8)/正回购col10
    _d(r, 14,
       f"=IFERROR((VLOOKUP(A{r},'{_SRC_S}'!{_AP},4,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_AP},8,0))"
       f"/VLOOKUP(A{r},'{_SRC_S}'!{_AP},10,0),0)", '0.00_ ')

ds2, de2, s2r = S2['ds'], S2['de'], S2['s']
_sname(s2r)
for ci, cl in enumerate(list('BCDE'), 2):
    _s(s2r, ci,
       f'=IFERROR(SUMPRODUCT(${cl}${ds2}:${cl}${de2},$B${ds1}:$B${de1})/$B${s1r},0)',
       '0.00_ ')
# WAM/WAL：NAV加权均值，保留整数（监管限额对比用）
for ci, cl in enumerate(list('FG'), 6):
    _s(s2r, ci,
       f'=IFERROR(SUMPRODUCT(${cl}${ds2}:${cl}${de2},$B${ds1}:$B${de1})/$B${s1r},0)',
       '0_ ')
# DLA/WLA/信用质量/集中度/内控：NAV加权均值，保留两位小数
for ci, cl in enumerate(list('HIJKLMN'), 8):
    _s(s2r, ci,
       f'=IFERROR(SUMPRODUCT(${cl}${ds2}:${cl}${de2},$B${ds1}:$B${de1})/$B${s1r},0)',
       '0.00_ ')

# ── SUMIF 裸式（供跨字段組合公式使用）────────────────────
def _si_raw(ref, col_letter):
    return (f"SUMIF('{_STR_S}'!$B:$B,{ref},"
            f"'{_STR_S}'!${col_letter}:${col_letter})")

# ── 申贖資料源 ────────────────────────────────────────────
_RD = '$A$96:$D$120'  # 10_sub_redeem: port(1),明日确认亿(2),当日&昨日亿(3),T-2净值亿(4)

# ═══ Section 3：压力测试结果 ════════════════════════════
# 仿 report_03：偏离度、前10大、压测情景、偏离资产占比、偏离金额、偏离度bp
_stitle(S3['t'], '压力测试结果', 9)
h, h1 = S3['h'], S3['h'] + 1

for ci, text in [(1,'组合名称'), (2,'偏离度（bp）'),
                  (3,'前10大占比\n(扣除固有资金,%)'),
                  (6,'可卖出偏离度资产\n占偏离资产比(%)'),
                  (7,'偏离资产占比(%)'),
                  (8,'压力情景下偏离\n金额（万）'),
                  (9,'压力情景下\n偏离度(bp)')]:
    _sh(h, ci, text, rs=2)

_shg(h,  4, '压力情景', cs=2)
_shl(h1, 4, '赎回比例(%)')
_shl(h1, 5, '收益率上行(bp)')

for i, fund in enumerate(FUNDS_S):
    r = S3['ds'] + i
    sj = _si_raw(f'A{r}', 'J')   # stressed_loss(万元)
    so = _si_raw(f'A{r}', 'O')   # stressed_loss_adj(万元)
    _d(r, 1, fund,                                   bold=True, algn='center')
    _d(r, 2, vl(f'A{r}', _N,  3),                   '0.00_ ')   # 偏离度bp
    _d(r, 3, vl(f'A{r}', _TH, 5),                   '0.00_ ')   # 前10大占比(近似)
    _d(r, 4, f'=IF(B{r}>=50,30,15)',                 '0_ ')      # 赎回比例
    _d(r, 5, '50',                                    '0_ ')      # 收益率上行bp
    # 可卖出偏离度资产占偏离资产比 = 修正损失 / 总压力损失 × 100
    _d(r, 6, f'=IFERROR(({so})/({sj})*100,0)',       '0.00_ ')
    # 偏离资产占比 = 压力损失(万元) / 净资产(亿元) / 100 → %
    _d(r, 7, f'=IFERROR(({sj})/(B{r}*100),0)',       '0.00_ ')
    _d(r, 8, f'=IFERROR({sj},0)',                     '#,##0.00') # 偏离金额(万元)
    # 偏离度bp = 压力损失(万) / 净资产(亿)（万/亿 = 1 bp 单位换算=1）
    _d(r, 9, f'=IFERROR(({sj})/B{r},0)',              '0.00_ ')

ds3, de3, s3r = S3['ds'], S3['de'], S3['s']
_sname(s3r)
_s(s3r, 2,
   f'=IFERROR(SUMPRODUCT($B${ds3}:$B${de3},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')
_s(s3r, 3,
   f'=IFERROR(SUMPRODUCT($C${ds3}:$C${de3},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')
_s(s3r, 4, '',   'General')
_s(s3r, 5, '50', '0_ ')
_s(s3r, 6,
   f'=IFERROR(SUMPRODUCT($F${ds3}:$F${de3},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')
_s(s3r, 7,
   f'=IFERROR(SUMPRODUCT($G${ds3}:$G${de3},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')
_s(s3r, 8, f'=SUM(H{ds3}:H{de3})',  '#,##0.00')
_s(s3r, 9,
   f'=IFERROR(SUMPRODUCT($I${ds3}:$I${de3},$B${ds1}:$B${de1})/$B${s1r},0)', '0.00_ ')

# ═══ Section 4：偏离度分解（bp）══════════════════════════
# 仿 report_03：按資產類別分解偏離度bp
# 列映射（03_deviation_breakdown SQL）：
#   存单  ← CD偏差(万元)/NAV亿 = bp
#   中票  ← 企业债偏差(万元)/NAV亿（含短融+中票）
#   政金债 ← 政府债偏差(万元)/NAV亿（含国债+政金债）
_stitle(S4['t'], '偏离度分解（bp）', 7)
for ci, text in enumerate(['偏离度（bp）', '基金整体', '存单', '短融', '中票', '国债', '政金债'], 1):
    _sh(S4['h'], ci, text, rs=1)

for i, fund in enumerate(FUNDS_S):
    r = S4['ds'] + i
    _d(r, 1, fund, bold=True, algn='center')
    # ── 偏離度分解（各資產類別 bp 貢獻）───────────────────────
    # 業務含義：基金整體偏離度 = 各資產類別偏離度貢獻之和
    #   各資產偏離度貢獻(bp) = 該資產佔總偏差比例 × 基金整體偏離度(bp)
    #
    # 注意：各子項方向可能不同（存單升值、中票貶值），子項絕對值可 > 整體，
    #       這是正常的「對沖抵消」效果，非計算錯誤。
    #
    # 03_deviation_breakdown.sql 列映射（_DV 範圍）：
    #   col2=total_deviation(元), col3=cd_dev(元), col4=scp_dev(元),
    #   col5=mtn_dev(元), col6=treasury_dev(元), col7=policy_dev(元),
    #   col8=cd_pct, col9=scp_pct, col10=mtn_pct, col11=treasury_pct, col12=policy_pct
    # 零值由數字格式自動顯示 "-"（格式：'0.00_ ;-0.00_ ;"-"'）
    _FMT_DV = '0.00_ ;-0.00_ ;"-"'
    _d(r, 2, vl(f'A{r}', _N, 3),               '0.00_ ')   # 基金整体bp（来自01_nav col3）
    _d(r, 3, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_DV},8,0)*B{r},0)",  _FMT_DV)  # 存单: cd_pct×bp
    _d(r, 4, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_DV},9,0)*B{r},0)",  _FMT_DV)  # 短融: scp_pct×bp
    _d(r, 5, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_DV},10,0)*B{r},0)", _FMT_DV)  # 中票: mtn_pct×bp
    _d(r, 6, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_DV},11,0)*B{r},0)", _FMT_DV)  # 国债: treasury_pct×bp
    _d(r, 7, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_DV},12,0)*B{r},0)", _FMT_DV)  # 政金债: policy_pct×bp

# ═══ Section 5：申赎与流动性分析 ════════════════════════
# 仿 report_03：各列独立2行表頭，按用户指定列标题
_stitle(S5['t'], '申赎与流动性分析', 14)
h = S5['h']

for ci, text in enumerate([
    '基金名称',
    '净值(亿元)',
    '前日净申赎金额（亿元）',
    '前日净申赎占比(%)',
    '前三日净申赎金额*（亿元）',
    '前三日净申赎占比(%)',
    '未来5日最大\n流动性缺口（亿元）',
    'T+14\n流入现金流(%)',
    'T+30\n流入现金流(%)',
    'T日至本月末\n流入现金流(%)',
    'T日至下月末\n流入现金流(%)',
    'T日至第3月月末\n流入现金流(%)',
    'T日至本季末\n流入现金流(%)',
    'T日至本年末\n流入现金流(%)',
], 1):
    _sh(h, ci, text, rs=2)

for i, fund in enumerate(FUNDS_S):
    r = S5['ds'] + i
    nav_e = f"IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_N},2,0)/10^8,1)"
    _d(r, 1, fund, bold=True, algn='center')
    _d(r, 2, vl(f'A{r}', _N, 2, '10^8'),             '0.00_ ')
    # 申贖：前日 = 当日&昨日(col3)；前三日 ≈ 明日确认+当日&昨日(col2+col3)
    _d(r, 3, vl(f'A{r}', _RD, 3),                    '0.00_ ')   # 前日净申赎金额
    _d(r, 4, f'=IFERROR(C{r}/B{r}*100,0)',            '0.00_ ')   # 前日占比
    _d(r, 5, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_RD},2,0)"
             f"+VLOOKUP(A{r},'{_SRC_S}'!{_RD},3,0),0)", '0.00_ ')# 前三日近似
    _d(r, 6, f'=IFERROR(E{r}/B{r}*100,0)',            '0.00_ ')   # 前三日占比
    # 未来5日最大流动性缺口：取 T+1~T+5 中最小到期量作保守估计
    _d(r, 7,
       f"=IFERROR(MIN("
       f"VLOOKUP(A{r},'{_SRC_S}'!{_T5},2,0),"
       f"VLOOKUP(A{r},'{_SRC_S}'!{_T5},3,0),"
       f"VLOOKUP(A{r},'{_SRC_S}'!{_T5},4,0),"
       f"VLOOKUP(A{r},'{_SRC_S}'!{_T5},5,0),"
       f"VLOOKUP(A{r},'{_SRC_S}'!{_T5},6,0)),0)",   '0.00_ ')
    # 流動性現金流 %：到期量 / 净值 × 100
    _d(r,  8, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_BKT},2,0)/({nav_e})*100,0)", '0.00_ ')  # T+14
    _d(r,  9, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_BKT},3,0)/({nav_e})*100,0)", '0.00_ ')  # T+30
    _d(r, 10, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_BKT},4,0)/({nav_e})*100,0)", '0.00_ ')  # 月末
    _d(r, 11, '0',  '0.00_ ')  # 下月末：SQL暂无分月数据
    _d(r, 12, '0',  '0.00_ ')  # 第3月末：SQL暂无
    _d(r, 13, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_BKT},5,0)/({nav_e})*100,0)", '0.00_ ')  # 季末
    _d(r, 14, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_BKT},6,0)/({nav_e})*100,0)", '0.00_ ')  # 年末

ds5, de5, s5r = S5['ds'], S5['de'], S5['s']
_sname(s5r)
_s(s5r, 2, f'=SUM(B{ds5}:B{de5})',  '0.00_ ')
_s(s5r, 3, f'=SUM(C{ds5}:C{de5})',  '0.00_ ')
_s(s5r, 4,
   f'=IFERROR(SUMPRODUCT($D${ds5}:$D${de5},$B${ds5}:$B${de5})/$B${s5r},0)', '0.00_ ')
_s(s5r, 5, f'=SUM(E{ds5}:E{de5})',  '0.00_ ')
_s(s5r, 6,
   f'=IFERROR(SUMPRODUCT($F${ds5}:$F${de5},$B${ds5}:$B${de5})/$B${s5r},0)', '0.00_ ')
_s(s5r, 7, f'=SUM(G{ds5}:G{de5})',  '0.00_ ')
for ci, cl in enumerate(list('HIJKLMN'), 8):
    _s(s5r, ci,
       f'=IFERROR(SUMPRODUCT(${cl}${ds5}:${cl}${de5},$B${ds5}:$B${de5})/$B${s5r},0)',
       '0.00_ ')

# ═══ Section 6：资产配置情况（成本占净值,%）══════════════
# 仿 report_03「资产组合以成本摊销值,%」，按用户指定列标题
# 06_asset_portfolio col: 1=port,3=净资产亿,5=债券,6=存款,7=CD,8=逆回购,
#   9=正回购,10=利率债,11=信用债,12=其他债
_stitle(S6['t'], '资产配置情况（成本占净值,%）', 13)
for ci, text in enumerate([
    '组合/指标',
    '债券(%)',
    '利率债(%)',
    '浮息债(%)',
    '信用债(%)',
    '同业存单(%)',
    '存款(%)',
    '存款（提前支取罚息）(%)',
    '逆回购(%)',
    '正回购(%)',
    '回购质押品\n资产比例(%)',
    '净值(亿元)',
    '最大利差损\n占NAV比(%)',
], 1):
    _sh(S6['h'], ci, text, rs=1)

for i, fund in enumerate(FUNDS_S):
    r = S6['ds'] + i
    # 正确列映射（06_asset_portfolio.sql 无估值日，从col2起）：
    # col2=净资产亿, col3=现金, col4=债券, col6=存款, col8=存单CD
    # col9=逆回购, col10=正回购, col11=利率债, col12=浮息债, col13=信用债
    # col14=存款提支罚息, col15=存款提支不罚息
    nav_e = f"IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},2,0),1)"   # col2=净资产亿
    _d(r, 1,  fund, bold=True, algn='center')
    _d(r, 2,  f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},4,0)/({nav_e})*100,0)",  '0.00_ ')  # 债券col4
    _d(r, 3,  f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},11,0)/({nav_e})*100,0)", '0.00_ ')  # 利率债col11
    _d(r, 4,  f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},12,0)/({nav_e})*100,0)", '0.00_ ')  # 浮息债col12
    _d(r, 5,  f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},13,0)/({nav_e})*100,0)", '0.00_ ')  # 信用债col13
    _d(r, 6,  f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},8,0)/({nav_e})*100,0)",  '0.00_ ')  # 存单CDcol8
    _d(r, 7,  f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},6,0)/({nav_e})*100,0)",  '0.00_ ')  # 存款col6
    _d(r, 8,  f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},14,0)/({nav_e})*100,0)", '0.00_ ')  # 存款提支罚息col14
    _d(r, 9,  f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},9,0)/({nav_e})*100,0)",  '0.00_ ')  # 逆回购col9
    _d(r, 10, f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_AP},10,0)/({nav_e})*100,0)", '0.00_ ')  # 正回购col10
    # 回购质押品比例 = (债券col4+存单col8)/正回购col10 × 100
    _d(r, 11,
       f"=IFERROR((VLOOKUP(A{r},'{_SRC_S}'!{_AP},4,0)"
       f"+VLOOKUP(A{r},'{_SRC_S}'!{_AP},8,0))"
       f"/VLOOKUP(A{r},'{_SRC_S}'!{_AP},10,0)*100,0)", '0.00_ ')
    _d(r, 12, vl(f'A{r}', _AP, 2),    '0.00_ ')  # 净值亿元col2
    # 最大利差损占NAV比(%) = 利差损(元)/(净值亿col2×10^8)×100
    _d(r, 13,
       f"=IFERROR(VLOOKUP(A{r},'{_SRC_S}'!{_DL},3,0)"
       f"/(VLOOKUP(A{r},'{_SRC_S}'!{_AP},2,0)*10^8)*100,0)", '0.00_ ')

ds6, de6, s6r = S6['ds'], S6['de'], S6['s']
_sname(s6r)
_s(s6r, 12, f'=SUM(L{ds6}:L{de6})',  '0.00_ ')
for ci, cl in enumerate(list('BCDEFGHIJK'), 2):
    _s(s6r, ci,
       f'=IFERROR(SUMPRODUCT(${cl}${ds6}:${cl}${de6},$L${ds6}:$L${de6})/$L${s6r},0)',
       '0.00_ ')
_s(s6r, 13,
   f'=IFERROR(SUMPRODUCT($M${ds6}:$M${de6},$L${ds6}:$L${de6})/$L${s6r},0)', '0.00_ ')

# ── 列宽（A-N）─────────────────────────────────────────
for col, w in [('A', 14), ('B', 12), ('C', 14), ('D', 12), ('E', 14),
               ('F', 12), ('G', 12), ('H', 12), ('I', 12), ('J', 12),
               ('K', 12), ('L', 12), ('M', 12), ('N', 12)]:
    ws.column_dimensions[col].width = w

# ── 每張表格加邊框：inner=thin，outer=medium ─────────────────
def _frame(sec, ncols):
    """為整個 section（標題行→合計行，第1列→ncols列）統一邊框。

    規則：外框（四週）medium，內部 thin，完全按位置決定，不保留既有樣式。

    合併格處理：
      普通格  → 用自身 (r, c) 判斷是否在邊界
      合併錨格 → 用 merge_map 查詢該合併範圍的 max_col/max_row，
                確保跨列合併格（如標題行 A1:K1）的右/下外框也升為 medium。
      MergedCell 佔位格 → 跳過，由錨格統一代表整個合併範圍的邊框。
    """
    r1, r2 = sec['t'], sec['s']

    # 錨點 → MergedCellRange（僅本節範圍）
    merge_map = {
        (mr.min_row, mr.min_col): mr
        for mr in ws.merged_cells.ranges
        if r1 <= mr.min_row <= r2 and 1 <= mr.min_col <= ncols
    }

    for r in range(r1, r2 + 1):
        for c in range(1, ncols + 1):
            cell = ws.cell(row=r, column=c)
            if cell.__class__.__name__ == 'MergedCell':
                continue

            mr         = merge_map.get((r, c))
            right_col  = mr.max_col if mr else c
            bottom_row = mr.max_row if mr else r

            cell.border = Border(
                top    = _MS if r         == r1    else _TS,
                bottom = _MS if bottom_row == r2    else _TS,
                left   = _MS if c         == 1     else _TS,
                right  = _MS if right_col == ncols else _TS,
            )

_frame(S1, 11)
_frame(S2, 14)
_frame(S3,  9)
_frame(S4,  7)
_frame(S5, 14)
_frame(S6, 13)

# 鎖定標題 + 表頭行（rows 1 ~ S1['ds']-1），數據行從 S1['ds'] 起滾動
ws.freeze_panes = f'B{S1["ds"]}'

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
# SQL 实际输出：无估值日，列顺序严格对应 06_asset_portfolio.sql SELECT
h06 = ['组合', '净资产(亿)', '现金', '债券', '债券利息',
       '存款', '存款利息', '存单(CD)', '逆回购', '正回购',
       '利率债', '浮息债', '信用债', '存款提支罚息', '存款提支不罚息']
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
# 8. 债券及存单新  (壓力測試計算層，按 Template 精確生成)
# ══════════════════════════════════════════════════════════
ws15 = wb.create_sheet('债券及存单新')
ws15.sheet_properties.tabColor = TAB_RED

YEL      = PatternFill('solid', fgColor='FFFF00')
YEL_ARGB = PatternFill('solid', fgColor='FFFF00')          # Row 1 黃
THEME9   = PatternFill('solid', fgColor=Color(theme=9))    # Row 2 A-P 主題色9
NFMT     = '0.00_ '
MAX_ROWS = 5570
_THIN        = Side(border_style='thin')
_BORDER_THIN = Border(top=_THIN, bottom=_THIN, left=_THIN, right=_THIN)
_ALIGN_CTR   = Alignment(horizontal='center', vertical='center', wrap_text=True)
_ALIGN_H_CTR = Alignment(horizontal='center')   # 水平置中，無垂直設定

# ── Row 1：參數行 ─────────────────────────────────────────
ws15.row_dimensions[1].height = 14.5
# A1: Arial bold 紅色; B1/M1/N1: Arial bold; Q1: 宋体 bold
ws15['A1'].value          = '=TDaysOffset(TODAY(),"Offset=-1")'
ws15['A1'].number_format  = 'yyyy\\-mm\\-dd'
ws15['A1'].fill           = YEL
ws15['A1'].font           = Font(name='Arial', size=10, bold=True, color='FF0000')

ws15['B1'].value          = '=参数!L2'
ws15['B1'].number_format  = 'mm-dd-yy'
ws15['B1'].fill           = YEL
ws15['B1'].font           = Font(name='Arial', size=10, bold=True)

ws15['M1'].value          = 'FIXED'   # 對應 SQL 輸出 coupon_type=FIXED
ws15['M1'].fill           = YEL
ws15['M1'].font           = Font(name='Arial', size=10, bold=True)

ws15['N1'].value          = '0.005'
ws15['N1'].number_format  = '0.00%'
ws15['N1'].fill           = YEL
ws15['N1'].font           = Font(name='Arial', size=10, bold=True)

ws15['Q1'].value          = '公式列'
ws15['Q1'].number_format  = '0.0000_ '
ws15['Q1'].font           = Font(name='宋体', size=10, bold=True)
ws15['Q1'].border         = _BORDER_THIN

# ── Row 2：表頭（thin 四邊框 + center/wrap + size=10）────
# A-P: Microsoft Sans Serif；Q-Y: 宋体
ws15.row_dimensions[2].height = 48.0
_H2 = [
    # (col, text, fmt, fill, font_name)
    # A-P: theme color 9；Q-Y: 黃色 FFFF00
    ('A','组合名称',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('B','证券类型',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('C','证券代码',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('D','证券名称',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('E','数量',                         NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('F','成本',                         NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('G','市值净价',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('H','成本全价',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('I','影价偏离度',                   NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('J','市值占净值比（%）',            NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('K','偏离金额（万元）',             NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('L','到期日',                       NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('M','利率类型',                     NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('N','久期',                         NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('O','评级',                         NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('P','是否当季到期',                 NFMT,       THEME9, 'Microsoft Sans Serif'),
    ('Q','压力情景净价(亿元)',           '0.0000_ ', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('R','压力情景全价(亿元)',           '0.0000_ ', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('S','压力情景偏离金额(万元)',       '#,##0.00', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('T','压力情景偏离金额绝对值(万元)', '#,##0.00', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('U','债券类别',                     NFMT,       PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('V','变现系数',                     NFMT,       PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('W','压力情景全价修正(亿元)',       '0.0000_ ', PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('X','压力情景偏离金额修正(万元)',   NFMT,       PatternFill('solid', fgColor='FFFF00'), '宋体'),
    ('Y','需变现偏离资产金额（亿元）',   NFMT,       PatternFill('solid', fgColor='FFFF00'), '宋体'),
]
for col, text, fmt, fill, font_name in _H2:
    c = ws15[col + '2']
    c.value = text; c.number_format = fmt
    c.font      = Font(name=font_name, size=10, bold=True)
    c.border    = _BORDER_THIN
    c.alignment = _ALIGN_CTR
    c.fill      = fill

# ── AA 欄：組合名稱參考列表 ───────────────────────────────
_AA = ['组合名称','薪金宝','现金增利','现金宝','沃利货币',
       '天利货币','收益宝','快线货币','惠利货币','华夏货币','财富宝','保证金货币']
for i, v in enumerate(_AA, 3):
    c = ws15.cell(row=i, column=27, value=v)
    c.number_format = NFMT
    c.border        = _BORDER_THIN
    c.alignment     = _ALIGN_CTR

# ── Q 欄公式模板（Row n，n >= 3）────────────────────────
_Q = (
    '=IF(M{n}=$M$1,G{n}-$N$1*N{n}*G{n},'
    'IF(C{n}="160309",VLOOKUP($A$1,shibor债定价!$A:$F,6,FALSE)*E{n},'
    'IF(C{n}="130208",VLOOKUP($A$1,shibor债定价!$AQ:$BC,6,FALSE)*E{n},'
    'IF(C{n}="160305",VLOOKUP($A$1,shibor债定价!$O:$T,6,FALSE)*E{n},'
    'IF(C{n}="110236",VLOOKUP($A$1,shibor债定价!#REF!,6,FALSE)*E{n},'
    'IF(C{n}="160202",VLOOKUP($A$1,shibor债定价!$AC:$AO,6,FALSE)*E{n},'
    'IF(C{n}="110236",VLOOKUP($A$1,shibor债定价!#REF!,6,FALSE)*E{n},'
    'IF(C{n}="150315",VLOOKUP($A$1,shibor债定价!$AQ:$AZ,6,FALSE)*E{n},'
    'IF(C{n}="130235",VLOOKUP($A$1,shibor债定价!$BE:$BN,6,FALSE)*E{n},'
    '0)))))))))/10^8'
)
_DATA_COLS = list('ABCDEFGHIJKLMNOP')

# ── Rows 3~MAX_ROWS：公式行 ───────────────────────────────
# 每欄的格式設定（col索引, fmt, alignment）
# A-P(1-16): General, center水平; Q/R(17-18): 0.0000_, 無align;
# S/T(19-20): #,##0.00, 無align; U/V(21-22): General, center;
# W(23): 0.0000_, center; X(24): 0.00_, center; Y(25): 0.00, center
_COL_CFG = {
    **{ci: ('General',   _ALIGN_H_CTR) for ci in range(1, 17)},   # A-P
    17: ('0.0000_ ',  None),          # Q
    18: ('0.0000_ ',  None),          # R
    19: ('#,##0.00',  None),          # S
    20: ('#,##0.00',  None),          # T
    21: ('General',   _ALIGN_H_CTR),  # U
    22: ('General',   _ALIGN_H_CTR),  # V
    23: ('0.0000_ ',  _ALIGN_H_CTR),  # W
    24: ('0.00_ ',    _ALIGN_H_CTR),  # X
    25: ('0.00',      _ALIGN_H_CTR),  # Y
}

print('  生成 债券及存单新 公式行...')
for row in range(3, MAX_ROWS + 1):
    src = row - 1
    n   = row
    # A:P — 引用持仓数据（宋体 size=10）
    for ci, cl in enumerate(_DATA_COLS, 1):
        c = ws15.cell(row=row, column=ci, value=f'=持仓数据!{cl}{src}')
        c.font      = Font(name='宋体', size=10)
        c.border    = _BORDER_THIN
        c.alignment = _ALIGN_H_CTR

    # Q~X — VLOOKUP 引用 压力测试结果 sheet（組合鍵 = port_name | security_code）
    # 压力测试结果 欄位：A=key, B=port, C=sec_code, ...,
    #   I(9)=stressed_mv_100m, J(10)=stressed_loss, K(11)=abs,
    #   L(12)=bond_category, M(13)=liq_ratio, N(14)=stressed_mv_adj_100m, O(15)=stressed_loss_adj
    _key = f'A{n}&"|"&C{n}'
    _lkp = lambda col: f'=IFERROR(VLOOKUP({_key},压力测试结果!$A:$O,{col},0),0)'

    def _qcell(ws_col, src_col, fmt=None, align=None):
        c = ws15.cell(row=row, column=ws_col, value=_lkp(src_col))
        c.font   = Font(name='宋体', size=11)
        c.border = _BORDER_THIN
        if fmt:   c.number_format = fmt
        if align: c.alignment     = align

    _qcell(17,  9, '0.0000_ ')                  # Q: 压力情景净价(亿元)
    _qcell(18,  9, '0.0000_ ')                  # R: 压力情景全价(亿元) ≈ Q
    _qcell(19, 10, '#,##0.00')                  # S: 压力偏离金额(万元)
    _qcell(20, 11, '#,##0.00')                  # T: 偏离绝对值(万元)
    _qcell(21, 12, 'General', _ALIGN_H_CTR)     # U: 债券类别
    _qcell(22, 13, 'General', _ALIGN_H_CTR)     # V: 变现系数
    _qcell(23, 14, '0.0000_ ', _ALIGN_H_CTR)   # W: 全价修正(亿元)
    _qcell(24, 15, NFMT,       _ALIGN_H_CTR)   # X: 偏离修正(万元)
    # Y: 需变现偏离资产金额（亿元）= X列（万元）÷ 10000
    cy = ws15.cell(row=row, column=25, value=f'=IFERROR(X{row}/10000,0)')
    cy.font          = Font(name='宋体', size=11)
    cy.border        = _BORDER_THIN
    cy.number_format = '0.00'
    cy.alignment     = _ALIGN_H_CTR

    if row % 1000 == 0:
        print(f'    {row}/{MAX_ROWS}')

# ── 欄寬 ──────────────────────────────────────────────────
_CW = {'A':13.18,'B':10.36,'C':16.18,'E':11.0,
       'F':15.36,'G':15.09,'H':14.27,'I':11.45,'J':9.82,
       'L':16.45,'M':9.82,'P':10.91,
       'Q':12.36,'R':9.82,'S':10.36,'T':9.82,
       'W':9.82,'X':11.0,'Y':11.45}
for col, w in _CW.items():
    ws15.column_dimensions[col].width = w

# ══════════════════════════════════════════════════════════
# 9. 压力测试结果  (42_stress_result.sql → A2，SQL 直接計算)
# ══════════════════════════════════════════════════════════
ws42 = wb.create_sheet('压力测试结果')
ws42.sheet_properties.tabColor = TAB_BLUE
# 15列，严格对应 42_stress_result.sql SELECT 输出顺序
# 债券及存单新 Q~X 的 VLOOKUP 按列号1-15引用此表
_H42 = [
    '组合键(lookup_key)',  # A(1)  port_name|security_code，VLOOKUP索引键
    '组合名称',            # B(2)
    '证券代码',            # C(3)
    '证券名称',            # D(4)
    '资产类型',            # E(5)  BOND_GOVT/BOND_CORP/CD/DEPOSIT
    '利率类型',            # F(6)  FIXED/FLOAT/DEPOSIT
    '当前市值(元)',         # G(7)
    '有效久期(年)',         # H(8)
    '压力市值(亿元)',       # I(9)  +50bp压力市值（亿元）
    '压力损失(万元)',       # J(10) 市值-压力市值（万元）
    '偏离绝对值(万元)',     # K(11) 压力损失绝对值（万元）
    '债券类别',            # L(12) 利率债/信用债/同业存单/存款
    '变现系数',            # M(13) 0~0.80，压力损失修正权重
    '压力全价修正(亿元)',   # N(14) 压力市值×变现系数（亿元）
    '压力损失修正(万元)',   # O(15) 压力损失×变现系数（万元），真实风险敞口
]
for i, h in enumerate(_H42, 1):
    hdr(ws42, 1, i, h)
yell(ws42, 2, 1, 200, len(_H42))
for col in range(1, len(_H42) + 1):
    ws42.column_dimensions[get_column_letter(col)].width = 16
ws42.freeze_panes = 'A2'

# ══════════════════════════════════════════════════════════
# 10. 债券及存单新程序结果NEW
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
for i, h in enumerate(['参数名称', '参数值', '说明'], 1):
    hdr(ws17, 1, i, h)
params = [
    ('rate_shock_bps',  50,       '利率衝擊幅度（基點），壓力測試用'),
    ('evaluate_date',   '',       '估值日期，由 run_report.py 注入'),
    ('coupon_type_fi',  'FIXED',  '固定利率類型代碼'),
    ('coupon_type_fl',  'FLOAT',  '浮息類型代碼'),
    ('coupon_type_zc',  'ZERO',   '零息/貼現券類型代碼'),
    ('shock_50bp',      0.005,    '+50bp（小數），= rate_shock_bps / 10000'),
]
for row, (name, val, desc) in enumerate(params, 2):
    ws17.cell(row=row, column=1, value=name)
    ws17.cell(row=row, column=2, value=val)
    ws17.cell(row=row, column=3, value=desc)
ws17.column_dimensions['A'].width = 20
ws17.column_dimensions['B'].width = 12
ws17.column_dimensions['C'].width = 40

# ── F1:N1 行 ─────────────────────────────────────────────
ws17['F1'] = '当前日期所在月倒数第5个交易日'
ws17['K1'] = '今天'
ws17['L1'].value         = '=TODAY()'
ws17['L1'].number_format = 'mm-dd-yy'
ws17['M1'].value         = '=TODAY()'
ws17['M1'].number_format = 'mm-dd-yy'
ws17['N1'] = '=TDays(G1,"2026-12-15","TradingCalendar=HKEX")'

# ── F2:L2 行 ─────────────────────────────────────────────
BLUE_CELL = PatternFill('solid', fgColor='00B0F0')
ws17['F2'].value         = ('=IF(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1)-1'
                             '=WORKDAY(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1),-1),'
                             'WORKDAY(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1)-1,-4),'
                             'WORKDAY(DATE(YEAR(WORKDAY(TODAY(),-1)),MONTH(WORKDAY(TODAY(),-1))+1,1)-1,-5))')
ws17['F2'].fill          = BLUE_CELL
ws17['F2'].number_format = 'mm-dd-yy'
ws17['K2'] = '5个交易日后'
ws17['L2'].value         = '=N5'
ws17['L2'].number_format = 'mm-dd-yy'

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
