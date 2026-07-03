"""
create_factsheet.py — 精確克隆 ChinaAMC MMF Factsheet PDF
策略：從 ref_layout.json 讀取參考 PDF 的所有元素（文字位置/顏色/字型、矩形），
      逐像素渲染，只把可變字段替換為我們的基金數據。
用法：python create_factsheet.py --date 2026-06-25 [--fund 基金名]
"""
import sys, os, io, argparse, json
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date, timedelta
from pathlib import Path

BASE_DIR   = Path(__file__).parent
LAYOUT_FILE = BASE_DIR / 'ref_layout.json'
OUTPUT_DIR  = BASE_DIR.parent / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 依賴 ─────────────────────────────────────────────────
try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import Color, black, white
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
except ImportError:
    print('pip install reportlab'); sys.exit(1)

try:
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    for _fp in ['C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/simhei.ttf']:
        if os.path.exists(_fp):
            plt.rcParams.update({'font.family':[fm.FontProperties(fname=_fp).get_name(),'sans-serif'],
                                 'axes.unicode_minus':False}); break
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

try:
    import psycopg2, psycopg2.extras
    from dotenv import load_dotenv; load_dotenv()
    HAVE_DB = True
except ImportError:
    HAVE_DB = False

W, H = A4  # 595.92 × 841.92

# ══════════════════════════════════════════════════════════
# 字型設定
# ══════════════════════════════════════════════════════════
def _setup():
    fonts = {}
    for path, name in [('C:/Windows/Fonts/msyh.ttc','MYH'),
                        ('C:/Windows/Fonts/simhei.ttf','MYH')]:
        if os.path.exists(path) and 'cjk' not in fonts:
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                addMapping(name,0,0,name); addMapping(name,1,0,name)
                fonts['cjk'] = name; break
            except: pass
    for path, name in [('C:/Windows/Fonts/arial.ttf','ARL')]:
        if os.path.exists(path) and 'arial' not in fonts:
            try: pdfmetrics.registerFont(TTFont(name,path)); fonts['arial'] = name; break
            except: pass
    for path, name in [('C:/Windows/Fonts/arialbd.ttf','ARLB')]:
        if os.path.exists(path) and 'arialb' not in fonts:
            try: pdfmetrics.registerFont(TTFont(name,path)); fonts['arialb'] = name; break
            except: pass
    fonts.setdefault('cjk','Helvetica')
    fonts.setdefault('arial','Helvetica')
    fonts.setdefault('arialb','Helvetica-Bold')
    return fonts

FONTS = _setup()

def _map_font(ref_font):
    """參考 PDF 字型名 → ReportLab 字型名"""
    r = ref_font.lower()
    if 'bold' in r and ('yahe' in r or 'hei' in r or 'sun' in r): return FONTS['cjk']
    if 'yahe' in r or 'hei' in r or 'sun' in r: return FONTS['cjk']
    if 'bold' in r: return FONTS['arialb']
    return FONTS['arial']

def _map_color(int_color):
    """整數顏色 → ReportLab Color"""
    r = (int_color >> 16) & 0xFF
    g = (int_color >> 8)  & 0xFF
    b =  int_color        & 0xFF
    return Color(r/255, g/255, b/255)

# ══════════════════════════════════════════════════════════
# 資料庫查詢
# ══════════════════════════════════════════════════════════
def _conn():
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST','localhost'),
        port=int(os.getenv('POSTGRES_PORT','5432')),
        dbname=os.getenv('POSTGRES_DB','fsi_risk'),
        user=os.getenv('POSTGRES_USER','fsi_user'),
        password=os.getenv('POSTGRES_PASSWORD','change_me'))

