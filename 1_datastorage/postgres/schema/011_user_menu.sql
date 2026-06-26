-- ============================================================
-- 011_user_menu.sql  用戶權限與菜單查詢配置層
-- FSI Financial Services Intelligence Platform
-- 逆向還原自 RMT C# 系統 + IA 系統使用手冊
-- 設計原則：每個葉節點 = 唯一一種查詢模式，無切換
--           多個子菜單替代切換，方便精細化角色授權
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. 角色定義
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_role (
    role_id      INTEGER      PRIMARY KEY,
    role_name    VARCHAR(60)  NOT NULL,
    role_name_en VARCHAR(60),
    description  TEXT,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE fsi.para_role IS '系統角色：FIPM/EquityPM/RiskManager/Admin等';

INSERT INTO fsi.para_role (role_id, role_name, role_name_en) VALUES
    (10001, '固定收益基金經理', 'Fixed Income PM'),
    (10002, '股票基金經理',     'Equity PM'),
    (10003, '系統管理員',       'Admin'),
    (10004, '風控經理',         'Risk Manager'),
    (10005, '高級報表用戶',     'Advanced Reporter'),
    (10006, '基礎報表用戶',     'Reporter'),
    (10007, '信用風控經理',     'Credit Risk Manager')
ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 2. 系統用戶
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_user (
    user_id         VARCHAR(32)  PRIMARY KEY,
    user_name       VARCHAR(60)  NOT NULL,
    email           VARCHAR(120),
    password_hash   VARCHAR(256),
    mac_addresses   VARCHAR(500),
    port_permission TEXT,
    is_locked       BOOLEAN      NOT NULL DEFAULT FALSE,
    last_login_at   TIMESTAMPTZ,
    last_login_ip   VARCHAR(64),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_user IS '系統用戶：含設備綁定和組合訪問權限';
COMMENT ON COLUMN fsi.para_user.port_permission IS 'SQL WHERE子句，空=全組合，如 port_id in (''P001'')';

-- ────────────────────────────────────────────────────────────
-- 3. 用戶-角色（多對多）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_user_role (
    user_id  VARCHAR(32)  NOT NULL,
    role_id  INTEGER      NOT NULL,
    PRIMARY KEY (user_id, role_id)
);
COMMENT ON TABLE fsi.para_user_role IS '用戶角色分配：一用戶可有多角色';

-- ────────────────────────────────────────────────────────────
-- 4. 菜單樹
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_menu (
    menu_id      VARCHAR(16)  PRIMARY KEY,
    parent_id    VARCHAR(16),
    menu_name    VARCHAR(80)  NOT NULL,
    menu_name_en VARCHAR(80),
    icon         VARCHAR(32),
    sort_order   INTEGER      NOT NULL DEFAULT 0,
    menu_level   SMALLINT     NOT NULL DEFAULT 1,
    is_leaf      BOOLEAN      NOT NULL DEFAULT FALSE,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_menu IS '菜單樹：每個葉節點對應唯一一種查詢模式，無切換設計';
COMMENT ON COLUMN fsi.para_menu.is_leaf IS 'TRUE=報表節點；FALSE=分組節點';

CREATE INDEX IF NOT EXISTS idx_para_menu_parent ON fsi.para_menu(parent_id);

-- ────────────────────────────────────────────────────────────
-- 5. 角色-菜單禁止（黑名單）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_role_menu_deny (
    role_id  INTEGER      NOT NULL,
    menu_id  VARCHAR(16)  NOT NULL,
    PRIMARY KEY (role_id, menu_id)
);
COMMENT ON TABLE fsi.para_role_menu_deny IS '角色菜單禁止清單：黑名單，列出的菜單對該角色不可見';

-- ────────────────────────────────────────────────────────────
-- 6. 查詢定義
--   每條記錄 = 一種報表 + 一種參數模式（無切換）
--   參數組合說明：
--     multi_port + single_date  = 多組合時點比較
--     single_port + date_range  = 單組合時序分析
--     multi_port + date_range   = 多組合區間比較
--     single_port + single_date = 單組合時點詳情
--     no_port + single_date     = 市場數據/全局視圖
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_query_def (
    query_id       INTEGER      PRIMARY KEY,
    query_name     VARCHAR(120) NOT NULL,
    query_name_en  VARCHAR(120),
    api_endpoint   VARCHAR(256),
    is_single_port BOOLEAN      NOT NULL DEFAULT FALSE,
    is_multi_port  BOOLEAN      NOT NULL DEFAULT FALSE,
    is_single_date BOOLEAN      NOT NULL DEFAULT FALSE,
    is_date_range  BOOLEAN      NOT NULL DEFAULT FALSE,
    is_custom1     BOOLEAN      NOT NULL DEFAULT FALSE,
    custom1_name   VARCHAR(32),
    is_custom2     BOOLEAN      NOT NULL DEFAULT FALSE,
    custom2_name   VARCHAR(32),
    max_records    INTEGER      DEFAULT 5000,
    description    TEXT,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_query_def IS '查詢定義：每張報表一條，每條只有一種參數模式';
COMMENT ON COLUMN fsi.para_query_def.api_endpoint IS '對應 2_processing 層 REST API 路徑';

-- ────────────────────────────────────────────────────────────
-- 7. 菜單-查詢映射
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_menu_query (
    menu_id    VARCHAR(16)  NOT NULL,
    query_id   INTEGER      NOT NULL,
    tab_order  INTEGER      DEFAULT 1,
    tab_name   VARCHAR(60),
    PRIMARY KEY (menu_id, query_id)
);
COMMENT ON TABLE fsi.para_menu_query IS '菜單-查詢映射：月報等複合菜單可掛多個子查詢（Tab展示）';

-- ────────────────────────────────────────────────────────────
-- 8. 用戶收藏菜單
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_user_favorite (
    user_id    VARCHAR(32)  NOT NULL,
    menu_id    VARCHAR(16)  NOT NULL,
    sort_order INTEGER      DEFAULT 0,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, menu_id)
);
COMMENT ON TABLE fsi.para_user_favorite IS '用戶收藏菜單（☆功能）：個人收藏報表列表';

-- ────────────────────────────────────────────────────────────
-- 9. 查詢參數記憶
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_user_query_pref (
    user_id     VARCHAR(32)  NOT NULL,
    query_id    INTEGER      NOT NULL,
    port_ids    TEXT,
    last_date   DATE,
    date_from   DATE,
    date_to     DATE,
    custom1_val VARCHAR(256),
    custom2_val VARCHAR(256),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, query_id)
);
COMMENT ON TABLE fsi.para_user_query_pref IS '查詢參數記憶：進入報表自動填充上次參數';

-- ────────────────────────────────────────────────────────────
-- 10. 列格式化
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_column_format (
    column_name     VARCHAR(64)  PRIMARY KEY,
    display_name    VARCHAR(64)  NOT NULL,
    display_name_en VARCHAR(64),
    scale_factor    NUMERIC(8,4) DEFAULT 1,
    decimal_digits  INTEGER      DEFAULT 2,
    format_code     VARCHAR(16),
    alignment       VARCHAR(8)   DEFAULT 'right',
    is_sortable     BOOLEAN      DEFAULT TRUE,
    unit            VARCHAR(16)
);
COMMENT ON TABLE fsi.para_column_format IS '報表列格式：統一管理中文表頭/精度/格式碼';

-- ============================================================
-- 種子數據：菜單樹
-- 命名規範：(時點)=多組合+單日期  (時序)=單組合+日期區間
--           (區間)=多組合+日期區間  無後綴=唯一模式
-- ============================================================
INSERT INTO fsi.para_menu
    (menu_id, parent_id, menu_name, menu_name_en, sort_order, menu_level, is_leaf)
VALUES

-- L1 根節點
('01000000', NULL,       'FSI風控業績平台',   'FSI Risk Platform',        0, 1, FALSE),

-- L2
('01010000', '01000000', '收藏報表',          'Favorites',                 0, 2, FALSE),
('01020000', '01000000', '組合報告',          'Portfolio Report',          1, 2, FALSE),
('01030000', '01000000', '市場數據',          'Market Data',               2, 2, FALSE),
('01040000', '01000000', '風控預警',          'Risk Alerts',               3, 2, FALSE),
('01050000', '01000000', '可比分析',          'Peer Analysis',             4, 2, FALSE),
('01060000', '01000000', '系統設置',          'Admin Settings',            9, 2, FALSE),

-- L3: 組合報告
('01020100', '01020000', '組合概況',          'Portfolio Overview',         1, 3, FALSE),
('01020200', '01020000', '合規監控',          'Compliance Monitor',         2, 3, FALSE),
('01020300', '01020000', '風險指標',          'Risk Indicators',            3, 3, FALSE),
('01020400', '01020000', '組合持倉',          'Holdings',                   4, 3, FALSE),
('01020500', '01020000', '組合交易',          'Transactions',               5, 3, FALSE),
('01020600', '01020000', '業績歸因',          'Performance Attribution',    6, 3, FALSE),
('01020700', '01020000', '投資月報',          'Monthly Report',             7, 3, FALSE),

-- L3: 市場數據
('01030100', '01030000', '債券',              'Bond',                       1, 3, FALSE),
('01030200', '01030000', '股票',              'Equity',                     2, 3, FALSE),
('01030300', '01030000', '指數',              'Index',                      3, 3, FALSE),
('01030400', '01030000', '匯率利率',          'FX & Rates',                 4, 3, FALSE),

-- L3: 風控預警
('01040100', '01040000', '今日預警',          'Today Alerts',               1, 3, TRUE),
('01040200', '01040000', '預警歷史',          'Alert History',              2, 3, TRUE),
('01040300', '01040000', '審核工作流',        'Review Workflow',            3, 3, TRUE),

-- L3: 可比分析
('01050100', '01050000', '業績簡報',          'Performance Brief',          1, 3, TRUE),
('01050200', '01050000', '同類排名',          'Peer Ranking',               2, 3, TRUE),
('01050300', '01050000', '比較組管理',        'Peer Group Management',      3, 3, TRUE),

-- L3: 系統設置
('01060100', '01060000', '用戶管理',          'User Management',            1, 3, TRUE),
('01060200', '01060000', '組合管理',          'Portfolio Management',       2, 3, TRUE),
('01060300', '01060000', '菜單配置',          'Menu Config',                3, 3, TRUE),
('01060400', '01060000', '查詢管理',          'Query Management',           4, 3, TRUE),
('01060500', '01060000', '列格式化',          'Column Formats',             5, 3, TRUE),

-- ─────────────────────────────────────────────────────────────
-- L4: 組合概況（時點/時序分別獨立菜單，無切換）
-- ─────────────────────────────────────────────────────────────
('01020101', '01020100', '總體業績（時點）',   'Performance - Cross',        1, 4, TRUE),
('01020102', '01020100', '總體業績（時序）',   'Performance - Trend',        2, 4, TRUE),
('01020103', '01020100', '資產配置（時點）',   'Asset Alloc - Cross',        3, 4, TRUE),
('01020104', '01020100', '資產配置（時序）',   'Asset Alloc - Trend',        4, 4, TRUE),
('01020105', '01020100', '靜態收益率（時點）', 'Static Yield - Cross',       5, 4, TRUE),
('01020106', '01020100', '靜態收益率（時序）', 'Static Yield - Trend',       6, 4, TRUE),
('01020107', '01020100', '債券資產（時點）',   'Bond Assets - Cross',        7, 4, TRUE),
('01020108', '01020100', '債券資產（時序）',   'Bond Assets - Trend',        8, 4, TRUE),
('01020109', '01020100', '申贖統計（時點）',   'Sub/Redeem - Cross',         9, 4, TRUE),
('01020110', '01020100', '申贖統計（時序）',   'Sub/Redeem - Trend',        10, 4, TRUE),
('01020111', '01020100', '當日申贖明細',       'Today Sub/Redeem Detail',   11, 4, TRUE),
('01020112', '01020100', '持有人明細',         'Holder Detail',             12, 4, TRUE),

-- L4: 合規監控（MMF守則）
('01020201', '01020200', 'WAM時序走勢',        'WAM Trend',                  1, 4, TRUE),
('01020202', '01020200', 'WAL時序走勢',        'WAL Trend',                  2, 4, TRUE),
('01020203', '01020200', '多組合WAM/WAL時點',  'WAM/WAL Cross',              3, 4, TRUE),
('01020204', '01020200', '每日流動性時序',     'Daily Liquidity Trend',      4, 4, TRUE),
('01020205', '01020200', '每週流動性時序',     'Weekly Liquidity Trend',     5, 4, TRUE),
('01020206', '01020200', '多組合流動性時點',   'Liquidity Cross',            6, 4, TRUE),
('01020207', '01020200', '發行人集中度',       'Issuer Concentration',       7, 4, TRUE),
('01020208', '01020200', '集團集中度',         'Group Concentration',        8, 4, TRUE),
('01020209', '01020200', '信用質素分佈',       'Credit Quality',             9, 4, TRUE),
('01020210', '01020200', '合規違規歷史',       'Breach History',            10, 4, TRUE),

-- L4: 風險指標
('01020301', '01020300', '區間收益率',         'Interval Return',            1, 4, TRUE),
('01020302', '01020300', '年化波動率',         'Annualized Volatility',      2, 4, TRUE),
('01020303', '01020300', '最大回撤',           'Max Drawdown',               3, 4, TRUE),
('01020304', '01020300', 'VaR（時點）',        'VaR Snapshot',               4, 4, TRUE),
('01020305', '01020300', 'VaR歷史走勢',        'VaR History',                5, 4, TRUE),
('01020306', '01020300', '債券久期（時點）',   'Duration Cross',             6, 4, TRUE),
('01020307', '01020300', '債券久期（時序）',   'Duration Trend',             7, 4, TRUE),
('01020308', '01020300', '利率敏感性',         'IR Sensitivity',             8, 4, TRUE),
('01020309', '01020300', '股票換手率',         'Equity Turnover',            9, 4, TRUE),
('01020310', '01020300', '股票Beta（時點）',   'Equity Beta Cross',         10, 4, TRUE),
('01020311', '01020300', '股票估值（時點）',   'Equity Valuation Cross',    11, 4, TRUE),

-- L4: 組合持倉（全部時點，按資產類別分菜單）
('01020401', '01020400', '現金及存款',         'Cash & Deposits',            1, 4, TRUE),
('01020402', '01020400', '存款證',             'Certificates of Deposit',    2, 4, TRUE),
('01020403', '01020400', '債券',               'Bonds',                      3, 4, TRUE),
('01020404', '01020400', '股票',               'Equities',                   4, 4, TRUE),
('01020405', '01020400', '基金',               'Funds',                      5, 4, TRUE),
('01020406', '01020400', '期貨',               'Futures',                    6, 4, TRUE),
('01020407', '01020400', '期權',               'Options',                    7, 4, TRUE),
('01020408', '01020400', '回購',               'Repo',                       8, 4, TRUE),
('01020409', '01020400', '養老金持倉',         'Pension Holdings',           9, 4, TRUE),
('01020410', '01020400', '估值資產負債表',     'Valuation Sheet',           10, 4, TRUE),

-- L4: 組合交易（全部區間）
('01020501', '01020500', '債券交易',           'Bond Transactions',          1, 4, TRUE),
('01020502', '01020500', '股票交易',           'Equity Transactions',        2, 4, TRUE),
('01020503', '01020500', '存款及CD交易',       'Deposit & CD Transactions',  3, 4, TRUE),
('01020504', '01020500', '銀行間交易',         'Interbank Transactions',     4, 4, TRUE),
('01020505', '01020500', '申贖流水',           'Subscription Flow',          5, 4, TRUE),
('01020506', '01020500', '損益明細',           'P&L Detail',                 6, 4, TRUE),
('01020507', '01020500', '損益匯總',           'P&L Summary',                7, 4, TRUE),

-- L4: 業績歸因
('01020601', '01020600', '各類資產收益貢獻',   'Asset Return Contribution',  1, 4, TRUE),
('01020602', '01020600', '行業配置收益',       'Sector Attribution',         2, 4, TRUE),
('01020603', '01020600', '行業超配情況',       'Sector Overweight',          3, 4, TRUE),
('01020604', '01020600', '個券損益前十大',     'Top 10 Winners',             4, 4, TRUE),
('01020605', '01020600', '個券損益後十大',     'Top 10 Losers',              5, 4, TRUE),
('01020606', '01020600', '日均十大重倉',       'Avg Top 10 Holdings',        6, 4, TRUE),
('01020607', '01020600', '固收利率歸因',       'FI Rate Attribution',        7, 4, TRUE),
('01020608', '01020600', '固收利差歸因',       'FI Spread Attribution',      8, 4, TRUE),

-- L4: 投資月報（多張子表各自獨立菜單）
('01020701', '01020700', '月報-行業配置一級',  'Monthly - Sector L1',        1, 4, TRUE),
('01020702', '01020700', '月報-行業配置二級',  'Monthly - Sector L2',        2, 4, TRUE),
('01020703', '01020700', '月報-前十大持倉',    'Monthly - Top Holdings',     3, 4, TRUE),
('01020704', '01020700', '月報-持倉調出',      'Monthly - Dropped Holdings', 4, 4, TRUE),
('01020705', '01020700', '月報-大額交易',      'Monthly - Large Trades',     5, 4, TRUE),

-- L4: 市場數據
('01030101', '01030100', '債券行情',           'Bond Quotes',                1, 4, TRUE),
('01030102', '01030100', '收益率曲線',         'Yield Curves',               2, 4, TRUE),
('01030103', '01030100', '負面信息',           'Credit Negative News',       3, 4, TRUE),
('01030104', '01030100', '新債發行',           'Bond Issuance',              4, 4, TRUE),
('01030201', '01030200', '股票行情',           'Equity Quotes',              1, 4, TRUE),
('01030202', '01030200', '行業指數表現',       'Sector Index Performance',   2, 4, TRUE),
('01030203', '01030200', '股票股息',           'Stock Dividends',            3, 4, TRUE),
('01030301', '01030300', '指數行情',           'Index Quotes',               1, 4, TRUE),
('01030302', '01030300', '指數成分',           'Index Components',           2, 4, TRUE),
('01030401', '01030400', '外匯匯率',           'FX Rates',                   1, 4, TRUE),
('01030402', '01030400', 'HIBOR利率',          'HIBOR Rates',                2, 4, TRUE),
('01030403', '01030400', 'SHIBOR利率',         'SHIBOR Rates',               3, 4, TRUE)

ON CONFLICT DO NOTHING;

-- ============================================================
-- 種子數據：查詢定義（para_query_def）
-- 每條 = 一張報表 + 唯一參數模式
-- ============================================================
INSERT INTO fsi.para_query_def
    (query_id, query_name, query_name_en,
     is_single_port, is_multi_port, is_single_date, is_date_range,
     api_endpoint, description)
VALUES

-- 組合概況
(1001,'總體業績（時點）','Performance Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/portfolio/overview/performance/cross',
 '多組合同一日期：NAV/份額/單位淨值/各期收益率對比'),

(1002,'總體業績（時序）','Performance Time-Series',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/portfolio/overview/performance/trend',
 '單組合歷史走勢：NAV/份額/日收益率時序折線圖'),

(1003,'資產配置（時點）','Asset Allocation Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/portfolio/overview/asset-allocation/cross',
 '多組合同一日期各大類資產佔NAV比例對比'),

(1004,'資產配置（時序）','Asset Allocation Time-Series',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/portfolio/overview/asset-allocation/trend',
 '單組合資產配置歷史變化，面積圖展示'),

(1005,'靜態收益率（時點）','Static Yield Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/portfolio/overview/static-yield/cross',
 '多組合時點：債券YTM/存單YTM/存款利率/回購利率/資產端收益率'),

(1006,'靜態收益率（時序）','Static Yield Time-Series',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/portfolio/overview/static-yield/trend',
 '單組合資產端收益率歷史走勢'),

(1007,'債券資產（時點）','Bond Assets Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/portfolio/overview/bond-assets/cross',
 '多組合時點利率債/公司債/短融/ABS/可轉債等細分佔比'),

(1008,'債券資產（時序）','Bond Assets Time-Series',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/portfolio/overview/bond-assets/trend',
 '單組合債券類資產結構歷史變化'),

(1009,'申贖統計（時點）','Sub/Redeem Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/portfolio/overview/sub-redeem/cross',
 '多組合時點申購/贖回/淨申購金額及佔淨值比'),

(1010,'申贖統計（時序）','Sub/Redeem Time-Series',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/portfolio/overview/sub-redeem/trend',
 '單組合申贖趨勢：淨申購金額歷史走勢'),

(1011,'當日申贖明細','Today Sub/Redeem Detail',
 TRUE,FALSE,TRUE,FALSE,
 '/api/v1/portfolio/overview/sub-redeem/detail',
 '單組合時點：持有人當日淨贖回額/佔淨值比/佔持有人持倉比'),

(1012,'持有人明細','Holder Detail',
 TRUE,FALSE,TRUE,FALSE,
 '/api/v1/portfolio/overview/holders',
 '單組合時點前N大持有人：編號/名稱/金額/佔比'),

-- 合規監控
(1021,'WAM時序走勢','WAM Trend',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/compliance/wam/trend',
 '單組合WAM日歷史走勢 vs SFC守則60天上限'),

(1022,'WAL時序走勢','WAL Trend',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/compliance/wal/trend',
 '單組合WAL日歷史走勢 vs SFC守則120天上限'),

(1023,'多組合WAM/WAL時點','WAM/WAL Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/compliance/wam-wal/cross',
 '多MMF組合同一日期WAM/WAL達標狀態對比'),

(1024,'每日流動性時序','Daily Liquidity Trend',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/compliance/liquidity/daily/trend',
 '單組合每日流動資產佔比歷史走勢 vs 7.5%下限'),

(1025,'每週流動性時序','Weekly Liquidity Trend',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/compliance/liquidity/weekly/trend',
 '單組合每週流動資產佔比歷史走勢 vs 15%下限'),

(1026,'多組合流動性時點','Liquidity Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/compliance/liquidity/cross',
 '多組合流動性達標狀態：每日/每週流動性佔比'),

(1027,'發行人集中度','Issuer Concentration',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/compliance/concentration/issuer',
 '按發行人排名敞口佔NAV比，標識超10%上限的發行人'),

(1028,'集團集中度','Group Concentration',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/compliance/concentration/group',
 '按集團彙總敞口，標識超20%上限的集團'),

(1029,'信用質素分佈','Credit Quality Distribution',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/compliance/credit-quality',
 '投資級/未評級/各評級佔比分佈'),

(1030,'合規違規歷史','Compliance Breach History',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/compliance/breach-history',
 '單組合違規事件歷史：規則/實際值/限制/觸發時間/處置'),

-- 風險指標
(1031,'區間收益率','Interval Return',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/risk/return',
 '多組合區間累計收益率/年化收益率對比'),

(1032,'年化波動率','Annualized Volatility',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/risk/volatility',
 '多組合區間年化波動率，不足一年用算術年化'),

(1033,'最大回撤','Max Drawdown',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/risk/max-drawdown',
 '多組合區間最大回撤：開始日/結束日/幅度/恢復天數'),

(1034,'VaR時點','VaR Snapshot',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/risk/var/snapshot',
 '多組合時點1天/10天 95%/99% VaR及CVaR'),

(1035,'VaR歷史走勢','VaR Historical Trend',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/risk/var/trend',
 '單組合VaR歷史走勢，監控風險動態變化'),

(1036,'債券久期時點','Duration Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/risk/duration/cross',
 '多組合時點久期：總久期/利率債久期/信用債久期/凸性'),

(1037,'債券久期時序','Duration Time-Series',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/risk/duration/trend',
 '單組合久期歷史走勢，利率敞口管理'),

(1038,'利率敏感性','IR Sensitivity',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/risk/ir-sensitivity',
 '多組合時點DV01及+100bp利率情景市值變動'),

(1039,'股票換手率','Equity Turnover',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/risk/equity-turnover',
 '多組合區間日均股票餘額/買入賣出額/單邊年換手率'),

(1040,'股票Beta時點','Equity Beta Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/risk/equity-beta',
 '多組合時點市值加權Beta/股票市值/佔淨值比'),

(1041,'股票估值時點','Equity Valuation Cross-Sectional',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/risk/equity-valuation',
 '多組合時點市值加權PE/PB/PS/PCF/Beta'),

-- 組合持倉
(1051,'現金及存款持倉','Cash & Deposit Holdings',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/holdings/cash-deposit',
 '多組合時點活期現金+定期存款：銀行/幣種/利率/到期/集團'),

(1052,'存款證持倉','CD Holdings',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/holdings/cd',
 '多組合時點CD：發行人/評級/票息/到期/YTM/久期/市值'),

(1053,'債券持倉','Bond Holdings',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/holdings/bond',
 '多組合時點債券：類型/發行人/到期/YTM/久期/凸性/評級'),

(1054,'股票持倉','Equity Holdings',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/holdings/equity',
 '多組合時點個股：數量/成本/價格/市值/浮盈虧/板塊/行業'),

(1055,'基金持倉','Fund Holdings',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/holdings/fund',
 '多組合時點基金：代碼/份額/NAV/市值'),

(1056,'期貨持倉','Futures Holdings',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/holdings/futures',
 '多組合時點期貨：多空/合約/名義金額/盯市盈虧'),

(1057,'期權持倉','Options Holdings',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/holdings/options',
 '多組合時點期權：Delta/Gamma/Vega/Theta/隱含波動率'),

(1058,'回購持倉','Repo Holdings',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/holdings/repo',
 '多組合時點回購：交易對手/質押券/利率/到期/金額'),

(1059,'養老金持倉','Pension Holdings',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/holdings/pension',
 '多組合時點國內養老金：社保/企業年金/職業年金'),

(1060,'估值資產負債表','Valuation Sheet',
 TRUE,FALSE,TRUE,FALSE,
 '/api/v1/holdings/valuation-sheet',
 '單組合時點估值系統科目表：資產/負債各科目市值'),

-- 組合交易
(1061,'債券交易','Bond Transactions',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/transactions/bond',
 '多組合區間債券買賣：方向/淨價/應計利息/成交YTM/久期'),

(1062,'股票交易','Equity Transactions',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/transactions/equity',
 '多組合區間股票買賣：方向/價格/金額/印花稅/傭金'),

(1063,'存款及CD交易','Deposit & CD Transactions',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/transactions/deposit-cd',
 '多組合區間存款新存/到期/提前支取，CD買賣/到期'),

(1064,'銀行間交易','Interbank Transactions',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/transactions/interbank',
 '多組合區間銀行間債券+回購：含CFETS執行ID'),

(1065,'申贖流水','Subscription Flow',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/transactions/subscription',
 '多組合區間投資者申購贖回：持有人/金額/份額/確認NAV'),

(1066,'損益明細','P&L Detail by Security',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/transactions/pnl-detail',
 '多組合區間個券損益拆解：盯市/利息/已實現/外匯'),

(1067,'損益匯總','P&L Summary by Asset Class',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/transactions/pnl-summary',
 '多組合區間按資產類別匯總損益，NAV驗算基礎'),

-- 業績歸因
(1071,'各類資產收益貢獻','Asset Return Contribution',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/attribution/asset-contribution',
 '多組合區間各資產類別收益貢獻拆解'),

(1072,'行業配置收益','Sector Attribution',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/attribution/sector',
 '單組合區間Brinson歸因：配置/選股/交互效應，申萬/中信/內部'),

(1073,'行業超配情況','Sector Overweight',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/attribution/sector-overweight',
 '單組合區間月末時點行業配置比例 vs 基準，超配/低配'),

(1074,'個券損益前十大','Top 10 Winners',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/attribution/top-winners',
 '單組合區間損益前十大：絕對收益/貢獻/持倉天數/日均佔淨值'),

(1075,'個券損益後十大','Top 10 Losers',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/attribution/top-losers',
 '單組合區間損益後十大，風控覆盤'),

(1076,'日均十大重倉','Avg Top 10 Holdings',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/attribution/top-holdings-avg',
 '單組合區間日均十大重倉個券：收益/貢獻/持倉天數'),

(1077,'固收利率歸因','FI Rate Attribution',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/attribution/fi-rate',
 '單組合區間固收利率曲線效應拆解'),

(1078,'固收利差歸因','FI Spread Attribution',
 TRUE,FALSE,FALSE,TRUE,
 '/api/v1/attribution/fi-spread',
 '單組合區間固收信用利差效應+持有效應+選券效應'),

-- 投資月報
(1081,'月報-行業配置一級','Monthly Sector L1',
 TRUE,FALSE,TRUE,FALSE,
 '/api/v1/report/monthly/sector-l1',
 '單組合時點內部一級行業佔股票淨值比'),

(1082,'月報-行業配置二級','Monthly Sector L2',
 TRUE,FALSE,TRUE,FALSE,
 '/api/v1/report/monthly/sector-l2',
 '單組合時點內部二級行業佔股票淨值比'),

(1083,'月報-前十大持倉','Monthly Top Holdings',
 TRUE,FALSE,TRUE,FALSE,
 '/api/v1/report/monthly/top-holdings',
 '前十大佔比，標識是否新進前十大（vs上月末）'),

(1084,'月報-持倉調出','Monthly Dropped Holdings',
 TRUE,FALSE,TRUE,FALSE,
 '/api/v1/report/monthly/dropped-holdings',
 '上月末前十大中本月末不再持有的股票'),

(1085,'月報-大額交易','Monthly Large Trades',
 TRUE,FALSE,TRUE,FALSE,
 '/api/v1/report/monthly/large-trades',
 '本月佔比超淨值0.5%以上的買賣明細'),

-- 市場數據
(1091,'債券行情','Bond Market Quotes',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/bond-quotes',
 '債券估值/YTM，按發行人/評級/到期日段篩選'),

(1092,'收益率曲線','Yield Curves',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/yield-curves',
 'HIBOR/SHIBOR/國債/信用各期限，曲線圖展示'),

(1093,'負面信息','Credit Negative News',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/credit-news',
 '報告主體/負面類別/評級，持倉關聯標識'),

(1094,'新債發行','Bond Issuance',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/bond-issuance',
 '近期新發債券：發行人/規模/期限/評級'),

(1095,'股票行情','Equity Quotes',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/equity-quotes',
 '股票收盤/漲跌幅/成交量'),

(1096,'行業指數表現','Sector Index Performance',
 FALSE,FALSE,FALSE,TRUE,
 '/api/v1/market/sector-index',
 '申萬/中信/GICS行業指數區間漲跌幅'),

(1097,'股票股息','Stock Dividends',
 FALSE,FALSE,FALSE,TRUE,
 '/api/v1/market/stock-dividends',
 '區間內股息/送股/資本公積轉增記錄'),

(1098,'指數行情','Index Quotes',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/index-quotes',
 '主要指數每日收盤/PE/PB'),

(1099,'指數成分','Index Components',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/index-components',
 '指數成分股及權重'),

(1100,'外匯匯率','FX Rates',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/fx-rates',
 '即期+遠期匯率，主要貨幣對HKD'),

(1101,'HIBOR利率','HIBOR Rates',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/hibor',
 'HIBOR各期限每日報價'),

(1102,'SHIBOR利率','SHIBOR Rates',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/market/shibor',
 'SHIBOR各期限每日報價'),

-- 風控預警
(1111,'今日預警','Today Risk Alerts',
 FALSE,FALSE,TRUE,FALSE,
 '/api/v1/alerts/today',
 '未處理預警：嚴重程度/觸發規則/組合/已觸發時間'),

(1112,'預警歷史','Alert History',
 FALSE,FALSE,FALSE,TRUE,
 '/api/v1/alerts/history',
 '歷史預警：觸發/處置/結果'),

(1113,'審核工作流','Review Workflow',
 FALSE,FALSE,FALSE,FALSE,
 '/api/v1/workflow/reviews',
 '待審/已審/已拒，支持批准/拒絕/升級'),

-- 可比分析
(1121,'業績簡報','Performance Brief',
 FALSE,TRUE,TRUE,FALSE,
 '/api/v1/peer/performance-brief',
 '多組合時點：淨資產/股票佔比/年初以來收益率/換手率'),

(1122,'同類排名','Peer Ranking',
 FALSE,TRUE,FALSE,TRUE,
 '/api/v1/peer/ranking',
 '可比組內收益率/分位數排名'),

(1123,'比較組管理','Peer Group Management',
 FALSE,FALSE,FALSE,FALSE,
 '/api/v1/peer/groups',
 '新增/編輯/歸檔比較組，管理成員基金列表'),

-- 系統設置
(1131,'用戶管理','User Management',
 FALSE,FALSE,FALSE,FALSE,
 '/api/v1/admin/users',
 'CRUD用戶：MAC/組合權限/鎖定/角色'),

(1132,'組合管理','Portfolio Management',
 FALSE,FALSE,FALSE,FALSE,
 '/api/v1/admin/portfolios',
 '組合主數據維護'),

(1133,'菜單配置','Menu Config',
 FALSE,FALSE,FALSE,FALSE,
 '/api/v1/admin/menus',
 '菜單樹維護/角色授權'),

(1134,'查詢管理','Query Management',
 FALSE,FALSE,FALSE,FALSE,
 '/api/v1/admin/queries',
 'GeneralQuery配置'),

(1135,'列格式化','Column Formats',
 FALSE,FALSE,FALSE,FALSE,
 '/api/v1/admin/column-formats',
 '報表列定義管理')

ON CONFLICT (query_id) DO NOTHING;

-- ============================================================
-- 菜單-查詢映射（para_menu_query）
-- ============================================================
INSERT INTO fsi.para_menu_query (menu_id, query_id, tab_order, tab_name) VALUES
('01020101',1001,1,NULL), ('01020102',1002,1,NULL),
('01020103',1003,1,NULL), ('01020104',1004,1,NULL),
('01020105',1005,1,NULL), ('01020106',1006,1,NULL),
('01020107',1007,1,NULL), ('01020108',1008,1,NULL),
('01020109',1009,1,NULL), ('01020110',1010,1,NULL),
('01020111',1011,1,NULL), ('01020112',1012,1,NULL),
('01020201',1021,1,NULL), ('01020202',1022,1,NULL),
('01020203',1023,1,NULL), ('01020204',1024,1,NULL),
('01020205',1025,1,NULL), ('01020206',1026,1,NULL),
('01020207',1027,1,NULL), ('01020208',1028,1,NULL),
('01020209',1029,1,NULL), ('01020210',1030,1,NULL),
('01020301',1031,1,NULL), ('01020302',1032,1,NULL),
('01020303',1033,1,NULL), ('01020304',1034,1,NULL),
('01020305',1035,1,NULL), ('01020306',1036,1,NULL),
('01020307',1037,1,NULL), ('01020308',1038,1,NULL),
('01020309',1039,1,NULL), ('01020310',1040,1,NULL),
('01020311',1041,1,NULL),
('01020401',1051,1,NULL), ('01020402',1052,1,NULL),
('01020403',1053,1,NULL), ('01020404',1054,1,NULL),
('01020405',1055,1,NULL), ('01020406',1056,1,NULL),
('01020407',1057,1,NULL), ('01020408',1058,1,NULL),
('01020409',1059,1,NULL), ('01020410',1060,1,NULL),
('01020501',1061,1,NULL), ('01020502',1062,1,NULL),
('01020503',1063,1,NULL), ('01020504',1064,1,NULL),
('01020505',1065,1,NULL), ('01020506',1066,1,NULL),
('01020507',1067,1,NULL),
('01020601',1071,1,NULL), ('01020602',1072,1,NULL),
('01020603',1073,1,NULL), ('01020604',1074,1,NULL),
('01020605',1075,1,NULL), ('01020606',1076,1,NULL),
('01020607',1077,1,NULL), ('01020608',1078,1,NULL),
-- 月報5張子表掛同一菜單節點
('01020701',1081,1,NULL), ('01020702',1082,1,NULL),
('01020703',1083,1,NULL), ('01020704',1084,1,NULL),
('01020705',1085,1,NULL),
-- 市場數據
('01030101',1091,1,NULL), ('01030102',1092,1,NULL),
('01030103',1093,1,NULL), ('01030104',1094,1,NULL),
('01030201',1095,1,NULL), ('01030202',1096,1,NULL),
('01030203',1097,1,NULL),
('01030301',1098,1,NULL), ('01030302',1099,1,NULL),
('01030401',1100,1,NULL), ('01030402',1101,1,NULL),
('01030403',1102,1,NULL),
-- 預警/可比/設置
('01040100',1111,1,NULL), ('01040200',1112,1,NULL),
('01040300',1113,1,NULL),
('01050100',1121,1,NULL), ('01050200',1122,1,NULL),
('01050300',1123,1,NULL),
('01060100',1131,1,NULL), ('01060200',1132,1,NULL),
('01060300',1133,1,NULL), ('01060400',1134,1,NULL),
('01060500',1135,1,NULL)
ON CONFLICT DO NOTHING;
