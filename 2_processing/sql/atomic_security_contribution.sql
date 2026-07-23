-- atomic_security_contribution.sql
-- 個股/個券每日收益累計與區間貢獻分析 (Atomic Security Contribution with Carino Linking)
-- 採用 Carino 多期連鎖調整法，將每日 (w_i * r_i) 歸因幾何累加，確保區間單券貢獻度相加嚴格等於組合總超額/總收益。

WITH daily_pos AS (
    SELECT
        as_of_date,
        fund_id,
        COALESCE(security_code, instrument_id, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        COALESCE(market_value_hkd, 0.0) AS mv_i,
        COALESCE(pnl_hkd, 0.0) AS pnl_i
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date BETWEEN :start_date AND :end_date
),
daily_portfolio AS (
    SELECT
        as_of_date,
        fund_id,
        SUM(mv_i) AS total_mv,
        SUM(pnl_i) AS total_pnl
    FROM daily_pos
    GROUP BY as_of_date, fund_id
),
daily_security_contrib AS (
    SELECT
        p.as_of_date,
        p.fund_id,
        p.security_code,
        p.security_name,
        p.mv_i,
        p.pnl_i,
        f.total_mv,
        -- 日權重 w_{i,t}
        CASE WHEN f.total_mv > 0 THEN p.mv_i / f.total_mv ELSE 0.0 END AS w_i,
        -- 日收益率 r_{i,t}
        CASE WHEN p.mv_i > 0 THEN p.pnl_i / p.mv_i ELSE 0.0 END AS r_i,
        -- 日貢獻度 c_{i,t} = w_{i,t} * r_{i,t} = pnl_{i,t} / total_mv_{t}
        CASE WHEN f.total_mv > 0 THEN p.pnl_i / f.total_mv ELSE 0.0 END AS c_i,
        -- 日組合總收益率 R_{P,t}
        CASE WHEN f.total_mv > 0 THEN f.total_pnl / f.total_mv ELSE 0.0 END AS r_p
    FROM daily_pos p
    JOIN daily_portfolio f ON p.as_of_date = f.as_of_date AND p.fund_id = f.fund_id
),
portfolio_summary AS (
    SELECT
        fund_id,
        -- 區間累積組合收益率 R_P = \prod (1 + R_{P,t}) - 1
        EXP(SUM(LN(1.0 + r_p))) - 1.0 AS cumulative_r_p
    FROM (
        SELECT DISTINCT as_of_date, fund_id, r_p FROM daily_security_contrib
    ) t
    GROUP BY fund_id
),
carino_factors AS (
    SELECT
        c.as_of_date,
        c.fund_id,
        c.r_p,
        s.cumulative_r_p,
        -- Carino 多期連鎖因子 k_t 計算
        CASE 
            WHEN c.r_p = 0.0 OR s.cumulative_r_p = 0.0 THEN 1.0
            ELSE (LN(1.0 + c.r_p) / c.r_p) / (LN(1.0 + s.cumulative_r_p) / s.cumulative_r_p)
        END AS k_t
    FROM (
        SELECT DISTINCT as_of_date, fund_id, r_p FROM daily_security_contrib
    ) c
    JOIN portfolio_summary s ON c.fund_id = s.fund_id
)
SELECT
    d.fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    d.security_code,
    d.security_name,
    
    -- 區間平均持倉權重 (%)
    ROUND(AVG(d.w_i) * 100.0, 6) AS avg_weight_pct,
    
    -- 未經連鎖調整的每日 (w * r) 簡單算術累加 (%)
    ROUND(SUM(d.c_i) * 100.0, 6) AS simple_sum_contrib_pct,
    
    -- 經 Carino 多期幾何連鎖調整後的真實區間收益貢獻度 (%)
    ROUND(SUM(d.c_i * k.k_t) * 100.0, 6) AS cumulative_contrib_pct
FROM daily_security_contrib d
JOIN carino_factors k ON d.as_of_date = k.as_of_date AND d.fund_id = k.fund_id
GROUP BY d.fund_id, d.security_code, d.security_name
ORDER BY cumulative_contrib_pct DESC NULLS LAST;