def _q(sql, conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        c.execute(sql); return [dict(r) for r in c.fetchall()]

def load_fund_data(fund_name, ev):
    d = ev.isoformat()
    conn = _conn()
    info = _q(f"""
        SELECT p.port_name, COALESCE(p.base_currency,'HKD') AS ccy,
               ROUND(n.net_asset/1e6,2) AS nav_millions,
               COALESCE(m.wam_days,0) AS wam, COALESCE(m.wal_days,0) AS wal,
               COALESCE(m.return_rate_7d,0) AS ret7d
        FROM fsi.para_portfolio p
        JOIN fsi.balance_portfolio_nav n ON n.port_id=p.port_id
             AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
        LEFT JOIN fsi.balance_portfolio_mmf m ON m.port_id=p.port_id
             AND m.evaluate_date='{d}'::DATE
        WHERE p.port_name='{fund_name}' AND p.is_mmf=TRUE""", conn)

    # NAV 各類別
    nav_cls = _q(f"""
        SELECT COALESCE(n.class_id::TEXT,'Base') AS cls,
               ROUND(COALESCE(n.unit_nav,0),4) AS nav_pu, n.evaluate_date AS dt
        FROM fsi.para_portfolio p
        JOIN fsi.balance_portfolio_nav n ON n.port_id=p.port_id
             AND n.evaluate_date='{d}'::DATE
        WHERE p.port_name='{fund_name}' AND p.is_mmf=TRUE
        ORDER BY n.class_id NULLS LAST""", conn)

    # 累積業績
    cur = _q(f"""SELECT n.unit_nav FROM fsi.balance_portfolio_nav n
        JOIN fsi.para_portfolio p ON p.port_id=n.port_id
        WHERE p.port_name='{fund_name}' AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL""", conn)
    cn = float(cur[0]['unit_nav']) if cur else 0

    def _nav_ago(lo, hi):
        r = _q(f"""SELECT DISTINCT ON(n.class_id) n.unit_nav
            FROM fsi.balance_portfolio_nav n
            JOIN fsi.para_portfolio p ON p.port_id=n.port_id
            WHERE p.port_name='{fund_name}' AND n.class_id IS NULL
              AND n.evaluate_date BETWEEN '{d}'::DATE-{hi} AND '{d}'::DATE-{lo}
            ORDER BY n.class_id, n.evaluate_date DESC""", conn)
        v = float(r[0]['unit_nav']) if r else 0
        return round((cn/v-1)*100,2) if v>0 and cn>0 else None

    inc = _q(f"""SELECT n.unit_nav, n.evaluate_date AS d0
        FROM fsi.balance_portfolio_nav n
        JOIN fsi.para_portfolio p ON p.port_id=n.port_id
        WHERE p.port_name='{fund_name}' AND n.class_id IS NULL
        ORDER BY n.evaluate_date ASC LIMIT 1""", conn)

    perf = {'1m':_nav_ago(25,40),'3m':_nav_ago(85,100),'6m':_nav_ago(175,195),
            '1y':_nav_ago(355,380), 'since':None,'ann':None,'d0':None,'ret7d':0}
    if inc and cn>0:
        v0=float(inc[0]['unit_nav']); d0=inc[0]['d0']; days=(ev-d0).days
        if v0>0:
            perf['since']=round((cn/v0-1)*100,2); perf['d0']=d0
            if days>0: perf['ann']=round((pow(cn/v0,365/days)-1)*100,2)
    if info: perf['ret7d']=info[0].get('ret7d',0)

    # 年度業績
    annual=[]
    for yr in range(2021, ev.year+1):
        lbl = '本年至今' if yr==ev.year else str(yr)
        end = d if yr==ev.year else f'{yr}-12-31'
        rows = _q(f"""SELECT n.unit_nav FROM fsi.balance_portfolio_nav n
            JOIN fsi.para_portfolio p ON p.port_id=n.port_id
            WHERE p.port_name='{fund_name}' AND n.class_id IS NULL
              AND n.evaluate_date IN (
                (SELECT MIN(e2) FROM (
                  SELECT evaluate_date AS e2 FROM fsi.balance_portfolio_nav n2
                  JOIN fsi.para_portfolio p2 ON p2.port_id=n2.port_id
                  WHERE p2.port_name='{fund_name}' AND n2.class_id IS NULL
                    AND n2.evaluate_date >= '{yr}-01-01' AND n2.evaluate_date <= '{yr}-01-10') t),
                (SELECT MAX(e3) FROM (
                  SELECT evaluate_date AS e3 FROM fsi.balance_portfolio_nav n3
                  JOIN fsi.para_portfolio p3 ON p3.port_id=n3.port_id
                  WHERE p3.port_name='{fund_name}' AND n3.class_id IS NULL
                    AND n3.evaluate_date <= '{end}') t2))
            ORDER BY n.evaluate_date""", conn)
        if len(rows)>=2:
            v0,v1=float(rows[0]['unit_nav']),float(rows[-1]['unit_nav'])
            if v0>0: annual.append({'lbl':lbl,'pct':round((v1/v0-1)*100,2)})

    # 資產配置
    _LBL={'CASH':'現金及等價物','DEPOSIT':'定期存款','CD':'同業存單',
          'BOND_GOVT':'政府/公共債券','BOND_CORP':'企業債券','REPO':'逆回購協議'}
    alloc=[]
    for r in _q(f"""SELECT a.asset_class::TEXT AS cls,
               ROUND(SUM(a.market_value)/n.net_asset*100,2) AS pct
        FROM fsi.balance_portfolio_asset a
        JOIN fsi.para_portfolio p ON p.port_id=a.port_id
        JOIN fsi.balance_portfolio_nav n ON n.port_id=a.port_id
             AND n.evaluate_date=a.evaluate_date AND n.class_id IS NULL
        WHERE p.port_name='{fund_name}' AND a.evaluate_date='{d}'::DATE AND n.net_asset>0
        GROUP BY a.asset_class,n.net_asset ORDER BY pct DESC""", conn):
        alloc.append({'lbl':_LBL.get(r['cls'],r['cls']),'pct':float(r['pct'])})

    # 到期分佈
    mat=[]
    for r in _q(f"""WITH h AS (
        SELECT b.port_id,GREATEST(COALESCE(b.remaining_days,(b.maturity_date-'{d}'::DATE)::INT),0) AS rd,
               COALESCE(b.market_value,0) AS mv FROM fsi.balance_bond b
        JOIN fsi.para_portfolio p ON p.port_id=b.port_id WHERE p.port_name='{fund_name}'
          AND b.evaluate_date='{d}'::DATE AND b.quantity>0
        UNION ALL SELECT c.port_id,GREATEST(COALESCE(c.remaining_days,(c.maturity_date-'{d}'::DATE)::INT),0),
               COALESCE(c.market_value,0) FROM fsi.balance_cd c
        JOIN fsi.para_portfolio p ON p.port_id=c.port_id WHERE p.port_name='{fund_name}'
          AND c.evaluate_date='{d}'::DATE
        UNION ALL SELECT d2.port_id,GREATEST((d2.maturity_date-'{d}'::DATE)::INT,0),COALESCE(d2.principal,0)
        FROM fsi.balance_deposit d2 JOIN fsi.para_portfolio p ON p.port_id=d2.port_id
        WHERE p.port_name='{fund_name}' AND d2.evaluate_date='{d}'::DATE
        UNION ALL SELECT r.port_id,GREATEST((COALESCE(r.actual_maturity_date,r.maturity_date)-'{d}'::DATE)::INT,0),
               COALESCE(r.principal,0) FROM fsi.balance_repo r
        JOIN fsi.para_portfolio p ON p.port_id=r.port_id WHERE p.port_name='{fund_name}'
          AND r.evaluate_date='{d}'::DATE AND r.repo_type='REV_REPO')
        SELECT CASE WHEN rd<=1 THEN 1 WHEN rd<=7 THEN 2 WHEN rd<=30 THEN 3
                    WHEN rd<=60 THEN 4 WHEN rd<=90 THEN 5 WHEN rd<=180 THEN 6
                    WHEN rd<=365 THEN 7 ELSE 8 END AS ord,
               CASE WHEN rd<=1 THEN '1天以內' WHEN rd<=7 THEN '2-7天' WHEN rd<=30 THEN '8-30天'
                    WHEN rd<=60 THEN '31-60天' WHEN rd<=90 THEN '61-90天' WHEN rd<=180 THEN '91-180天'
                    WHEN rd<=365 THEN '181-365天' ELSE '365天以上' END AS bucket,
               ROUND(SUM(mv)/n.net_asset*100,2) AS pct
        FROM h JOIN fsi.balance_portfolio_nav n ON n.port_id=h.port_id
               AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
        GROUP BY ord,bucket,n.net_asset ORDER BY ord""", conn):
        mat.append({'lbl':r['bucket'],'pct':float(r['pct'])})

    # YTM
    ytm_r=_q(f"""SELECT ROUND(SUM(ytm*mv)/NULLIF(SUM(mv),0),4) AS v FROM(
        SELECT COALESCE(b.ytm,0) AS ytm,COALESCE(b.market_value,0) AS mv FROM fsi.balance_bond b
        JOIN fsi.para_portfolio p ON p.port_id=b.port_id WHERE p.port_name='{fund_name}'
          AND b.evaluate_date='{d}'::DATE AND b.quantity>0
        UNION ALL SELECT COALESCE(c.ytm,0),COALESCE(c.market_value,0) FROM fsi.balance_cd c
        JOIN fsi.para_portfolio p ON p.port_id=c.port_id WHERE p.port_name='{fund_name}'
          AND c.evaluate_date='{d}'::DATE
        UNION ALL SELECT COALESCE(d2.interest_rate,0)*100,COALESCE(d2.principal,0)
        FROM fsi.balance_deposit d2 JOIN fsi.para_portfolio p ON p.port_id=d2.port_id
        WHERE p.port_name='{fund_name}' AND d2.evaluate_date='{d}'::DATE)t""", conn)
    conn.close()
    base=info[0] if info else {}
    return dict(port_name=fund_name,ccy=base.get('ccy','HKD'),
                nav_millions=base.get('nav_millions',0),
                wam=base.get('wam',0),wal=base.get('wal',0),
                nav_cls=nav_cls,perf=perf,annual=annual,
                alloc=alloc,mat=mat,
                ytm=float(ytm_r[0]['v']) if ytm_r and ytm_r[0]['v'] else 0,
                eval_date=ev)

# ══════════════════════════════════════════════════════════
# 圖表生成
# ══════════════════════════════════════════════════════════
PIE_COLORS=['#2E75B6','#70AD47','#ED7D31','#FFC000','#5B9BD5','#7030A0','#FF0000','#00B0F0']

def _make_pie(labels, values, w_pt, h_pt, dpi=150):
    if not HAVE_MPL or not values: return None
    fig,ax=plt.subplots(figsize=(w_pt/72,h_pt/72),dpi=dpi)
    wedges,_,autotexts=ax.pie(values,labels=None,colors=PIE_COLORS[:len(values)],
        autopct=lambda p:f'{p:.1f}%' if p>=3 else '',startangle=90,pctdistance=0.72,
        wedgeprops={'linewidth':0.4,'edgecolor':'white'})
    for at in autotexts: at.set_fontsize(6.5)
    ax.legend(wedges,[f'{l}  {v:.1f}%' for l,v in zip(labels,values)],
        loc='lower center',bbox_to_anchor=(0.5,-0.35),ncol=2,
        fontsize=6,frameon=False,handlelength=0.8)
    ax.set_aspect('equal')
    plt.tight_layout(pad=0.1)
    buf=io.BytesIO(); plt.savefig(buf,format='png',bbox_inches='tight',dpi=dpi); plt.close(); buf.seek(0)
    return buf.read()

def _make_bar(labels, values, w_pt, h_pt, dpi=150):
    if not HAVE_MPL or not values: return None
    fig,ax=plt.subplots(figsize=(w_pt/72,h_pt/72),dpi=dpi)
    ax.bar(range(len(labels)),values,color='#2E75B6',width=0.6,edgecolor='white')
    for i,v in enumerate(values):
        if v>0.5: ax.text(i,v+0.3,f'{v:.1f}%',ha='center',va='bottom',fontsize=6.5)
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels,fontsize=7,rotation=30,ha='right')
    ax.set_ylabel('%',fontsize=7); ax.yaxis.set_tick_params(labelsize=7)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.set_ylim(0,max(values)*1.25 if values else 100)
    plt.tight_layout(pad=0.3)
    buf=io.BytesIO(); plt.savefig(buf,format='png',bbox_inches='tight',dpi=dpi); plt.close(); buf.seek(0)
    return buf.read()

