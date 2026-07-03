"""
create_factsheet.py — MMF 月報 Factsheet PDF（精確仿 ChinaAMC 格式）
用法：python create_factsheet.py --date 2026-06-25 [--fund 基金名]

使用 ReportLab Canvas 低層 API，精確雙欄佈局，品牌紅 #BF0008
輸出目錄：mmf/output/report_04_mmf_monthly/（與 XLSX 相同）
"""
import sys, os, io, argparse
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date
from pathlib import Path

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR.parent / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 依賴 ─────────────────────────────────────────────────
try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import Color, white, black, HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.utils import ImageReader
except ImportError:
    print('pip install reportlab'); sys.exit(1)

try:
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt, matplotlib.font_manager as fm
    for _fp in ['C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/simhei.ttf']:
        if os.path.exists(_fp):
            matplotlib.rcParams.update({
                'font.family': [fm.FontProperties(fname=_fp).get_name(), 'sans-serif'],
                'axes.unicode_minus': False})
            break
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

try:
    import psycopg2, psycopg2.extras
    from dotenv import load_dotenv; load_dotenv()
    HAVE_DB = True
except ImportError:
    HAVE_DB = False

# ══════════════════════════════════════════════════════════
# 頁面常數（精確對應參考 PDF 解析結果）
# ══════════════════════════════════════════════════════════
W, H = A4   # 595.92 × 841.92 pt

# 欄位分界（參考 PDF 分析）
LX  = 15.3     # 左邊距
LC  = 291.6    # 左欄右界（同時是分隔線位置）
RX  = 303.9    # 右欄左界
RE  = 580.0    # 右欄右界
LCW = LC - LX  # 左欄寬 ≈ 276 pt
RCW = RE - RX  # 右欄寬 ≈ 276 pt

# 品牌色（精確匹配 PyMuPDF 解析的 RGB 191/0/8）
RED   = Color(191/255, 0/255, 8/255)     # #BF0008 品牌紅
BLACK = Color(0, 0, 0)
LGREY = Color(0.96, 0.96, 0.96)          # 淺灰交替行背景
LINE  = Color(0.7, 0.7, 0.7)             # 表格線

# 字型大小（對應參考 PDF 各元素）
FS_TITLE  = 13.5   # 基金名稱
FS_DATE   = 8.6    # 月報/日期副標題
FS_BADGE  = 4.9    # 合資格基金標籤
FS_RATING = 6.1    # AAAmf
FS_HEAD   = 9.8    # 節標題
FS_SUBHD  = 7.4    # 子標題（組合配置）
FS_BODY   = 6.1    # 正文/表格
FS_SMALL  = 5.9    # 上標/小字
FS_NOTE   = 6.1    # 腳注
FS_CONT   = 8.6    # 聯絡資料

# 座標轉換（PyMuPDF 為頂部原點，RL 為底部原點）
def yt(y_from_top): return H - y_from_top

# ══════════════════════════════════════════════════════════
# 字型設定
# ══════════════════════════════════════════════════════════
def _setup_fonts():
    cjk, cjk_b = 'Helvetica', 'Helvetica-Bold'
    arial, arial_b = 'Helvetica', 'Helvetica-Bold'
    for path, nm in [('C:/Windows/Fonts/msyh.ttc','MYH'),
                     ('C:/Windows/Fonts/simhei.ttf','SHH'),
                     ('C:/Windows/Fonts/simsun.ttc','SUN')]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(nm, path))
                addMapping(nm, 0, 0, nm); addMapping(nm, 1, 0, nm)
                cjk = cjk_b = nm; break
            except: pass
    for path, nm in [('C:/Windows/Fonts/arial.ttf','ARL'),
                     ('C:/Windows/Fonts/verdana.ttf','ARL')]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(nm, path)); arial = nm; break
            except: pass
    for path, nm in [('C:/Windows/Fonts/arialbd.ttf','ARLB')]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(nm, path)); arial_b = nm; break
            except: pass
    return cjk, cjk_b, arial, arial_b

CJK, CJK_B, ARIAL, ARIAL_B = _setup_fonts()

