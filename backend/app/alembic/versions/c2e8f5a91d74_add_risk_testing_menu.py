"""Add standalone professional risk testing menu.

The module reuses existing portfolio-level authorization and grants menu access
to the existing investment/viewer roles.  It is released as BETA for controlled
validation of FinancePy pricing and risk assumptions.

Revision ID: c2e8f5a91d74
Revises: a1c3e7f52b94
Create Date: 2026-09-02 00:00:00.000000
"""

from alembic import op

revision = "c2e8f5a91d74"
down_revision = "a1c3e7f52b94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create and grant the existing-role risk testing menu."""

    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000022',
          '风险测试', 'risk-testing', '/risk-testing', 25, TRUE, 'BETA', NOW()
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
        JOIN iam.menu m ON m.code = 'risk-testing'
        WHERE r.code IN (
          'PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR',
          'INVESTMENT_MANAGER', 'SYSTEM_ADMIN'
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove the risk testing menu and role mappings."""

    op.execute(
        """
        DELETE FROM iam.role_menu
        WHERE menu_id IN (SELECT id FROM iam.menu WHERE code = 'risk-testing')
        """
    )
    op.execute("DELETE FROM iam.menu WHERE code = 'risk-testing'")
