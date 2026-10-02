-- ============================================================
-- 報表06 / 10_sfc_stress.sql  SFC 香港貨幣市場基金壓力測試
-- 對應文檔：lmt-mmf-test-sfc.docx（Indicative Liquidity Profile）
-- 對應 Sheet：SFC壓力測試原始（明细）+ SFC壓力測試（展示）
--
-- ═══ 雙口徑設計（核心）══════════════════════════════════════
-- 口徑 A：流動性分層（SFC 文檔 §1(i) — 非累計，資產端 sum to 100%）
--   每筆持倉的全額市值歸入「完全變現所需天數」對應的 5 檔桶：
--     1D / 2-7D / 8-30D / 31-90D / GT90D
--   完全變現天數估算：
--     · 現金 → 0 天（1D 桶）
--     · 隔夜存款 / 逆回購到期 / 1 日內到期債券 → 1 天（1D 桶）
--     · 存款 Normal → 0 天（僅無罰息可早破；有罰息按合約到期，SFC §2(a)）
--       存款 Stressed → 合約剩餘天數（零早破，SFC §1(iv)）
--     · 債券/CD 二級市場 → 持倉市值 / 日可變現規模(tradable_size)，向上取整
--       若到期在 5 日內優先到期變現；若 tradable_size=0 → GT90D（不可變現）
--
-- 口徑 B：DLA / WLA（SFC UT Code §8.2(n) — ADTV 約束下的可覆蓋額）
--   realizable_amount    = 1 交易日內可變現額 = MIN(市值, tradable_size) + 現金 + 隔夜 + 1 日到期
--   realizable_5d_amount = 5 交易日內可變現額 = MIN(市值, tradable_size × 5) + 5 日內到期 + 可早破存款
--   DLA% = Σ realizable_amount / NAV × 100，須 ≥ 7.5%
--   WLA% = Σ realizable_5d_amount / NAV × 100，須 ≥ 15%
--   Stressed：存款零早破（不計入 5 日可變現）、ADTV 50% haircut
--
-- ═══ 利率變化（+50bp 久期近似法，沿用 42_stress_result.sql）═══
--   stressed_mv   = market_value × (1 - duration × 0.005)（存款/現金/逆回購不變）
--   stressed_loss = market_value - stressed_mv
--   變現係數 liq_ratio（向後兼容靜態口徑，DEPOSIT=0/FLOAT=0.05/GOVT=0.2/CD=0.2/CORP=0.8）
--   stressed_loss_adj = stressed_loss × liq_ratio
--
-- 參數：params.evaluate_date DATE, params.port_ids TEXT[], params.rate_shock_bps NUMERIC(默認 50)
-- 執行：臨時表緩存計算結果 → DELETE 舊數據 → INSERT 明細 → INSERT 匯總 → 返回明細
--       （分語句執行，避免 data-modifying CTE 快照順序問題）
-- ============================================================

DROP TABLE IF EXISTS tmp_sfc_priced;

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids,
        50::NUMERIC                              AS rate_shock_bps
),
nav AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n, params
    WHERE n.evaluate_date = params.evaluate_date AND n.class_id IS NULL
),