# ══════════════════════════════════════════════════════════
# Canvas 繪製輔助工具
# ══════════════════════════════════════════════════════════
class FS:
    """Factsheet 繪製工具，封裝 ReportLab Canvas 常用操作"""

    def __init__(self, c):
        self.c = c

    # ── 文字 ──────────────────────────────────────────────
    def text(self, x, y_top, s, font=None, size=FS_BODY, color=BLACK, align='left'):
        if s is None or str(s).strip() == '': return
        c = self.c
        c.setFillColor(color); c.setFont(font or CJK, size)
        y_rl = yt(y_top)
        if align == 'right':
            c.drawRightString(x, y_rl, str(s))
        elif align == 'center':
            c.drawCentredString(x, y_rl, str(s))
        else:
            c.drawString(x, y_rl, str(s))

    def text_rl(self, x, y_rl, s, font=None, size=FS_BODY, color=BLACK, align='left'):
        """直接用 RL 座標（從底部）"""
        if s is None or str(s).strip() == '': return
        c = self.c
        c.setFillColor(color); c.setFont(font or CJK, size)
        if align == 'right':  c.drawRightString(x, y_rl, str(s))
        elif align == 'center': c.drawCentredString(x, y_rl, str(s))
        else: c.drawString(x, y_rl, str(s))

    # ── 矩形 ──────────────────────────────────────────────
    def rect(self, x, y_top_pdf, w, h_pdf, fill=None, stroke=None, lw=0.3):
        c = self.c
        y_rl = yt(y_top_pdf + h_pdf)   # RL 底部 = H - (y_top + height)
        c.setLineWidth(lw)
        if fill: c.setFillColor(fill)
        if stroke: c.setStrokeColor(stroke)
        kwargs = {}
        if fill: kwargs['fill'] = 1
        if stroke: kwargs['stroke'] = 1
        if not fill and not stroke: c.setStrokeColor(LINE); kwargs['stroke'] = 1
        c.rect(x, y_rl, w, h_pdf, **kwargs)

    def hline(self, x1, x2, y_top_pdf, color=LINE, lw=0.4):
        c = self.c
        c.setStrokeColor(color); c.setLineWidth(lw)
        y_rl = yt(y_top_pdf)
        c.line(x1, y_rl, x2, y_rl)

    def vline(self, x, y1_top, y2_top, color=LINE, lw=0.4):
        c = self.c
        c.setStrokeColor(color); c.setLineWidth(lw)
        c.line(x, yt(y1_top), x, yt(y2_top))

    # ── 節標題（紅色小方塊 + 粗體文字）──────────────────
    def section_head(self, x, y_top, text, size=FS_HEAD):
        sq = 7.4  # 小方塊邊長
        self.rect(x, y_top, sq, sq, fill=RED)
        self.text(x + sq + 2, y_top - 0.5, text, font=CJK_B, size=size, color=RED)

    # ── 圖片 ──────────────────────────────────────────────
    def image(self, x, y_top, w, h, img_bytes):
        y_rl = yt(y_top + h)
        self.c.drawImage(ImageReader(io.BytesIO(img_bytes)), x, y_rl, w, h)


# ══════════════════════════════════════════════════════════
# 圖表生成
# ══════════════════════════════════════════════════════════
PIE_COLORS = ['#2E75B6','#70AD47','#ED7D31','#FFC000','#5B9BD5',
              '#7030A0','#FF0000','#00B0F0']

def _pie_png(labels, values, w_pt, h_pt, dpi=130):
    if not HAVE_MPL or not values: return None
    fig, ax = plt.subplots(figsize=(w_pt/72, h_pt/72), dpi=dpi)
    cols = PIE_COLORS[:len(values)]
    wedges, _, autotexts = ax.pie(
        values, labels=None, colors=cols,
        autopct=lambda p: f'{p:.1f}%' if p >= 3 else '',
        startangle=90, pctdistance=0.72,
        wedgeprops={'linewidth': 0.5, 'edgecolor': 'white'})
    for at in autotexts: at.set_fontsize(6)
    ax.legend(wedges, [f'{l}  {v:.1f}%' for l, v in zip(labels, values)],
              loc='lower center', bbox_to_anchor=(0.5, -0.25),
              ncol=2, fontsize=5.5, frameon=False, handlelength=0.8)
    ax.set_aspect('equal')
    plt.tight_layout(pad=0.2)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=dpi); plt.close()
    buf.seek(0); return buf.read()

def _bar_png(labels, values, w_pt, h_pt, dpi=130):
    if not HAVE_MPL or not values: return None
    fig, ax = plt.subplots(figsize=(w_pt/72, h_pt/72), dpi=dpi)
    x = range(len(labels))
    ax.bar(x, values, color='#2E75B6', width=0.6, edgecolor='white')
    for i, v in enumerate(values):
        if v > 0.5:
            ax.text(i, v + 0.3, f'{v:.1f}%', ha='center', va='bottom', fontsize=5.5)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=6, rotation=30, ha='right')
    ax.set_ylabel('%', fontsize=6); ax.yaxis.set_tick_params(labelsize=6)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.set_ylim(0, max(values) * 1.2 if values else 100)
    plt.tight_layout(pad=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=dpi); plt.close()
    buf.seek(0); return buf.read()


