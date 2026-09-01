-- position_exposure_summary.sql
-- 持倉暴露與合規彙總查詢 (Processing API 專用)
-- 包含：1. 資產類別暴露 2. 發行人/集團集中度 (SFC 7.1) 3. 貨幣市場基金 WAM/WAL (SFC 8.2)

WITH base_positions AS (
    -- 1. 基礎持倉數據與動態 NAV 分母計算
    SELECT
        fund_id,
        as_of_date,
        security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        COALESCE(asset_type, 'OTHER') AS asset_type,
        COALESCE(issuer_name, 'UNKNOWN_ISSUER') AS issuer_name,
        COALESCE(issuer_group, issuer_name, 'UNKNOWN_GROUP') AS issuer_group,
        credit_rating,
        maturity_date,
        next_reset_date,
        market_value_hkd,
        -- 動態計算組合持倉總市值 (Gross Portfolio Market Value)
        SUM(market_value_hkd) OVER (PARTITION BY fund_id, as_of_date) AS total_portfolio_mv
    FROM fsi.positions
    WHERE fund_id = :fund_id
      AND as_of_date = CAST(:as_of_date AS DATE)
),

-- ====================================================================
-- 模塊 1: 按資產類型彙總 (Asset Type Breakdown)
-- ====================================================================
asset_type_exposure AS (
    SELECT
        fund_id,
        as_of_date,
        asset_type,
        COUNT(*) AS position_count,
        SUM(market_value_hkd) AS total_mv_hkd,
        ROUND(
            (SUM(market_value_hkd) / NULLIF(MAX(total_portfolio_mv), 0.0)) * 100.0, 
            4
        ) AS weight_pct
    FROM base_positions
    GROUP BY fund_id, as_of_date, asset_type
),

-- ====================================================================
-- 模塊 2: 發行人及集團集中度 (Issuer & Group Concentration - SFC Code 7.1)
-- ====================================================================
issuer_concentration AS (
    SELECT
        fund_id,
        as_of_date,
        issuer_group,
        -- 穿透列出該集團下包含的發行人與證券數量
        COUNT(DISTINCT issuer_name) AS issuer_count,
        COUNT(*) AS instrument_count,
        SUM(market_value_hkd) AS total_mv_hkd,
        ROUND(
            (SUM(market_value_hkd) / NULLIF(MAX(total_portfolio_mv), 0.0)) * 100.0, 
            4
        ) AS weight_pct,
        MAX(credit_rating) AS best_credit_rating,
        
        -- SFC 7.1 合規檢查：單一實體/集團通常不得超過 NAV 的 10%
        CASE 
            WHEN (SUM(market_value_hkd) / NULLIF(MAX(total_portfolio_mv), 0.0)) * 100.0 > 10.0 THEN 'BREACH'
            WHEN (SUM(market_value_hkd) / NULLIF(MAX(total_portfolio_mv), 0.0)) * 100.0 > 8.0  THEN 'WARNING'
            ELSE 'OK' 
        END AS sfc_concentration_status
    FROM base_positions
    GROUP BY fund_id, as_of_date, issuer_group
),

-- ====================================================================
-- 模塊 3: WAM / WAL 計算 (Money Market Fund Metrics - SFC 8.2)
-- ====================================================================
wam_wal_metrics AS (
    SELECT
        fund_id,
        as_of_date,
        
        -- WAM (加權平均到期日): 考慮利率重置日 (Reset Date) 或 最終到期日，上限上限 397 天
        ROUND(
            SUM(
                (market_value_hkd / NULLIF(total_portfolio_mv, 0.0)) * 
                LEAST(
                    GREATEST(COALESCE(next_reset_date, maturity_date) - as_of_date, 0), 
                    397
                )
            ), 
            2
        ) AS wam_days,
        
        -- WAL (加權平均加術壽命): 僅考慮最終到期日 (Maturity Date)
        ROUND(
            SUM(
                (market_value_hkd / NULLIF(total_portfolio_mv, 0.0)) * 
                GREATEST(maturity_date - as_of_date, 0)
            ), 
            2
        ) AS wal_days
    FROM base_positions
    WHERE maturity_date IS NOT NULL
      AND asset_type IN ('FIXED_INCOME', 'MONEY_MARKET', 'CASH_EQUIVALENT')
    GROUP BY fund_id, as_of_date
)

-- ====================================================================
-- Processing API 輸出層 (可根據 API Request 選擇切換或聯合輸出)
-- 以下預設輸出：發行人集中度與合規狀態 (API 常用主表)
-- ====================================================================
SELECT
    c.fund_id,
    c.as_of_date,
    c.issuer_group,
    c.issuer_count,
    c.instrument_count,
    c.total_mv_hkd,
    c.weight_pct,
    c.best_credit_rating,
    c.sfc_concentration_status,
    
    -- 附帶組合整體 WAM / WAL 指標 (SFC 8.2: WAM <= 60天, WAL <= 120天)
    w.wam_days,
    CASE WHEN w.wam_days > 60 THEN 'BREACH' ELSE 'OK' END AS wam_status,
    w.wal_days,
    CASE WHEN w.wal_days > 120 THEN 'BREACH' ELSE 'OK' END AS wal_status

FROM issuer_concentration c
LEFT JOIN wam_wal_metrics w ON c.fund_id = w.fund_id AND c.as_of_date = w.as_of_date
ORDER BY c.weight_pct DESC;