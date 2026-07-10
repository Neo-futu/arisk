"""Add pgvector extension and knowledge/memory tables

Revision ID: e5f2a1c83b01
Revises: d4a1b7e92c03
Create Date: 2026-07-09 00:00:00.000000

Layer 2 — Memory & Knowledge:
  fsi.knowledge_document  — 知識文檔索引（SFC規例、基金章程、分析報告）
  fsi.knowledge_chunk     — 文檔分塊 + pgvector 嵌入向量
  iam.agent_episode       — Agent 情景記憶（過去成功/失敗分析的經驗記錄）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e5f2a1c83b01'
down_revision = 'd4a1b7e92c03'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── pgvector 擴展（可選，未安裝時降級為 JSONB 存儲嵌入向量） ──────
    import logging
    bind = op.get_bind()
    row = bind.execute(sa.text(
        "SELECT COUNT(*) FROM pg_available_extensions WHERE name='vector'"
    )).scalar()
    pgvector_available = (row or 0) > 0

    if pgvector_available:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        logging.getLogger(__name__).info("[migration] pgvector enabled")
    else:
        logging.getLogger(__name__).warning(
            "[migration] pgvector not installed — embedding stored as JSONB. "
            "Install: https://github.com/pgvector/pgvector"
        )

    # ── 知識文檔索引 ──────────────────────────────────────────────────
    op.create_table(
        "knowledge_document",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title",       sa.String(300), nullable=False),
        sa.Column("source",      sa.String(100), nullable=False),
        sa.Column("doc_type",    sa.String(50),  nullable=False),
        sa.Column("language",    sa.String(10),  nullable=False, server_default="zh-HK"),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("chunk_count", sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("has_vectors", sa.Boolean(),   nullable=False, server_default="false"),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="fsi",
    )
    op.create_index("ix_kd_source",   "knowledge_document", ["source"],   schema="fsi")
    op.create_index("ix_kd_doc_type", "knowledge_document", ["doc_type"], schema="fsi")

    # ── 文檔分塊（embedding 列根據 pgvector 可用性選擇類型） ──────────
    if pgvector_available:
        op.execute("""
            CREATE TABLE IF NOT EXISTS fsi.knowledge_chunk (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id  UUID NOT NULL REFERENCES fsi.knowledge_document(id) ON DELETE CASCADE,
                chunk_index  INTEGER NOT NULL,
                content      TEXT NOT NULL,
                embedding    vector(1536),
                token_count  INTEGER,
                metadata     JSONB DEFAULT '{}'::jsonb,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_kc_document_id ON fsi.knowledge_chunk(document_id)")
        try:
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_kc_embedding_cosine
                ON fsi.knowledge_chunk USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)
        except Exception:
            pass   # ivfflat index requires data; OK to skip on empty table
    else:
        # 降級：用 JSONB 存儲嵌入向量（不支持向量相似度索引，僅作存儲）
        op.execute("""
            CREATE TABLE IF NOT EXISTS fsi.knowledge_chunk (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id  UUID NOT NULL REFERENCES fsi.knowledge_document(id) ON DELETE CASCADE,
                chunk_index  INTEGER NOT NULL,
                content      TEXT NOT NULL,
                embedding    JSONB,
                token_count  INTEGER,
                metadata     JSONB DEFAULT '{}'::jsonb,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_kc_document_id ON fsi.knowledge_chunk(document_id)")

    # ── Agent 情景記憶（Episodic Memory） ─────────────────────────────
    # 記錄 Agent 過去成功完成的分析任務，作為 few-shot 示例供未來參考
    op.create_table(
        "agent_episode",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",     postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("iam.user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id",    sa.String(50),  nullable=False),
        sa.Column("model_id",    sa.String(100), nullable=False),
        sa.Column("query",       sa.Text(),      nullable=False),   # 用戶原始問題
        sa.Column("summary",     sa.Text(),      nullable=True),    # Agent 輸出摘要
        sa.Column("tool_calls",  sa.Text(),      nullable=True),    # JSON: 使用了哪些工具
        sa.Column("embedding",   sa.Text(),      nullable=True),    # query 的向量（JSON array）
        sa.Column("outcome",     sa.String(20),  nullable=False, server_default="success"),  # success|failure
        sa.Column("fund_id",     sa.String(20),  nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="iam",
    )
    op.create_index("ix_ae_agent_id",   "agent_episode", ["agent_id"],   schema="iam")
    op.create_index("ix_ae_user_id",    "agent_episode", ["user_id"],    schema="iam")
    op.create_index("ix_ae_created_at", "agent_episode", ["created_at"], schema="iam")


def downgrade() -> None:
    op.drop_table("agent_episode",       schema="iam")
    op.execute("DROP TABLE IF EXISTS fsi.knowledge_chunk")
    op.drop_table("knowledge_document",  schema="fsi")
    # 不 DROP pgvector extension（可能被其他表使用）
