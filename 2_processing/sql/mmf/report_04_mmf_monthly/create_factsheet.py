"""
create_factsheet.py — MMF 月報 Factsheet PDF 生成器
用法：python create_factsheet.py --date 2026-06-25 [--fund 博匯港元貨幣市場基金I]

仿 ChinaAMC Select MMF Factsheet 雙頁 A4 格式
  第1頁：基金資料、股份類別NAV、費用、累積業績、年度業績
  第2頁：投資組合特點、資產配置餅圖、到期分佈柱狀圖、免責聲明

輸出：同 run_report.py 的 output/report_04_mmf_monthly/
"""

import sys, os, argparse, io
sys.stdout.reconfigure(encoding='utf-8')

from datetime import date
from pathlib import Path

# ── 路徑（與 run_report.py 輸出目錄一致）────────────────
BASE_DIR   = Path(__file__).parent
MMF_DIR    = BASE_DIR.parent          # .../report_04_mmf_monthly/..  → mmf/
OUTPUT_DIR = MMF_DIR / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 外部依賴 ─────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, white, black, Color
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.fonts import addMapping
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, Image as RLImage,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except ImportError:
    print('pip install reportlab'); sys.exit(1)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    # 讓圖表標籤支援中文
    import matplotlib.font_manager as fm
    for _fp in ['C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/simhei.ttf','C:/Windows/Fonts/simsun.ttc']:
        if os.path.exists(_fp):
            matplotlib.rcParams['font.family'] = [fm.FontProperties(fname=_fp).get_name(), 'sans-serif']
            break
    matplotlib.rcParams['axes.unicode_minus'] = False
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

try:
    import psycopg2, psycopg2.extras
    from dotenv import load_dotenv
    load_dotenv()
    HAVE_DB = True
except ImportError:
    HAVE_DB = False

# ══════════════════════════════════════════════════════════
# 字型（系統 CJK → 回退 Helvetica）
# ══════════════════════════════════════════════════════════
def _setup_fonts():
    for path, name in [
        ('C:/Windows/Fonts/msyh.ttc',   'CJK'),
        ('C:/Windows/Fonts/simhei.ttf', 'CJK'),
        ('C:/Windows/Fonts/simsun.ttc', 'CJK'),
    ]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                addMapping(name, 0, 0, name)
                addMapping(name, 1, 0, name)   # bold 也用同一字型
                return name
            except Exception:
                pass
    return 'Helvetica'

CJK = _setup_fonts()

def P(text, size=9, bold=False, color=black, align='LEFT', leading=None):
    """快捷 Paragraph"""
    style = ParagraphStyle(
        f'p{size}{"b" if bold else ""}',
        fontName=CJK,
        fontSize=size,
        textColor=color,
        alignment={'LEFT':0,'CENTER':1,'RIGHT':2}.get(align, 0),
        leading=leading or size * 1.4,
        wordWrap='CJK',
    )
    return Paragraph(str(text), style)

# ══════════════════════════════════════════════════════════
# 品牌色系
# ══════════════════════════════════════════════════════════
DEEP_BLUE  = HexColor('#1F3864')
MID_BLUE   = HexColor('#2E75B6')
LIGHT_BLUE = HexColor('#BDD7EE')
GREY_BG    = HexColor('#F4F7FB')
GREY_TXT   = HexColor('#595959')
GOLD       = HexColor('#C9A227')

W, H   = A4
ML = MR = 15 * mm
CW = W - ML - MR          # 內容寬度 ≈ 180 mm

# ══════════════════════════════════════════════════════════
# 資料庫查詢
# ══════════════════════════════════════════════════════════
def _conn():
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST','localhost'),
        port=int(os.getenv('POSTGRES_PORT','5432')),
        dbname=os.getenv('POSTGRES_DB','fsi_risk'),
        user=os.getenv('POSTGRES_USER','fsi_user'),
        password=os.getenv('POSTGRES_PASSWORD','change_me'),
    )

