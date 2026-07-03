"""
create_factsheet.py — 生成 MMF 月報 Factsheet PDF
執行：python 2_processing/sql/mmf/report_04_mmf_monthly/create_factsheet.py --date 2026-06-25

仿 ChinaAMC Select MMF Factsheet 雙頁格式：
  第1頁：基金資料、股份類別NAV、費用、累積業績、年度業績
  第2頁：投資組合特點（WAM/YTM）、資產配置圓餅圖、到期分佈柱狀圖、免責聲明

依賴：reportlab、matplotlib、psycopg2、python-dotenv
"""

import sys, os, argparse, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

from datetime import date, timedelta
from pathlib import Path
import re

# ── 依賴檢查 ──────────────────────────────────────────────
try:
    import psycopg2
    import psycopg2.extras
    from dotenv import load_dotenv
    load_dotenv()
    HAVE_DB = True
except ImportError:
    HAVE_DB = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Table, TableStyle, HRFlowable, PageBreak,
                                     KeepTogether, Flowable)
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAVE_RL = True
except ImportError:
    HAVE_RL = False
    print('請安裝 reportlab: pip install reportlab')
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

import io

# ── 路徑設定 ──────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR.parent.parent.parent / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 品牌顏色（仿 ChinaAMC 藍色系）────────────────────────
C_DEEP_BLUE  = HexColor('#1F3864')   # 深藍
C_MID_BLUE   = HexColor('#2E75B6')   # 中藍
C_LIGHT_BLUE = HexColor('#BDD7EE')   # 淺藍
C_GOLD       = HexColor('#C9A227')   # 金色（評級）
C_GREY_BG    = HexColor('#F2F7FF')   # 淺藍背景
C_GREY_TEXT  = HexColor('#595959')   # 灰色文字
C_RED_WARN   = HexColor('#C00000')   # 警示紅

# ── 字型設定 ──────────────────────────────────────────────
# 嘗試載入系統中文字型
def _register_fonts():
    """注冊 CJK 字型並返回字型名稱對（regular, bold）"""
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping

    candidates = [
        # (regular_path, bold_path, name)
        ('C:/Windows/Fonts/msyh.ttc',  'C:/Windows/Fonts/msyhbd.ttc',  'CJKFont'),
        ('C:/Windows/Fonts/simhei.ttf', 'C:/Windows/Fonts/simhei.ttf', 'CJKFont'),
        ('C:/Windows/Fonts/simsun.ttc', 'C:/Windows/Fonts/simsun.ttc', 'CJKFont'),
    ]
    for reg_path, bold_path, name in candidates:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont(name, reg_path))
                bold_name = name + 'B'
                if os.path.exists(bold_path) and bold_path != reg_path:
                    pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                else:
                    bold_name = name   # 無單獨粗體字型，用同一字型
                addMapping(name, 0, 0, name)
                addMapping(name, 1, 0, bold_name)
                return name, bold_name
            except Exception:
                pass
    return None, None   # 回退到 Helvetica

_CJK_REG, _CJK_BOLD = _register_fonts()
CJK_FONT      = _CJK_REG  or 'Helvetica'
CJK_FONT_BOLD = _CJK_BOLD or 'Helvetica-Bold'

def _font(name=None, size=9, bold=False, color=black):
    fn = (CJK_FONT_BOLD if bold else CJK_FONT) if name is None else name
    return ParagraphStyle(
        'fs_' + str(size) + ('b' if bold else ''),
        fontName=fn,
        fontSize=size,
        textColor=color,
        leading=size * 1.35,
        wordWrap='CJK',
    )

STYLE_TITLE   = _font(size=18, bold=True, color=white)
STYLE_SUBTITLE= _font(size=10, color=white)
STYLE_H2      = _font(size=11, bold=True, color=C_DEEP_BLUE)
STYLE_BODY    = _font(size=9,  color=black)
STYLE_SMALL   = _font(size=7.5, color=C_GREY_TEXT)
STYLE_NOTE    = _font(size=7,  color=C_GREY_TEXT)
STYLE_NUM     = _font(size=9,  color=black)