# ══════════════════════════════════════════════════════════
# 可變字段替換表
# ══════════════════════════════════════════════════════════
def build_replacements(data, ev):
    """根據基金數據構建 (y_round, x_round) → new_text 替換表"""
    fn = data['port_name']
    ccy = data['ccy']
    p = data['perf']
    nav_m = data['nav_millions']
    nav_cls = data['nav_cls']
    annual = data['annual']
    wam = data['wam']
    ytm = data['ytm']

    def fmt(v, dec=2): return f'{float(v):.{dec}f}' if v is not None else '—'
    def fmtp(v): return f'{float(v):.2f}' if v is not None else '—'

    R = {}
    def add(y, x, t): R[(round(y), round(x))] = t

    # ── Page 1 可變字段 ────────────────────────────────
    # 基金名稱
    add(18.9, 15.3, fn)
    # 日期（年/月/日）
    add(41.3, 79.8,  str(ev.year))
    add(41.3, 112.3, f'{ev.month:02d}')
    add(41.3, 130.5, f'{ev.day:02d}')
    # 投資經理/受託人/託管人（暫用原值）
    add(309.1, 217.9, '博匯投資管理有限公司')
    add(316.4, 205.7, '博匯保誠信託有限公司')
    add(324.4, 226.1, '中國銀行')
    add(324.4, 252.7, '（香港）')
    add(324.4, 267.1, '有限公司')
    # 基礎貨幣（右欄值）
    add(331.8, 279.3, ccy)
    # 基金規模（幣種+金額）
    add(339.8, 236.3, ccy)
    add(340.7, 248.6, f'{nav_m:,.2f}')
    add(339.8, 279.3, '百萬')
    # 非基礎貨幣股份類別
    add(347.1, 279.3, '—')

    # NAV 類別表（最多4行，多餘行用"—"）
    cls_rows = [
        (399.6, 398.7, 113.8, 159.2, 171.5, 204.7, 248.9),
        (408.8, 407.9, 114.2, 159.2, 171.5, 200.6, 248.9),
        (418.1, 417.1, 113.8, 159.2, 171.5, 200.6, 248.9),
        (427.2, 426.3, 113.8, 159.2, 171.5, 199.9, 248.9),
    ]
    for i, (yn, yt2, xdt, xccy, xnav, xbb, xisin) in enumerate(cls_rows):
        if i < len(nav_cls):
            c2 = nav_cls[i]
            add(yn,  15.3,  c2['cls'])
            add(yt2, 17.1,  '類基金單位')
            add(yn,  xdt,   str(c2['dt']))
            add(yt2, xccy,  ccy)
            add(yn,  xnav,  fmt(c2['nav_pu'], 4))
            add(yn,  xbb,   '—')
            add(yn,  xisin, '—')
        else:
            add(yn,  15.3,  '—')
            add(yt2, 17.1,  '')
            add(yn,  xdt,   ''); add(yt2, xccy, ''); add(yn, xnav, ''); add(yn, xbb, ''); add(yn, xisin, '')

    # 費用表（類別名稱對應 NAV 類別）
    fee_rows = [(466.5,465.6),(475.8,474.8),(485.0,484.0),(494.2,493.2)]
    fee_suffixes = ['類基金單位']*4
    for i, (yn, yt2) in enumerate(fee_rows):
        if i < len(nav_cls):
            add(yn,  15.3, nav_cls[i]['cls'])
            add(yt2, 17.1, fee_suffixes[i])
        else:
            add(yn, 15.3, '—'); add(yt2, 17.1, '')

    # 數據來源日期
    add(438.3, 72.3,  str(ev.year))
    add(438.3, 93.8,  f'{ev.month:02d}')
    add(438.3, 106.8, f'{ev.day:02d}')

    # 累積業績表（4行，只填第1行，其餘用—）
    perf_rows = [
        (456.7, 455.8, 385.9, 410.7, 435.6, 460.5, 493.0, 532.3, 568.2),
        (465.9, 465.0, 385.9, 410.7, 435.6, 460.5, 493.0, 532.3, 568.2),
        (475.1, 474.2, 385.9, 410.7, 435.6, 460.5, 493.4, 532.3, 568.2),
        (484.4, 483.4, 385.9, 410.7, 435.6, 460.5, 493.0, 532.3, 568.2),
    ]
    perf_vals = [[fmtp(p.get('1m')),fmtp(p.get('3m')),fmtp(p.get('6m')),
                  fmtp(p.get('1y')),fmtp(p.get('since')),fmtp(p.get('ann')),fmtp(p.get('ret7d'))]]
    perf_vals += [['—','—','—','—','—','—','—']]*3
    for i,(yn,yt2,x1m,x3m,x6m,x1y,xsi,xann,x7d) in enumerate(perf_rows):
        cls_lbl = nav_cls[i]['cls'] if i<len(nav_cls) else '—'
        add(yn,  303.9, cls_lbl)
        add(yt2, 305.6, '類基金單位' if i<len(nav_cls) else '')
        vs = perf_vals[i]
        add(yn, x1m, vs[0]); add(yn, x3m, vs[1]); add(yn, x6m, vs[2])
        add(yn, x1y, vs[3]); add(yn, xsi, vs[4]); add(yn, xann, vs[5]); add(yn, x7d, vs[6])

    # 年度業績表
    ann_rows = [
        (537.8,536.8),(547.0,546.0),(556.2,555.2),(565.4,564.5)
    ]
    # 年份列 x 坐標（2021-2025+本年至今）
    ann_xs = [430.1, 457.7, 485.3, 513.0, 540.6, 568.2]
    # 只在第1行填真實數據
    ann_vals_row0 = [a['pct'] for a in annual]
    # 確保最多6個值（對應6列）
    while len(ann_vals_row0) < 6: ann_vals_row0.append(None)
    for i,(yn,yt2) in enumerate(ann_rows):
        cls_lbl = nav_cls[i]['cls'] if i<len(nav_cls) else '—'
        add(yn,  303.9, cls_lbl)
        add(yt2, 305.6, '類基金單位' if i<len(nav_cls) else '')
        vs = ann_vals_row0 if i==0 else [None]*6
        for j,x in enumerate(ann_xs):
            v = vs[j] if j<len(vs) else None
            add(yn, x, fmtp(v))

    # ── Page 2 可變字段 ────────────────────────────────
    add(94.8,  268.4, fmt(wam, 2))   # WAM 天數
    add(104.9, 274.2, f'{ytm:.2f}%') # YTM

    # 腳注 4 日期（7日前）
    d7 = ev - timedelta(days=7)
    add(796.8, 156.2, str(ev.year)); add(796.8, 176.0, f'{ev.month:02d}'); add(796.8, 189.0, f'{d7.day:02d}')
    add(796.8, 208.2, str(ev.year)); add(796.8, 228.1, f'{ev.month:02d}'); add(796.8, 241.1, f'{ev.day:02d}')

    return R