# ══════════════════════════════════════════════════════════
# 資料查詢
# ══════════════════════════════════════════════════════════
def _conn():
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST','localhost'), port=int(os.getenv('POSTGRES_PORT','5432')),
        dbname=os.getenv('POSTGRES_DB','fsi_risk'), user=os.getenv('POSTGRES_USER','fsi_user'),
        password=os.getenv('POSTGRES_PASSWORD','change_me'))

def _q(sql, conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql); return [dict(r) for r in cur.fetchall()]

def _nav_ago(d, fn, lo, hi):
    return (f"(SELECT DISTINCT ON(n.port_id,n.class_id) n.unit_nav "
            f"FROM fsi.balance_portfolio_nav n "
            f"JOIN fsi.para_portfolio p ON p.port_id=n.port_id "
            f"WHERE p.port_name='{fn}' "
            f"AND n.evaluate_date BETWEEN '{d}'::DATE-{hi} AND '{d}'::DATE-{lo} "
            f"ORDER BY n.port_id,n.class_id,n.evaluate_date DESC LIMIT 1)")

def load_fund_data(fund_name: str, ev: date) -> dict:
    d = ev.isoformat()
    conn = _conn()

    info = _q(f"""
        SELECT p.port_name, COALESCE(p.base_currency,'HKD') AS ccy,
               ROUND(n.net_asset/1e8,4) AS nav_100m,
               COALESCE(m.wam_days,0)   AS wam,
               COALESCE(m.wal_days,0)   AS wal,
               COALESCE(m.return_rate_7d,0) AS ret7d
        FROM fsi.para_portfolio p
        JOIN fsi.balance_portfolio_nav n ON n.port_id=p.port_id
             AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
        LEFT JOIN fsi.balance_portfolio_mmf m ON m.port_id=p.port_id
             AND m.evaluate_date='{d}'::DATE
        WHERE p.port_name='{fund_name}' AND p.is_mmf=TRUE
    """, conn)

    nav_cls = _q(f"""
        SELECT COALESCE(n.class_id::TEXT,'Base') AS cls,
               ROUND(COALESCE(n.unit_nav,0),4)   AS nav_pu, n.evaluate_date AS dt
        FROM fsi.para_portfolio p
        JOIN fsi.balance_portfolio_nav n ON n.port_id=p.port_id
             AND n.evaluate_date='{d}'::DATE
        WHERE p.port_name='{fund_name}' AND p.is_mmf=TRUE
        ORDER BY n.class_id NULLS LAST
    """, conn)

    # 累積業績
    cur_nav = _q(f"""SELECT n.unit_nav FROM fsi.balance_portfolio_nav n
        JOIN fsi.para_portfolio p ON p.port_id=n.port_id
        WHERE p.port_name='{fund_name}' AND n.evaluate_date='{d}'::DATE
          AND n.class_id IS NULL""", conn)
    cn = float(cur_nav[0]['unit_nav']) if cur_nav else 0

    def _p(lo, hi):
        r = _q(f"SELECT {_nav_ago(d,fund_name,lo,hi)} AS v", conn)
        v = r[0]['v'] if r else None
        if v and float(v) > 0 and cn > 0:
            return round((cn / float(v) - 1) * 100, 2)
        return None

    inc_r = _q(f"""SELECT n.unit_nav, n.evaluate_date AS d0
        FROM fsi.balance_portfolio_nav n
        JOIN fsi.para_portfolio p ON p.port_id=n.port_id
        WHERE p.port_name='{fund_name}' AND n.class_id IS NULL
        ORDER BY n.evaluate_date ASC LIMIT 1""", conn)

    perf = {'1m':_p(25,40),'3m':_p(85,100),'6m':_p(175,195),'1y':_p(355,380),
            'since':None,'ann':None,'incept_date':None,'ret7d':None}
    if inc_r and cn > 0:
        nav0 = float(inc_r[0]['unit_nav']); d0 = inc_r[0]['d0']
        days = (ev - d0).days
        if nav0 > 0:
            perf['since'] = round((cn/nav0 - 1)*100, 2)
            perf['incept_date'] = d0
            if days > 0: perf['ann'] = round((pow(cn/nav0, 365/days)-1)*100, 2)
    if info: perf['ret7d'] = info[0].get('ret7d', 0)

    # 年度業績（2021起）
    annual = []
    for yr in range(2021, ev.year + 1):
        lbl  = '本年至今' if yr == ev.year else str(yr)
        e_d  = d if yr == ev.year else f'{yr}-12-31'
        rows = _q(f"""SELECT n.unit_nav FROM fsi.balance_portfolio_nav n
            JOIN fsi.para_portfolio p ON p.port_id=n.port_id
            WHERE p.port_name='{fund_name}' AND n.class_id IS NULL
              AND n.evaluate_date IN (
                  (SELECT MIN(evaluate_date) FROM fsi.balance_portfolio_nav n2
                   JOIN fsi.para_portfolio p2 ON p2.port_id=n2.port_id
                   WHERE p2.port_name='{fund_name}' AND n2.class_id IS NULL
                     AND n2.evaluate_date >= '{yr}-01-01' AND n2.evaluate_date <= '{yr}-01-10'),
                  (SELECT MAX(evaluate_date) FROM fsi.balance_portfolio_nav n3
                   JOIN fsi.para_portfolio p3 ON p3.port_id=n3.port_id
                   WHERE p3.port_name='{fund_name}' AND n3.class_id IS NULL
                     AND n3.evaluate_date <= '{e_d}'))
            ORDER BY n.evaluate_date""", conn)
        if len(rows) >= 2:
            v0, v1 = float(rows[0]['unit_nav']), float(rows[-1]['unit_nav'])
            if v0 > 0: annual.append({'lbl':lbl, 'pct':round((v1/v0-1)*100,2)})

    # 資產配置
    alloc = []
    _LBL = {'CASH':'現金及等價物','DEPOSIT':'定期存款','CD':'同業存單',
             'BOND_GOVT':'政府/公共債券','BOND_CORP':'企業債券','REPO':'逆回購'}
    for r in _q(f"""
        SELECT a.asset_class::TEXT AS cls, ROUND(SUM(a.market_value)/n.net_asset*100,2) AS pct
        FROM fsi.balance_portfolio_asset a
        JOIN fsi.para_portfolio p ON p.port_id=a.port_id
        JOIN fsi.balance_portfolio_nav n ON n.port_id=a.port_id
             AND n.evaluate_date=a.evaluate_date AND n.class_id IS NULL
        WHERE p.port_name='{fund_name}' AND a.evaluate_date='{d}'::DATE AND n.net_asset>0
        GROUP BY a.asset_class, n.net_asset ORDER BY pct DESC""", conn):
        alloc.append({'lbl': _LBL.get(r['cls'],r['cls']), 'pct': float(r['pct'])})

    # 到期分佈
    _BUCK = [(1,'1天以內'),(7,'2-7天'),(30,'8-30天'),(60,'31-60天'),
             (90,'61-90天'),(180,'91-180天'),(365,'181-365天'),(9999,'365天以上')]
    mat_raw = _q(f"""
        WITH h AS (
            SELECT b.port_id,
                   GREATEST(COALESCE(b.remaining_days,(b.maturity_date-'{d}'::DATE)::INT),0) AS rd,
                   COALESCE(b.market_value,0) AS mv
            FROM fsi.balance_bond b JOIN fsi.para_portfolio p ON p.port_id=b.port_id
            WHERE p.port_name='{fund_name}' AND b.evaluate_date='{d}'::DATE AND b.quantity>0
            UNION ALL
            SELECT c.port_id,
                   GREATEST(COALESCE(c.remaining_days,(c.maturity_date-'{d}'::DATE)::INT),0),
                   COALESCE(c.market_value,0)
            FROM fsi.balance_cd c JOIN fsi.para_portfolio p ON p.port_id=c.port_id
            WHERE p.port_name='{fund_name}' AND c.evaluate_date='{d}'::DATE
            UNION ALL
            SELECT d2.port_id, GREATEST((d2.maturity_date-'{d}'::DATE)::INT,0),
                   COALESCE(d2.principal,0)
            FROM fsi.balance_deposit d2 JOIN fsi.para_portfolio p ON p.port_id=d2.port_id
            WHERE p.port_name='{fund_name}' AND d2.evaluate_date='{d}'::DATE
            UNION ALL
            SELECT r.port_id,
                   GREATEST((COALESCE(r.actual_maturity_date,r.maturity_date)-'{d}'::DATE)::INT,0),
                   COALESCE(r.principal,0)
            FROM fsi.balance_repo r JOIN fsi.para_portfolio p ON p.port_id=r.port_id
            WHERE p.port_name='{fund_name}' AND r.evaluate_date='{d}'::DATE AND r.repo_type='REV_REPO'
        )
        SELECT SUM(mv) AS total_mv,
               CASE WHEN rd<=1 THEN 1 WHEN rd<=7 THEN 2 WHEN rd<=30 THEN 3
                    WHEN rd<=60 THEN 4 WHEN rd<=90 THEN 5 WHEN rd<=180 THEN 6
                    WHEN rd<=365 THEN 7 ELSE 8 END AS ord,
               ROUND(SUM(mv)/n.net_asset*100,2) AS pct
        FROM h JOIN fsi.balance_portfolio_nav n ON n.port_id=h.port_id
               AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
        GROUP BY ord, n.net_asset ORDER BY ord""", conn)
    _BLBL = {1:'1天以內',2:'2-7天',3:'8-30天',4:'31-60天',
             5:'61-90天',6:'91-180天',7:'181-365天',8:'超365天'}
    mat = [{'lbl':_BLBL[r['ord']], 'pct':float(r['pct'])} for r in mat_raw]

    # 加權平均 YTM
    ytm_r = _q(f"""
        SELECT ROUND(SUM(ytm*mv)/NULLIF(SUM(mv),0),4) AS ytm_pct FROM (
            SELECT COALESCE(b.ytm,0) AS ytm, COALESCE(b.market_value,0) AS mv
            FROM fsi.balance_bond b JOIN fsi.para_portfolio p ON p.port_id=b.port_id
            WHERE p.port_name='{fund_name}' AND b.evaluate_date='{d}'::DATE AND b.quantity>0
            UNION ALL SELECT COALESCE(c.ytm,0), COALESCE(c.market_value,0)
            FROM fsi.balance_cd c JOIN fsi.para_portfolio p ON p.port_id=c.port_id
            WHERE p.port_name='{fund_name}' AND c.evaluate_date='{d}'::DATE
            UNION ALL SELECT COALESCE(d2.interest_rate,0)*100, COALESCE(d2.principal,0)
            FROM fsi.balance_deposit d2 JOIN fsi.para_portfolio p ON p.port_id=d2.port_id
            WHERE p.port_name='{fund_name}' AND d2.evaluate_date='{d}'::DATE
        ) t""", conn)

    conn.close()
    base = info[0] if info else {}
    return dict(port_name=fund_name, ccy=base.get('ccy','HKD'),
                nav_100m=base.get('nav_100m',0), wam=base.get('wam',0),
                wal=base.get('wal',0), ret7d=perf.get('ret7d',0),
                nav_cls=nav_cls, perf=perf, annual=annual,
                alloc=alloc, mat=mat,
                ytm=float(ytm_r[0]['ytm_pct']) if ytm_r and ytm_r[0]['ytm_pct'] else 0,
                eval_date=ev)