# ══════════════════════════════════════════════════════════
# 資料查詢
# ══════════════════════════════════════════════════════════
def get_db_conn():
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        dbname=os.getenv('POSTGRES_DB', 'fsi_risk'),
        user=os.getenv('POSTGRES_USER', 'fsi_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'change_me'),
    )

def query(sql, conn, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]

def load_data(eval_date: date):
    """從資料庫讀取所有 Factsheet 需要的數據"""
    if not HAVE_DB:
        return _mock_data(eval_date)
    try:
        conn = get_db_conn()
        d = eval_date.isoformat()
        data = {}

        # 基金基本資料
        data['fund_info'] = query(f"""
            SELECT p.port_name, p.base_currency,
                   ROUND(n.net_asset/1e8, 4) AS nav_100m,
                   COALESCE(m.wam_days, 0) AS wam_days,
                   COALESCE(m.wal_days, 0) AS wal_days,
                   COALESCE(m.return_rate_7d, 0) AS return_7d
            FROM fsi.para_portfolio p
            JOIN fsi.balance_portfolio_nav n ON n.port_id=p.port_id
                AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
            LEFT JOIN fsi.balance_portfolio_mmf m ON m.port_id=p.port_id
                AND m.evaluate_date='{d}'::DATE
            WHERE p.is_mmf=TRUE AND p.is_active=TRUE
            ORDER BY p.port_name
        """, conn)

        # 各類別 NAV
        data['nav_class'] = query(f"""
            SELECT p.port_name,
                   COALESCE(n.class_id::TEXT,'整體') AS class_id,
                   ROUND(COALESCE(n.unit_nav,0),4) AS nav_per_unit,
                   n.evaluate_date
            FROM fsi.para_portfolio p
            JOIN fsi.balance_portfolio_nav n ON n.port_id=p.port_id
                AND n.evaluate_date='{d}'::DATE
            WHERE p.is_mmf=TRUE AND p.is_active=TRUE
            ORDER BY p.port_name, n.class_id NULLS LAST
        """, conn)

        # 累積表現
        def nav_at(delta_days, min_days=None, max_days=None):
            min_d = delta_days - (min_days or 5)
            max_d = delta_days + (max_days or 5)
            return f"""(
                SELECT DISTINCT ON (n.port_id, n.class_id)
                       n.port_id, n.class_id, n.unit_nav
                FROM fsi.balance_portfolio_nav n
                WHERE n.evaluate_date BETWEEN '{d}'::DATE - {max_d}
                                          AND '{d}'::DATE - {min_d}
                ORDER BY n.port_id, n.class_id, n.evaluate_date DESC
            )"""
        data['performance'] = query(f"""
            WITH t AS (
                SELECT n.port_id, n.class_id, n.unit_nav
                FROM fsi.balance_portfolio_nav n WHERE n.evaluate_date='{d}'::DATE
            ),
            m1  AS {nav_at(30, 25, 40)},
            m3  AS {nav_at(91, 85, 100)},
            m6  AS {nav_at(182, 175, 195)},
            y1  AS {nav_at(365, 355, 380)},
            ytd AS (
                SELECT DISTINCT ON (n.port_id, n.class_id)
                       n.port_id, n.class_id, n.unit_nav
                FROM fsi.balance_portfolio_nav n
                WHERE n.evaluate_date >= DATE_TRUNC('year','{d}'::DATE)::DATE
                  AND n.evaluate_date <= DATE_TRUNC('year','{d}'::DATE)::DATE + 5
                ORDER BY n.port_id, n.class_id, n.evaluate_date ASC
            ),
            inc AS (
                SELECT DISTINCT ON (n.port_id, n.class_id)
                       n.port_id, n.class_id, n.unit_nav, n.evaluate_date AS inc_date
                FROM fsi.balance_portfolio_nav n
                JOIN fsi.para_portfolio p ON p.port_id=n.port_id WHERE p.is_mmf=TRUE
                ORDER BY n.port_id, n.class_id, n.evaluate_date ASC
            ),
            mmf AS (SELECT m.port_id, m.return_rate_7d
                    FROM fsi.balance_portfolio_mmf m WHERE m.evaluate_date='{d}'::DATE)
            SELECT p.port_name,
                   COALESCE(t.class_id::TEXT,'整體') AS class_id,
                   ROUND((t.unit_nav/NULLIF(m1.unit_nav,0)-1)*100,2) AS p1m,
                   ROUND((t.unit_nav/NULLIF(m3.unit_nav,0)-1)*100,2) AS p3m,
                   ROUND((t.unit_nav/NULLIF(m6.unit_nav,0)-1)*100,2) AS p6m,
                   ROUND((t.unit_nav/NULLIF(y1.unit_nav,0)-1)*100,2) AS p1y,
                   ROUND((t.unit_nav/NULLIF(i.unit_nav,0)-1)*100,2)  AS p_incept,
                   CASE WHEN i.unit_nav>0 AND ('{d}'::DATE-i.inc_date)>0
                        THEN ROUND((POWER(t.unit_nav::NUMERIC/NULLIF(i.unit_nav,0),
                             365.0/NULLIF(('{d}'::DATE-i.inc_date),0))-1)*100,2) END AS p_ann,
                   COALESCE(mf.return_rate_7d,0) AS ret7d,
                   i.inc_date,
                   ROUND((t.unit_nav/NULLIF(ytd.unit_nav,0)-1)*100,2) AS p_ytd
            FROM t
            JOIN fsi.para_portfolio p ON p.port_id=t.port_id
            LEFT JOIN m1  ON m1.port_id=t.port_id  AND m1.class_id  IS NOT DISTINCT FROM t.class_id
            LEFT JOIN m3  ON m3.port_id=t.port_id  AND m3.class_id  IS NOT DISTINCT FROM t.class_id
            LEFT JOIN m6  ON m6.port_id=t.port_id  AND m6.class_id  IS NOT DISTINCT FROM t.class_id
            LEFT JOIN y1  ON y1.port_id=t.port_id  AND y1.class_id  IS NOT DISTINCT FROM t.class_id
            LEFT JOIN ytd ON ytd.port_id=t.port_id AND ytd.class_id IS NOT DISTINCT FROM t.class_id
            LEFT JOIN inc i ON i.port_id=t.port_id AND i.class_id   IS NOT DISTINCT FROM t.class_id
            LEFT JOIN mmf mf ON mf.port_id=t.port_id
            WHERE p.is_mmf=TRUE AND p.is_active=TRUE
            ORDER BY p.port_name, t.class_id NULLS LAST
        """, conn)

        # 資產配置（標籤在 Python 端映射，避免 enum 類型比較編碼問題）
        _LABEL_MAP = {'CASH':'現金及等價物','DEPOSIT':'定期存款','CD':'同業存單',
                      'BOND_GOVT':'政府/公共債券','BOND_CORP':'企業債券','REPO':'逆回購'}
        raw_alloc = query(f"""
            SELECT p.port_name, a.asset_class::TEXT AS asset_class,
                   ROUND(SUM(a.market_value)/n.net_asset*100,2) AS pct
            FROM fsi.balance_portfolio_asset a
            JOIN fsi.para_portfolio p ON p.port_id=a.port_id
            JOIN fsi.balance_portfolio_nav n ON n.port_id=a.port_id
                AND n.evaluate_date=a.evaluate_date AND n.class_id IS NULL
            WHERE p.is_mmf=TRUE AND p.is_active=TRUE
              AND a.evaluate_date='{d}'::DATE AND n.net_asset>0
            GROUP BY p.port_name, a.asset_class, n.net_asset
            ORDER BY p.port_name, pct DESC
        """, conn)
        data['asset_alloc'] = [
            {**r, 'label': _LABEL_MAP.get(r['asset_class'], r['asset_class'])}
            for r in raw_alloc
        ]

        # 到期分佈
        data['maturity'] = query(f"""
            WITH h AS (
                SELECT b.port_id,
                       GREATEST(COALESCE(b.remaining_days,(b.maturity_date-'{d}'::DATE)::INT),0) AS d,
                       COALESCE(b.market_value,0) AS mv FROM fsi.balance_bond b
                WHERE b.evaluate_date='{d}'::DATE AND b.quantity>0
                UNION ALL
                SELECT c.port_id,
                       GREATEST(COALESCE(c.remaining_days,(c.maturity_date-'{d}'::DATE)::INT),0),
                       COALESCE(c.market_value,0) FROM fsi.balance_cd c WHERE c.evaluate_date='{d}'::DATE
                UNION ALL
                SELECT d2.port_id,
                       GREATEST((d2.maturity_date-'{d}'::DATE)::INT,0),
                       COALESCE(d2.principal,0) FROM fsi.balance_deposit d2
                WHERE d2.evaluate_date='{d}'::DATE
                UNION ALL
                SELECT r.port_id,
                       GREATEST((COALESCE(r.actual_maturity_date,r.maturity_date)-'{d}'::DATE)::INT,0),
                       COALESCE(r.principal,0) FROM fsi.balance_repo r
                WHERE r.evaluate_date='{d}'::DATE AND r.repo_type='REV_REPO'
            )
            SELECT p.port_name,
                   CASE WHEN d<=1 THEN '1日以內' WHEN d<=7 THEN '2-7日'
                        WHEN d<=30 THEN '8-30日' WHEN d<=60 THEN '31-60日'
                        WHEN d<=90 THEN '61-90日' WHEN d<=180 THEN '91-180日'
                        WHEN d<=365 THEN '181-365日' ELSE '365日以上' END AS bucket,
                   CASE WHEN d<=1 THEN 1 WHEN d<=7 THEN 2 WHEN d<=30 THEN 3
                        WHEN d<=60 THEN 4 WHEN d<=90 THEN 5 WHEN d<=180 THEN 6
                        WHEN d<=365 THEN 7 ELSE 8 END AS ord,
                   ROUND(SUM(mv)/n.net_asset*100,2) AS pct
            FROM h
            JOIN fsi.para_portfolio p ON p.port_id=h.port_id
            JOIN fsi.balance_portfolio_nav n ON n.port_id=h.port_id
                AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
            WHERE p.is_mmf=TRUE AND p.is_active=TRUE AND n.net_asset>0
            GROUP BY p.port_name, bucket, ord, n.net_asset
            ORDER BY p.port_name, ord
        """, conn)

        # YTM（加权平均到期收益率）
        data['ytm'] = query(f"""
            WITH h AS (
                SELECT b.port_id, COALESCE(b.ytm,0)*COALESCE(b.market_value,0) AS wv,
                       COALESCE(b.market_value,0) AS mv FROM fsi.balance_bond b
                WHERE b.evaluate_date='{d}'::DATE AND b.quantity>0
                UNION ALL
                SELECT c.port_id, COALESCE(c.ytm,0)*COALESCE(c.market_value,0),
                       COALESCE(c.market_value,0) FROM fsi.balance_cd c
                WHERE c.evaluate_date='{d}'::DATE
                UNION ALL
                SELECT d2.port_id,
                       COALESCE(d2.interest_rate,0)*100*COALESCE(d2.principal,0),
                       COALESCE(d2.principal,0)
                FROM fsi.balance_deposit d2 WHERE d2.evaluate_date='{d}'::DATE
            )
            SELECT p.port_name,
                   ROUND(SUM(wv)/NULLIF(SUM(mv),0),4) AS ytm_pct
            FROM h JOIN fsi.para_portfolio p ON p.port_id=h.port_id
            WHERE p.is_mmf=TRUE AND p.is_active=TRUE
            GROUP BY p.port_name ORDER BY p.port_name
        """, conn)

        conn.close()
        return data
    except Exception as e:
        print(f'  ⚠ 資料庫連接失敗，使用示例數據：{e}')
        return _mock_data(eval_date)