def _q(sql, conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        c.execute(sql)
        return [dict(r) for r in c.fetchall()]

def load_fund_data(fund_name: str, eval_date: date) -> dict:
    d = eval_date.isoformat()
    conn = _conn()

    # 基金基本資料
    info = _q(f"""
        SELECT p.port_name, COALESCE(p.base_currency,'HKD') AS base_currency,
               ROUND(n.net_asset/1e8,4)      AS nav_100m,
               COALESCE(m.wam_days,0)         AS wam_days,
               COALESCE(m.wal_days,0)         AS wal_days,
               COALESCE(m.return_rate_7d,0)   AS ret7d
        FROM fsi.para_portfolio p
        JOIN fsi.balance_portfolio_nav n
             ON n.port_id=p.port_id AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
        LEFT JOIN fsi.balance_portfolio_mmf m
             ON m.port_id=p.port_id AND m.evaluate_date='{d}'::DATE
        WHERE p.is_mmf=TRUE AND p.is_active=TRUE
          AND p.port_name='{fund_name}'
    """, conn)

    # 各類別 NAV（unit_nav 正確欄位名）
    nav_cls = _q(f"""
        SELECT COALESCE(n.class_id::TEXT,'Base') AS class_id,
               ROUND(COALESCE(n.unit_nav,0),4)  AS nav_per_unit,
               n.evaluate_date
        FROM fsi.para_portfolio p
        JOIN fsi.balance_portfolio_nav n
             ON n.port_id=p.port_id AND n.evaluate_date='{d}'::DATE
        WHERE p.port_name='{fund_name}' AND p.is_mmf=TRUE
        ORDER BY n.class_id NULLS LAST
    """, conn)

    # 業績（近 N 天最近一個交易日）
    def _nav_ago(lo, hi):
        return f"""(SELECT DISTINCT ON(n.port_id,n.class_id)
                   n.unit_nav FROM fsi.balance_portfolio_nav n
                   JOIN fsi.para_portfolio p ON p.port_id=n.port_id
                   WHERE p.port_name='{fund_name}'
                     AND n.evaluate_date BETWEEN '{d}'::DATE-{hi} AND '{d}'::DATE-{lo}
                   ORDER BY n.port_id,n.class_id,n.evaluate_date DESC LIMIT 1)"""

    def _perf(lo, hi):
        r = _q(f"SELECT {_nav_ago(lo,hi)} AS v", conn)
        v = r[0]['v'] if r else None
        if v and v > 0:
            cur = _q(f"SELECT unit_nav FROM fsi.balance_portfolio_nav n "
                     f"JOIN fsi.para_portfolio p ON p.port_id=n.port_id "
                     f"WHERE p.port_name='{fund_name}' AND n.evaluate_date='{d}'::DATE "
                     f"AND n.class_id IS NULL LIMIT 1", conn)
            if cur:
                return round((float(cur[0]['unit_nav']) / float(v) - 1) * 100, 2)
        return None

    perf = {
        '1M':  _perf(25,40), '3M': _perf(85,100),
        '6M':  _perf(175,195), '1Y': _perf(355,380),
    }

    # 自成立表現
    inc_q = _q(f"""
        SELECT n.unit_nav, n.evaluate_date AS d0
        FROM fsi.balance_portfolio_nav n
        JOIN fsi.para_portfolio p ON p.port_id=n.port_id
        WHERE p.port_name='{fund_name}' AND n.class_id IS NULL
        ORDER BY n.evaluate_date ASC LIMIT 1
    """, conn)
    cur_q = _q(f"""
        SELECT n.unit_nav FROM fsi.balance_portfolio_nav n
        JOIN fsi.para_portfolio p ON p.port_id=n.port_id
        WHERE p.port_name='{fund_name}' AND n.evaluate_date='{d}'::DATE
          AND n.class_id IS NULL
    """, conn)

    perf['since_incept'] = None
    perf['ann']          = None
    perf['incept_date']  = None
    if inc_q and cur_q and float(inc_q[0]['unit_nav']) > 0:
        nav0 = float(inc_q[0]['unit_nav'])
        navT = float(cur_q[0]['unit_nav'])
        d0   = inc_q[0]['d0']
        days = (eval_date - d0).days
        perf['since_incept'] = round((navT/nav0 - 1)*100, 2)
        perf['incept_date']  = d0
        if days > 0:
            perf['ann'] = round((pow(navT/nav0, 365/days) - 1)*100, 2)

    # 年度業績（2021-本年至今）
    annual = []
    for yr in range(2021, eval_date.year + 1):
        label = '本年至今' if yr == eval_date.year else str(yr)
        start_d = f'{yr}-01-01'
        end_d   = d if yr == eval_date.year else f'{yr}-12-31'
        rows = _q(f"""
            SELECT n.unit_nav, n.evaluate_date AS dt
            FROM fsi.balance_portfolio_nav n
            JOIN fsi.para_portfolio p ON p.port_id=n.port_id
            WHERE p.port_name='{fund_name}' AND n.class_id IS NULL
              AND n.evaluate_date BETWEEN '{start_d}' AND '{end_d}'
            ORDER BY n.evaluate_date
        """, conn)
        if len(rows) >= 2:
            v0 = float(rows[0]['unit_nav'])
            v1 = float(rows[-1]['unit_nav'])
            annual.append({'label': label, 'pct': round((v1/v0-1)*100, 2) if v0>0 else None})

    # 資產配置
    alloc_raw = _q(f"""
        SELECT a.asset_class::TEXT AS cls,
               ROUND(SUM(a.market_value)/n.net_asset*100, 2) AS pct
        FROM fsi.balance_portfolio_asset a
        JOIN fsi.para_portfolio p ON p.port_id=a.port_id
        JOIN fsi.balance_portfolio_nav n ON n.port_id=a.port_id
             AND n.evaluate_date=a.evaluate_date AND n.class_id IS NULL
        WHERE p.port_name='{fund_name}' AND a.evaluate_date='{d}'::DATE AND n.net_asset>0
        GROUP BY a.asset_class, n.net_asset
        ORDER BY pct DESC
    """, conn)
    _LBL = {'CASH':'現金及等價物','DEPOSIT':'定期存款','CD':'同業存單',
             'BOND_GOVT':'政府/公共債券','BOND_CORP':'企業債券','REPO':'逆回購協議'}
    alloc = [{'label': _LBL.get(r['cls'], r['cls']), 'pct': float(r['pct'])} for r in alloc_raw]

    # 到期分佈
    mat_raw = _q(f"""
        WITH h AS (
            SELECT b.port_id,
                   GREATEST(COALESCE(b.remaining_days,(b.maturity_date-'{d}'::DATE)::INT),0) AS rd,
                   COALESCE(b.market_value,0) AS mv
            FROM fsi.balance_bond b
            JOIN fsi.para_portfolio p ON p.port_id=b.port_id
            WHERE p.port_name='{fund_name}' AND b.evaluate_date='{d}'::DATE AND b.quantity>0
            UNION ALL
            SELECT c.port_id,
                   GREATEST(COALESCE(c.remaining_days,(c.maturity_date-'{d}'::DATE)::INT),0),
                   COALESCE(c.market_value,0)
            FROM fsi.balance_cd c
            JOIN fsi.para_portfolio p ON p.port_id=c.port_id
            WHERE p.port_name='{fund_name}' AND c.evaluate_date='{d}'::DATE
            UNION ALL
            SELECT d2.port_id,
                   GREATEST((d2.maturity_date-'{d}'::DATE)::INT,0),
                   COALESCE(d2.principal,0)
            FROM fsi.balance_deposit d2
            JOIN fsi.para_portfolio p ON p.port_id=d2.port_id
            WHERE p.port_name='{fund_name}' AND d2.evaluate_date='{d}'::DATE
            UNION ALL
            SELECT r.port_id,
                   GREATEST((COALESCE(r.actual_maturity_date,r.maturity_date)-'{d}'::DATE)::INT,0),
                   COALESCE(r.principal,0)
            FROM fsi.balance_repo r
            JOIN fsi.para_portfolio p ON p.port_id=r.port_id
            WHERE p.port_name='{fund_name}' AND r.evaluate_date='{d}'::DATE
              AND r.repo_type='REV_REPO'
        )
        SELECT CASE WHEN rd<=1 THEN '1天以內'
                    WHEN rd<=7 THEN '2至7天' WHEN rd<=30 THEN '8至30天'
                    WHEN rd<=60 THEN '31至60天' WHEN rd<=90 THEN '61至90天'
                    WHEN rd<=180 THEN '91至180天' WHEN rd<=365 THEN '181至365天'
                    ELSE '超過365天' END AS bucket,
               CASE WHEN rd<=1 THEN 1 WHEN rd<=7 THEN 2 WHEN rd<=30 THEN 3
                    WHEN rd<=60 THEN 4 WHEN rd<=90 THEN 5 WHEN rd<=180 THEN 6
                    WHEN rd<=365 THEN 7 ELSE 8 END AS ord,
               ROUND(SUM(mv)/n.net_asset*100,2) AS pct
        FROM h
        JOIN fsi.balance_portfolio_nav n ON n.port_id=h.port_id
             AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
        GROUP BY bucket, ord, n.net_asset ORDER BY ord
    """, conn)
    mat = [{'bucket': r['bucket'], 'pct': float(r['pct'])} for r in mat_raw]

    # 加權平均 YTM
    ytm_q = _q(f"""
        SELECT ROUND(SUM(ytm*mv)/NULLIF(SUM(mv),0),4) AS ytm_pct
        FROM (
            SELECT COALESCE(b.ytm,0) AS ytm, COALESCE(b.market_value,0) AS mv
            FROM fsi.balance_bond b JOIN fsi.para_portfolio p ON p.port_id=b.port_id
            WHERE p.port_name='{fund_name}' AND b.evaluate_date='{d}'::DATE AND b.quantity>0
            UNION ALL
            SELECT COALESCE(c.ytm,0), COALESCE(c.market_value,0)
            FROM fsi.balance_cd c JOIN fsi.para_portfolio p ON p.port_id=c.port_id
            WHERE p.port_name='{fund_name}' AND c.evaluate_date='{d}'::DATE
            UNION ALL
            SELECT COALESCE(d2.interest_rate,0)*100, COALESCE(d2.principal,0)
            FROM fsi.balance_deposit d2 JOIN fsi.para_portfolio p ON p.port_id=d2.port_id
            WHERE p.port_name='{fund_name}' AND d2.evaluate_date='{d}'::DATE
        ) t
    """, conn)
    ytm = float(ytm_q[0]['ytm_pct']) if ytm_q and ytm_q[0]['ytm_pct'] else 0.0

    conn.close()
    base = info[0] if info else {}
    return dict(
        port_name   = fund_name,
        base_currency = base.get('base_currency','HKD'),
        nav_100m    = base.get('nav_100m', 0),
        wam_days    = base.get('wam_days', 0),
        wal_days    = base.get('wal_days', 0),
        ret7d       = base.get('ret7d', 0),
        nav_cls     = nav_cls,
        perf        = perf,
        annual      = annual,
        alloc       = alloc,
        mat         = mat,
        ytm         = ytm,
        eval_date   = eval_date,
    )


# ══════════════════════════════════════════════════════════
# 圖表輔助
# ══════════════════════════════════════════════════════════
PIE_COLORS = ['#2E75B6','#70AD47','#ED7D31','#FFC000','#5B9BD5','#7030A0','#00B0F0']

def _png_pie(labels, values):
    if not HAVE_MPL or not values: return None
    fig, ax = plt.subplots(figsize=(3.8, 3.0), dpi=130)
    wedges, _, autotexts = ax.pie(
        values, labels=None, colors=PIE_COLORS[:len(values)],
        autopct=lambda p: f'{p:.1f}%' if p>=3 else '',
        startangle=90, pctdistance=0.72,
        wedgeprops={'linewidth':0.5,'edgecolor':'white'})
    for at in autotexts: at.set_fontsize(7)
    ax.legend(wedges, [f'{l}  {v:.1f}%' for l,v in zip(labels,values)],
              loc='center left', bbox_to_anchor=(1.0,0.5),
              fontsize=7, frameon=False, handlelength=0.8)
    ax.set_aspect('equal')
    plt.tight_layout()
    buf = io.BytesIO(); plt.savefig(buf,format='png',bbox_inches='tight',dpi=130); plt.close(); buf.seek(0)
    return buf.read()

def _png_bar(labels, values):
    if not HAVE_MPL or not values: return None
    fig, ax = plt.subplots(figsize=(5.0, 2.6), dpi=130)
    x = range(len(labels))
    bars = ax.bar(x, values, color='#2E75B6', width=0.6, edgecolor='white')
    for bar, v in zip(bars, values):
        if v > 0.5:
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.3,
                    f'{v:.1f}%', ha='center', va='bottom', fontsize=6.5)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=7, rotation=25, ha='right')
    ax.set_ylabel('%', fontsize=8); ax.yaxis.set_tick_params(labelsize=7)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout()
    buf = io.BytesIO(); plt.savefig(buf,format='png',bbox_inches='tight',dpi=130); plt.close(); buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════
