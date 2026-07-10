"""Move chat/AI tables from iam/fsi to new chatdb schema

Revision ID: b9e1f3c84d27
Revises: a2c9f4e71d08
Create Date: 2026-07-09 00:00:00.000000

將 AI/Chat 數據表從 iam/fsi 遷移到獨立的 chatdb schema：

從 iam 移出（AI 對話和記憶數據）：
  chat_session / chat_message      — 個人聊天歷史
  agent_episode                    — AI 情景記憶
  frontend_log                     — 前端日誌

從 fsi 移出（AI 知識庫數據）：
  knowledge_document / knowledge_chunk  — 知識庫（3_skills 索引）

保留在 iam（用戶身份和配置）：
  user / role / permission / menu / item   — 身份認證/RBAC
  user_agent_config                        — 用戶 AI 偏好設置（屬於用戶配置）
  user_custom_tool                         — 用戶個人工具定義（屬於用戶配置）

保留在 fsi（業務數據）：
  97張業務表（持倉/風控/NAV等）
"""
from alembic import op

revision = 'b9e1f3c84d27'
down_revision = 'a2c9f4e71d08'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS chatdb")

    # 按 FK 依賴順序移動（被依賴的先移，依賴方後移）
    # 知識庫（fsi → chatdb，無跨組 FK）
    op.execute("ALTER TABLE fsi.knowledge_document SET SCHEMA chatdb")
    op.execute("ALTER TABLE fsi.knowledge_chunk     SET SCHEMA chatdb")

    # AI 數據（iam → chatdb，FK 指向 iam.user，跨 schema FK PostgreSQL 支持）
    # 注：user_agent_config / user_custom_tool 保留在 iam（屬於用戶配置）
    op.execute("ALTER TABLE iam.agent_episode SET SCHEMA chatdb")
    op.execute("ALTER TABLE iam.frontend_log  SET SCHEMA chatdb")

    # 聊天歷史（chat_session 先移，chat_message 依賴它）
    op.execute("ALTER TABLE iam.chat_session SET SCHEMA chatdb")
    op.execute("ALTER TABLE iam.chat_message SET SCHEMA chatdb")


def downgrade() -> None:
    # 反向移回
    op.execute("ALTER TABLE chatdb.chat_message     SET SCHEMA iam")
    op.execute("ALTER TABLE chatdb.chat_session     SET SCHEMA iam")
    op.execute("ALTER TABLE chatdb.frontend_log  SET SCHEMA iam")
    op.execute("ALTER TABLE chatdb.agent_episode SET SCHEMA iam")
    op.execute("ALTER TABLE chatdb.knowledge_chunk    SET SCHEMA fsi")
    op.execute("ALTER TABLE chatdb.knowledge_document SET SCHEMA fsi")
    op.execute("DROP SCHEMA IF EXISTS chatdb")
