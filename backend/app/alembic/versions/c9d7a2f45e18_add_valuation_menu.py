"""Add valuation & P&L menu (gray-release BETA).

Surfaces Module 4 (portfolio valuation report + period P&L) at /valuation. Ships
as BETA so only superusers preview it until validated. Read-only; access uses the
existing portfolio.view portfolio-scoped grant, so no new permission is added.

Revision ID: c9d7a2f45e18
Revises: b3e5f1c88a92
Create Date: 2026-09-01 00:00:00.000000
"""

from alembic import op

revision = "c9d7a2f45e18"
down_revision = "b3e5f1c88a92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000018',
          '组合估值', 'valuation', '/valuation', 55, TRUE, 'BETA', NOW()
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
        JOIN iam.menu m ON m.code = 'valuation'
        WHERE r.code IN (
          'PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR',
          'INVESTMENT_MANAGER', 'SYSTEM_ADMIN'
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM iam.role_menu
        WHERE menu_id IN (SELECT id FROM iam.menu WHERE code = 'valuation')
        """
    )
    op.execute("DELETE FROM iam.menu WHERE code = 'valuation'")