# ══════════════════════════════════════════════════════════
# PDF 構建（精確雙欄，仿參考 Factsheet）
# ══════════════════════════════════════════════════════════
def _fmt(v, dec=2):
    if v is None: return '—'
    return f'{float(v):.{dec}f}%'

def build_pdf(data: dict, out_path: Path):
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    f = FS(c)
    ev  = data['eval_date']
    ccy = data['ccy']
    fn  = data['port_name']
    ev_tc = f'{ev.year}年{ev.month:02d}月{ev.day:02d}日'

    # ══════════════════════════════════════════
    # 第 1 頁
    # ══════════════════════════════════════════

    # ── 頁首 ──────────────────────────────────
    # 基金名稱（13.5pt 粗）
    f.text(LX, 18.9 + FS_TITLE, fn, font=CJK_B, size=FS_TITLE)
    # 基金月報 + 日期（8.6pt 粗）
    f.text(LX, 40.0 + FS_DATE, f'基金月報    截至  {ev_tc}', font=CJK_B, size=FS_DATE)
    # 「新資本投資者入境計劃」合資格基金（小字，紅色）
    f.text(160.3, 42.7 + FS_BADGE + 1, '「新資本投資者入境計劃」合資格基金',
           font=CJK_B, size=FS_BADGE, color=RED)
    # 品牌橫條（紅 + 黑）
    c.setFillColor(RED);   c.rect(LX, yt(69.4), 192.2 - LX, 9.2, fill=1, stroke=0)
    c.setFillColor(BLACK); c.rect(192.2, yt(69.4), RE - 192.2 + 0.6, 9.2, fill=1, stroke=0)

    # ── 左欄 ─────────────────────────────────
    # 投資目標
    f.section_head(LX, 221.7, '投資目標')
    invest_obj = ('本基金旨在提供與通行貨幣市場利率相若的回報，以資本安全及流動性為'
                  '首要考慮，主要投資於港幣計價的短期存款及高質量貨幣市場工具。')
    _wrap_text(f, LX + 2, 238.5, invest_obj, LC - LX - 4, FS_BODY, leading=8.5)

    # 基金資料
    f.section_head(LX, 286.7, '基金資料')
    f.hline(LX, LC, 300.2, lw=0.5)
    fund_info_rows = [
        ('法律結構', '香港傘子式單位信託基金'),
        ('投資經理', '博匯基金管理有限公司'),
        ('基礎貨幣', ccy),
        ('基金規模',  f'{ccy} {data["nav_100m"]:.2f} 百萬'),
        ('交易頻率', '每日'),
    ]
    _draw_kv_table(f, LX, 301.1, LC, fund_info_rows, 8.1)
    f.hline(LX, LC, 301.1 + len(fund_info_rows)*8.1, lw=0.5)

    # 基金單位類別
    y_cls = 373.3
    f.section_head(LX, y_cls, '基金單位類別')
    f.hline(LX, LC, y_cls + 14, lw=0.5)
    # 表頭
    hdrs = [('類別',80), ('發行日期',42), ('每股資產淨值',52), ('彭博編碼',50), ('ISIN編碼',51)]
    _draw_table_row(f, LX, y_cls + 14.5, hdrs, bold=True)
    f.hline(LX, LC, y_cls + 22, lw=0.5)
    yx = y_cls + 22.5
    for r in data['nav_cls']:
        _draw_table_row(f, LX, yx, [
            (r['cls'], 80), (str(r['dt']), 42),
            (f"{ccy} {r['nav_pu']:.4f}", 52), ('—', 50), ('—', 51)])
        yx += 9.2
        f.hline(LX, LC, yx - 0.3, lw=0.3)
    f.text(LX, yx + 2, f'數據來源：本公司。截至 {ev_tc}，除非另有說明。',
           size=FS_BODY-0.5, color=Color(0.4,0.4,0.4))

    # ── 右欄 ─────────────────────────────────
    # 基金表現
    f.section_head(RX, 221.7, '基金表現')
    y_perf = 235.0
    # 累積表現
    f.text(RX, y_perf, '累積表現', font=CJK_B, size=FS_HEAD, color=RED)
    f.text(RX + 40, y_perf, '(%)', font=ARIAL_B, size=FS_HEAD, color=RED)

    y_ph = y_perf + 14   # 表頭 y_top（PDF 座標）
    perf_cols = [('類別',78),('一個月',26),('三個月',26),('六個月',26),
                 ('一年',22),('自成立',30),('年化表現\n(自成立)',36),('7日\n年化',24)]
    _draw_table_header(f, RX, y_ph, perf_cols)
    ypp = y_ph + 18
    p = data['perf']
    # 僅顯示基金整體（我們基金可能沒有分類別）
    _draw_table_data(f, RX, ypp, perf_cols, [
        fn[:12],
        _fmt(p.get('1m')), _fmt(p.get('3m')), _fmt(p.get('6m')),
        _fmt(p.get('1y')), _fmt(p.get('since')), _fmt(p.get('ann')),
        _fmt(p.get('ret7d'))])
    ypp += 9
    f.hline(RX, RE, ypp, lw=0.4)

    # 年度表現
    y_ann = ypp + 8
    f.text(RX, y_ann, '年度表現', font=CJK_B, size=FS_HEAD, color=RED)
    f.text(RX + 40, y_ann, '(%)', font=ARIAL_B, size=FS_HEAD, color=RED)
    y_anh = y_ann + 13
    ann_lbls = [a['lbl'] for a in data['annual']]
    ann_w = max(16, int(RCW / max(len(ann_lbls)+1, 2)))
    ann_cols = [('類別', 78)] + [(l, ann_w) for l in ann_lbls]
    _draw_table_header(f, RX, y_anh, ann_cols)
    y_anv = y_anh + 18
    _draw_table_data(f, RX, y_anv, ann_cols,
                     [fn[:12]] + [_fmt(a['pct']) for a in data['annual']])
    y_anv += 9
    f.hline(RX, RE, y_anv, lw=0.4)

    # 頁1 腳注 + 免責聲明
    _draw_page1_footnotes(f, fn, ev_tc)

    c.showPage()  # ── 翻頁 ──────────────────────────

    # ══════════════════════════════════════════
    # 第 2 頁
    # ══════════════════════════════════════════
    # 重複頁首
    f.text(LX, 18.9 + FS_TITLE, fn, font=CJK_B, size=FS_TITLE)
    f.text(LX, 40.0 + FS_DATE, f'基金月報    截至  {ev_tc}', font=CJK_B, size=FS_DATE)
    f.text(160.3, 42.7 + FS_BADGE + 1, '「新資本投資者入境計劃」合資格基金',
           font=CJK_B, size=FS_BADGE, color=RED)
    c.setFillColor(RED);   c.rect(LX, yt(69.4), 192.2 - LX, 9.2, fill=1, stroke=0)
    c.setFillColor(BLACK); c.rect(192.2, yt(69.4), RE - 192.2 + 0.6, 9.2, fill=1, stroke=0)

    # ── 左欄：投資組合特點 ────────────────────
    f.section_head(LX, 79.2, '投資組合特點')
    f.hline(LX, LC, 93.0, lw=0.5)
    f.text(LX, 94.8 + FS_BODY, '加權平均到期日', size=FS_BODY)
    f.text(LC - 5, 94.8 + FS_BODY, f'{data["wam"]:.2f} 天', align='right', size=FS_BODY)
    f.hline(LX, LC, 103.0, lw=0.3)
    f.text(LX, 104.0 + FS_BODY, '加權平均到期收益率', size=FS_BODY)
    f.text(LX + 70, 103.9 + FS_SMALL, '1', font=ARIAL_B, size=FS_SMALL, color=BLACK)
    f.text(LC - 5, 104.0 + FS_BODY, f'{data["ytm"]:.2f}%', align='right', size=FS_BODY)
    f.hline(LX, LC, 113.0, lw=0.5)

    # ── 右欄：組合配置 + 到期分佈 ────────────
    f.section_head(RX, 79.2, '組合配置')

    # 資產類別分佈（餅圖）
    f.text(RX, 100.9 + FS_SUBHD, '資產類別分佈', font=CJK_B, size=FS_SUBHD, color=RED)
    f.text(RX + 46, 100.9 + FS_SUBHD, '(%)', font=ARIAL_B, size=FS_SUBHD, color=RED)
    if data['alloc']:
        pie_bytes = _pie_png([a['lbl'] for a in data['alloc']],
                             [a['pct'] for a in data['alloc']],
                             w_pt=RCW, h_pt=88)
        if pie_bytes:
            f.image(RX, 108.0, RCW, 88, pie_bytes)

    # 到期日分佈（柱狀圖）
    f.text(RX, 199.1 + FS_SUBHD, '到期日分佈', font=CJK_B, size=FS_SUBHD, color=RED)
    f.text(RX + 36, 199.1 + FS_SUBHD, '(%)', font=ARIAL_B, size=FS_SUBHD, color=RED)
    if data['mat']:
        bar_bytes = _bar_png([m['lbl'] for m in data['mat']],
                             [m['pct'] for m in data['mat']],
                             w_pt=RCW, h_pt=100)
        if bar_bytes:
            f.image(RX, 207.0, RCW, 100, bar_bytes)

    # ── 頁2 腳注 + 免責聲明 ───────────────────
    _draw_page2_footnotes(f, fn, ev_tc)

    c.save()
    print(f'  ✅ {out_path.name}')


