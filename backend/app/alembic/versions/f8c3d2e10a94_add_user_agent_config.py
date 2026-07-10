"""Add iam.user_agent_config — per-user AI Agent configuration

Revision ID: f8c3d2e10a94
Revises: e5f2a1c83b01
Create Date: 2026-07-09 00:00:00.000000

每個用戶擁有一個專屬 AI Agent 配置記錄：
  - 默認模型、默認 Agent 角色
  - 個人自定義指令（注入每次對話的 system prompt）
  - 工具啟用清單、記憶開關
  - Agent 自定義名稱（用戶可命名自己的助理）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f8c3d2e10a94'
down_revision = 'e5f2a1c83b01'
branch_labels = None
depends_on = None
IAM = "iam"


def upgrade() -> None:
    op.create_table(
        "user_agent_config",
        # 主鍵 = user_id（每個用戶唯一一個 Agent 配置）
        sa.Column("user_id",
                  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey(f"{IAM}.user.id", ondelete="CASCADE"),
                  primary_key=True),
        # Agent 基本設置
        sa.Column("agent_name",            sa.String(100),  nullable=True),   # 用戶為自己的 Agent 起的名字
        sa.Column("default_agent_id",      sa.String(50),   nullable=False, server_default="general"),
        sa.Column("default_model_id",      sa.String(100),  nullable=False, server_default="claude-sonnet-4-6"),
        # 個人化指令（注入 system prompt，如「我是博匯基金的風控主任，主要關注 BHMMF001」）
        sa.Column("custom_instructions",   sa.Text(),       nullable=True),
        # 工具與記憶控制
        sa.Column("tools_enabled",         sa.Text(),       nullable=False, server_default="[]"),    # JSON array，空=全部啟用
        sa.Column("memory_enabled",        sa.Boolean(),    nullable=False, server_default="true"),  # 情景記憶開關
        sa.Column("rag_enabled",           sa.Boolean(),    nullable=False, server_default="true"),  # RAG 搜索開關
        sa.Column("max_context_turns",     sa.Integer(),    nullable=False, server_default="40"),    # 短期記憶最大輪數
        # 時間戳
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=IAM,
    )


def downgrade() -> None:
    op.drop_table("user_agent_config", schema=IAM)
