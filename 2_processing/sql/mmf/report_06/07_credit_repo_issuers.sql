-- ============================================================
-- 報表06 / 07_credit_repo_issuers.sql
-- 原始：SmartReport/06/07.sql  信用債及質押債發行人/交易對手
-- 功能：信用債發行人 + 回購融出交易對手（需關注的機構清單）
-- 對應 Sheet：信用债及质押债原始
-- 參數：params.port_ids TEXT[], params.evaluate_date DATE
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
-- ============================================================

SELECT
    p.port_name,
    issuer_name,
    holding_type
FROM (
    -- 信用債發行人
    SELECT DISTINCT
        b.port_id,
        COALESCE(b.issuer_name, b.issuer_id) AS issuer_name,
        '信用債' AS holding_type
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids)
      AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype != 'BOND_GOVT'

    UNION ALL

    -- 逆回購（融出）交易對手（對手方未還資金，信用敞口）
    SELECT DISTINCT
        r.port_id,
        COALESCE(r.counterparty_name, r.counterparty_id) AS issuer_name,
        '回購融出對手' AS holding_type
    FROM fsi.balance_repo r, params
    WHERE r.port_id = ANY(params.port_ids)
      AND r.evaluate_date = params.evaluate_date
      AND r.repo_type = 'REV_REPO'
      AND r.counterparty_name IS NOT NULL
) t
JOIN fsi.para_portfolio p ON p.port_id = t.port_id
ORDER BY p.port_name, holding_type, issuer_name;
