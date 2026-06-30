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
             sfc_code, wind_code)
        VALUES (%s,%s,%s,'MMF','HKD','2020-01-15',TRUE,TRUE,60,120,7.5,15.0,%s,%s)
        ON CONFLICT (port_id) DO UPDATE SET wind_code = EXCLUDED.wind_code
    """, [
        # sfc_code 格式參考：AGW600 = BOCHK HK Dollar MMF（SFC 認可代碼）
        # wind_code 為測試佔位，實際代碼待基金在 Wind 錄入後更新
        ("BHMMF001", PORT_NAMES[0], "Bolide HKD MMF I",  "BWH001", "BHMF001.OF"),
        ("BHMMF002", PORT_NAMES[1], "Bolide HKD MMF II", "BWH002", "BHMF002.OF"),
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
    # Wind 代碼來源：用戶確認的香港貨幣市場基金可交易債券清單
    bonds = [
        # ── BHMMF001 持倉 ────────────────────────────────────
        # code               name                              subtype      issuer                    ccy   qty          cost         mv           ytm     dur    cvx    cpn     maturity             rating  wt
        # 4701.HK：香港機場管理局 4.25% 到期 2026-08-05（41天，AAA，HKD）
        ("BHMMF001","4701.HK",
         "Airport Authority HK 4.25% 20260805",
         "BOND_GOVT","Airport Authority Hong Kong","HKD",
         50_000_000, 49_975_000, 49_980_000, 0.0428, 0.11, 0.001, 0.0425,
         date(2026,8,5), "AAA", 0.1847),

        # BNYHFN26213.CMU：香港大學 3.8% 到期 2036-06-22（AAA，HKD，CMU）
        ("BHMMF001","BNYHFN26213.CMU",
         "HKU 3.8% 20360622",
         "BOND_CORP","University of Hong Kong","HKD",
         30_000_000, 28_500_000, 28_560_000, 0.0450, 7.80, 0.85, 0.0380,
         date(2036,6,22), "AAA", 0.1056),

        # DBANFN25034.CMU：Scentre 4.03% 到期 2035-06-18（A，HKD，CMU）
        ("BHMMF001","DBANFN25034.CMU",
         "SCENTRE 4.03% 20350618",
         "BOND_CORP","Scentre Group","HKD",
         20_000_000, 19_200_000, 19_250_000, 0.0460, 6.90, 0.72, 0.0403,
         date(2035,6,18), "A", 0.0711),

        # 40032.HK：香港電燈 3.3% 到期 2031-01-11（AA-，HKD，聯交所）
        ("BHMMF001","40032.HK",
         "HK Electric 3.3% 20310111",
         "BOND_CORP","CLP Power Hong Kong","HKD",
         15_000_000, 13_800_000, 13_850_000, 0.0455, 3.95, 0.22, 0.0330,
         date(2031,1,11), "AA-", 0.0512),

        # ── BHMMF002 持倉 ────────────────────────────────────
        # 4701.HK：同一隻機管局債，BHMMF002 也持有
        ("BHMMF002","4701.HK",
         "Airport Authority HK 4.25% 20260805",
         "BOND_GOVT","Airport Authority Hong Kong","HKD",
         40_000_000, 39_980_000, 39_984_000, 0.0428, 0.11, 0.001, 0.0425,
         date(2026,8,5), "AAA", 0.2159),

        # DBANFN25028.CMU：RE1 4.205% 到期 2035-05-07（A+，HKD，CMU）
        ("BHMMF002","DBANFN25028.CMU",
         "RE1 4.205% 20350507",
         "BOND_CORP","Link REIT","HKD",
         25_000_000, 24_100_000, 24_150_000, 0.0448, 6.50, 0.62, 0.0421,
         date(2035,5,7), "A+", 0.1303),

        # 40198.HK：IFCDCN 2.67% 到期 2030-04-08（AA，HKD，聯交所）
        ("BHMMF002","40198.HK",
         "IFCDCN 2.67% 20300408",
         "BOND_CORP","IFC Development China","HKD",
         18_000_000, 16_200_000, 16_250_000, 0.0442, 3.20, 0.16, 0.0267,
         date(2030,4,8), "AA", 0.0877),
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
        # value_date 設為較早日期，使持有天數>0，令利差損計算有意義
        # 格式：(port_id, deposit_id, name, bank_id, bank_name, bank_group, ccy,
        #        value_date, maturity_date, principal, interest_rate, penalty, weight)
        ("BHMMF001","DEP_BOCHK_01","中銀香港定存3M", "BOCHK","中國銀行(香港)","中銀集團","HKD",
         TEST_DATE-timedelta(45), TEST_DATE+timedelta(46), 150_000_000,0.0415,True, 0.0554),  # 已持有45天
        ("BHMMF001","DEP_HSBC_01", "匯豐定存6M",    "HSBC", "匯豐銀行",      "匯豐集團","HKD",
         TEST_DATE-timedelta(30), TEST_DATE+timedelta(152),100_000_000,0.0428,True, 0.0370),  # 已持有30天
        ("BHMMF001","DEP_SCB_ON",  "渣打隔夜存款",  "SCB",  "渣打銀行",      "渣打集團","HKD",
         TEST_DATE,               TEST_DATE+timedelta(1),  50_000_000, 0.0410,False,0.0185),  # 隔夜，無罰息
        ("BHMMF002","DEP_BOCHK_02","中銀香港定存6M","BOCHK","中國銀行(香港)","中銀集團","HKD",
         TEST_DATE-timedelta(60), TEST_DATE+timedelta(120),120_000_000,0.0420,True, 0.0648),  # 已持有60天
        ("BHMMF002","DEP_HSBC_02", "匯豐定存3M",   "HSBC", "匯豐銀行",      "匯豐集團","HKD",
         TEST_DATE-timedelta(20), TEST_DATE+timedelta(72), 80_000_000, 0.0425,True, 0.0432),  # 已持有20天
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

    # ── balance_holder_by_channel（網商渠道份額，供 18.sql 使用）────
    channel_data = [
        # port_id   channel_id  channel_name      shares（份）          amount（元）
        ("BHMMF001","000392","螞蟻財富（網商）",  8_500_000_000, 8_500_000_000.0),  # 85億份≈85億元
        ("BHMMF002","000392","螞蟻財富（網商）",  3_200_000_000, 3_200_000_000.0),  # 32億份
        ("BHMMF001","000001","銀行直銷",           500_000_000,   500_000_000.0),
        ("BHMMF002","000001","銀行直銷",           200_000_000,   200_000_000.0),
    ]
    for pid, cid, cname, shares, amount in channel_data:
        cur.execute("""
            INSERT INTO fsi.balance_holder_by_channel
                (confirm_date, port_id, channel_id, channel_name,
                 shares, amount, unit_nav)
            VALUES (%s,%s,%s,%s,%s,%s,1.0)
            ON CONFLICT DO NOTHING
        """, (TEST_DATE, pid, cid, cname, shares, amount))

    # ── balance_portfolio_nav 歷史（T-1/T-2，供 10.sql 申贖計算用）────
    hist_nav = [
        # port_id   ccy   date               net_asset
        ("BHMMF001","HKD", TEST_DATE-timedelta(1), 2_692_000_000),  # T-1 NAV
        ("BHMMF001","HKD", TEST_DATE-timedelta(2), 2_705_000_000),  # T-2 NAV
        ("BHMMF002","HKD", TEST_DATE-timedelta(1), 1_843_000_000),  # T-1 NAV
        ("BHMMF002","HKD", TEST_DATE-timedelta(2), 1_860_000_000),  # T-2 NAV
    ]
    for port_id, ccy, d, nav in hist_nav:
        cur.execute("""
            INSERT INTO fsi.balance_portfolio_nav
                (evaluate_date, port_id, currency, net_asset,
                 shares_outstanding, unit_nav, acc_unit_nav, day_return, loaded_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT DO NOTHING
        """, (d, port_id, ccy, nav, nav/1.0, 1.0, 1.0, 0.000118))

    # ── transact_portfolio_cashflow（T+1申購數據，供 10.sql 明日確認）───
    t1_cashflow = [
        # port_id  currency  date(T+1)           net_purchase(淨申購，正=申購>贖回)
        ("BHMMF001","HKD", TEST_DATE+timedelta(1),  80_000_000),   # 明日確認淨申購+8000萬
        ("BHMMF002","HKD", TEST_DATE+timedelta(1), -50_000_000),   # 明日確認淨贖回-5000萬
    ]
    for port_id, ccy, d, net_pur in t1_cashflow:
        cur.execute("""
            INSERT INTO fsi.transact_portfolio_cashflow
                (evaluate_date, port_id, currency,
                 net_purchase, data_source, loaded_at)
            VALUES (%s,%s,%s,%s,'TEST',NOW())
            ON CONFLICT DO NOTHING
        """, (d, port_id, ccy, net_pur))

    conn.commit()
    print(f"[OK] seed data inserted. evaluate_date={TEST_DATE}  port_ids={PORT_IDS}")


if __name__ == "__main__":
    conn = connect()
    try:
        seed(conn)
    finally:
        conn.close()
