"""Sync iam.menu with current ARISK platform navigation.

Updates Chinese names / sort orders for all first-level modules used by the
sidebar, grants missing menus to SYSTEM_ADMIN (and core business roles), and
hides the obsolete standalone positions entry (now under data-management).
"""

from __future__ import annotations

from alembic import op

revision = "e4b9c2a71f55"
down_revision = "d3a7b1e84c20"
branch_labels = None
depends_on = None


# (id, name, code, path, sort_order, release_stage, is_active)
# IDs must match prior seed / feature migrations.
MENUS: list[tuple[str, str, str, str, int, str, bool]] = [
    ("12000000-0000-4000-8000-000000000001", "工作台", "dashboard", "/", 10, "GA", True),
    ("12000000-0000-4000-8000-000000000020", "组合驾驶舱", "portfolio-cockpit", "/portfolio-cockpit", 20, "GA", True),
    ("12000000-0000-4000-8000-000000000002", "投资风险分析", "investment-risk", "/investment-risk", 30, "GA", True),
    ("12000000-0000-4000-8000-000000000021", "组合配置测算", "portfolio-opt", "/portfolio-opt", 40, "GA", True),
    ("12000000-0000-4000-8000-000000000022", "风险情景分析", "risk-testing", "/risk-testing", 50, "GA", True),
    ("12000000-0000-4000-8000-000000000015", "数据管理中心", "data-management", "/data-management", 60, "GA", True),
    ("12000000-0000-4000-8000-000000000017", "市场数据与指标", "indicator-explorer", "/indicator-explorer", 70, "GA", True),
    ("12000000-0000-4000-8000-000000000019", "SQL 资产库", "sql-library", "/sql-library", 80, "GA", True),
    ("12000000-0000-4000-8000-000000000018", "估值与损益", "valuation", "/valuation", 90, "GA", True),
    ("12000000-0000-4000-8000-000000000023", "交易管理", "trading", "/trading", 100, "GA", True),
    ("12000000-0000-4000-8000-000000000024", "风险治理", "risk-governance", "/risk-governance", 110, "GA", True),
    ("12000000-0000-4000-8000-000000000005", "风控规则配置", "risk-rules", "/risk-rules", 120, "GA", True),
    ("12000000-0000-4000-8000-000000000004", "合规核查", "compliance", "/compliance", 130, "GA", True),
    ("12000000-0000-4000-8000-000000000006", "报表中心", "reports", "/reports", 140, "GA", True),
    ("12000000-0000-4000-8000-000000000007", "定时任务", "schedules", "/schedules", 150, "GA", True),
    ("12000000-0000-4000-8000-000000000008", "自动风控", "autorisk", "/autorisk", 160, "GA", True),
    ("12000000-0000-4000-8000-000000000009", "AI 助手", "chat", "/chat", 170, "GA", True),
    ("12000000-0000-4000-8000-000000000010", "专家知识库", "expert", "/expert", 180, "GA", True),
    ("12000000-0000-4000-8000-000000000011", "用户与权限管理", "admin", "/admin", 200, "GA", True),
    ("12000000-0000-4000-8000-000000000016", "系统配置", "system-config", "/system-config", 210, "GA", True),
    ("12000000-0000-4000-8000-000000000012", "API Key 管理", "api-keys", "/api-keys", 220, "GA", True),
    ("12000000-0000-4000-8000-000000000013", "通知中心", "notifications", "/notifications", 230, "GA", True),
    ("12000000-0000-4000-8000-000000000014", "设置", "settings", "/settings", 240, "GA", True),
    # Obsolete standalone entry (holdings live under data-management).
    ("12000000-0000-4000-8000-000000000003", "持仓明细（已并入数据管理）", "positions", "/positions", 999, "HIDDEN", False),
]


def upgrade() -> None:
    for menu_id, name, code, path, sort_order, stage, is_active in MENUS:
        active_sql = "TRUE" if is_active else "FALSE"
        op.execute(
            f"""
            INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
            VALUES (
              '{menu_id}', '{name}', '{code}', '{path}', {sort_order},
              {active_sql}, '{stage}', NOW()
            )
            ON CONFLICT (code) DO UPDATE SET
              name = EXCLUDED.name,
              path = EXCLUDED.path,
              sort_order = EXCLUDED.sort_order,
              is_active = EXCLUDED.is_active,
              release_stage = EXCLUDED.release_stage
            """
        )

    # SYSTEM_ADMIN gets every active menu.
    op.execute(
        """
        INSERT INTO iam.role_menu (role_id, menu_id, created_at)
        SELECT r.id, m.id, NOW()
        FROM iam.role r
        JOIN iam.menu m ON m.is_active = TRUE
        WHERE r.code = 'SYSTEM_ADMIN'
        ON CONFLICT DO NOTHING
        """
    )

    # Business roles: core product menus (no system-admin-only pages).
    op.execute(
        """
        INSERT INTO iam.role_menu (role_id, menu_id, created_at)
        SELECT r.id, m.id, NOW()
        FROM iam.role r
        JOIN iam.menu m ON m.code IN (
          'dashboard', 'portfolio-cockpit', 'investment-risk', 'portfolio-opt',
          'risk-testing', 'data-management', 'indicator-explorer', 'sql-library',
          'valuation', 'trading', 'risk-governance', 'risk-rules', 'compliance',
          'reports', 'schedules', 'autorisk', 'chat', 'expert',
          'api-keys', 'notifications', 'settings'
        )
        WHERE r.code IN ('PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR', 'INVESTMENT_MANAGER')
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    # Keep rows; only restore the legacy positions visibility flag.
    op.execute(
        """
        UPDATE iam.menu
        SET name = '持仓明细', is_active = TRUE, release_stage = 'GA', sort_order = 30
        WHERE code = 'positions'
        """
    )