# ══════════════════════════════════════════════════════════
# 表格繪製輔助
# ══════════════════════════════════════════════════════════
def _wrap_text(f, x, y_top, text, max_w, size, leading=8.0, color=BLACK):
    """簡單換行文字繪製"""
    words = text
    # 按字元寬估算換行（CJK 每字約 size*0.6pt）
    chars_per_line = int(max_w / (size * 0.62))
    lines = []
    while len(words) > chars_per_line:
        lines.append(words[:chars_per_line])
        words = words[chars_per_line:]
    if words: lines.append(words)
    for i, ln in enumerate(lines):
        f.text(x, y_top + size + i * leading, ln, size=size, color=color)

def _draw_kv_table(f, x, y_top, x_end, rows, row_h):
    """左右兩欄鍵值表（鍵 / 值）"""
    vx = x + 65   # 值欄起始 x
    for i, (k, v) in enumerate(rows):
        yt_row = y_top + i * row_h
        if i % 2 == 1:
            f.rect(x, yt_row - 1, x_end - x, row_h, fill=LGREY)
        f.text(x + 2, yt_row + FS_BODY, k, size=FS_BODY, color=Color(0.4,0.4,0.4))
        f.text(vx, yt_row + FS_BODY, v, size=FS_BODY)

def _draw_table_row(f, x, y_top, cols, bold=False):
    """單行，cols = [(text, width), ...]"""
    fn_use = CJK_B if bold else CJK
    cx = x
    for text, w in cols:
        f.text(cx + 1, y_top + FS_BODY, text, font=fn_use, size=FS_BODY - 0.3)
        cx += w

