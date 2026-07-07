"""Move auth tables to iam schema and add RBAC base tables

Revision ID: b7f9a7c21d3e
Revises: fe56fa70289e
Create Date: 2026-07-07 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b7f9a7c21d3e"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


IAM_SCHEMA = "iam"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {IAM_SCHEMA}")

    # Move existing auth tables from public to iam
    op.execute('ALTER TABLE IF EXISTS "user" SET SCHEMA iam')
    op.execute("ALTER TABLE IF EXISTS item SET SCHEMA iam")

    # Keep compatibility for extension-generated UUIDs
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "role",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_iam_role_name"),
        sa.UniqueConstraint("code", name="uq_iam_role_code"),
        schema=IAM_SCHEMA,
    )

    op.create_table(
        "permission",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_iam_permission_name"),
        sa.UniqueConstraint("code", name="uq_iam_permission_code"),
        schema=IAM_SCHEMA,
    )

    op.create_table(
        "menu",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], [f"{IAM_SCHEMA}.menu.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_iam_menu_code"),
        schema=IAM_SCHEMA,
    )

    op.create_table(
        "user_role",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [f"{IAM_SCHEMA}.user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], [f"{IAM_SCHEMA}.role.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        schema=IAM_SCHEMA,
    )

    op.create_table(
        "role_permission",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["role_id"], [f"{IAM_SCHEMA}.role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["permission_id"], [f"{IAM_SCHEMA}.permission.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
        schema=IAM_SCHEMA,
    )

    op.create_table(
        "role_menu",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menu_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["role_id"], [f"{IAM_SCHEMA}.role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["menu_id"], [f"{IAM_SCHEMA}.menu.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "menu_id"),
        schema=IAM_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("role_menu", schema=IAM_SCHEMA)
    op.drop_table("role_permission", schema=IAM_SCHEMA)
    op.drop_table("user_role", schema=IAM_SCHEMA)

    op.drop_table("menu", schema=IAM_SCHEMA)

    op.drop_table("permission", schema=IAM_SCHEMA)

    op.drop_table("role", schema=IAM_SCHEMA)

    # Move legacy tables back to public
    op.execute("ALTER TABLE IF EXISTS iam.item SET SCHEMA public")
    op.execute('ALTER TABLE IF EXISTS iam."user" SET SCHEMA public')

    op.execute("DROP SCHEMA IF EXISTS iam")
