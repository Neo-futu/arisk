-- ============================================================
-- 報表06 / 03_maturity_ladder.sql
-- 原始：SmartReport/06/03.sql  完整到期期限分佈
-- 功能：D+1至D+20，以及月/季/年度期限段分佈
--       按資產類型分行，最後一行為各期限合計
--       其中 1Y以上 以「剩餘期限結構」展示為主，適用於貨幣基金持倉的長端到期分析；
--       真正流動性判斷仍以 T+1~T+7 及可變現資產為核心。
-- 參數：params.port_ids TEXT[], params.evaluate_date DATE
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
-- ============================================================
base AS (
    SELECT
        port_id,
        asset_type,
        remaining_days,
        mv
    FROM (
        -- 現金（活期存款，T+0 可用）
        SELECT
            ca.port_id,
            '现金' AS asset_type,
            0 AS remaining_days,
            COALESCE(ca.amount, 0) * 100 AS mv
        FROM fsi.balance_cash ca
        WHERE ca.port_id = ANY(params.port_ids) AND ca.evaluate_date = params.evaluate_date

        UNION ALL

        -- 存款（定期，含隔夜）
        SELECT
            d.port_id,
            '存款' AS asset_type,
            CASE WHEN d.is_overnight THEN 1 ELSE d.remaining_days END AS remaining_days,
            COALESCE(d.principal, 0) * 100 AS mv
        FROM fsi.balance_deposit d
        WHERE d.port_id = ANY(params.port_ids) AND d.evaluate_date = params.evaluate_date

        UNION ALL

        -- 存款證（CD）
        SELECT
            c.port_id,
            '存款證CD',
            c.remaining_days,
            COALESCE(c.market_value, 0) * 100
        FROM fsi.balance_cd c
        WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date

        UNION ALL

        -- 逆回購（融出，到期收回，計入流動性）
        SELECT
            r.port_id,
            '逆回購',
            COALESCE(COALESCE(r.actual_maturity_date, r.maturity_date) - r.evaluate_date,
                     r.interest_days, 999),
            COALESCE(r.principal, 0) * 100
        FROM fsi.balance_repo r
        WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date
          AND r.repo_type = 'REV_REPO'

        UNION ALL

        -- 政府/利率債
        SELECT
            b.port_id,
            '利率債',
            b.remaining_days,
            COALESCE(b.market_value, 0) * 100
        FROM fsi.balance_bond b
        WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
          AND b.asset_subtype = 'BOND_GOVT'

        UNION ALL

        -- 信用債
        SELECT
            b.port_id,
            '信用債',
            b.remaining_days,
            COALESCE(b.market_value, 0) * 100
        FROM fsi.balance_bond b
        WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
          AND b.asset_subtype != 'BOND_GOVT'

        UNION ALL

        -- 正回購（融入，到期還款，計為負流動性）
        SELECT
            r.port_id,
            '正回購（融入）',
            COALESCE(COALESCE(r.actual_maturity_date, r.maturity_date) - r.evaluate_date,
                     r.interest_days, 999),
            -COALESCE(r.principal, 0) * 100   -- 負號
        FROM fsi.balance_repo r
        WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date
          AND r.repo_type = 'REPO'
    ) t
    WHERE remaining_days >= 0
),

-- 月末/季末/年末節點
dates AS (
    SELECT
        params.evaluate_date::DATE + 21   AS d21,
        -- 下月末
        DATE_TRUNC('month', params.evaluate_date::DATE) + INTERVAL '2 month' - INTERVAL '1 day' AS m1_end,
        -- 3個月末
        DATE_TRUNC('month', params.evaluate_date::DATE) + INTERVAL '4 month' - INTERVAL '1 day' AS m3_end,
        -- 6個月末
        DATE_TRUNC('month', params.evaluate_date::DATE) + INTERVAL '7 month' - INTERVAL '1 day' AS m6_end,
        -- 9個月末
        DATE_TRUNC('month', params.evaluate_date::DATE) + INTERVAL '10 month' - INTERVAL '1 day' AS m9_end,
        -- 年末
        DATE_TRUNC('year', params.evaluate_date::DATE) + INTERVAL '1 year' - INTERVAL '1 day'   AS y1_end
),