def _draw_table_header(f, x, y_top, cols):
    """深色背景表頭行"""
    total_w = sum(w for _, w in cols)
    f.c.setFillColor(Color(0.85, 0.85, 0.85))
    f.c.rect(x, yt(y_top + 9), total_w, 9, fill=1, stroke=0)
    cx = x
    for text, w in cols:
        f.text(cx + 1, y_top + FS_BODY, text, font=CJK_B, size=FS_BODY - 0.5)
        cx += w
    f.hline(x, x + total_w, y_top, lw=0.4)
    f.hline(x, x + total_w, y_top + 9, lw=0.4)

def _draw_table_data(f, x, y_top, cols, values):
    """數據行"""
    cx = x
    for (_, w), v in zip(cols, values):
        f.text(cx + 1, y_top + FS_BODY, v or '—', font=ARIAL, size=FS_BODY - 0.3)
        cx += w

def _draw_page1_footnotes(f, fund_name, ev_tc):
    """第1頁：腳注 + 免責聲明"""
    # 腳注
    f.text(LX, 773.0, '1  關於基金詳情（包括費用）請參考基金說明書。', size=FS_NOTE, color=Color(0.4,0.4,0.4))
    f.text(LX, 782.0, '2  過往表現並不代表未來業績。業績以資產淨值對資產淨值計算，並已計入股息再投資。', size=FS_NOTE, color=Color(0.4,0.4,0.4))

    # 免責聲明
    f.hline(LX, RE, 640, lw=0.5)
    disclaimer = ('投資涉及風險，包括損失本金。基金單位價格可升亦可跌，過往業績並不代表未來回報。'
                  '本基金是投資基金而非銀行存款。投資於貨幣市場工具涉及流動性風險、信貸風險、利率風險及估值風險。'
                  '本資料僅供參考，不構成任何投資建議，亦不構成對任何證券的買賣邀約。'
                  '閣下應細閱基金銷售文件，了解基金詳情及風險因素，如有需要應諮詢獨立專業意見。'
                  f'本資料之發行人為{fund_name}的管理人。此資料並未獲香港證監會審閱。')
    _wrap_text(f, LX, 648, disclaimer, RE - LX - 4, FS_NOTE - 0.3,
               leading=7.2, color=Color(0.35, 0.35, 0.35))