def _mock_data(eval_date):
    """示例數據（無資料庫時使用）"""
    funds = ['博匯港元貨幣市場基金I', '博匯港元貨幣市場基金II']
    d = eval_date.strftime('%Y-%m-%d')
    return {
        'fund_info': [
            {'port_name': f, 'base_currency': 'HKD',
             'nav_100m': 1.0 + i*0.5, 'wam_days': 45, 'wal_days': 80, 'return_7d': 2.5}
            for i, f in enumerate(funds)
        ],
        'nav_class': [
            {'port_name': funds[0], 'class_id': '整體', 'nav_per_unit': 10.1234, 'evaluate_date': eval_date},
            {'port_name': funds[1], 'class_id': '整體', 'nav_per_unit': 10.0567, 'evaluate_date': eval_date},
        ],
        'performance': [
            {'port_name': f, 'class_id': '整體',
             'p1m': 0.19, 'p3m': 0.60, 'p6m': 1.30, 'p1y': 2.42,
             'p_incept': 12.0, 'p_ann': 2.1, 'ret7d': 2.5,
             'inc_date': date(2020,1,1), 'p_ytd': 1.0}
            for f in funds
        ],
        'asset_alloc': [
            {'port_name': funds[0], 'asset_class': 'DEPOSIT', 'label': '定期存款', 'pct': 30.0},
            {'port_name': funds[0], 'asset_class': 'REV_REPO', 'label': '逆回購', 'pct': 35.0},
            {'port_name': funds[0], 'asset_class': 'CD', 'label': '同業存單', 'pct': 20.0},
            {'port_name': funds[0], 'asset_class': 'BOND_GOVT', 'label': '政府/公共債券', 'pct': 10.0},
            {'port_name': funds[0], 'asset_class': 'CASH', 'label': '現金及等價物', 'pct': 5.0},
        ],
        'maturity': [
            {'port_name': funds[0], 'bucket': '1日以內', 'ord': 1, 'pct': 38.0},
            {'port_name': funds[0], 'bucket': '2-7日',   'ord': 2, 'pct': 20.0},
            {'port_name': funds[0], 'bucket': '8-30日',  'ord': 3, 'pct': 22.0},
            {'port_name': funds[0], 'bucket': '31-60日', 'ord': 4, 'pct': 12.0},
            {'port_name': funds[0], 'bucket': '61-90日', 'ord': 5, 'pct':  8.0},
        ],
        'ytm': [{'port_name': f, 'ytm_pct': 2.45} for f in funds],
    }