pivot AS (
    SELECT
        b.port_id,
        b.asset_type,
        -- D+1 至 D+20 逐天
        ROUND(SUM(CASE WHEN remaining_days = 1  THEN mv ELSE 0 END) / 100000000, 4) AS d1,
        ROUND(SUM(CASE WHEN remaining_days = 2  THEN mv ELSE 0 END) / 100000000, 4) AS d2,
        ROUND(SUM(CASE WHEN remaining_days = 3  THEN mv ELSE 0 END) / 100000000, 4) AS d3,
        ROUND(SUM(CASE WHEN remaining_days = 4  THEN mv ELSE 0 END) / 100000000, 4) AS d4,
        ROUND(SUM(CASE WHEN remaining_days = 5  THEN mv ELSE 0 END) / 100000000, 4) AS d5,
        ROUND(SUM(CASE WHEN remaining_days = 6  THEN mv ELSE 0 END) / 100000000, 4) AS d6,
        ROUND(SUM(CASE WHEN remaining_days = 7  THEN mv ELSE 0 END) / 100000000, 4) AS d7,
        ROUND(SUM(CASE WHEN remaining_days = 8  THEN mv ELSE 0 END) / 100000000, 4) AS d8,
        ROUND(SUM(CASE WHEN remaining_days = 9  THEN mv ELSE 0 END) / 100000000, 4) AS d9,
        ROUND(SUM(CASE WHEN remaining_days = 10 THEN mv ELSE 0 END) / 100000000, 4) AS d10,
        ROUND(SUM(CASE WHEN remaining_days = 11 THEN mv ELSE 0 END) / 100000000, 4) AS d11,
        ROUND(SUM(CASE WHEN remaining_days = 12 THEN mv ELSE 0 END) / 100000000, 4) AS d12,
        ROUND(SUM(CASE WHEN remaining_days = 13 THEN mv ELSE 0 END) / 100000000, 4) AS d13,
        ROUND(SUM(CASE WHEN remaining_days = 14 THEN mv ELSE 0 END) / 100000000, 4) AS d14,
        ROUND(SUM(CASE WHEN remaining_days = 15 THEN mv ELSE 0 END) / 100000000, 4) AS d15,
        ROUND(SUM(CASE WHEN remaining_days = 16 THEN mv ELSE 0 END) / 100000000, 4) AS d16,
        ROUND(SUM(CASE WHEN remaining_days = 17 THEN mv ELSE 0 END) / 100000000, 4) AS d17,
        ROUND(SUM(CASE WHEN remaining_days = 18 THEN mv ELSE 0 END) / 100000000, 4) AS d18,
        ROUND(SUM(CASE WHEN remaining_days = 19 THEN mv ELSE 0 END) / 100000000, 4) AS d19,
        ROUND(SUM(CASE WHEN remaining_days = 20 THEN mv ELSE 0 END) / 100000000, 4) AS d20,
        -- D+21 以上月/季/年段（累計到各節點）
        ROUND(SUM(CASE WHEN remaining_days BETWEEN 21 AND 60  THEN mv ELSE 0 END) / 100000000, 4) AS d21_m1,
        ROUND(SUM(CASE WHEN remaining_days BETWEEN 61 AND 90  THEN mv ELSE 0 END) / 100000000, 4) AS m1_m3,
        ROUND(SUM(CASE WHEN remaining_days BETWEEN 91 AND 180 THEN mv ELSE 0 END) / 100000000, 4) AS m3_m6,
        ROUND(SUM(CASE WHEN remaining_days BETWEEN 181 AND 270 THEN mv ELSE 0 END) / 100000000, 4) AS m6_m9,
        ROUND(SUM(CASE WHEN remaining_days BETWEEN 271 AND 365 THEN mv ELSE 0 END) / 100000000, 4) AS m9_1y,
        ROUND(SUM(CASE WHEN remaining_days > 365 THEN mv ELSE 0 END) / 100000000, 4) AS y1_plus,
        ROUND(SUM(mv) / 100000000, 4) AS total
    FROM base b
    GROUP BY b.port_id, b.asset_type
)

-- 明細行
SELECT * FROM (
    SELECT
        p.port_name,
        pv.port_id,
        pv.asset_type,
        pv.d1, pv.d2, pv.d3, pv.d4, pv.d5, pv.d6, pv.d7, pv.d8, pv.d9, pv.d10,
        pv.d11, pv.d12, pv.d13, pv.d14, pv.d15, pv.d16, pv.d17, pv.d18, pv.d19, pv.d20,
        pv.d21_m1, pv.m1_m3, pv.m3_m6, pv.m6_m9, pv.m9_1y, pv.y1_plus,
        CASE pv.asset_type
            WHEN '现金' THEN '现金'
            WHEN '存款' THEN '存款'
            WHEN '存款證CD' THEN '存款'
            WHEN '逆回購' THEN '回购'
            WHEN '正回購（融入）' THEN '回购'
            WHEN '利率債' THEN '债券'
            WHEN '信用債' THEN '债券'
            ELSE pv.asset_type
        END AS big_type
    FROM pivot pv
    JOIN fsi.para_portfolio p ON p.port_id = pv.port_id

    UNION ALL

    -- 合計行
    SELECT
        p.port_name,
        pv.port_id,
        '合計' AS asset_type,
        SUM(pv.d1), SUM(pv.d2), SUM(pv.d3), SUM(pv.d4), SUM(pv.d5),
        SUM(pv.d6), SUM(pv.d7), SUM(pv.d8), SUM(pv.d9), SUM(pv.d10),
        SUM(pv.d11), SUM(pv.d12), SUM(pv.d13), SUM(pv.d14), SUM(pv.d15),
        SUM(pv.d16), SUM(pv.d17), SUM(pv.d18), SUM(pv.d19), SUM(pv.d20),
        SUM(pv.d21_m1), SUM(pv.m1_m3), SUM(pv.m3_m6), SUM(pv.m6_m9), SUM(pv.m9_1y), SUM(pv.y1_plus),
        '合计' AS big_type
    FROM pivot pv
    JOIN fsi.para_portfolio p ON p.port_id = pv.port_id
    GROUP BY p.port_name, pv.port_id
) t
ORDER BY port_name, port_id, CASE asset_type WHEN '合計' THEN 99 ELSE 0 END, asset_type;