-- ── 統一持倉視圖（債券/CD/存款/逆回購/現金）─────────────
holdings AS (
    SELECT
        b.port_id,
        b.security_code,
        b.security_name,
        CASE WHEN COALESCE(b.coupon_type,'FIXED') = 'FLOAT' THEN 'BOND_FLOAT'
             ELSE b.asset_subtype::TEXT END            AS asset_category,
        COALESCE(b.market_value, 0)                     AS market_value,
        ROUND(
            CASE WHEN COALESCE(b.coupon_type,'FIXED') = 'FLOAT'
                THEN (b.maturity_date - params.evaluate_date)::NUMERIC / 365.0 * 0.5
                   + 0.5 * COALESCE(
                         (b.next_coupon_date - params.evaluate_date)::NUMERIC / 365.0,
                         (b.maturity_date - params.evaluate_date)::NUMERIC / 365.0)
                ELSE COALESCE(b.duration, b.remaining_days / 365.0, 0.0)
            END
        , 4)                                            AS duration,
        b.remaining_days,
        b.maturity_date,
        FALSE                                           AS is_overnight
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids)
      AND b.evaluate_date = params.evaluate_date
      AND b.quantity > 0

    UNION ALL

    SELECT
        c.port_id, c.security_code, c.security_name,
        'CD'::TEXT, COALESCE(c.market_value, 0),
        ROUND(COALESCE(c.duration, c.remaining_days / 365.0, 0.0), 4),
        c.remaining_days, c.maturity_date, FALSE
    FROM fsi.balance_cd c, params
    WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date

    UNION ALL

    SELECT
        d.port_id, d.deposit_id AS security_code, d.deposit_name AS security_name,
        'DEPOSIT'::TEXT, COALESCE(d.principal, 0), 0::NUMERIC,
        d.remaining_days, d.maturity_date, d.is_overnight
    FROM fsi.balance_deposit d, params
    WHERE d.port_id = ANY(params.port_ids) AND d.evaluate_date = params.evaluate_date
      AND (d.maturity_date > params.evaluate_date OR d.maturity_date IS NULL OR d.is_overnight = TRUE)

    UNION ALL

    SELECT
        r.port_id, r.repo_id AS security_code,
        ('逆回購:' || COALESCE(r.counterparty_name,''))::VARCHAR AS security_name,
        'REV_REPO'::TEXT, COALESCE(r.principal, 0), 0::NUMERIC,
        r.remaining_days, COALESCE(r.actual_maturity_date, r.maturity_date),
        (r.remaining_days = 1)
    FROM fsi.balance_repo r, params
    WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date AND r.repo_type = 'REV_REPO'

    UNION ALL

    SELECT
        ca.port_id, 'CASH' || ca.cash_account_id AS security_code, ca.account_name AS security_name,
        'CASH'::TEXT, COALESCE(ca.amount, 0), 0::NUMERIC,
        0, params.evaluate_date, TRUE
    FROM fsi.balance_cash ca, params
    WHERE ca.port_id = ANY(params.port_ids) AND ca.evaluate_date = params.evaluate_date
),

-- ── 兩場景 + 配置 + ADTV + NAV ────────────────────────────
scenario_holdings AS (
    SELECT
        h.*,
        s.scenario,
        sdef.market_participation_pct,
        sdef.adtv_haircut_pct,
        sdef.early_break_pct,
        sdef.bid_ask_cost_bps,
        sdef.liq_ratio_static,
        n.net_asset,
        COALESCE(a.adtv_30d, 0)                          AS adtv_30d,
        COALESCE(a.data_source, 'NONE')                  AS adtv_source
    FROM holdings h
    CROSS JOIN (VALUES ('NORMAL'), ('STRESSED')) AS s(scenario)
    JOIN fsi.sfc_liquidity_bucket_def sdef
      ON sdef.asset_category = h.asset_category AND sdef.scenario = s.scenario
    LEFT JOIN nav n ON n.port_id = h.port_id
    LEFT JOIN fsi.mktdata_adtv a
      ON a.security_code = h.security_code AND a.adtv_date = (SELECT evaluate_date FROM params)
)

