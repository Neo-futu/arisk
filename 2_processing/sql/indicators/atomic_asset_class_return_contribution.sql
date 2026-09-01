-- atomic_asset_class_return_contribution.sql
-- 多期資產類別收益貢獻分析（基於 Carino 模型的多期鏈式連結法）
-- 維度： 基金，大類資產匯總層面，item 是單券層面的

WITH portfolio_daily AS (
    -- 取得組合每日的淨值與日收益率
    SELECT
        evaluate_date AS as_of_date,
        port_id AS fund_id,
        COALESCE(net_asset, total_asset, 0.0) AS nav,
        COALESCE(day_return, 0.0) AS r_p
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
asset_daily_pnl AS (
    -- 取得每日各資產類別（L1）的損益（使用 net_pnl）
    SELECT
        evaluate_date AS as_of_date,
        port_id AS fund_id,
        COALESCE(asset_class_l1::text, 'UNCLASSIFIED') AS asset_class,
        SUM(COALESCE(net_pnl, 0.0)) AS asset_pnl
    FROM fsi.transact_portfolio_pnl
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
    GROUP BY evaluate_date, port_id, COALESCE(asset_class_l1::text, 'UNCLASSIFIED')
),
daily_contribution AS (
    -- 計算每日各資產類別對組合的單期貢獻率 = 當日資產盈虧 / 當日初始淨值
    SELECT
        p.as_of_date,
        p.fund_id,
        p.asset_class,
        CASE WHEN b.nav > 0 THEN p.asset_pnl / b.nav ELSE 0.0 END AS c_t
    FROM asset_daily_pnl p
    JOIN portfolio_daily b
      ON p.as_of_date = b.as_of_date
     AND p.fund_id = b.fund_id
),
period_totals AS (
    -- 計算整段區間的總累積組合收益率 R_total
    SELECT
        fund_id,
        EXP(SUM(LN(1.0 + r_p))) - 1.0 AS r_total
    FROM portfolio_daily
    GROUP BY fund_id
),
carino_factor_calc AS (
    -- Carino 多期對數平滑調整係數 (Carino Multi-period Adjustment Factor)
    SELECT
        pt.fund_id,
        pt.r_total,
        CASE 
            WHEN pt.r_total = 0 THEN 1.0
            ELSE LN(1.0 + pt.r_total) / pt.r_total
        END AS k_factor
    FROM period_totals pt
),
summed_raw_contrib AS (
    -- 加總各資產類別在區間內的每日原始貢獻
    SELECT
        fund_id,
        asset_class,
        SUM(c_t) AS raw_sum_c
    FROM daily_contribution
    GROUP BY fund_id, asset_class
)
SELECT
    s.fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    s.asset_class,
    -- Carino 調整後的區間資產類別收益貢獻 (%)
    ROUND((s.raw_sum_c * c.k_factor) * 100.0, 6) AS return_contribution_pct
FROM summed_raw_contrib s
JOIN carino_factor_calc c
  ON s.fund_id = c.fund_id
ORDER BY return_contribution_pct DESC NULLS LAST;

