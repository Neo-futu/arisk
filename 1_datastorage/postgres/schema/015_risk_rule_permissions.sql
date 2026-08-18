-- ARISK 风控规则新增表运行时权限
-- 独立迁移确保已执行过 013/014 的环境也能获得授权。

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE fsi.para_risk_rule_attachment TO fsi_user;
GRANT USAGE, SELECT ON SEQUENCE fsi.para_risk_rule_attachment_attachment_id_seq TO fsi_user;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE fsi.para_risk_rule_application TO fsi_user;
GRANT USAGE, SELECT ON SEQUENCE fsi.para_risk_rule_application_application_id_seq TO fsi_user;
