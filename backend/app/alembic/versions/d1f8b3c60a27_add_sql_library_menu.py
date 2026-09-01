"""Add SQL asset library menu (gray-release BETA).

Surfaces the SQL asset library at /sql-library (feature 11 / SQL 资产化). Ships as
BETA so only superusers preview it until validated. Read-only; login access only,
so no new permission is added.

Revision ID: d1f8b3c60a27
Revises: c9d7a2f45e18
Create Date: 2026-09-01 00:00:00.000000
"""

from alembic import op

revision = "d1f8b3c60a27"
down_revision = "c9d7a2f45e18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000019',
          'SQL 资产库', 'sql-library', '/sql-library', 95, TRUE, 'BETA', NOW()
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
        JOIN iam.menu m ON m.code = 'sql-library'
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
        WHERE menu_id IN (SELECT id FROM iam.menu WHERE code = 'sql-library')
        """
    )
    op.execute("DELETE FROM iam.menu WHERE code = 'sql-library'")