-- ── 計算結果緩存到臨時表（tradable_size / stressed_mv / 桶 / DLA/WLA）──
SELECT
    (SELECT evaluate_date FROM params)                  AS evaluate_date,
    sh.*,
    (SELECT rate_shock_bps FROM params)                  AS rate_shock_bps,
    ROUND(
        CASE WHEN sh.asset_category IN ('DEPOSIT','CASH','REV_REPO')
             THEN sh.market_value
             ELSE sh.market_value * (1.0 - sh.duration * (SELECT rate_shock_bps FROM params) / 10000.0)
        END
    , 2)                                                AS stressed_mv,
    ROUND(sh.adtv_30d * sh.market_participation_pct * (1.0 - sh.adtv_haircut_pct), 2) AS tradable_size,
    -- 完全變現所需天數（決定分層桶）
    CASE
        WHEN sh.asset_category = 'CASH' THEN 0
        WHEN sh.asset_category = 'REV_REPO' THEN GREATEST(COALESCE(sh.remaining_days,1),1)
        WHEN sh.asset_category = 'DEPOSIT' THEN
            CASE WHEN sh.scenario = 'NORMAL'
                      AND sh.early_break_pct > 0            -- 配置允許早破
                      AND sh.early_break_pct >= 1            -- 全額早破
                     THEN 0                                   -- 可無損早破 → T+0
                 -- 有罰息定存（is_penalty_on_early_redeem）在 Normal 亦按合約到期（SFC §2(a)）
                 ELSE GREATEST(COALESCE(sh.remaining_days,1),1)
            END
        WHEN sh.asset_category IN ('BOND_GOVT','BOND_CORP','BOND_FLOAT','CD') THEN
            CASE
                WHEN COALESCE(sh.remaining_days,99999) <= 5 THEN COALESCE(sh.remaining_days,1)
                WHEN sh.adtv_30d * sh.market_participation_pct * (1.0 - sh.adtv_haircut_pct) > 0
                    THEN CEIL(sh.market_value /
                         NULLIF(sh.adtv_30d * sh.market_participation_pct * (1.0 - sh.adtv_haircut_pct), 0))::INTEGER
                ELSE 99999
            END
        ELSE 99999
    END                                                 AS liquidation_days,
    -- 口徑 B（DLA）：1 交易日內可變現額
    CASE
        WHEN sh.asset_category IN ('CASH','REV_REPO') THEN sh.market_value
        WHEN sh.asset_category = 'DEPOSIT' THEN
            CASE WHEN sh.scenario = 'NORMAL' AND sh.early_break_pct > 0 THEN sh.market_value
                 WHEN sh.is_overnight OR COALESCE(sh.remaining_days,99999) <= 1 THEN sh.market_value
                 ELSE 0 END
        ELSE
            LEAST(sh.market_value,
                  sh.adtv_30d * sh.market_participation_pct * (1.0 - sh.adtv_haircut_pct))
            + CASE WHEN COALESCE(sh.remaining_days,99999) <= 1 THEN sh.market_value ELSE 0 END
    END                                                 AS realizable_amount,
    -- 口徑 B（WLA）：5 交易日內可變現額
    CASE
        WHEN sh.asset_category IN ('CASH','REV_REPO') THEN sh.market_value
        WHEN sh.asset_category = 'DEPOSIT' THEN
            CASE WHEN sh.scenario = 'NORMAL' AND sh.early_break_pct > 0 THEN sh.market_value
                 WHEN sh.is_overnight OR COALESCE(sh.remaining_days,99999) <= 5 THEN sh.market_value
                 ELSE 0 END
        ELSE
            LEAST(sh.market_value,
                  sh.adtv_30d * sh.market_participation_pct * (1.0 - sh.adtv_haircut_pct) * 5)
            + CASE WHEN COALESCE(sh.remaining_days,99999) <= 5 THEN sh.market_value ELSE 0 END
    END                                                 AS realizable_5d_amount
INTO TEMP TABLE tmp_sfc_priced
FROM scenario_holdings sh;

-- ── 寫入明細結果表（先刪後插，冪等）──────────────────────
DELETE FROM fsi.sfc_liquidity_stress sl
USING (SELECT DISTINCT '2026-06-25'::DATE AS d, unnest(ARRAY['BHMMF001','BHMMF002']::TEXT[]) AS pid) prm
WHERE sl.evaluate_date = prm.d AND sl.port_id = prm.pid;