# PDF 構建
# ══════════════════════════════════════════════════════════
def _ts(cmds): return TableStyle(cmds)

BASE_TS = _ts([
    ('GRID',        (0,0),(-1,-1), 0.3, LIGHT_BLUE),
    ('TOPPADDING',  (0,0),(-1,-1), 3),
    ('BOTTOMPADDING',(0,0),(-1,-1), 3),
    ('LEFTPADDING', (0,0),(-1,-1), 5),
    ('RIGHTPADDING',(0,0),(-1,-1), 5),
    ('FONTNAME',    (0,0),(-1,-1), CJK),
    ('FONTSIZE',    (0,0),(-1,-1), 8),
])
HDR_TS = _ts([
    *BASE_TS._cmds,
    ('BACKGROUND',  (0,0),(-1,0), MID_BLUE),
    ('TEXTCOLOR',   (0,0),(-1,0), white),
    ('FONTNAME',    (0,0),(-1,0), CJK),
    ('FONTSIZE',    (0,0),(-1,0), 8),
    ('ROWBACKGROUNDS',(0,1),(-1,-1),[white, GREY_BG]),
])

def _sec(title):
    """藍色節標題 + 底線"""
    t = Table([[P(title, 10, bold=True, color=white)]], colWidths=[CW])
    t.setStyle(_ts([
        ('BACKGROUND',(0,0),(-1,-1), MID_BLUE),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),8),
    ]))
    return t

