"""Add iam.frontend_log table for client-side logging

Revision ID: d4a1b7e92c03
Revises: c3f8e2a91b05
Create Date: 2026-07-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd4a1b7e92c03'
down_revision = 'c3f8e2a91b05'
branch_labels = None
depends_on = None
IAM = "iam"


def upgrade() -> None:
    op.create_table(
        "frontend_log",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",    postgresql.UUID(as_uuid=True),
                  sa.ForeignKey(f"{IAM}.user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("log_type",   sa.String(30),  nullable=False),   # user_action|operation|audit|error
        sa.Column("level",      sa.String(10),  nullable=False, server_default="info"),
        sa.Column("module",     sa.String(100), nullable=False),
        sa.Column("action",     sa.String(200), nullable=False),
        sa.Column("detail",     sa.Text(),      nullable=True),    # JSON string
        sa.Column("user_agent", sa.Text(),      nullable=True),
        sa.Column("url",        sa.Text(),      nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=IAM,
    )
    op.create_index("ix_frontend_log_user_id",    "frontend_log", ["user_id"],    schema=IAM)
    op.create_index("ix_frontend_log_log_type",   "frontend_log", ["log_type"],   schema=IAM)
    op.create_index("ix_frontend_log_created_at", "frontend_log", ["created_at"], schema=IAM)


def downgrade() -> None:
    op.drop_table("frontend_log", schema=IAM)