def _draw_page2_footnotes(f, fund_name, ev_tc):
    """第2頁：腳注 + 聯絡資料"""
    f.hline(LX, RE, 733.0, lw=0.5)
    f.text(LX, 738.0, '1  使用基金中每個持倉的加權平均到期收益率計算。', size=FS_NOTE, color=Color(0.4,0.4,0.4))
    f.text(LX, 746.5, f'數據來源：除非另有說明，資料來源均來自本公司。截至 {ev_tc}。', size=FS_NOTE, color=Color(0.4,0.4,0.4))

    f.hline(LX, RE, 756.0, lw=0.3)
    disc = ('重要聲明：投資涉及風險。基金股價可升亦可跌，過往業績並不表示將來基金回報，未來回報不能被保證。'
            '閣下亦可能損失所投資之本金。本資料並不構成對於任何證券或基金的買賣或進行任何交易之邀約或任何投資建議。'
            '本文件只供閣下參考之用，閣下不應依賴本文件作任何投資決定。'
            '本文所載之部份資料或數據是從第三方取得的，本公司合理地相信該等資料或數據是準確，完整及至所示日期為最新的；'
            '本公司確保準確地再製造該等數據或資料，但並不保證其準確性及完整性。'
            f'本資料之發行人為{fund_name}的管理人。此資料並未獲香港證監會審閱。')
    _wrap_text(f, LX, 763.0, disc, RE - LX - 4, FS_NOTE - 0.3,
               leading=7.0, color=Color(0.35, 0.35, 0.35))

    # 聯絡資料
    f.text(LX + 2, 812.0 + FS_CONT, '服務熱線：(852) XXXX XXXX', size=FS_CONT)
    f.text(260, 812.0 + FS_CONT, '網站：www.example.com.hk', size=FS_CONT)
    f.text(415, 812.0 + FS_CONT, '電郵：fund@example.com', size=FS_CONT)


