-- atomic_security_contribution.sql
-- 個股/個券每日收益累計與區間貢獻分析 (Atomic Security Contribution with Carino Linking)
-- 說明：
-- 1. 淨值來源：fsi.balance_portfolio_nav (port_id, evaluate_date, net_asset)
-- 2. 持倉來源：fsi.balance_stock, fsi.balance_bond, fsi.balance_fund, fsi.balance_repo 等
-- 3. 採用 Carino 多期連鎖調整法，確保各單券在區間內的 cumulative_contrib_pct 嚴格相加等於組合區間總收益率 R_P。

WITH daily_nav AS (
    -- 1. 取得每日組合淨資產 (NAV)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS nav_t
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
daily_pos_union AS (
    -- 2. 彙整多資產持倉與每日 PnL
    -- 股票持倉
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(security_code, wind_code, ticker, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        COALESCE(market_value, 0.0) AS mv_i,
        COALESCE(holding_pnl, daily_pnl, pnl, 0.0) AS pnl_i
    FROM fsi.balance_stock
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date

    UNION ALL

    -- 債券持倉
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(security_code, wind_code, bond_code, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        COALESCE(market_value, 0.0) AS mv_i,
        COALESCE(holding_pnl, daily_pnl, pnl, 0.0) AS pnl_i
    FROM fsi.balance_bond
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date

    UNION ALL

    -- 基金持倉
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(security_code, fund_code, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        COALESCE(market_value, 0.0) AS mv_i,
        COALESCE(holding_pnl, daily_pnl, pnl, 0.0) AS pnl_i
    FROM fsi.balance_fund
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date

    UNION ALL

    -- 逆回購 / 其他貨幣持倉
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(security_code, repo_code, 'REVERSE_REPO') AS security_code,
        COALESCE(security_name, 'Reverse Repo') AS security_name,
        COALESCE(market_value, amount, 0.0) AS mv_i,
        COALESCE(holding_pnl, daily_pnl, interest_income, 0.0) AS pnl_i
    FROM fsi.balance_repo
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
daily_portfolio_pnl AS (
    -- 3. 算當日組合總持倉 PnL 與總收益率 R_{P,t}
    SELECT
        p.fund_id,
        p.as_of_date,
        n.nav_t,
        SUM(p.pnl_i) AS total_pnl_t,
        -- 當日組合收益率 R_{P,t} = Total PnL_t / NAV_t
        CASE 
            WHEN n.nav_t > 0.0 THEN SUM(p.pnl_i) / n.nav_t 
            ELSE 0.0 
        END AS r_p
    FROM daily_pos_union p
    JOIN daily_nav n 
      ON p.fund_id = n.fund_id 
     AND p.as_of_date = n.as_of_date
    GROUP BY p.fund_id, p.as_of_date, n.nav_t
),
daily_security_contrib AS (
    -- 4. 計算個券當日權重 w_{i,t} 與當日收益貢獻度 c_{i,t}
    SELECT
        p.fund_id,
        p.as_of_date,
        p.security_code,
        p.security_name,
        p.mv_i,
        p.pnl_i,
        dp.nav_t,
        dp.r_p,
        -- 當日持倉權重 w_{i,t} = MV_{i,t} / NAV_t
        CASE WHEN dp.nav_t > 0.0 THEN p.mv_i / dp.nav_t ELSE 0.0 END AS w_i,
        -- 當日貢獻度 c_{i,t} = PnL_{i,t} / NAV_t
        CASE WHEN dp.nav_t > 0.0 THEN p.pnl_i / dp.nav_t ELSE 0.0 END AS c_i
    FROM daily_pos_union p
    JOIN daily_portfolio_pnl dp 
      ON p.fund_id = dp.fund_id 
     AND p.as_of_date = dp.as_of_date
),
portfolio_summary AS (
    -- 5. 計算區間累積組合總收益率 R_P = \prod (1 + R_{P,t}) - 1
    SELECT
        fund_id,
        EXP(SUM(LN(1.0 + r_p))) - 1.0 AS cumulative_r_p
    FROM (
        SELECT DISTINCT fund_id, as_of_date, r_p 
        FROM daily_portfolio_pnl
    ) t
    GROUP BY fund_id
),
carino_factors AS (
    -- 6. 計算 Carino 多期連鎖因子 k_t
    SELECT
        dp.fund_id,
        dp.as_of_date,
        dp.r_p,
        ps.cumulative_r_p,
        -- Carino 因子 k_t 計算：
        -- k_t = [LN(1 + R_{P,t}) / R_{P,t}] / [LN(1 + R_P) / R_P]
        -- 當 R_{P,t} -> 0 或 R_P -> 0 時，極限值趨近於 1.0
        CASE 
            WHEN ABS(dp.r_p) < 1e-12 AND ABS(ps.cumulative_r_p) < 1e-12 THEN 1.0
            WHEN ABS(dp.r_p) < 1e-12 THEN 1.0 / (LN(1.0 + ps.cumulative_r_p) / NULLIF(ps.cumulative_r_p, 0.0))
            WHEN ABS(ps.cumulative_r_p) < 1e-12 THEN (LN(1.0 + dp.r_p) / dp.r_p) / 1.0
            ELSE (LN(1.0 + dp.r_p) / dp.r_p) / (LN(1.0 + ps.cumulative_r_p) / ps.cumulative_r_p)
        END AS k_t
    FROM daily_portfolio_pnl dp
    JOIN portfolio_summary ps ON dp.fund_id = ps.fund_id
)
SELECT
    d.fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    d.security_code,
    d.security_name,
    
    -- 區間平均持倉權重 (%)
    ROUND(AVG(d.w_i) * 100.0, 6) AS avg_weight_pct,
    
    -- 未經連鎖調整的每日簡單算術累加貢獻度 (%)
    ROUND(SUM(d.c_i) * 100.0, 6) AS simple_sum_contrib_pct,
    
    -- 經 Carino 多期幾何連鎖調整後的真實區間收益貢獻度 (%)
    ROUND(SUM(d.c_i * k.k_t) * 100.0, 6) AS cumulative_contrib_pct

FROM daily_security_contrib d
JOIN carino_factors k 
  ON d.fund_id = k.fund_id 
 AND d.as_of_date = k.as_of_date
GROUP BY d.fund_id, d.security_code, d.security_name
ORDER BY cumulative_contrib_pct DESC NULLS LAST;