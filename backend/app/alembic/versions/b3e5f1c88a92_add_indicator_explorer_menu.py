"""Add indicator-explorer menu (gray-release BETA).

Surfaces the DataJungle-style indicator explorer at /indicator-explorer. Ships
as BETA so only superusers preview it until validated; writes reuse the existing
market_data.manage permission, so no new permission is added.

Revision ID: b3e5f1c88a92
Revises: a7c2e9b41d33
Create Date: 2026-09-01 00:00:00.000000
"""

from alembic import op

revision = "b3e5f1c88a92"
down_revision = "a7c2e9b41d33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000017',
          '指标探索', 'indicator-explorer', '/indicator-explorer', 35, TRUE, 'BETA', NOW()
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
        JOIN iam.menu m ON m.code = 'indicator-explorer'
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
        WHERE menu_id IN (SELECT id FROM iam.menu WHERE code = 'indicator-explorer')
        """
    )
    op.execute("DELETE FROM iam.menu WHERE code = 'indicator-explorer'")
