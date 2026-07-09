"""
extract_data.py — 查詢資料庫，輸出 outputdata.json
用法：python extract_data.py --date 2026-06-25 --fund 博匯港元貨幣市場基金I

輸出：output/report_04_mmf_monthly/outputdata_{YYYYMMDD}_{基金名}.json
      每個字段對應 PDF 中一個可變位置，可直接檢查數據是否正確。
"""
import sys
import os
import json
import argparse
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

SQL_MMF    = Path(__file__).parent.parent.parent.parent / "sql" / "mmf"
OUTPUT_DIR = SQL_MMF / 'output' / 'report_04_mmf_monthly'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    import psycopg2
    import psycopg2.extras
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print('pip install psycopg2-binary python-dotenv')
    sys.exit(1)


class MmfDataExtractor:
    """貨幣市場基金月報資料提取器。將資料庫查詢分拆為可復用、易維護的方法。"""

    ASSET_LABELS = {
        'CASH': '現金及等價物',
        'DEPOSIT': '定期存款',
        'CD': '同業存單',
        'BOND_GOVT': '政府/公共債券',
        'BOND_CORP': '企業債券',
        'REPO': '逆回購協議',
    }

    MATURITY_BUCKETS = {
        1: '1天以內', 2: '2-7天', 3: '8-30天', 4: '31-60天',
        5: '61-90天', 6: '91-180天', 7: '181-365天', 8: '超365天',
    }

    def __init__(self):
        self.db_params = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'dbname': os.getenv('POSTGRES_DB', 'fsi_risk'),
            'user': os.getenv('POSTGRES_USER', 'fsi_user'),
            'password': os.getenv('POSTGRES_PASSWORD', 'change_me'),
        }

    def _conn(self):
        return psycopg2.connect(**self.db_params)

    def _query(self, conn, sql, params=None):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _format_date(value):
        return value.isoformat() if hasattr(value, 'isoformat') else str(value)

    def get_active_funds(self, fund_name: str | None = None, port_id: str | None = None):
        """
        port_id 優先：直接查 port_id = %s（精確匹配，避免 BHMMF001/BHMMF002 混淆）。
        fund_name 降級：用精確 = 匹配，不再用 in（子串匹配會讓「基金I」誤匹配「基金II」）。
        """
        if port_id:
            sql = (
                'SELECT p.port_name FROM fsi.para_portfolio p '
                'WHERE p.port_id = %s AND p.is_mmf=TRUE AND p.is_active=TRUE'
            )
            with self._conn() as conn:
                return [row['port_name'] for row in self._query(conn, sql, (port_id,))]

        sql = (
            'SELECT p.port_name FROM fsi.para_portfolio p '
            'WHERE p.is_mmf=TRUE AND p.is_active=TRUE ORDER BY p.port_name'
        )
        with self._conn() as conn:
            funds = [row['port_name'] for row in self._query(conn, sql)]
        # 精確匹配（= 而非 in），解決「基金I」子串命中「基金II」的 bug
        return [name for name in funds if name == fund_name] if fund_name else funds

    def extract(self, fund_name: str, ev: date) -> dict:
        d = ev.isoformat()
        with self._conn() as conn:
            base = self._fetch_fund_info(conn, fund_name, d)
            nav_classes = self._fetch_nav_classes(conn, fund_name, d)
            performance = self._build_performance(conn, fund_name, d, base)
            annual_performance = self._fetch_annual_performance(conn, fund_name, ev)
            asset_allocation = self._fetch_asset_allocation(conn, fund_name, d)
            maturity_dist = self._fetch_maturity_dist(conn, fund_name, d)
            ytm_pct = self._fetch_weighted_ytm(conn, fund_name, d)

        return {
            'fund_name':          fund_name,
            'base_currency':      base.get('base_currency', 'HKD'),
            'eval_date':          d,
            'nav_millions':       float(base.get('nav_millions', 0)),
            'wam_days':           float(base.get('wam_days', 0)),
            'wal_days':           float(base.get('wal_days', 0)),
            'ytm_pct':            ytm_pct,
            'investment_manager': '博匯投資管理有限公司',
            'trustee':            '博匯保誠信託有限公司',
            'custodian':          '中國銀行（香港）有限公司',
            'nav_classes':        nav_classes,
            'performance':        performance,
            'annual_performance': annual_performance,
            'asset_allocation':   asset_allocation,
            'maturity_dist':      maturity_dist,
        }

    def _fetch_fund_info(self, conn, fund_name, d):
        sql = (
            'SELECT p.port_name, COALESCE(p.base_currency, ''HKD'') AS base_currency, '
            'ROUND(n.net_asset / 1e6, 2) AS nav_millions, '
            'COALESCE(m.wam_days, 0) AS wam_days, '
            'COALESCE(m.wal_days, 0) AS wal_days, '
            'COALESCE(m.return_rate_7d, 0) AS ret_7d_ann '
            'FROM fsi.para_portfolio p '
            'JOIN fsi.balance_portfolio_nav n ON n.port_id = p.port_id '
            '  AND n.evaluate_date = %s::DATE AND n.class_id IS NULL '
            'LEFT JOIN fsi.balance_portfolio_mmf m ON m.port_id = p.port_id '
            '  AND m.evaluate_date = %s::DATE '
            'WHERE p.port_name = %s AND p.is_mmf = TRUE'
        )
        rows = self._query(conn, sql, (d, d, fund_name))
        return rows[0] if rows else {}

    def _fetch_nav_classes(self, conn, fund_name, d):
        sql = (
            'SELECT COALESCE(n.class_id::TEXT, ''Base'') AS class_id, '
            'ROUND(COALESCE(n.unit_nav, 0), 4) AS nav_per_unit, '
            'n.evaluate_date::TEXT AS date '
            'FROM fsi.para_portfolio p '
            'JOIN fsi.balance_portfolio_nav n ON n.port_id = p.port_id '
            '  AND n.evaluate_date = %s::DATE '
            'WHERE p.port_name = %s AND p.is_mmf = TRUE '
            'ORDER BY n.class_id NULLS LAST'
        )
        return [
            {
                'class_id': row['class_id'],
                'nav_per_unit': float(row['nav_per_unit']),
                'issue_date': row['date'],
            }
            for row in self._query(conn, sql, (d, fund_name))
        ]

    def _fetch_current_nav(self, conn, fund_name, d):
        sql = (
            'SELECT n.unit_nav FROM fsi.balance_portfolio_nav n '
            'JOIN fsi.para_portfolio p ON p.port_id = n.port_id '
            'WHERE p.port_name = %s AND n.evaluate_date = %s::DATE AND n.class_id IS NULL'
        )
        rows = self._query(conn, sql, (fund_name, d))
        return float(rows[0]['unit_nav']) if rows else 0

    def _fetch_inception_row(self, conn, fund_name):
        sql = (
            'SELECT n.unit_nav, n.evaluate_date AS d0 FROM fsi.balance_portfolio_nav n '
            'JOIN fsi.para_portfolio p ON p.port_id = n.port_id '
            'WHERE p.port_name = %s AND n.class_id IS NULL '
            'ORDER BY n.evaluate_date ASC LIMIT 1'
        )
        rows = self._query(conn, sql, (fund_name,))
        return rows[0] if rows else None

    def _build_performance(self, conn, fund_name, d, base):
        cn = self._fetch_current_nav(conn, fund_name, d)

        def nav_ago(lo, hi):
            sql = (
                'SELECT n.unit_nav FROM fsi.balance_portfolio_nav n '
                'JOIN fsi.para_portfolio p ON p.port_id = n.port_id '
                'WHERE p.port_name = %s AND n.class_id IS NULL '
                '  AND n.evaluate_date BETWEEN %s::DATE-%s AND %s::DATE-%s '
                'ORDER BY n.evaluate_date DESC LIMIT 1'
            )
            rows = self._query(conn, sql, (fund_name, d, hi, d, lo))
            if not rows or cn == 0:
                return None
            v = float(rows[0]['unit_nav'])
            return round((cn / v - 1) * 100, 2) if v > 0 else None

        inception = self._fetch_inception_row(conn, fund_name)
        performance = {
            'ret_1m': self._safe_percentage(nav_ago(25, 40)),
            'ret_3m': self._safe_percentage(nav_ago(85, 100)),
            'ret_6m': self._safe_percentage(nav_ago(175, 195)),
            'ret_1y': self._safe_percentage(nav_ago(355, 380)),
            'ret_since_inception': None,
            'ret_ann_since_inception': None,
            'ret_7d_ann': float(base.get('ret_7d_ann', 0)),
            'inception_date': None,
        }
        if inception and cn > 0:
            v0 = float(inception['unit_nav'])
            d0 = inception['d0']
            days = (date.fromisoformat(d) - d0).days
            if v0 > 0:
                performance['ret_since_inception'] = round((cn / v0 - 1) * 100, 2)
                performance['inception_date'] = self._format_date(d0)
                if days > 0:
                    performance['ret_ann_since_inception'] = round((pow(cn / v0, 365 / days) - 1) * 100, 2)
        return performance

    @staticmethod
    def _safe_percentage(value):
        return value

    def _fetch_annual_performance(self, conn, fund_name, ev):
        """查詢年度收益率及本年累計，並在 Python 層進行日期選擇與計算。"""
        sql = (
            'SELECT n.unit_nav, n.evaluate_date '
            'FROM fsi.balance_portfolio_nav n '
            'JOIN fsi.para_portfolio p ON p.port_id = n.port_id '
            'WHERE p.port_name = %s AND n.class_id IS NULL '
            '  AND n.evaluate_date BETWEEN %s::DATE AND %s::DATE '
            'ORDER BY n.evaluate_date'
        )
        rows = self._query(conn, sql, (fund_name, '2021-01-01', ev.isoformat()))
        nav_rows = []
        for row in rows:
            dt = row['evaluate_date']
            if isinstance(dt, str):
                dt = date.fromisoformat(dt)
            nav_rows.append({'date': dt, 'unit_nav': float(row['unit_nav'])})

        if not nav_rows:
            return []

        by_year = {}
        for row in nav_rows:
            by_year.setdefault(row['date'].year, []).append(row)

        results = []
        for year in range(2021, ev.year):
            current_year = by_year.get(year, [])
            previous_year = by_year.get(year - 1, [])
            if not current_year or not previous_year:
                continue
            start_nav = previous_year[-1]['unit_nav']
            end_nav = current_year[-1]['unit_nav']
            if start_nav > 0:
                results.append({'year': str(year), 'return_pct': round((end_nav / start_nav - 1) * 100, 2)})

        current_year_rows = by_year.get(ev.year, [])
        if current_year_rows:
            start_nav = current_year_rows[0]['unit_nav']
            end_nav = current_year_rows[-1]['unit_nav']
            if start_nav > 0:
                results.append({'year': '本年至今', 'return_pct': round((end_nav / start_nav - 1) * 100, 2)})

        return results

    def _fetch_asset_allocation(self, conn, fund_name, d):
        sql = (
            'SELECT a.asset_class::TEXT AS cls, '
            'ROUND(SUM(a.market_value) / n.net_asset * 100, 2) AS pct '
            'FROM fsi.balance_portfolio_asset a '
            'JOIN fsi.para_portfolio p ON p.port_id = a.port_id '
            'JOIN fsi.balance_portfolio_nav n ON n.port_id = a.port_id '
            '  AND n.evaluate_date = a.evaluate_date AND n.class_id IS NULL '
            'WHERE p.port_name = %s AND a.evaluate_date = %s::DATE AND n.net_asset > 0 '
            'GROUP BY a.asset_class, n.net_asset ORDER BY pct DESC'
        )
        rows = self._query(conn, sql, (fund_name, d))
        return [
            {
                'asset_class': row['cls'],
                'label': self.ASSET_LABELS.get(row['cls'], row['cls']),
                'pct_of_nav': float(row['pct']),
            }
            for row in rows
        ]

    def _fetch_maturity_dist(self, conn, fund_name, d):
        sql = (
            'WITH h AS ( '
            '  SELECT b.port_id, GREATEST(COALESCE(b.remaining_days, (b.maturity_date - %s::DATE)::INT), 0) AS rd, '
            '         COALESCE(b.market_value, 0) AS mv '
            '  FROM fsi.balance_bond b JOIN fsi.para_portfolio p ON p.port_id = b.port_id '
            '  WHERE p.port_name = %s AND b.evaluate_date = %s::DATE AND b.quantity > 0 '
            '  UNION ALL '
            '  SELECT c.port_id, GREATEST(COALESCE(c.remaining_days, (c.maturity_date - %s::DATE)::INT), 0), '
            '         COALESCE(c.market_value, 0) '
            '  FROM fsi.balance_cd c JOIN fsi.para_portfolio p ON p.port_id = c.port_id '
            '  WHERE p.port_name = %s AND c.evaluate_date = %s::DATE '
            '  UNION ALL '
            '  SELECT d2.port_id, GREATEST((d2.maturity_date - %s::DATE)::INT, 0), COALESCE(d2.principal, 0) '
            '  FROM fsi.balance_deposit d2 JOIN fsi.para_portfolio p ON p.port_id = d2.port_id '
            '  WHERE p.port_name = %s AND d2.evaluate_date = %s::DATE '
            '  UNION ALL '
            '  SELECT r.port_id, GREATEST((COALESCE(r.actual_maturity_date, r.maturity_date) - %s::DATE)::INT, 0), '
            '         COALESCE(r.principal, 0) '
            '  FROM fsi.balance_repo r JOIN fsi.para_portfolio p ON p.port_id = r.port_id '
            '  WHERE p.port_name = %s AND r.evaluate_date = %s::DATE AND r.repo_type = %s '
            ') '
            'SELECT CASE WHEN rd <= 1 THEN 1 WHEN rd <= 7 THEN 2 WHEN rd <= 30 THEN 3 '
            '            WHEN rd <= 60 THEN 4 WHEN rd <= 90 THEN 5 WHEN rd <= 180 THEN 6 '
            '            WHEN rd <= 365 THEN 7 ELSE 8 END AS ord, '
            '       ROUND(SUM(mv) / n.net_asset * 100, 2) AS pct '
            'FROM h JOIN fsi.balance_portfolio_nav n ON n.port_id = h.port_id '
            '       AND n.evaluate_date = %s::DATE AND n.class_id IS NULL '
            'GROUP BY ord, n.net_asset ORDER BY ord'
        )
        params = (
            d, fund_name, d,
            d, fund_name, d,
            d, fund_name, d,
            d, fund_name, d, 'REV_REPO', d,
        )
        rows = self._query(conn, sql, params)
        return [
            {'bucket': self.MATURITY_BUCKETS[row['ord']], 'pct_of_nav': float(row['pct'])}
            for row in rows
        ]

    def _fetch_weighted_ytm(self, conn, fund_name, d):
        sql = (
            'SELECT ROUND(SUM(ytm * mv) / NULLIF(SUM(mv), 0), 4) AS v FROM ( '
            '  SELECT COALESCE(b.ytm, 0) AS ytm, COALESCE(b.market_value, 0) AS mv '
            '  FROM fsi.balance_bond b JOIN fsi.para_portfolio p ON p.port_id = b.port_id '
            '  WHERE p.port_name = %s AND b.evaluate_date = %s::DATE AND b.quantity > 0 '
            '  UNION ALL '
            '  SELECT COALESCE(c.ytm, 0), COALESCE(c.market_value, 0) '
            '  FROM fsi.balance_cd c JOIN fsi.para_portfolio p ON p.port_id = c.port_id '
            '  WHERE p.port_name = %s AND c.evaluate_date = %s::DATE '
            '  UNION ALL '
            '  SELECT COALESCE(d2.interest_rate, 0) * 100, COALESCE(d2.principal, 0) '
            '  FROM fsi.balance_deposit d2 JOIN fsi.para_portfolio p ON p.port_id = d2.port_id '
            '  WHERE p.port_name = %s AND d2.evaluate_date = %s::DATE '
            ') t'
        )
        rows = self._query(conn, sql, (fund_name, d, fund_name, d, fund_name, d))
        return float(rows[0]['v']) if rows and rows[0]['v'] is not None else 0.0

    def save_output(self, data, ev, fund_name):
        safe = fund_name.replace('/', '-').replace(' ', '_')
        out_path = OUTPUT_DIR / f'outputdata_{ev.strftime("%Y%m%d")}_{safe}.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return out_path