# ══════════════════════════════════════════════════════════
# 圖表生成
# ══════════════════════════════════════════════════════════
CHART_COLORS = ['#2E75B6','#70AD47','#ED7D31','#FFC000','#FF0000','#7030A0','#00B0F0','#92D050']

def _pie_chart(labels, values, title=''):
    """資產配置圓餅圖 → PNG bytes"""
    if not HAVE_MPL or not values:
        return None
    fig, ax = plt.subplots(figsize=(3.5, 3.0), dpi=120)
    colors = CHART_COLORS[:len(values)]
    wedges, texts, autotexts = ax.pie(
        values, labels=None, colors=colors,
        autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
        startangle=90, pctdistance=0.75,
        wedgeprops={'linewidth': 0.5, 'edgecolor': 'white'}
    )
    for at in autotexts:
        at.set_fontsize(7)
    # 圖例
    legend_labels = [f'{l} {v:.1f}%' for l, v in zip(labels, values)]
    ax.legend(wedges, legend_labels, loc='center left',
              bbox_to_anchor=(1.0, 0.5), fontsize=7, frameon=False)
    if title:
        ax.set_title(title, fontsize=9, pad=6)
    ax.set_aspect('equal')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=120)
    plt.close()
    buf.seek(0)
    return buf.read()


