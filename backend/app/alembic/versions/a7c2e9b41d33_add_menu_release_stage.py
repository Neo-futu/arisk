"""Add menu release_stage (gray-release), system-config menu and permission.

Introduces a release-stage dimension on iam.menu so half-built modules can be
hidden from regular users (BETA = only superusers preview) or taken down
(HIDDEN) via a system-config page, independently of per-role menu grants.

Revision ID: a7c2e9b41d33
Revises: f1d4a8c72b10
Create Date: 2026-09-01 00:00:00.000000
"""

from alembic import op

revision = "a7c2e9b41d33"
down_revision = "f1d4a8c72b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Gray-release dimension: GA=released, BETA=superuser preview, HIDDEN=taken down.
    op.execute(
        """
        ALTER TABLE iam.menu
        ADD COLUMN IF NOT EXISTS release_stage VARCHAR(8) NOT NULL DEFAULT 'GA'
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'menu_release_stage_check'
          ) THEN
            ALTER TABLE iam.menu
            ADD CONSTRAINT menu_release_stage_check
            CHECK (release_stage IN ('GA', 'BETA', 'HIDDEN'));
          END IF;
        END $$;
        """
    )
    # The in-flight data-management module ships gray (superuser preview only).
    op.execute(
        "UPDATE iam.menu SET release_stage = 'BETA' WHERE code = 'data-management'"
    )

    # System-config management permission (drives the gray-release page).
    op.execute(
        """
        INSERT INTO iam.permission (id, name, code, description, created_at)
        VALUES (
          '10000000-0000-4000-8000-000000000009',
          '系统配置管理', 'system.config.manage',
          '管理模块灰度发布阶段与菜单前端显示开关', NOW()
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
        JOIN iam.permission p ON p.code = 'system.config.manage'
        WHERE r.code = 'SYSTEM_ADMIN'
        ON CONFLICT DO NOTHING
        """
    )

    # System-config menu entry (GA; only surfaced to system-config managers).
    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, release_stage, created_at)
        VALUES (
          '12000000-0000-4000-8000-000000000016',
          '系统配置', 'system-config', '/system-config', 240, TRUE, 'GA', NOW()
        )
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          path = EXCLUDED.path,
          sort_order = EXCLUDED.sort_order,
          is_active = TRUE,
          release_stage = 'GA'
        """
    )
    op.execute(
        """
        INSERT INTO iam.role_menu (role_id, menu_id, created_at)
        SELECT r.id, m.id, NOW()
        FROM iam.role r
        JOIN iam.menu m ON m.code = 'system-config'
        WHERE r.code = 'SYSTEM_ADMIN'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM iam.role_menu
        WHERE menu_id IN (SELECT id FROM iam.menu WHERE code = 'system-config')
        """
    )
    op.execute("DELETE FROM iam.menu WHERE code = 'system-config'")
    op.execute(
        """
        DELETE FROM iam.role_permission
        WHERE permission_id IN (
          SELECT id FROM iam.permission WHERE code = 'system.config.manage'
        )
        """
    )
    op.execute("DELETE FROM iam.permission WHERE code = 'system.config.manage'")
    op.execute(
        "ALTER TABLE iam.menu DROP CONSTRAINT IF EXISTS menu_release_stage_check"
    )
    op.execute("ALTER TABLE iam.menu DROP COLUMN IF EXISTS release_stage")
