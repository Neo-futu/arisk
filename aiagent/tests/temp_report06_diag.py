import os
import re
import pathlib
import psycopg2
from dotenv import load_dotenv

load_dotenv()
dsn = dict(
    host=os.getenv('POSTGRES_HOST','localhost'),
    port=int(os.getenv('POSTGRES_PORT','5432')),
    dbname=os.getenv('POSTGRES_DB','fsi_risk'),
    user=os.getenv('POSTGRES_USER','fsi_user'),
    password=os.getenv('POSTGRES_PASSWORD','change_me'),
)
conn = psycopg2.connect(**dsn)
files = [
    '2_processing/sql/mmf/report_06/03_maturity_ladder.sql',
    '2_processing/sql/mmf/report_06/04_deposit_early_redeem.sql',
    '2_processing/sql/mmf/report_06/06_asset_liquidity.sql',
    '2_processing/sql/mmf/report_06/07_credit_repo_issuers.sql',
    '2_processing/sql/mmf/report_06/08_compliance_daily.sql',
]
params = {'evaluate_date': '2026-06-25', 'port_ids': ['BHMMF001', 'BHMMF002']}
for f in files:
    path = pathlib.Path(f)
    sql = path.read_text(encoding='utf-8')
    sql = re.sub(r"'\d{4}-\d{2}-\d{2}'::DATE", f"'{params['evaluate_date']}'::DATE", sql)
    if params['port_ids']:
        arr = ', '.join(f"'{p}'" for p in params['port_ids'])
        sql = re.sub(r"ARRAY\[.*?\]::TEXT\[\]", f"ARRAY[{arr}]::TEXT[]", sql)
        sql = sql.replace('params.port_ids', f"ARRAY[{arr}]::TEXT[]")
    sql = sql.replace('params.evaluate_date', f"'{params['evaluate_date']}'::DATE")
    sql = sql.replace('params.trade_days_ahead', '5')
    sql = sql.replace('params.rate_shock_bps', '50')
    sql = re.sub(r",\s*params\b", '', sql)
    print('---', f)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall() if cur.description else []
            print('OK', len(rows), 'rows')
    except Exception as e:
        print('ERROR', e)
        conn.rollback()
        import traceback
        traceback.print_exc()
conn.close()