# ══════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description='MMF Factsheet PDF')
    ap.add_argument('--date', default=date.today().isoformat())
    ap.add_argument('--fund', default=None, help='指定基金名稱（缺省=全部）')
    args = ap.parse_args()
    ev = date.fromisoformat(args.date)

    if not HAVE_DB:
        print('⚠ 需要 psycopg2 + .env 才能連接資料庫'); return

    conn = _conn()
    funds = [r['port_name'] for r in _q(
        "SELECT p.port_name FROM fsi.para_portfolio p "
        "WHERE p.is_mmf=TRUE AND p.is_active=TRUE ORDER BY p.port_name", conn)]
    conn.close()
    if args.fund: funds = [f for f in funds if args.fund in f]
    if not funds: print('找不到基金'); return

    print(f'\n[MMF Factsheet] 日期：{ev}  基金：{funds}')
    for fn in funds:
        print(f'  處理：{fn} ...', end='', flush=True)
        try:
            data = load_fund_data(fn, ev)
            safe = fn.replace('/', '-').replace(' ', '_')
            out  = OUTPUT_DIR / f'MMF_Factsheet_{ev.strftime("%Y%m%d")}_{safe}.pdf'
            build_pdf(data, out)
        except Exception as e:
            print(f'\n  ✗ 失敗：{e}')
            import traceback; traceback.print_exc()

if __name__ == '__main__':
    main()
