"""Add data-management menu and market-data permission.

Revision ID: f1d4a8c72b10
Revises: e8a4c1d92f70
Create Date: 2026-09-01 00:00:00.000000
"""

from alembic import op

revision = "f1d4a8c72b10"
down_revision = "e8a4c1d92f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO iam.permission (id, name, code, description, created_at)
        VALUES (
          '10000000-0000-4000-8000-000000000008',
          '市场数据维护', 'market_data.manage',
          '维护共享市场行情数据；变更写入审计日志', NOW()
        )
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          description = EXCLUDED.description
        """
    )
    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000015',
          '数据管理中心', 'data-management', '/data-management', 25, TRUE, NOW()
        )
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          path = EXCLUDED.path,
          sort_order = EXCLUDED.sort_order,
          is_active = TRUE
        """
    )
    op.execute(
        """
        INSERT INTO iam.role_menu (role_id, menu_id, created_at)
        SELECT r.id, m.id, NOW()
        FROM iam.role r
        JOIN iam.menu m ON m.code = 'data-management'
        WHERE r.code IN (
          'PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR',
          'INVESTMENT_MANAGER', 'SYSTEM_ADMIN'
        )
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO iam.role_permission (role_id, permission_id, created_at)
        SELECT r.id, p.id, NOW()
        FROM iam.role r
        JOIN iam.permission p ON p.code = 'market_data.manage'
        WHERE r.code = 'SYSTEM_ADMIN'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM iam.role_menu
        WHERE menu_id IN (SELECT id FROM iam.menu WHERE code = 'data-management')
        """
    )
    op.execute(
        """
        DELETE FROM iam.role_permission
        WHERE permission_id IN (
          SELECT id FROM iam.permission WHERE code = 'market_data.manage'
        )
        """
    )
    op.execute("DELETE FROM iam.menu WHERE code = 'data-management'")
    op.execute("DELETE FROM iam.permission WHERE code = 'market_data.manage'")