def _fmt(v, decimals=2, suffix='%'):
    if v is None: return '—'
    return f'{float(v):.{decimals}f}{suffix}'


def build_pdf(data: dict, out_path: Path):
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=ML, rightMargin=MR,
        topMargin=10*mm, bottomMargin=10*mm,
    )
    ev  = data['eval_date']
    ev_str = f'截至  {ev.year}年{ev.month:02d}月{ev.day:02d}日'
    story = []

    # ── 頁首（深藍底，雙欄）──────────────────────────────
    hdr_tbl = Table([[
        P(data['port_name'], 15, bold=True, color=white),
        P('「新資本投資者入境計劃」合資格基金\n'
          f'基金月報  {ev_str}', 9, color=white, align='RIGHT'),
    ]], colWidths=[CW*0.65, CW*0.35])
    hdr_tbl.setStyle(_ts([
        ('BACKGROUND',(0,0),(-1,-1),DEEP_BLUE),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('LEFTPADDING',(0,0),(0,-1),10),('RIGHTPADDING',(-1,0),(-1,-1),10),
    ]))
    story += [hdr_tbl, Spacer(1,3*mm)]

    # ══ 第1頁 ═════════════════════════════════════════════

    # 基金資料
    story.append(_sec('基金資料'))
    story.append(Spacer(1,1*mm))
    fi_data = [
        ['法律結構','香港傘子式單位信託基金','交易頻率','每日'],
        ['基礎貨幣', data['base_currency'],
         '基金規模', f"{data['base_currency']} {data['nav_100m']:.2f} 億元"],
        ['加權平均到期期限（WAM）',
         f"{data['wam_days']:.0f} 天  （SFC上限 60 天）",
         '7日年化收益率',  f"{data['ret7d']:.2f}%"],
        ['加權平均存續期（WAL）',
         f"{data['wal_days']:.0f} 天  （SFC上限 120 天）",
         '成立日期', str(data['perf'].get('incept_date','—'))],
    ]
    fi_tbl = Table(
        [[P(c, 8, color=GREY_TXT if i%2==0 else black,
            bold=(i%2==0)) for i,c in enumerate(row)] for row in fi_data],
        colWidths=[CW*.22, CW*.28, CW*.22, CW*.28])
    fi_tbl.setStyle(_ts([*BASE_TS._cmds,
        ('ROWBACKGROUNDS',(0,0),(-1,-1),[white,GREY_BG])]))
    story += [fi_tbl, Spacer(1,4*mm)]

    # 基金單位類別 NAV
    story.append(_sec('基金單位類別'))
    story.append(Spacer(1,1*mm))
    nav_rows = [['類別', '每股資產淨值', '數據日期']]
    for r in data['nav_cls']:
        nav_rows.append([
            r['class_id'],
            f"{data['base_currency']} {r['nav_per_unit']:.4f}",
            str(r['evaluate_date']),
        ])
    nav_tbl = Table(nav_rows, colWidths=[CW*.35, CW*.35, CW*.30])
    nav_tbl.setStyle(HDR_TS)
    story += [nav_tbl, Spacer(1,4*mm)]

    # 累積業績
    story.append(_sec('基金表現²（累積，%）'))
    story.append(Spacer(1,1*mm))
    p = data['perf']
    perf_rows = [
        ['類別', '一個月', '三個月', '六個月', '一年', '自成立', '年化表現\n（自成立）', '7日\n年化表現³'],
        [data['port_name'],
         _fmt(p.get('1M')), _fmt(p.get('3M')), _fmt(p.get('6M')),
         _fmt(p.get('1Y')), _fmt(p.get('since_incept')),
         _fmt(p.get('ann')), _fmt(data['ret7d'])],
    ]
    perf_tbl = Table(perf_rows, colWidths=[CW*.25]+[CW*.107]*7)
    perf_tbl.setStyle(HDR_TS)
    story += [perf_tbl, Spacer(1,1.5*mm)]
    story.append(P('過往業績並不代表未來回報。業績以資產淨值對資產淨值計算，並已計入股息再投資。',
                   7, color=GREY_TXT))
    story.append(Spacer(1,4*mm))

    # 年度業績
    story.append(_sec('年度表現²（%）'))
    story.append(Spacer(1,1*mm))
    ann_hdrs = [a['label'] for a in data['annual']]
    ann_vals = [_fmt(a['pct']) for a in data['annual']]
    if ann_hdrs:
        ann_tbl = Table(
            [['類別']+ann_hdrs, [data['port_name']]+ann_vals],
            colWidths=[CW*.25]+[CW*.75/max(len(ann_hdrs),1)]*len(ann_hdrs))
        ann_tbl.setStyle(HDR_TS)
        story += [ann_tbl, Spacer(1,1.5*mm)]
    story.append(P('² 自成立日期起計算。過往業績並不代表未來業績，投資者可能無法取回全部本金。',
                   7, color=GREY_TXT))

    # ══ 第2頁 ═════════════════════════════════════════════
    story.append(PageBreak())
    story += [hdr_tbl, Spacer(1,3*mm)]   # 同一頁首

    # 投資組合特點（仿 Factsheet 大數字格式）
    story.append(_sec('投資組合特點'))
    story.append(Spacer(1,1*mm))
    chars_tbl = Table([[
        P(f'加權平均到期日\n{data["wam_days"]:.1f} 天', 13, bold=True, color=DEEP_BLUE, align='CENTER'),
        P(f'加權平均到期收益率¹\n{data["ytm"]:.2f}%',   13, bold=True, color=DEEP_BLUE, align='CENTER'),
    ]], colWidths=[CW*.5, CW*.5])
    chars_tbl.setStyle(_ts([
        ('BACKGROUND',(0,0),(-1,-1),GREY_BG),
        ('GRID',(0,0),(-1,-1),0.3,LIGHT_BLUE),
        ('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
    ]))
    story += [chars_tbl, Spacer(1,1.5*mm)]
    story.append(P('¹ 使用基金中每個持倉的中位到期收益率加權平均計算。', 7, color=GREY_TXT))
    story.append(Spacer(1,4*mm))

    # 組合配置 + 到期分佈（並排）
    story.append(_sec('組合配置'))
    story.append(Spacer(1,1*mm))

    pie_img = bar_img = None
    if data['alloc']:
        b = _png_pie([a['label'] for a in data['alloc']],
                     [a['pct']   for a in data['alloc']])
        if b: pie_img = RLImage(io.BytesIO(b), width=CW*.46, height=58*mm)

    if data['mat']:
        b = _png_bar([m['bucket'] for m in data['mat']],
                     [m['pct']   for m in data['mat']])
        if b: bar_img = RLImage(io.BytesIO(b), width=CW*.51, height=58*mm)

    if pie_img or bar_img:
        chart_row = [pie_img or P('(無數據)', 8), bar_img or P('(無數據)', 8)]
        c_tbl = Table([chart_row], colWidths=[CW*.48, CW*.52])
        c_tbl.setStyle(_ts([('VALIGN',(0,0),(-1,-1),'TOP'),
                             ('LEFTPADDING',(0,0),(-1,-1),0),
                             ('RIGHTPADDING',(0,0),(-1,-1),0)]))
        story += [c_tbl, Spacer(1,1.5*mm)]
        story.append(P('資產類別分佈（左）  到期日分佈（右）', 7, color=GREY_TXT, align='CENTER'))
    story.append(Spacer(1,4*mm))

    # 重要聲明
    story.append(HRFlowable(width=CW, thickness=0.5, color=LIGHT_BLUE))
    story.append(Spacer(1,2*mm))
    story.append(P('重要聲明', 9, bold=True, color=DEEP_BLUE))
    for line in [
        '投資涉及風險，包括損失本金。基金單位價格可升亦可跌，過往業績並不代表未來回報。',
        '本基金是投資基金而非銀行存款。投資於貨幣市場工具涉及流動性風險、信貸風險及利率風險。',
        f'³ 7日年化收益率根據過去7個自然日的NAV變化年化計算，不代表實際一年回報。',
        '數據來源：FSI Risk Platform 數據庫。本資料為內部風控用途，未獲香港證監會審閱。',
    ]:
        story.append(P(line, 7, color=GREY_TXT))
    story.append(Spacer(1,3*mm))
    story.append(P('服務熱線：(852) XXXX XXXX  ｜  電郵：fund@example.com.hk',
                   8, color=MID_BLUE))

    doc.build(story)
    print(f'  ✅ {out_path.name}')
    return out_path


# ══════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description='MMF Factsheet PDF')
    ap.add_argument('--date', default=date.today().isoformat())
    ap.add_argument('--fund', default=None, help='指定基金名（缺省=全部）')
    args = ap.parse_args()
    ev = date.fromisoformat(args.date)

    # 取基金清單
    conn = _conn()
    funds = [r['port_name'] for r in _q(
        "SELECT p.port_name FROM fsi.para_portfolio p "
        "WHERE p.is_mmf=TRUE AND p.is_active=TRUE ORDER BY p.port_name", conn)]
    conn.close()

    if args.fund:
        funds = [f for f in funds if args.fund in f]
    if not funds:
        print('找不到符合條件的基金'); return

    print(f'\n[MMF Factsheet] 估值日期：{ev}  基金：{funds}')
    for fn in funds:
        print(f'\n  處理：{fn}')
        data = load_fund_data(fn, ev)
        safe = fn.replace('/', '-').replace(' ', '_')
        pdf  = OUTPUT_DIR / f'MMF_Factsheet_{ev.strftime("%Y%m%d")}_{safe}.pdf'
        build_pdf(data, pdf)


if __name__ == '__main__':
    main()
