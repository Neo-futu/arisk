"""Add iam.user_api_key for local/API client authentication.

Revision ID: c7a4e8d12f60
Revises: b9e1f3c84d27
Create Date: 2026-07-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c7a4e8d12f60"
down_revision = "b9e1f3c84d27"
branch_labels = None
depends_on = None
IAM = "iam"


def upgrade() -> None:
    op.create_table(
        "user_api_key",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{IAM}.user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("last_four", sa.String(4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        schema=IAM,
    )
    op.create_index("ix_user_api_key_user_id", "user_api_key", ["user_id"], schema=IAM)
    op.create_index(
        "ix_user_api_key_key_hash",
        "user_api_key",
        ["key_hash"],
        unique=True,
        schema=IAM,
    )


def downgrade() -> None:
    op.drop_table("user_api_key", schema=IAM)
