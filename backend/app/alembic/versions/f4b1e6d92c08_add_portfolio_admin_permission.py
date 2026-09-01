"""Add portfolio.admin permission (portfolio master-data CRUD).

Gates create/update/delete of portfolios themselves (fsi.para_portfolio) in the
data-management center. A global admin capability (a new portfolio has no
per-portfolio grant yet); granted to SYSTEM_ADMIN, superusers bypass.

Revision ID: f4b1e6d92c08
Revises: e2a9c4d70f31
Create Date: 2026-09-01 00:00:00.000000
"""

from alembic import op

revision = "f4b1e6d92c08"
down_revision = "e2a9c4d70f31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO iam.permission (id, name, code, description, created_at)
        VALUES (
          '10000000-0000-4000-8000-000000000010',
          '组合主数据管理', 'portfolio.admin',
          '新建/编辑/停用/删除组合主数据（para_portfolio）', NOW()
        )
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          description = EXCLUDED.description
        """
    )
    op.execute(
        """
        INSERT INTO iam.role_permission (role_id, permission_id, created_at)
        SELECT r.id, p.id, NOW()
        FROM iam.role r
        JOIN iam.permission p ON p.code = 'portfolio.admin'
        WHERE r.code = 'SYSTEM_ADMIN'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM iam.role_permission
        WHERE permission_id IN (SELECT id FROM iam.permission WHERE code = 'portfolio.admin')
        """
    )
    op.execute("DELETE FROM iam.permission WHERE code = 'portfolio.admin'")