# ══════════════════════════════════════════════════════════
# PDF 渲染核心
# ══════════════════════════════════════════════════════════
def _draw_page(c, page_data, repl, charts=None):
    """渲染一頁：先畫填充矩形，再畫文字，最後嵌入圖表"""
    RED   = Color(191/255, 0, 8/255)
    BLACK = Color(0,0,0)

    # 1. 填充矩形（colored）
    for r in page_data['rects']:
        f = r['fill']
        if f is None: continue
        rx0,ry0,rx1,ry1 = r['rect']
        rw = rx1-rx0; rh = ry1-ry0
        if rw<=0 or rh<=0: continue
        c.setFillColor(Color(f[0],f[1],f[2]))
        c.setStrokeColor(Color(f[0],f[1],f[2]))
        c.rect(rx0, H-ry1, rw, rh, fill=1, stroke=0)

    # 2. 黑色矩形（header bar 右側、分隔線等）
    c.setFillColor(BLACK); c.setStrokeColor(BLACK)
    # 頁首橫條右側（黑色）
    c.rect(192.16, H-69.37, 580.15-192.16, 9.21, fill=1, stroke=0)
    # 垂直分隔線（左右欄之間）
    c.setLineWidth(0.5)
    c.line(297.75, H-221.62, 297.75, H-600)
    # 水平分隔線
    for hy in [300.21, 388.0, 436.5, 236.36, 735.09]:
        c.setLineWidth(0.5)
        c.line(15.35, H-hy, 580.15, H-hy)
    c.setLineWidth(0.5)
    c.line(303.89, H-435.88, 580.15, H-435.88)
    c.line(303.89, H-516.92, 580.15, H-516.92)
    c.line(303.89, H-236.36, 580.15, H-236.36)

    # 3. 文字
    for span in page_data['texts']:
        y0, x0 = span['y'], span['x']
        key = (round(y0), round(x0))
        text = repl.get(key, span['text'])
        if not text or not text.strip(): continue

        font_name = _map_font(span['font'])
        clr = _map_color(span['color'])
        size = span['size']
        # 渲染位置：使用 bbox 底部作為 RL baseline
        y_rl = H - span['y1'] + 0.5
        c.setFont(font_name, size)
        c.setFillColor(clr)
        c.drawString(x0, y_rl, text)

    # 4. 圖表圖片
    if charts:
        for (bx0,by0,bx1,by1), img_bytes in charts:
            if img_bytes:
                bw = bx1-bx0; bh = by1-by0
                c.drawImage(ImageReader(io.BytesIO(img_bytes)), bx0, H-by1, bw, bh)