INSERT INTO fsi.sfc_liquidity_stress (
    evaluate_date, port_id, security_code, security_name, asset_category, scenario,
    market_value, duration, rate_shock_bps, stressed_mv, stressed_loss,
    adtv_30d, tradable_size, realizable_amount, realizable_5d_amount,
    liquidation_bucket, liquidation_days, realizable_pct_nav, realizable_5d_pct_nav,
    bucket_pct_nav, bid_ask_cost, net_realizable, net_asset, data_source
)
SELECT
    t.evaluate_date,
    t.port_id,
    t.security_code,
    t.security_name,
    t.asset_category,
    t.scenario,
    t.market_value,
    t.duration,
    t.rate_shock_bps,
    t.stressed_mv,
    ROUND(t.market_value - t.stressed_mv, 2)             AS stressed_loss,
    t.adtv_30d,
    t.tradable_size,
    ROUND(t.realizable_amount, 2),
    ROUND(t.realizable_5d_amount, 2),
    CASE
        WHEN t.liquidation_days <= 1   THEN '1D'
        WHEN t.liquidation_days <= 7   THEN '2-7D'
        WHEN t.liquidation_days <= 30  THEN '8-30D'
        WHEN t.liquidation_days <= 90  THEN '31-90D'
        ELSE 'GT90D'
    END                                                  AS liquidation_bucket,
    t.liquidation_days,
    ROUND(t.realizable_amount / NULLIF(t.net_asset,0) * 100, 6),
    ROUND(t.realizable_5d_amount / NULLIF(t.net_asset,0) * 100, 6),
    ROUND(t.market_value / NULLIF(t.net_asset,0) * 100, 6),
    -- 買賣價差成本 = 1 日可變現額 × bid_ask_cost_bps / 10000（CASH/DEPOSIT/REV_REPO 免成本）
    ROUND(CASE WHEN t.asset_category IN ('CASH','DEPOSIT','REV_REPO') THEN 0
               ELSE t.realizable_amount * t.bid_ask_cost_bps / 10000.0 END, 2) AS bid_ask_cost,
    ROUND(t.realizable_amount - CASE WHEN t.asset_category IN ('CASH','DEPOSIT','REV_REPO') THEN 0
               ELSE t.realizable_amount * t.bid_ask_cost_bps / 10000.0 END, 2) AS net_realizable,
    t.net_asset,
    'CALC'
FROM tmp_sfc_priced t;

-- ── 寫入合規匯總表（先刪後插，冪等）──────────────────────
DELETE FROM fsi.sfc_liquidity_compliance sc
USING (SELECT DISTINCT '2026-06-25'::DATE AS d, unnest(ARRAY['BHMMF001','BHMMF002']::TEXT[]) AS pid) prm
WHERE sc.evaluate_date = prm.d AND sc.port_id = prm.pid;

INSERT INTO fsi.sfc_liquidity_compliance (
    evaluate_date, port_id, scenario, dla_amount, wla_amount, nav,
    dla_pct, wla_pct, dla_status, wla_status,
    bucket_1d_pct, bucket_2_7d_pct, bucket_8_30d_pct, bucket_31_90d_pct, bucket_gt90d_pct,
    total_pct, coverage_pct
)
WITH agg AS (
    SELECT
        t.port_id, t.scenario, t.net_asset,
        SUM(ROUND(t.realizable_amount, 2))    AS dla_amount,
        SUM(ROUND(t.realizable_5d_amount, 2)) AS wla_amount,
        SUM(CASE WHEN t.liquidation_days <= 1   THEN t.market_value ELSE 0 END) AS b1d,
        SUM(CASE WHEN t.liquidation_days > 1 AND t.liquidation_days <= 7    THEN t.market_value ELSE 0 END) AS b2_7d,
        SUM(CASE WHEN t.liquidation_days > 7 AND t.liquidation_days <= 30   THEN t.market_value ELSE 0 END) AS b8_30d,
        SUM(CASE WHEN t.liquidation_days > 30 AND t.liquidation_days <= 90  THEN t.market_value ELSE 0 END) AS b31_90d,
        SUM(CASE WHEN t.liquidation_days > 90 THEN t.market_value ELSE 0 END) AS b_gt90d,
        SUM(t.market_value) AS total
    FROM tmp_sfc_priced t
    GROUP BY t.port_id, t.scenario, t.net_asset
)
SELECT
    '2026-06-25'::DATE,
    a.port_id,
    a.scenario,
    a.dla_amount,
    a.wla_amount,
    a.net_asset,
    ROUND(a.dla_amount / NULLIF(a.net_asset,0) * 100, 6),
    ROUND(a.wla_amount / NULLIF(a.net_asset,0) * 100, 6),
    CASE WHEN a.dla_amount / NULLIF(a.net_asset,0) * 100 >= 7.5 THEN '合規' ELSE '未達標(≥7.5%)' END,
    CASE WHEN a.wla_amount / NULLIF(a.net_asset,0) * 100 >= 15  THEN '合規' ELSE '未達標(≥15%)' END,
    ROUND(a.b1d     / NULLIF(a.net_asset,0) * 100, 6),
    ROUND(a.b2_7d   / NULLIF(a.net_asset,0) * 100, 6),
    ROUND(a.b8_30d  / NULLIF(a.net_asset,0) * 100, 6),
    ROUND(a.b31_90d / NULLIF(a.net_asset,0) * 100, 6),
    ROUND(a.b_gt90d / NULLIF(a.net_asset,0) * 100, 6),
    ROUND(a.total   / NULLIF(a.net_asset,0) * 100, 6),
    ROUND(a.total   / NULLIF(a.net_asset,0) * 100, 6)