def _bar_chart(labels, values, title=''):
    """到期分佈柱狀圖 → PNG bytes"""
    if not HAVE_MPL or not values:
        return None
    fig, ax = plt.subplots(figsize=(4.5, 2.8), dpi=120)
    x = range(len(labels))
    bars = ax.bar(x, values, color='#2E75B6', width=0.6, edgecolor='white')
    # 數值標籤
    for bar, v in zip(bars, values):
        if v > 0.5:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                    f'{v:.1f}%', ha='center', va='bottom', fontsize=7)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=7, rotation=30, ha='right')
    ax.set_ylabel('%', fontsize=8)
    ax.yaxis.set_tick_params(labelsize=7)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    if title:
        ax.set_title(title, fontsize=9)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=120)
    plt.close()
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════
# PDF 元件
# ══════════════════════════════════════════════════════════
W, H = A4
M_LEFT = 15*mm
M_RIGHT = 15*mm
CONTENT_W = W - M_LEFT - M_RIGHT

def _header_block(fund_name, eval_date_str):
    """頁首：深藍底基金名稱 + 評級 + 日期"""
    from reportlab.platypus import Image as RLImage
    from reportlab.lib.utils import ImageReader

    data = [[
        Paragraph(f'<font size="16"><b>{fund_name}</b></font><br/>'
                  f'<font size="10">基金月報  {eval_date_str}</font>', _font(size=10, color=white)),
        Paragraph('<font size="10"><b>「新資本投資者入境計劃」合資格基金</b></font><br/>'
                  '<font size="9" color="#C9A227">★ AAAmf 評級</font>', _font(size=9, color=white)),
    ]]
    t = Table(data, colWidths=[CONTENT_W*0.65, CONTENT_W*0.35])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_DEEP_BLUE),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (0,-1), 10),
        ('RIGHTPADDING', (-1,0), (-1,-1), 10),
    ]))
    return t