# port_id → 基金全名映射（避免 shell 中文傳參編碼問題）
PORT_ID_MAP: dict[str, str] = {
    "BHMMF001": "博匯港元貨幣市場基金I",
    "BHMMF002": "博匯港元貨幣市場基金II",
}


def _placeholder_data(fund_name: str, ev: date) -> dict:
    """無數據時返回佔位結構，確保 PDF/Word 管道繼續執行（字段顯示 —）。"""
    return {
        "fund_name":          fund_name,
        "base_currency":      "HKD",
        "eval_date":          ev.isoformat(),
        "nav_millions":       0.0,
        "wam_days":           0.0,
        "wal_days":           0.0,
        "ytm_pct":            0.0,
        "investment_manager": "博匯投資管理有限公司",
        "trustee":            "博匯保誠信託有限公司",
        "custodian":          "中國銀行（香港）有限公司",
        "nav_classes":        [],
        "performance":        {},
        "annual_performance": [],
        "asset_allocation":   [],
        "maturity_dist":      [],
        "_empty_data":        True,
    }


def main():
    ap = argparse.ArgumentParser(description='MMF 月報資料提取 → outputdata.json')
    ap.add_argument('--date',    default=date.today().isoformat(), help='估值日期 YYYY-MM-DD')
    ap.add_argument('--fund',    default=None, help='基金名稱（缺省=全部 MMF）')
    ap.add_argument('--port-id', default=None, dest='port_id',
                    help='基金 port_id（ASCII，避免 shell 編碼問題，如 BHMMF001）')
    args = ap.parse_args()
    ev = date.fromisoformat(args.date)

    extractor = MmfDataExtractor()

    # port_id 優先（ASCII，避免 Windows shell 中文傳參問題；精確匹配避免 I/II 混淆）
    if args.port_id:
        if args.port_id not in PORT_ID_MAP:
            print(f'⚠ 未知 port_id：{args.port_id}，將提取全部 MMF 基金')
        funds = extractor.get_active_funds(port_id=args.port_id)
    elif args.fund:
        funds = extractor.get_active_funds(fund_name=args.fund)
    else:
        funds = extractor.get_active_funds()
    if not funds:
        # 有 port_id 但 DB 沒有匹配基金 → 用佔位名生成空 JSON，確保 PDF/Word 管道繼續
        fallback_name = fund_filter or "MMF基金"
        print(f'⚠ 找不到符合條件的基金（{fund_filter}），使用空白佔位數據繼續生成...')
        data = _placeholder_data(fallback_name, ev)
        out = extractor.save_output(data, ev, fallback_name)
        print(f'  → 佔位文件：{out.name}')
        return

    print(f'[extract_data] 估值日期：{ev}  基金數：{len(funds)}')
    for fund_name in funds:
        print(f'  提取：{fund_name} ...', end='', flush=True)
        try:
            data = extractor.extract(fund_name, ev)
            # 如果關鍵數據為空（該日期無 NAV），補充佔位結構
            if not data.get('nav_millions') and not data.get('asset_allocation'):
                print(' ⚠ 無數據，使用空白佔位', end='')
                data = _placeholder_data(fund_name, ev)
            out = extractor.save_output(data, ev, fund_name)
            print(f' ✅  →  {out.name}')
        except Exception as exc:
            print(f'\n  ⚠ {exc}，使用空白佔位')
            data = _placeholder_data(fund_name, ev)
            out = extractor.save_output(data, ev, fund_name)
            print(f'  → 佔位文件：{out.name}')


if __name__ == '__main__':
    main()
