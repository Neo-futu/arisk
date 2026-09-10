"""Add trading and risk-governance menus with unique path prefixes.

Revision ID: d3a7b1e84c20
Revises: c2e8f5a91d74
Create Date: 2026-09-09 00:00:00.000000
"""

from alembic import op

revision = "d3a7b1e84c20"
down_revision = "c2e8f5a91d74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create first-level trading and risk-governance menus."""

    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000023',
          '交易管理', 'trading', '/trading', 36, TRUE, 'GA', NOW()
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
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000024',
          '风险治理', 'risk-governance', '/risk-governance', 37, TRUE, 'GA', NOW()
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
        JOIN iam.menu m ON m.code IN ('trading', 'risk-governance')
        WHERE r.code IN (
          'PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR',
          'INVESTMENT_MANAGER', 'SYSTEM_ADMIN'
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove trading and risk-governance menus."""

    op.execute(
        """
        DELETE FROM iam.role_menu
        WHERE menu_id IN (
          SELECT id FROM iam.menu WHERE code IN ('trading', 'risk-governance')
        )
        """
    )
    op.execute("DELETE FROM iam.menu WHERE code IN ('trading', 'risk-governance')")