def _section_title(text):
    """藍色底節標題"""
    t = Table([[Paragraph(f'<b>{text}</b>', _font(size=10, bold=True, color=white))]],
              colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_MID_BLUE),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    return t


def _fund_info_table(fund_info_row, eval_date):
    """基金資料表格（左右兩欄）"""
    nav = fund_info_row
    rows = [
        ('法律結構', '香港傘子式單位信託基金', '交易頻率', '每日'),
        ('基礎貨幣', nav.get('base_currency','HKD'),
         '基金規模', f"HKD {nav.get('nav_100m',0):.2f} 億元"),
        ('加權平均期限(WAM)', f"{nav.get('wam_days',0):.0f} 天（≤60天）",
         '7日年化收益率', f"{nav.get('return_7d',0):.2f}%"),
        ('加權平均存續期(WAL)', f"{nav.get('wal_days',0):.0f} 天（≤120天）",
         '數據日期', eval_date.strftime('%Y年%m月%d日')),
    ]
    tdata = []
    for r in rows:
        tdata.append([
            Paragraph(r[0], _font(size=8, color=C_GREY_TEXT)),
            Paragraph(str(r[1]), _font(size=8)),
            Paragraph(r[2], _font(size=8, color=C_GREY_TEXT)),
            Paragraph(str(r[3]), _font(size=8)),
        ])
    t = Table(tdata, colWidths=[CONTENT_W*0.22, CONTENT_W*0.28, CONTENT_W*0.22, CONTENT_W*0.28])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_GREY_BG),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [white, C_GREY_BG]),
        ('GRID', (0,0), (-1,-1), 0.3, C_LIGHT_BLUE),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    return t


def _nav_table(nav_rows):
    """各類別NAV表格"""
    hdr = ['類別', '每股資產淨值', '數據日期']
    tdata = [[Paragraph(h, _font(size=8, bold=True, color=white)) for h in hdr]]
    for r in nav_rows:
        nav_val = r.get('nav_per_unit', 0)
        d = r.get('evaluate_date')
        d_str = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
        tdata.append([
            Paragraph(r.get('class_id','—'), _font(size=8)),
            Paragraph(f"HKD {nav_val:.4f}", _font(size=8)),
            Paragraph(d_str, _font(size=8)),
        ])
    t = Table(tdata, colWidths=[CONTENT_W*0.4, CONTENT_W*0.3, CONTENT_W*0.3])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_MID_BLUE),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [white, C_GREY_BG]),
        ('GRID', (0,0), (-1,-1), 0.3, C_LIGHT_BLUE),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    return t


def _perf_table(perf_rows):
    """累積業績表格（仿 Factsheet 格式）"""
    hdr = ['類別', '一個月', '三個月', '六個月', '一年', '自成立', '年化', '7日年化']
    tdata = [[Paragraph(h, _font(size=7.5, bold=True, color=white)) for h in hdr]]
    for r in perf_rows:
        def fmt(v):
            if v is None: return '—'
            return f"{float(v):.2f}%"
        tdata.append([
            Paragraph(r.get('class_id','整體'), _font(size=7.5)),
            Paragraph(fmt(r.get('p1m')),    _font(size=7.5)),
            Paragraph(fmt(r.get('p3m')),    _font(size=7.5)),
            Paragraph(fmt(r.get('p6m')),    _font(size=7.5)),
            Paragraph(fmt(r.get('p1y')),    _font(size=7.5)),
            Paragraph(fmt(r.get('p_incept')), _font(size=7.5)),
            Paragraph(fmt(r.get('p_ann')),  _font(size=7.5)),
            Paragraph(fmt(r.get('ret7d')),  _font(size=7.5)),
        ])
    cw = CONTENT_W / len(hdr)
    t = Table(tdata, colWidths=[cw*1.4]+[cw*0.94]*(len(hdr)-1))
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_MID_BLUE),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [white, C_GREY_BG]),
        ('GRID', (0,0), (-1,-1), 0.3, C_LIGHT_BLUE),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (0,-1), 6),
    ]))
    return t


