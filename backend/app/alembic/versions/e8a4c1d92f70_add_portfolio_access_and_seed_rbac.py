"""Add scoped portfolio access and seed platform RBAC.

Revision ID: e8a4c1d92f70
Revises: 20260803_0002
Create Date: 2026-08-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e8a4c1d92f70"
down_revision = "20260803_0002"
branch_labels = None
depends_on = None

IAM = "iam"


def upgrade() -> None:
    op.create_table(
        "user_portfolio_access",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("port_id", sa.String(length=16), nullable=False),
        sa.Column("access_level", sa.String(length=16), nullable=False),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("access_level IN ('VIEW', 'MANAGE')", name="ck_user_portfolio_access_level"),
        sa.ForeignKeyConstraint(["user_id"], [f"{IAM}.user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], [f"{IAM}.user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("user_id", "port_id"),
        schema=IAM,
    )
    op.create_index(
        "ix_user_portfolio_access_port_id",
        "user_portfolio_access",
        ["port_id"],
        schema=IAM,
    )

    op.execute(
        """
        INSERT INTO iam.permission (id, name, code, description, created_at)
        VALUES
          ('10000000-0000-4000-8000-000000000001', '查看组合', 'portfolio.view', '查看已授权组合及其风险、持仓和报表', NOW()),
          ('10000000-0000-4000-8000-000000000002', '组合监督', 'portfolio.oversight', '总监级组合监督与合规查看', NOW()),
          ('10000000-0000-4000-8000-000000000003', '投资管理', 'portfolio.manage', '管理已授权组合', NOW()),
          ('10000000-0000-4000-8000-000000000004', '投资交易', 'trade.manage', '对已授权组合执行交易前检查和交易管理', NOW()),
          ('10000000-0000-4000-8000-000000000005', '风控规则管理', 'risk_rules.manage', '配置风控规则及其应用范围', NOW()),
          ('10000000-0000-4000-8000-000000000006', '用户授权管理', 'iam.access.manage', '配置用户角色、菜单和组合权限', NOW()),
          ('10000000-0000-4000-8000-000000000007', '角色菜单管理', 'iam.role.manage', '配置角色的菜单和功能权限', NOW())
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          description = EXCLUDED.description
        """
    )

    op.execute(
        """
        INSERT INTO iam.role (id, name, code, description, is_active, created_at)
        VALUES
          ('11000000-0000-4000-8000-000000000001', '平台查看者', 'PORTFOLIO_VIEWER', '查看获授权组合', TRUE, NOW()),
          ('11000000-0000-4000-8000-000000000002', '投资总监', 'INVESTMENT_DIRECTOR', '查看和监督获授权组合', TRUE, NOW()),
          ('11000000-0000-4000-8000-000000000003', '投资经理', 'INVESTMENT_MANAGER', '投资管理与交易获授权组合', TRUE, NOW()),
          ('11000000-0000-4000-8000-000000000004', '系统管理员', 'SYSTEM_ADMIN', '用户、角色、菜单及组合授权管理', TRUE, NOW())
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          description = EXCLUDED.description,
          is_active = TRUE
        """
    )

    op.execute(
        """
        INSERT INTO iam.menu (id, name, code, path, sort_order, is_active, created_at)
        VALUES
          ('12000000-0000-4000-8000-000000000001', '风控仪表板', 'dashboard', '/', 10, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000002', '投资风险分析', 'investment-risk', '/investment-risk', 20, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000003', '持仓明细', 'positions', '/positions', 30, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000004', '合规核查', 'compliance', '/compliance', 40, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000005', '风控规则配置', 'risk-rules', '/risk-rules', 50, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000006', '报表中心', 'reports', '/reports', 60, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000007', '定时任务', 'schedules', '/schedules', 70, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000008', '自动风控', 'autorisk', '/autorisk', 80, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000009', 'Agent Chat', 'chat', '/chat', 90, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000010', '专家知识库', 'expert', '/expert', 100, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000011', '用户权限管理', 'admin', '/admin', 200, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000012', 'API Key 管理', 'api-keys', '/api-keys', 210, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000013', '通知中心', 'notifications', '/notifications', 220, TRUE, NOW()),
          ('12000000-0000-4000-8000-000000000014', '设置', 'settings', '/settings', 230, TRUE, NOW())
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          path = EXCLUDED.path,
          sort_order = EXCLUDED.sort_order,
          is_active = TRUE
        """
    )

    op.execute(
        """
        INSERT INTO iam.role_permission (role_id, permission_id, created_at)
        SELECT r.id, p.id, NOW()
        FROM iam.role r
        JOIN iam.permission p ON (
             (r.code = 'PORTFOLIO_VIEWER' AND p.code IN ('portfolio.view'))
          OR (r.code = 'INVESTMENT_DIRECTOR' AND p.code IN ('portfolio.view', 'portfolio.oversight'))
          OR (r.code = 'INVESTMENT_MANAGER' AND p.code IN ('portfolio.view', 'portfolio.manage', 'trade.manage'))
          OR (r.code = 'SYSTEM_ADMIN')
        )
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO iam.role_menu (role_id, menu_id, created_at)
        SELECT r.id, m.id, NOW()
        FROM iam.role r
        JOIN iam.menu m ON (
             (r.code IN ('PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR') AND m.code IN
                ('dashboard', 'investment-risk', 'positions', 'compliance', 'reports', 'autorisk', 'chat', 'expert', 'api-keys', 'notifications', 'settings'))
          OR (r.code = 'INVESTMENT_MANAGER' AND m.code IN
                ('dashboard', 'investment-risk', 'positions', 'compliance', 'reports', 'schedules', 'autorisk', 'chat', 'expert', 'api-keys', 'notifications', 'settings'))
          OR (r.code = 'SYSTEM_ADMIN')
        )
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO iam.user_role (user_id, role_id, created_at)
        SELECT u.id, r.id, NOW()
        FROM iam."user" u
        JOIN iam.role r ON r.code = CASE WHEN u.is_superuser THEN 'SYSTEM_ADMIN' ELSE 'PORTFOLIO_VIEWER' END
        ON CONFLICT DO NOTHING
        """
    )

    # Preserve existing access after upgrade. Administrators can narrow these grants in the UI.
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('fsi.para_portfolio') IS NOT NULL THEN
            EXECUTE $sql$
              INSERT INTO iam.user_portfolio_access
                (user_id, port_id, access_level, granted_by, created_at, updated_at)
              SELECT u.id, p.port_id, 'VIEW', NULL, NOW(), NOW()
              FROM iam."user" u
              CROSS JOIN fsi.para_portfolio p
              WHERE u.is_superuser = FALSE AND p.is_active = TRUE
              ON CONFLICT (user_id, port_id) DO NOTHING
            $sql$;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM iam.user_role
        WHERE role_id IN (SELECT id FROM iam.role WHERE code IN
          ('PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR', 'INVESTMENT_MANAGER', 'SYSTEM_ADMIN'))
        """
    )
    op.execute(
        """
        DELETE FROM iam.role_menu
        WHERE role_id IN (SELECT id FROM iam.role WHERE code IN
          ('PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR', 'INVESTMENT_MANAGER', 'SYSTEM_ADMIN'))
        """
    )
    op.execute(
        """
        DELETE FROM iam.role_permission
        WHERE role_id IN (SELECT id FROM iam.role WHERE code IN
          ('PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR', 'INVESTMENT_MANAGER', 'SYSTEM_ADMIN'))
        """
    )
    op.drop_table("user_portfolio_access", schema=IAM)
    op.execute("DELETE FROM iam.role WHERE code IN ('PORTFOLIO_VIEWER', 'INVESTMENT_DIRECTOR', 'INVESTMENT_MANAGER', 'SYSTEM_ADMIN')")
    op.execute("DELETE FROM iam.permission WHERE code IN ('portfolio.view', 'portfolio.oversight', 'portfolio.manage', 'trade.manage', 'risk_rules.manage', 'iam.access.manage', 'iam.role.manage')")
    op.execute("DELETE FROM iam.menu WHERE code IN ('dashboard', 'investment-risk', 'positions', 'compliance', 'risk-rules', 'reports', 'schedules', 'autorisk', 'chat', 'expert', 'admin', 'api-keys', 'notifications', 'settings')")
