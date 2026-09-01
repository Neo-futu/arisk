"""Add portfolio cockpit menu (gray-release BETA).

Surfaces Module 2.1 (portfolio list & fundamentals cockpit) at /portfolio-cockpit,
right after the dashboard. Ships as BETA so only superusers preview it until
validated. Read-only; portfolio-scoped view access, so no new permission is added.

Revision ID: e2a9c4d70f31
Revises: d1f8b3c60a27
Create Date: 2026-09-01 00:00:00.000000
"""

from alembic import op

revision = "e2a9c4d70f31"
down_revision = "d1f8b3c60a27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000020',
          '组合驾驶舱', 'portfolio-cockpit', '/portfolio-cockpit', 15, TRUE, 'BETA', NOW()
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
        JOIN iam.menu m ON m.code = 'portfolio-cockpit'
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
        WHERE menu_id IN (SELECT id FROM iam.menu WHERE code = 'portfolio-cockpit')
        """
    )
    op.execute("DELETE FROM iam.menu WHERE code = 'portfolio-cockpit'")
