"""
seed_data.py  report_03 測試數據插入
=====================================
插入兩只虛擬 MMF 基金（BHMMF001/BHMMF002）的一日測試數據。
運行：python 1_datastorage/test/test_report_03/seed_data.py

涉及表：
  para_portfolio · balance_portfolio_nav · balance_portfolio_asset
  balance_bond · balance_cd · balance_deposit · balance_repo
  balance_valuation_sheet · balance_holder_summary · balance_holder_rank
"""

import os
import sys
from datetime import date, timedelta

import psycopg2
from dotenv import load_dotenv

load_dotenv()

TEST_DATE   = date(2026, 6, 25)
PORT_IDS    = ["BHMMF001", "BHMMF002"]
PORT_NAMES  = ["博匯港元貨幣市場基金I", "博匯港元貨幣市場基金II"]


def connect():
    return psycopg2.connect(
        host     = os.getenv("POSTGRES_HOST", "localhost"),
        port     = int(os.getenv("POSTGRES_PORT", "5432")),
        dbname   = os.getenv("POSTGRES_DB", "fsi_risk"),
        user     = os.getenv("POSTGRES_USER", "fsi_user"),
        password = os.getenv("POSTGRES_PASSWORD", "change_me"),
    )


def seed(conn):
    cur = conn.cursor()

    # ── para_portfolio ───────────────────────────────────────
    cur.executemany("""
        INSERT INTO fsi.para_portfolio
            (port_id, port_name, port_name_en, port_type, base_currency,
             inception_date, is_active, is_mmf,
             mmf_wam_limit_days, mmf_wal_limit_days,
             mmf_daily_liq_pct, mmf_weekly_liq_pct,
             sfc_code)
        VALUES (%s,%s,%s,'MMF','HKD','2020-01-15',TRUE,TRUE,60,120,7.5,15.0,%s)
        ON CONFLICT (port_id) DO NOTHING
    """, [
        ("BHMMF001", PORT_NAMES[0], "Bolide HKD MMF I",  "SFC-MMF-001"),
        ("BHMMF002", PORT_NAMES[1], "Bolide HKD MMF II", "SFC-MMF-002"),
    ])

    # ── balance_portfolio_nav ────────────────────────────────
    nav_rows = [
        # port_id   ccy   net_asset(元)     shares      unit_nav  acc_unit_nav
        # day_ret   wam   wal   deviation_bp  income_10k  ret7d
        # deviation_bp: 偏離度基點（1bp=0.01%），正=高於攤余/負=低於攤余
        # income_per_10k: 每萬份收益（元/天）= 1.0×10000×(ret7d%/365)
        #   BHMMF001: 4.32%/365×10000 ≈ 1.1836 元/萬份
        #   BHMMF002: 4.18%/365×10000 ≈ 1.1452 元/萬份
        ("BHMMF001","HKD",2_704_500_000,270_450_000,1.000000,1.012345,
         0.000118, 52, 68,  12.50, 1.1836, 4.32),    # +12.5bp 偏差，HIBOR4.32%
        ("BHMMF002","HKD",1_852_000_000,185_200_000,1.000000,1.008765,
         0.000114, 47, 61,  -8.00, 1.1452, 4.18),    # -8bp 偏差，HIBOR4.18%
    ]
    for row in nav_rows:
        (port_id, ccy, net_asset, shares, unit_nav, acc_unit_nav,
         day_ret, wam, wal, deviation_bp, income, ret7d) = row
        # 偏離金額（元）= 偏離度(bp) / 10000 × NAV
        dev_amount = deviation_bp / 10000 * net_asset
        # balance_portfolio_nav：通用字段（所有基金類型）
        cur.execute("""
            INSERT INTO fsi.balance_portfolio_nav
                (evaluate_date, port_id, currency, net_asset, shares_outstanding,
                 unit_nav, acc_unit_nav, day_return, loaded_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT DO NOTHING
        """, (TEST_DATE, port_id, ccy, net_asset, shares,
              unit_nav, acc_unit_nav, day_ret))

        # balance_portfolio_mmf：貨基專有字段（對應 T_Balance_Portfolio_MMF）
        cur.execute("""
            INSERT INTO fsi.balance_portfolio_mmf
                (evaluate_date, port_id,
                 income_per_10k, return_rate_7d,
                 nav_deviation, nav_deviation_amount,
                 wam_days, wal_days, loaded_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT DO NOTHING
        """, (TEST_DATE, port_id, income, ret7d,
              deviation_bp, dev_amount, int(wam), int(wal)))

    # ── balance_portfolio_asset ──────────────────────────────
    asset_rows = []
    for pid, nav in [("BHMMF001", 2_704_500_000), ("BHMMF002", 1_852_000_000)]:
        asset_rows += [
            (pid, "BOND_GOVT", nav * 0.28),
            (pid, "BOND_CORP", nav * 0.15),
            (pid, "CD",        nav * 0.22),
            (pid, "DEPOSIT",   nav * 0.18),
            (pid, "REV_REPO",  nav * 0.10),
            (pid, "CASH",      nav * 0.07),
        ]
    for pid, ac, mv in asset_rows:
        nav_val = 2_704_500_000 if pid == "BHMMF001" else 1_852_000_000
        cur.execute("""
            INSERT INTO fsi.balance_portfolio_asset
                (evaluate_date, port_id, asset_class, market_value,
                 market_value_base, weight_pct, loaded_at)
            VALUES (%s,%s,%s::fsi.asset_class,%s,%s,%s,NOW())
            ON CONFLICT DO NOTHING
        """, (TEST_DATE, pid, ac, mv, mv, mv / nav_val * 100))

    # ── balance_bond ─────────────────────────────────────────
    # remaining_days 是 Generated Column（= maturity_date - evaluate_date），不能手動插入
    bonds = [
        # port_id   code             name                   subtype      issuer_name          ccy   qty         cost        mv          ytm    dur   cvx   cpn    maturity_date                rating   wt
        ("BHMMF001","HK_GOVT_2026", "香港政府債券2026",    "BOND_GOVT","香港特別行政區政府","HKD",50_000_000,49_800_000,49_850_000,0.0428,0.50,0.01,0.0450,TEST_DATE+timedelta(182),"AAA", 0.1842),
        ("BHMMF001","HKMA_TB_09",  "金管局國庫票據0926",  "BOND_GOVT","香港金融管理局",    "HKD",30_000_000,29_920_000,29_940_000,0.0431,0.25,0.005,0.0435,TEST_DATE+timedelta(91), "AAA", 0.1107),
        ("BHMMF001","BOCHK_CP_01", "中銀香港商票0926",    "BOND_CORP","中國銀行(香港)",    "HKD",20_000_000,19_950_000,19_960_000,0.0442,0.24,0.004,0.0445,TEST_DATE+timedelta(88), "A-1", 0.0738),
        ("BHMMF001","HSBC_MTN_01", "匯豐中期票據",        "BOND_CORP","匯豐銀行",          "HKD",15_000_000,14_910_000,14_925_000,0.0455,0.48,0.009,0.0460,TEST_DATE+timedelta(175),"A-1+",0.0552),
        ("BHMMF002","HK_GOVT_2027","香港政府債券2027",    "BOND_GOVT","香港特別行政區政府","HKD",40_000_000,39_720_000,39_760_000,0.0432,0.75,0.02, 0.0440,TEST_DATE+timedelta(273),"AAA", 0.2147),
        ("BHMMF002","HKMA_TB_12",  "金管局國庫票據1226",  "BOND_GOVT","香港金融管理局",    "HKD",25_000_000,24_940_000,24_950_000,0.0429,0.49,0.01, 0.0433,TEST_DATE+timedelta(180),"AAA", 0.1348),
        ("BHMMF002","STAN_CP_01",  "渣打商票0926",        "BOND_CORP","渣打銀行",          "HKD",18_000_000,17_960_000,17_965_000,0.0448,0.24,0.004,0.0450,TEST_DATE+timedelta(87), "A-1", 0.0970),
    ]
    for b in bonds:
        (pid,code,name,subtype,issuer,ccy,qty,cost,mv,ytm,dur,cvx,cpn,matdt,rating,wt) = b
        cur.execute("""
            INSERT INTO fsi.balance_bond
                (evaluate_date,port_id,security_code,security_name,asset_subtype,
                 issuer_name,currency,quantity,cost,market_value,market_value_base,
                 ytm,duration,convexity,coupon_rate,maturity_date,
                 issuer_rating,weight_pct,loaded_at)
            VALUES (%s,%s,%s,%s,%s::fsi.asset_class,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT DO NOTHING
        """, (TEST_DATE,pid,code,name,subtype,issuer,ccy,qty,cost,mv,mv,ytm,dur,cvx,cpn,matdt,rating,wt*100))

    # ── balance_cd ───────────────────────────────────────────
    cds = [
        ("BHMMF001","CD_BOCHK_01","中銀香港存款證0926","BOCHK","中國銀行(香港)","中銀集團","HKD",
         30_000_000,29_970_000,0.0432,0.24,TEST_DATE+timedelta(91), "A-1",0.1108),
        ("BHMMF001","CD_HSBC_01", "匯豐存款證1226",   "HSBC", "匯豐銀行",      "匯豐集團","HKD",
         25_000_000,24_960_000,0.0438,0.49,TEST_DATE+timedelta(180),"A-1+",0.0923),
        ("BHMMF002","CD_SCB_01",  "渣打存款證0926",   "SCB",  "渣打銀行",      "渣打集團","HKD",
         20_000_000,19_980_000,0.0440,0.24,TEST_DATE+timedelta(88), "A-1",0.1080),
        ("BHMMF002","CD_HKMA_01", "金管局存款證1226", "HKMA", "香港金融管理局","HK政府",  "HKD",
         22_000_000,21_975_000,0.0435,0.49,TEST_DATE+timedelta(179),"AAA",0.1188),
    ]
    for cd in cds:
        (pid,code,name,iid,iname,igrp,ccy,qty,mv,ytm,dur,matdt,rating,wt) = cd
        cur.execute("""
            INSERT INTO fsi.balance_cd
                (evaluate_date,port_id,security_code,security_name,
                 issuer_id,issuer_name,issuer_group,currency,
                 quantity,market_value,market_value_base,
                 ytm,duration,maturity_date,issuer_rating,weight_pct,loaded_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT DO NOTHING
        """, (TEST_DATE,pid,code,name,iid,iname,igrp,ccy,qty,mv,mv,ytm,dur,matdt,rating,wt*100))

    # ── balance_deposit ──────────────────────────────────────
    deposits = [
        ("BHMMF001","DEP_BOCHK_01","中銀香港定存3M", "BOCHK","中國銀行(香港)","中銀集團","HKD",
         TEST_DATE,TEST_DATE+timedelta(91), 150_000_000,0.0415,True, 0.0554),
        ("BHMMF001","DEP_HSBC_01", "匯豐定存6M",    "HSBC", "匯豐銀行",      "匯豐集團","HKD",
         TEST_DATE,TEST_DATE+timedelta(182),100_000_000,0.0428,True, 0.0370),
        ("BHMMF001","DEP_SCB_ON",  "渣打隔夜存款",  "SCB",  "渣打銀行",      "渣打集團","HKD",
         TEST_DATE,TEST_DATE+timedelta(1),  50_000_000, 0.0410,False,0.0185),
        ("BHMMF002","DEP_BOCHK_02","中銀香港定存6M","BOCHK","中國銀行(香港)","中銀集團","HKD",
         TEST_DATE,TEST_DATE+timedelta(180),120_000_000,0.0420,True, 0.0648),
        ("BHMMF002","DEP_HSBC_02", "匯豐定存3M",   "HSBC", "匯豐銀行",      "匯豐集團","HKD",
         TEST_DATE,TEST_DATE+timedelta(92), 80_000_000, 0.0425,True, 0.0432),
    ]
    for d in deposits:
        (pid,did,dname,bid,bname,bgrp,ccy,vd,md,princ,rate,penalty,wt) = d
        rem = (md - TEST_DATE).days
        cur.execute("""
            INSERT INTO fsi.balance_deposit
                (evaluate_date,port_id,deposit_id,deposit_name,
                 bank_id,bank_name,bank_group,currency,
                 value_date,maturity_date,
                 principal,interest_rate,
                 is_penalty_on_early_redeem,is_overnight,
                 weight_pct,loaded_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT DO NOTHING
        """, (TEST_DATE,pid,did,dname,bid,bname,bgrp,ccy,
              vd,md,princ,rate,penalty,rem==1,wt*100))

    # ── balance_repo ─────────────────────────────────────────
    repos = [
        ("BHMMF001","REPO_IB_01","REV_REPO","BOCHK","中銀香港","HK_GOV_BOND_01","HKD",
         TEST_DATE,TEST_DATE+timedelta(1), 80_000_000,0.0408,1,0.0296),
        ("BHMMF001","REPO_IB_02","REV_REPO","HSBC", "匯豐銀行","HK_GOV_BOND_02","HKD",
         TEST_DATE,TEST_DATE+timedelta(3),100_000_000,0.0412,3,0.0370),
        ("BHMMF002","REPO_IB_03","REV_REPO","SCB",  "渣打銀行","HK_GOV_BOND_03","HKD",
         TEST_DATE,TEST_DATE+timedelta(1), 60_000_000,0.0405,1,0.0324),
        ("BHMMF002","REPO_IB_04","REV_REPO","BOCHK","中銀香港","HK_GOV_BOND_04","HKD",
         TEST_DATE,TEST_DATE+timedelta(7),125_000_000,0.0415,7,0.0675),
    ]
    for r in repos:
        (pid,rid,rtype,cpid,cpname,pldg,ccy,vd,md,princ,rate,idays,wt) = r
        cur.execute("""
            INSERT INTO fsi.balance_repo
                (evaluate_date,port_id,repo_id,repo_type,
                 counterparty_id,counterparty_name,pledged_security_code,
                 currency,value_date,maturity_date,
                 principal,interest_rate,interest_days,
                 actual_maturity_date,weight_pct,loaded_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT DO NOTHING
        """, (TEST_DATE,pid,rid,rtype,cpid,cpname,pldg,ccy,vd,md,
              princ,rate,idays,md,wt*100))

    # ── balance_valuation_sheet ───────────────────────────────
    subjects = [
        ("100201","現金及活期存款"),
        ("100203","定期存款"),
        ("1111",  "債券投資"),
        ("1202",  "買入返售金融資產(逆回購)"),
        ("831",   "資產合計"),
        ("2202",  "賣出回購金融資產(正回購)"),
    ]
    nav_map = {"BHMMF001": 2_704_500_000, "BHMMF002": 1_852_000_000}
    ratios  = {"100201":0.07,"100203":0.18,"1111":0.43,"1202":0.10,"831":1.0,"2202":0.02}
    for pid, nav in nav_map.items():
        for code, name in subjects:
            mv = nav * ratios.get(code, 0)
            cur.execute("""
                INSERT INTO fsi.balance_valuation_sheet
                    (evaluate_date,port_id,subject_code,subject_name,
                     currency,market_value,weight_pct,data_source,loaded_at)
                VALUES (%s,%s,%s,%s,'HKD',%s,%s,'VALUATION',NOW())
                ON CONFLICT DO NOTHING
            """, (TEST_DATE,pid,code,name,mv,mv/nav*100))

    # ── balance_holder_summary ────────────────────────────────
    for pid, nav in nav_map.items():
        cur.execute("""
            INSERT INTO fsi.balance_holder_summary
                (confirm_date,port_id,class_id,total_holders,retail_holders,
                 institutional_holders,total_shares,top10_amount,top10_pct)
            VALUES (%s,%s,'ALL',856,312,544,%s,%s,68.5)
            ON CONFLICT DO NOTHING
        """, (TEST_DATE, pid, nav/1.0, nav*0.685))

    # ── balance_holder_rank ───────────────────────────────────
    holders = [
        ("H001","中銀資管",  0.185),
        ("H002","匯豐資管",  0.142),
        ("H003","渣打私銀",  0.098),
        ("H004","富達基金",  0.087),
        ("H005","貝萊德",    0.073),
        ("H006","瑞銀財富",  0.065),
        ("H007","摩根資管",  0.058),
        ("H008","高盛私銀",  0.047),
        ("H009","德銀財富",  0.038),
        ("H010","花旗私銀",  0.032),
    ]
    for pid, nav in nav_map.items():
        for rank, (hid, hname, pct) in enumerate(holders, 1):
            cur.execute("""
                INSERT INTO fsi.balance_holder_rank
                    (confirm_date,port_id,rank_no,holder_id,holder_name,
                     amount,pct_of_total)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (TEST_DATE, pid, rank, hid, hname, nav*pct, pct*100))

    # ── svc_risk_perf（週/月/YTD/成立以來收益率 → 計算層結果）────
    # 這些不來自估值系統，由 2_processing 從 NAV 歷史計算後存入
    perf_data = [
        # port_id      period   fund_ret  bm_ret   active  te      sharpe  info    max_dd
        ("BHMMF001","1D",  0.000350, 0.000310, 0.000040, None,   None,   None,   None),
        ("BHMMF001","1W",  0.000123, 0.000110, 0.000013, None,   None,   None,   None),
        ("BHMMF001","1M",  0.003580, 0.003200, 0.000380, 0.0002, None,   None,  -0.0001),
        ("BHMMF001","YTD", 0.021450, 0.019200, 0.002250, 0.0003, 8.52,   7.50,  -0.0003),
        ("BHMMF001","SI",  0.124560, 0.112000, 0.012560, 0.0004, 7.80,   6.20,  -0.0005),
        ("BHMMF002","1D",  0.000280, 0.000310,-0.000030, None,   None,   None,   None),
        ("BHMMF002","1W",  0.000095, 0.000110,-0.000015, None,   None,   None,   None),
        ("BHMMF002","1M",  0.002980, 0.003200,-0.000220, 0.0003, None,   None,  -0.0002),
        ("BHMMF002","YTD", 0.018760, 0.019200,-0.000440, 0.0004, 6.24,  -1.10,  -0.0004),
        ("BHMMF002","SI",  0.098230, 0.112000,-0.013770, 0.0005, 5.90,  -2.75,  -0.0008),
    ]
    for pd_row in perf_data:
        (pid, period, fr, br, ar, te, sharpe, info, maxdd) = pd_row
        cur.execute("""
            INSERT INTO fsi.svc_risk_perf
                (port_id, class_id, as_of_date, period_type,
                 fund_return, benchmark_return, active_return,
                 tracking_error, sharpe_ratio, info_ratio, max_drawdown)
            VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (pid, TEST_DATE, period, fr, br, ar, te, sharpe, info, maxdd))

    conn.commit()
    print(f"[OK] seed data inserted. evaluate_date={TEST_DATE}  port_ids={PORT_IDS}")


if __name__ == "__main__":
    conn = connect()
    try:
        seed(conn)
    finally:
        conn.close()
