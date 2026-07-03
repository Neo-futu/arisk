"""
extract_data.py — 查詢資料庫，輸出 outputdata.json
用法：python extract_data.py --date 2026-06-25 --fund 博匯港元貨幣市場基金I

輸出：output/report_04_mmf_monthly/outputdata_{YYYYMMDD}_{基金名}.json
      每個字段對應 PDF 中一個可變位置，可直接檢查數據是否正確。
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date, timedelta
from pathlib import Path

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR.parent / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    import psycopg2, psycopg2.extras
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    print('pip install psycopg2-binary python-dotenv'); sys.exit(1)

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

def _fmt_date(d):
    return d.isoformat() if hasattr(d,'isoformat') else str(d)

def extract(fund_name: str, ev: date) -> dict:
    d = ev.isoformat()
    conn = _conn()

    # ── 基金基本資料 ──────────────────────────────────
    info = _q(f"""
        SELECT p.port_name, COALESCE(p.base_currency,'HKD') AS base_currency,
               ROUND(n.net_asset/1e6, 2)          AS nav_millions,
               COALESCE(m.wam_days, 0)             AS wam_days,
               COALESCE(m.wal_days, 0)             AS wal_days,
               COALESCE(m.return_rate_7d, 0)       AS ret_7d_ann
        FROM fsi.para_portfolio p
        JOIN fsi.balance_portfolio_nav n ON n.port_id=p.port_id
             AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
        LEFT JOIN fsi.balance_portfolio_mmf m ON m.port_id=p.port_id
             AND m.evaluate_date='{d}'::DATE
        WHERE p.port_name='{fund_name}' AND p.is_mmf=TRUE
    """, conn)
    base = info[0] if info else {}

    # ── 各類別 NAV ─────────────────────────────────────
    nav_cls = _q(f"""
        SELECT COALESCE(n.class_id::TEXT,'Base') AS class_id,
               ROUND(COALESCE(n.unit_nav,0),4)   AS nav_per_unit,
               n.evaluate_date::TEXT              AS date
        FROM fsi.para_portfolio p
        JOIN fsi.balance_portfolio_nav n ON n.port_id=p.port_id
             AND n.evaluate_date='{d}'::DATE
        WHERE p.port_name='{fund_name}' AND p.is_mmf=TRUE
        ORDER BY n.class_id NULLS LAST
    """, conn)

    # ── 累積業績 ───────────────────────────────────────
    cur_nav = _q(f"""SELECT n.unit_nav FROM fsi.balance_portfolio_nav n
        JOIN fsi.para_portfolio p ON p.port_id=n.port_id
        WHERE p.port_name='{fund_name}' AND n.evaluate_date='{d}'::DATE
          AND n.class_id IS NULL""", conn)
    cn = float(cur_nav[0]['unit_nav']) if cur_nav else 0

    def _nav_ago(lo, hi):
        r = _q(f"""SELECT n.unit_nav FROM fsi.balance_portfolio_nav n
            JOIN fsi.para_portfolio p ON p.port_id=n.port_id
            WHERE p.port_name='{fund_name}' AND n.class_id IS NULL
              AND n.evaluate_date BETWEEN '{d}'::DATE-{hi} AND '{d}'::DATE-{lo}
            ORDER BY n.evaluate_date DESC LIMIT 1""", conn)
        v = float(r[0]['unit_nav']) if r else 0
        return round((cn/v-1)*100,2) if v>0 and cn>0 else None

    inc = _q(f"""SELECT n.unit_nav, n.evaluate_date AS d0
        FROM fsi.balance_portfolio_nav n
        JOIN fsi.para_portfolio p ON p.port_id=n.port_id
        WHERE p.port_name='{fund_name}' AND n.class_id IS NULL
        ORDER BY n.evaluate_date ASC LIMIT 1""", conn)

    perf = {
        'ret_1m':  _nav_ago(25,40),   # 一個月
        'ret_3m':  _nav_ago(85,100),  # 三個月
        'ret_6m':  _nav_ago(175,195), # 六個月
        'ret_1y':  _nav_ago(355,380), # 一年
        'ret_since_inception': None,
        'ret_ann_since_inception': None,
        'ret_7d_ann': float(base.get('ret_7d_ann', 0)),
        'inception_date': None,
    }
    if inc and cn > 0:
        v0 = float(inc[0]['unit_nav']); d0 = inc[0]['d0']; days=(ev-d0).days
        if v0 > 0:
            perf['ret_since_inception'] = round((cn/v0-1)*100, 2)
            perf['inception_date'] = _fmt_date(d0)
            if days > 0: perf['ret_ann_since_inception'] = round((pow(cn/v0,365/days)-1)*100,2)

    # ── 年度業績 ──────────────────────────────────────
    annual = []
    for yr in range(2021, ev.year+1):
        lbl = '本年至今' if yr==ev.year else str(yr)
        end = d if yr==ev.year else f'{yr}-12-31'
        rows = _q(f"""SELECT n.unit_nav FROM fsi.balance_portfolio_nav n
            JOIN fsi.para_portfolio p ON p.port_id=n.port_id
            WHERE p.port_name='{fund_name}' AND n.class_id IS NULL AND n.evaluate_date IN (
                (SELECT MIN(evaluate_date) FROM fsi.balance_portfolio_nav n2
                 JOIN fsi.para_portfolio p2 ON p2.port_id=n2.port_id
                 WHERE p2.port_name='{fund_name}' AND n2.class_id IS NULL
                   AND n2.evaluate_date>='{yr}-01-01' AND n2.evaluate_date<='{yr}-01-10'),
                (SELECT MAX(evaluate_date) FROM fsi.balance_portfolio_nav n3
                 JOIN fsi.para_portfolio p3 ON p3.port_id=n3.port_id
                 WHERE p3.port_name='{fund_name}' AND n3.class_id IS NULL
                   AND n3.evaluate_date<='{end}'))
            ORDER BY n.evaluate_date""", conn)
        if len(rows) >= 2:
            v0, v1 = float(rows[0]['unit_nav']), float(rows[-1]['unit_nav'])
            if v0 > 0:
                annual.append({'year': lbl, 'return_pct': round((v1/v0-1)*100, 2)})

    # ── 資產配置 ──────────────────────────────────────
    _LBL = {'CASH':'現金及等價物','DEPOSIT':'定期存款','CD':'同業存單',
             'BOND_GOVT':'政府/公共債券','BOND_CORP':'企業債券','REPO':'逆回購協議'}
    alloc = []
    for r in _q(f"""SELECT a.asset_class::TEXT AS cls,
               ROUND(SUM(a.market_value)/n.net_asset*100, 2) AS pct
        FROM fsi.balance_portfolio_asset a
        JOIN fsi.para_portfolio p ON p.port_id=a.port_id
        JOIN fsi.balance_portfolio_nav n ON n.port_id=a.port_id
             AND n.evaluate_date=a.evaluate_date AND n.class_id IS NULL
        WHERE p.port_name='{fund_name}' AND a.evaluate_date='{d}'::DATE AND n.net_asset>0
        GROUP BY a.asset_class, n.net_asset ORDER BY pct DESC""", conn):
        alloc.append({'asset_class': r['cls'],
                      'label': _LBL.get(r['cls'], r['cls']),
                      'pct_of_nav': float(r['pct'])})

    # ── 到期日分佈 ────────────────────────────────────
    _B = {1:'1天以內',2:'2-7天',3:'8-30天',4:'31-60天',
          5:'61-90天',6:'91-180天',7:'181-365天',8:'超365天'}
    mat = []
    for r in _q(f"""WITH h AS (
        SELECT b.port_id,GREATEST(COALESCE(b.remaining_days,(b.maturity_date-'{d}'::DATE)::INT),0) AS rd,
               COALESCE(b.market_value,0) AS mv
        FROM fsi.balance_bond b JOIN fsi.para_portfolio p ON p.port_id=b.port_id
        WHERE p.port_name='{fund_name}' AND b.evaluate_date='{d}'::DATE AND b.quantity>0
        UNION ALL SELECT c.port_id,GREATEST(COALESCE(c.remaining_days,(c.maturity_date-'{d}'::DATE)::INT),0),
               COALESCE(c.market_value,0)
        FROM fsi.balance_cd c JOIN fsi.para_portfolio p ON p.port_id=c.port_id
        WHERE p.port_name='{fund_name}' AND c.evaluate_date='{d}'::DATE
        UNION ALL SELECT d2.port_id,GREATEST((d2.maturity_date-'{d}'::DATE)::INT,0),COALESCE(d2.principal,0)
        FROM fsi.balance_deposit d2 JOIN fsi.para_portfolio p ON p.port_id=d2.port_id
        WHERE p.port_name='{fund_name}' AND d2.evaluate_date='{d}'::DATE
        UNION ALL SELECT r.port_id,GREATEST((COALESCE(r.actual_maturity_date,r.maturity_date)-'{d}'::DATE)::INT,0),
               COALESCE(r.principal,0)
        FROM fsi.balance_repo r JOIN fsi.para_portfolio p ON p.port_id=r.port_id
        WHERE p.port_name='{fund_name}' AND r.evaluate_date='{d}'::DATE AND r.repo_type='REV_REPO')
        SELECT CASE WHEN rd<=1 THEN 1 WHEN rd<=7 THEN 2 WHEN rd<=30 THEN 3
                    WHEN rd<=60 THEN 4 WHEN rd<=90 THEN 5 WHEN rd<=180 THEN 6
                    WHEN rd<=365 THEN 7 ELSE 8 END AS ord,
               ROUND(SUM(mv)/n.net_asset*100,2) AS pct
        FROM h JOIN fsi.balance_portfolio_nav n ON n.port_id=h.port_id
               AND n.evaluate_date='{d}'::DATE AND n.class_id IS NULL
        GROUP BY ord,n.net_asset ORDER BY ord""", conn):
        mat.append({'bucket': _B[r['ord']], 'pct_of_nav': float(r['pct'])})

    # ── 加權平均 YTM ──────────────────────────────────
    ytm_r = _q(f"""SELECT ROUND(SUM(ytm*mv)/NULLIF(SUM(mv),0),4) AS v FROM (
        SELECT COALESCE(b.ytm,0) AS ytm,COALESCE(b.market_value,0) AS mv
        FROM fsi.balance_bond b JOIN fsi.para_portfolio p ON p.port_id=b.port_id
        WHERE p.port_name='{fund_name}' AND b.evaluate_date='{d}'::DATE AND b.quantity>0
        UNION ALL SELECT COALESCE(c.ytm,0),COALESCE(c.market_value,0)
        FROM fsi.balance_cd c JOIN fsi.para_portfolio p ON p.port_id=c.port_id
        WHERE p.port_name='{fund_name}' AND c.evaluate_date='{d}'::DATE
        UNION ALL SELECT COALESCE(d2.interest_rate,0)*100,COALESCE(d2.principal,0)
        FROM fsi.balance_deposit d2 JOIN fsi.para_portfolio p ON p.port_id=d2.port_id
        WHERE p.port_name='{fund_name}' AND d2.evaluate_date='{d}'::DATE) t""", conn)

    conn.close()

    return {
        # ── 可直接對應 PDF 中每個可變位置 ──
        'fund_name':          fund_name,
        'base_currency':      base.get('base_currency', 'HKD'),
        'eval_date':          d,
        'nav_millions':       float(base.get('nav_millions', 0)),  # 基金規模（百萬）
        'wam_days':           float(base.get('wam_days', 0)),      # 加權平均到期期限
        'wal_days':           float(base.get('wal_days', 0)),      # 加權平均存續期
        'ytm_pct':            float(ytm_r[0]['v']) if ytm_r and ytm_r[0]['v'] else 0,
        # 投資經理/受託人/託管人（暫用預設值，後期可從 para_portfolio 擴展字段讀取）
        'investment_manager': '博匯投資管理有限公司',
        'trustee':            '博匯保誠信託有限公司',
        'custodian':          '中國銀行（香港）有限公司',
        # NAV 各類別（PDF 表格中4行，不足則顯示"—"）
        'nav_classes':        [{'class_id': r['class_id'],
                                'nav_per_unit': float(r['nav_per_unit']),
                                'issue_date': r['date']} for r in nav_cls],
        # 累積業績（對應 PDF 右欄業績表第1行）
        'performance':        perf,
        # 年度業績
        'annual_performance': annual,
        # 資產配置（對應 P2 餅圖）
        'asset_allocation':   alloc,
        # 到期分佈（對應 P2 柱狀圖）
        'maturity_dist':      mat,
    }


def main():
    ap = argparse.ArgumentParser(description='MMF 月報資料提取 → outputdata.json')
    ap.add_argument('--date', default=date.today().isoformat(), help='估值日期 YYYY-MM-DD')
    ap.add_argument('--fund', default=None, help='基金名稱（缺省=全部 MMF）')
    args = ap.parse_args()
    ev = date.fromisoformat(args.date)

    conn = _conn()
    funds = [r['port_name'] for r in _q(
        "SELECT p.port_name FROM fsi.para_portfolio p "
        "WHERE p.is_mmf=TRUE AND p.is_active=TRUE ORDER BY p.port_name", conn)]
    conn.close()
    if args.fund: funds = [f for f in funds if args.fund in f]

    print(f'[extract_data] 估值日期：{ev}')
    for fn in funds:
        print(f'  提取：{fn} ...', end='', flush=True)
        try:
            data = extract(fn, ev)
            safe = fn.replace('/', '-').replace(' ', '_')
            out  = OUTPUT_DIR / f'outputdata_{ev.strftime("%Y%m%d")}_{safe}.json'
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            print(f' ✅  →  {out.name}')
        except Exception as e:
            print(f'\n  ✗ {e}')
            import traceback; traceback.print_exc()

if __name__ == '__main__':
    main()
