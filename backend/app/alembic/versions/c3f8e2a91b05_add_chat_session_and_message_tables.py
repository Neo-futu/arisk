"""Add chat_session and chat_message tables to iam schema

Revision ID: c3f8e2a91b05
Revises: b7f9a7c21d3e
Create Date: 2026-07-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c3f8e2a91b05'
down_revision = 'b7f9a7c21d3e'
branch_labels = None
depends_on = None

IAM = "iam"


def upgrade() -> None:
    op.create_table(
        "chat_session",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",    postgresql.UUID(as_uuid=True), sa.ForeignKey(f"{IAM}.user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title",      sa.String(100),  nullable=False, server_default="新對話"),
        sa.Column("agent_id",   sa.String(50),   nullable=False, server_default="general"),
        sa.Column("model_id",   sa.String(100),  nullable=False, server_default="claude-sonnet-4-6"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=IAM,
    )
    op.create_index("ix_chat_session_user_id", "chat_session", ["user_id"], schema=IAM)
    op.create_index("ix_chat_session_updated_at", "chat_session", ["updated_at"], schema=IAM)

    op.create_table(
        "chat_message",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey(f"{IAM}.chat_session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role",       sa.String(20),  nullable=False),
        sa.Column("content",    sa.Text(),      nullable=False, server_default=""),
        sa.Column("tool_calls", sa.Text(),      nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=IAM,
    )
    op.create_index("ix_chat_message_session_id", "chat_message", ["session_id"], schema=IAM)


def downgrade() -> None:
    op.drop_table("chat_message", schema=IAM)
    op.drop_table("chat_session", schema=IAM)
