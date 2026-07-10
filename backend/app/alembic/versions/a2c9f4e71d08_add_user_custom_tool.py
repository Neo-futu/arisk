"""Add iam.user_custom_tool — per-user custom AI tools

Revision ID: a2c9f4e71d08
Revises: f8c3d2e10a94
Create Date: 2026-07-09 00:00:00.000000

用戶可以在 Chat Agent 中定義自己的個人工具：
  - 工具名稱和描述（LLM 決定何時調用）
  - HTTP API 端點（調用 processing 或自定義服務）
  - 參數定義（JSON Schema）
  - 啟用/停用開關

這讓每個業務用戶都能擴展自己的 Chat Agent 工具集，
而不需要開發者介入。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a2c9f4e71d08'
down_revision = 'f8c3d2e10a94'
branch_labels = None
depends_on = None
IAM = "iam"


def upgrade() -> None:
    op.create_table(
        "user_custom_tool",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",      postgresql.UUID(as_uuid=True),
                  sa.ForeignKey(f"{IAM}.user.id", ondelete="CASCADE"), nullable=False),
        # 工具基本信息
        sa.Column("tool_name",    sa.String(100),  nullable=False),  # 工具 ID（snake_case）
        sa.Column("display_name", sa.String(200),  nullable=False),  # 顯示名稱
        sa.Column("description",  sa.Text(),       nullable=False),  # LLM 工具調用說明
        # 調用配置
        sa.Column("endpoint",     sa.String(500),  nullable=False),  # HTTP endpoint
        sa.Column("method",       sa.String(10),   nullable=False, server_default="GET"),
        sa.Column("parameters",   sa.Text(),       nullable=False, server_default="{}"),  # JSON Schema
        # 狀態
        sa.Column("enabled",      sa.Boolean(),    nullable=False, server_default="true"),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=IAM,
    )
    op.create_index("ix_user_custom_tool_user_id", "user_custom_tool", ["user_id"], schema=IAM)
    op.create_index(
        "uq_user_custom_tool_name",
        "user_custom_tool", ["user_id", "tool_name"],
        unique=True, schema=IAM,
    )


def downgrade() -> None:
    op.drop_table("user_custom_tool", schema=IAM)