def build_pdf(data, out_path, layout):
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    ev = data['eval_date']
    repl = build_replacements(data, ev)

    # 頁 1
    _draw_page(c, layout['p1'], repl)
    c.showPage()

    # 頁 2：生成圖表
    charts = []
    # 餅圖：bbox=(303.9, 111.7, 580.2, 190.3)
    pie_bytes = _make_pie([a['lbl'] for a in data['alloc']],
                          [a['pct'] for a in data['alloc']],
                          276.3, 78.6) if data['alloc'] else None
    charts.append(((303.89, 111.73, 580.15, 190.31), pie_bytes))

    # 柱狀圖：bbox=(303.9, 210.0, 580.2, 310.6)
    bar_bytes = _make_bar([m['lbl'] for m in data['mat']],
                          [m['pct'] for m in data['mat']],
                          276.3, 100.7) if data['mat'] else None
    charts.append(((303.89, 209.96, 580.15, 310.64), bar_bytes))

    _draw_page(c, layout['p2'], repl, charts=charts)
    c.save()
    print(f'  ✅ {out_path.name}')


# ══════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=date.today().isoformat())
    ap.add_argument('--fund', default=None)
    args = ap.parse_args()
    ev = date.fromisoformat(args.date)

    if not HAVE_DB: print('需要 psycopg2 + .env'); return
    if not LAYOUT_FILE.exists():
        print(f'找不到 {LAYOUT_FILE}，請先執行分析腳本'); return

    layout = json.load(open(LAYOUT_FILE, encoding='utf-8'))

    conn = _conn()
    funds = [r['port_name'] for r in _q(
        "SELECT p.port_name FROM fsi.para_portfolio p "
        "WHERE p.is_mmf=TRUE AND p.is_active=TRUE ORDER BY p.port_name", conn)]
    conn.close()
    if args.fund: funds = [f for f in funds if args.fund in f]

    print(f'\n[MMF Factsheet Clone] 日期：{ev}')
    for fn in funds:
        print(f'  {fn} ...', end='', flush=True)
        try:
            data = load_fund_data(fn, ev)
            safe = fn.replace('/', '-').replace(' ', '_')
            out  = OUTPUT_DIR / f'MMF_Factsheet_{ev.strftime("%Y%m%d")}_{safe}.pdf'
            build_pdf(data, out, layout)
        except Exception as e:
            print(f'\n  ✗ {e}')
            import traceback; traceback.print_exc()

if __name__ == '__main__':
    main()