FROM agg a;

-- ── 返回明細（供 Excel sheet 渲染）──────────────────────
SELECT
    pp.port_name,
    t.port_id,
    t.security_code,
    t.security_name,
    t.asset_category,
    t.scenario,
    t.market_value,
    t.duration,
    t.rate_shock_bps,
    t.stressed_mv,
    ROUND(t.market_value - t.stressed_mv, 2)              AS stressed_loss,
    t.adtv_30d,
    t.market_participation_pct,
    t.adtv_haircut_pct,
    t.tradable_size,
    ROUND(t.realizable_amount, 2)                         AS realizable_amount,
    ROUND(t.realizable_5d_amount, 2)                      AS realizable_5d_amount,
    CASE
        WHEN t.liquidation_days <= 1   THEN '1D'
        WHEN t.liquidation_days <= 7   THEN '2-7D'
        WHEN t.liquidation_days <= 30  THEN '8-30D'
        WHEN t.liquidation_days <= 90  THEN '31-90D'
        ELSE 'GT90D'
    END                                                   AS liquidation_bucket,
    t.liquidation_days,
    ROUND(t.realizable_amount / NULLIF(t.net_asset,0) * 100, 6) AS realizable_pct_nav,
    ROUND(t.realizable_5d_amount / NULLIF(t.net_asset,0) * 100, 6) AS realizable_5d_pct_nav,
    ROUND(t.market_value / NULLIF(t.net_asset,0) * 100, 6) AS bucket_pct_nav,
    ROUND(CASE WHEN t.asset_category IN ('CASH','DEPOSIT','REV_REPO') THEN 0
               ELSE t.realizable_amount * t.bid_ask_cost_bps / 10000.0 END, 2) AS bid_ask_cost,
    ROUND(t.realizable_amount - CASE WHEN t.asset_category IN ('CASH','DEPOSIT','REV_REPO') THEN 0
               ELSE t.realizable_amount * t.bid_ask_cost_bps / 10000.0 END, 2) AS net_realizable,
    t.liq_ratio_static                                    AS liq_ratio,
    ROUND((t.market_value - t.stressed_mv) * t.liq_ratio_static, 2) AS stressed_loss_adj,
    t.net_asset,
    t.adtv_source
FROM tmp_sfc_priced t
JOIN fsi.para_portfolio pp ON pp.port_id = t.port_id
ORDER BY pp.port_name, t.scenario,
         CASE
             WHEN t.liquidation_days <= 1   THEN 1
             WHEN t.liquidation_days <= 7   THEN 2
             WHEN t.liquidation_days <= 30  THEN 3
             WHEN t.liquidation_days <= 90  THEN 4
             ELSE 5
         END,
         t.asset_category, t.realizable_amount DESC;