def _portfolio_chars_table(fund_info_row, ytm_row):
    """投資組合特點（WAM + YTM）"""
    wam = fund_info_row.get('wam_days', 0)
    ytm = ytm_row.get('ytm_pct', 0) if ytm_row else 0
    data = [
        [Paragraph('加權平均到期日', _font(size=9, bold=True, color=C_DEEP_BLUE)),
         Paragraph(f'<b>{wam:.1f} 天</b>', _font(size=14, bold=True, color=C_MID_BLUE))],
        [Paragraph('加權平均到期收益率¹', _font(size=9, bold=True, color=C_DEEP_BLUE)),
         Paragraph(f'<b>{ytm:.2f}%</b>', _font(size=14, bold=True, color=C_MID_BLUE))],
    ]
    t = Table(data, colWidths=[CONTENT_W*0.5, CONTENT_W*0.5])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_GREY_BG),
        ('GRID', (0,0), (-1,-1), 0.3, C_LIGHT_BLUE),
        ('ALIGN', (1,0), (1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
    ]))
    return t


DISCLAIMER_TC = """
投資涉及風險。基金股價可升亦可跌，過往業績並不代表未來回報。投資者可能損失所投資之本金。
本資料僅供參考，不構成對任何證券或基金的買賣邀約或投資建議。閣下應細閱基金銷售文件，
了解基金詳情及風險因素。本資料之發行人為博匯基金管理有限公司，未獲香港證監會審閱。

¹ 使用基金中每個持倉的加權平均到期收益率計算。
數據來源：FSI Risk Platform 數據庫。截至報告日期，除非另有說明。
"""


