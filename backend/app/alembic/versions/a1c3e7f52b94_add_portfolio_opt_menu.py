"""Add portfolio optimization menu (gray-release BETA).

Surfaces the PyPortfolioOpt-based optimizer (efficient frontier / Black-Litterman /
HRP) at /portfolio-opt. Ships as BETA so only superusers preview it until validated.
Read-only analysis (login only), no new permission.

Revision ID: a1c3e7f52b94
Revises: f4b1e6d92c08
Create Date: 2026-09-01 00:00:00.000000
"""

from alembic import op

revision = "a1c3e7f52b94"
down_revision = "f4b1e6d92c08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000021',
          '组合优化', 'portfolio-opt', '/portfolio-opt', 65, TRUE, 'BETA', NOW()
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
        JOIN iam.menu m ON m.code = 'portfolio-opt'
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
        WHERE menu_id IN (SELECT id FROM iam.menu WHERE code = 'portfolio-opt')
        """
    )
    op.execute("DELETE FROM iam.menu WHERE code = 'portfolio-opt'")
