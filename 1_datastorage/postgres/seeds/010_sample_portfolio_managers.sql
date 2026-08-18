-- ============================================================
-- 樣本數據：投資人員 + 組合投資經理任職記錄
-- 用途：讓「基金基本信息 / 投資經理」模塊有可展示數據。
-- 冪等：ON CONFLICT DO NOTHING，可重複執行。
-- ============================================================

INSERT INTO fsi.para_person
    (person_id, person_name, person_name_en, email, phone, sfc_licence_no, is_active)
VALUES
    ('PSN0001', '陳志明', 'Chan Chi Ming',   'cm.chan@bohui.com',  '+852-2100-0001', 'BJK123', TRUE),
    ('PSN0002', '林嘉欣', 'Lam Ka Yan',      'ky.lam@bohui.com',   '+852-2100-0002', 'BJK456', TRUE),
    ('PSN0003', '黃國強', 'Wong Kwok Keung', 'kk.wong@bohui.com',  '+852-2100-0003', 'BJK789', TRUE),
    ('PSN0004', '張美玲', 'Cheung Mei Ling', 'ml.cheung@bohui.com','+852-2100-0004', 'BJK012', TRUE)
ON CONFLICT (person_id) DO NOTHING;

INSERT INTO fsi.para_portfolio_manager
    (port_id, person_id, role, begin_date, end_date, is_lead)
VALUES
    -- BHMMF001：首席基金經理 + 副經理 + 風控
    ('BHMMF001', 'PSN0001', 'FUND_MANAGER',   DATE '2020-01-15', NULL, TRUE),
    ('BHMMF001', 'PSN0002', 'DEPUTY_MANAGER', DATE '2021-06-01', NULL, FALSE),
    ('BHMMF001', 'PSN0003', 'RISK_OFFICER',   DATE '2020-01-15', NULL, FALSE),
    -- BHMMF002：首席基金經理 + 風控
    ('BHMMF002', 'PSN0002', 'FUND_MANAGER',   DATE '2021-03-01', NULL, TRUE),
    ('BHMMF002', 'PSN0003', 'RISK_OFFICER',   DATE '2021-03-01', NULL, FALSE),
    -- 歷史任職（已離任）示例
    ('BHMMF001', 'PSN0004', 'FUND_MANAGER',   DATE '2018-05-01', DATE '2020-01-14', FALSE)
ON CONFLICT (port_id, person_id, role, begin_date) DO NOTHING;