# ══════════════════════════════════════════════════════════
# PDF 組裝
# ══════════════════════════════════════════════════════════
def build_pdf(data, eval_date, output_path):
    from reportlab.platypus import Image as RLImage

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=M_LEFT, rightMargin=M_RIGHT,
        topMargin=12*mm, bottomMargin=12*mm,
        title=f'MMF月報 {eval_date}',
        author='FSI Risk Platform',
    )

    story = []

    for fi in data.get('fund_info', [{}]):
        fund_name = fi.get('port_name', '博匯港元貨幣市場基金')
        eval_str  = f'截至 {eval_date.strftime("%Y年%m月%d日")}'

        # ── 頁首 ─────────────────────────────────────────
        story.append(_header_block(fund_name, eval_str))
        story.append(Spacer(1, 4*mm))

        # ── 第1頁：基金資料 + NAV + 業績 ──────────────────
        story.append(_section_title('基金資料'))
        story.append(Spacer(1, 1*mm))
        story.append(_fund_info_table(fi, eval_date))
        story.append(Spacer(1, 4*mm))

        # 各類別 NAV
        nav_rows = [r for r in data.get('nav_class',[]) if r['port_name']==fund_name]
        if nav_rows:
            story.append(_section_title('基金單位類別'))
            story.append(Spacer(1, 1*mm))
            story.append(_nav_table(nav_rows))
            story.append(Spacer(1, 4*mm))

        # 累積業績
        perf_rows = [r for r in data.get('performance',[]) if r['port_name']==fund_name]
        if perf_rows:
            story.append(_section_title('基金表現（累積）'))
            story.append(Spacer(1, 1*mm))
            story.append(_perf_table(perf_rows))
            story.append(Spacer(1, 2*mm))
            story.append(Paragraph(
                '過往業績並不代表未來回報。業績計算以資產淨值對資產淨值，已計入股息再投資。',
                _font(size=7, color=C_GREY_TEXT)
            ))
            story.append(Spacer(1, 4*mm))

        # ── 第2頁：組合特點 + 圖表 ────────────────────────
        story.append(PageBreak())
        story.append(_header_block(fund_name, eval_str))
        story.append(Spacer(1, 4*mm))

        # 組合特點
        story.append(_section_title('投資組合特點'))
        story.append(Spacer(1, 1*mm))
        ytm_row = next((r for r in data.get('ytm',[]) if r['port_name']==fund_name), {})
        story.append(_portfolio_chars_table(fi, ytm_row))
        story.append(Spacer(1, 4*mm))

        # 組合配置 + 到期分佈（並排）
        story.append(_section_title('組合配置'))
        story.append(Spacer(1, 1*mm))

        alloc = [r for r in data.get('asset_alloc',[]) if r['port_name']==fund_name]
        mat   = sorted([r for r in data.get('maturity',[])  if r['port_name']==fund_name],
                       key=lambda r: r['ord'])

        pie_img = bar_img = None
        if alloc:
            pie_bytes = _pie_chart(
                [r['label'] for r in alloc],
                [float(r['pct']) for r in alloc],
                '資產類別分佈 (%)'
            )
            if pie_bytes:
                pie_img = io.BytesIO(pie_bytes)

        if mat:
            bar_bytes = _bar_chart(
                [r['bucket'] for r in mat],
                [float(r['pct']) for r in mat],
                '到期日分佈 (%)'
            )
            if bar_bytes:
                bar_img = io.BytesIO(bar_bytes)

        # 圖表並排
        if pie_img or bar_img:
            chart_cells = []
            if pie_img:
                chart_cells.append(RLImage(pie_img, width=CONTENT_W*0.46, height=60*mm))
            else:
                chart_cells.append(Paragraph('(無資產配置數據)', STYLE_SMALL))
            if bar_img:
                chart_cells.append(RLImage(bar_img, width=CONTENT_W*0.50, height=60*mm))
            else:
                chart_cells.append(Paragraph('(無到期分佈數據)', STYLE_SMALL))

            chart_table = Table([chart_cells],
                                colWidths=[CONTENT_W*0.48, CONTENT_W*0.52])
            chart_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(chart_table)
            story.append(Spacer(1, 4*mm))

        # 免責聲明
        story.append(HRFlowable(width=CONTENT_W, thickness=0.5, color=C_LIGHT_BLUE))
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph('<b>重要聲明</b>', _font(size=8, bold=True, color=C_DEEP_BLUE)))
        for line in DISCLAIMER_TC.strip().splitlines():
            if line.strip():
                story.append(Paragraph(line.strip(), _font(size=7, color=C_GREY_TEXT)))
        story.append(Spacer(1, 4*mm))

        # 聯絡資料
        story.append(Paragraph(
            '服務熱線：(852) XXXX XXXX  |  網站：www.example.com.hk  |  '
            '電郵：fund_services@example.com',
            _font(size=7.5, color=C_MID_BLUE)
        ))

        # 多基金換頁（非最後一個）
        if fi != data['fund_info'][-1]:
            story.append(PageBreak())

    doc.build(story)
    print(f'  PDF 已生成：{output_path}')


# ══════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description='MMF月報 Factsheet PDF生成器')
    parser.add_argument('--date', default=date.today().isoformat(),
                        help='估值日期 YYYY-MM-DD（默認今天）')
    args = parser.parse_args()
    eval_date = date.fromisoformat(args.date)

    print(f'[MMF Factsheet] 估值日期：{eval_date}')
    print('  正在讀取數據庫...')
    data = load_data(eval_date)

    funds = [r['port_name'] for r in data.get('fund_info', [])]
    print(f'  基金：{funds}')

    pdf_path = OUTPUT_DIR / f'MMF_Factsheet_{eval_date.strftime("%Y%m%d")}_TC.pdf'
    print(f'  正在生成 PDF...')
    build_pdf(data, eval_date, pdf_path)

    print(f'\n✅ 完成：{pdf_path}')
    return str(pdf_path)


if __name__ == '__main__':
    main()
