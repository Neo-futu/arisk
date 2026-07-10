"""
aiagent/memory/vector_store.py — Layer 2: 長期記憶 / 知識庫 RAG

知識存儲與搜索的實現機制：

  文檔來源（3 種）
  ─────────────────────────────────────────────────────────
  3_skills/skills/*.md       → 業務領域知識（系統知識庫）
  aiagent/agents/*.md        → Agent 角色業務規則
  自定義文件（--path 參數）  → 任意 txt/md/pdf 文檔

  索引流程（index_document）
  ─────────────────────────────────────────────────────────
  原文 → 分塊（500字/塊）→ 生成 embedding → 存入 chatdb.knowledge_chunk

  搜索策略（自動適配）
  ─────────────────────────────────────────────────────────
  有 pgvector：向量相似度（60%）+ BM25 全文（40%）= 混合搜索
  無 pgvector：BM25 全文搜索（PostgreSQL 原生，始終可用）

  Embedding 模型優先級
  ─────────────────────────────────────────────────────────
  1. OpenAI text-embedding-3-small（1536d，需 OPENAI_API_KEY）
  2. sentence-transformers all-MiniLM-L6-v2（本地，無 API Key）
  3. 無模型可用 → 跳過 embedding，僅 BM25 搜索
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ── DB 連接 ───────────────────────────────────────────────────────
_RAW_DB_URL = os.getenv("DATABASE_URL") or (
    f"postgresql://{os.getenv('POSTGRES_USER','postgres')}:"
    f"{os.getenv('POSTGRES_PASSWORD','postgres')}@"
    f"{os.getenv('POSTGRES_SERVER','localhost')}:"
    f"{os.getenv('POSTGRES_PORT','5432')}/"
    f"{os.getenv('POSTGRES_DB','fsi_risk')}"
)
# asyncpg 不接受 +asyncpg scheme
DB_URL = _RAW_DB_URL.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
EMBED_DIM  = 1536
TOP_K      = 5

# ── pgvector 可用性（運行時檢測，緩存結果） ─────────────────────────
_pgvector_available: bool | None = None

async def _has_pgvector() -> bool:
    """檢測 PostgreSQL 是否安裝了 pgvector 擴展。結果緩存。"""
    global _pgvector_available
    if _pgvector_available is not None:
        return _pgvector_available
    try:
        import asyncpg
        conn = await asyncpg.connect(DB_URL)
        row = await conn.fetchval(
            "SELECT COUNT(*) FROM pg_extension WHERE extname='vector'"
        )
        await conn.close()
        _pgvector_available = (row or 0) > 0
    except Exception:
        _pgvector_available = False
    if not _pgvector_available:
        logger.info(
            "[VectorStore] pgvector 未安裝 → 使用 BM25 全文搜索模式。\n"
            "  安裝 pgvector 可啟用向量語義搜索：\n"
            "  Windows: 下載 https://github.com/pgvector/pgvector/releases\n"
            "  Linux:   apt install postgresql-17-pgvector"
        )
    return _pgvector_available


# ── Embedding 生成 ────────────────────────────────────────────────

async def embed(text: str) -> list[float] | None:
    """
    生成文本嵌入向量。若無可用模型返回 None（降級到 BM25）。
    """
    if OPENAI_KEY:
        try:
            return await _embed_openai(text)
        except Exception as exc:
            logger.warning("[VectorStore] OpenAI embed failed: %s", exc)
    try:
        return await _embed_local(text)
    except ImportError:
        logger.debug("[VectorStore] No embedding model available → BM25 only")
        return None


async def _embed_openai(text: str) -> list[float]:
    import openai
    client = openai.AsyncOpenAI(api_key=OPENAI_KEY)
    resp = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],
    )
    return resp.data[0].embedding


async def _embed_local(text: str) -> list[float]:
    """sentence-transformers 本地 embedding（384d → padding 到 1536d）。"""
    from sentence_transformers import SentenceTransformer
    import asyncio
    model = SentenceTransformer("all-MiniLM-L6-v2")
    loop = asyncio.get_event_loop()
    vec = await loop.run_in_executor(None, lambda: model.encode(text[:2000]).tolist())
    if len(vec) < EMBED_DIM:
        vec = vec + [0.0] * (EMBED_DIM - len(vec))
    return vec[:EMBED_DIM]


# ── 搜索（自動適配 pgvector / BM25）─────────────────────────────────

async def search(
    query: str,
    top_k: int = TOP_K,
    source_filter: str | None = None,
    doc_type_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    語義搜索知識庫。
    - pgvector 可用：余弦相似度搜索
    - pgvector 不可用：自動降級到 BM25 全文搜索
    """
    if await _has_pgvector():
        try:
            vec = await embed(query)
            if vec:
                return await _vector_search(vec, top_k, source_filter, doc_type_filter)
        except Exception as exc:
            logger.warning("[VectorStore] vector search failed: %s → fallback BM25", exc)
    return await _bm25_search(query, top_k, source_filter)


async def hybrid_search(
    query: str,
    top_k: int = TOP_K,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    混合搜索（pgvector 60% + BM25 40%）。
    無 pgvector 時自動降級為純 BM25。
    """
    bm25 = await _bm25_search(query, top_k * 2, source_filter)
    if not await _has_pgvector():
        return bm25[:top_k]

    try:
        vec = await embed(query)
        if not vec:
            return bm25[:top_k]
        vecs = await _vector_search(vec, top_k * 2, source_filter)
    except Exception:
        return bm25[:top_k]

    # 合并去重
    seen: set[str] = set()
    merged: list[dict] = []
    for r in vecs:
        key = r["content"][:80]
        if key not in seen:
            seen.add(key)
            merged.append({**r, "score": r["score"] * 0.6, "search_type": "vector"})
    for r in bm25:
        key = r["content"][:80]
        if key not in seen:
            seen.add(key)
            merged.append({**r, "score": r.get("score", 0) * 0.4, "search_type": "bm25"})
    merged.sort(key=lambda x: x.get("score", 0), reverse=True)
    return merged[:top_k]


async def _vector_search(
    query_vec: list[float],
    top_k: int,
    source_filter: str | None,
    doc_type_filter: str | None = None,
) -> list[dict]:
    import asyncpg
    conn = await asyncpg.connect(DB_URL)
    vec_str = "[" + ",".join(f"{v:.6f}" for v in query_vec) + "]"
    where, params = [], [vec_str, top_k]
    if source_filter:
        params.append(source_filter); where.append(f"d.source = ${len(params)}")
    if doc_type_filter:
        params.append(doc_type_filter); where.append(f"d.doc_type = ${len(params)}")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT c.content, d.title, d.source, d.doc_type, c.metadata,
               1 - (c.embedding::vector <=> $1::vector) AS score
        FROM chatdb.knowledge_chunk c
        JOIN chatdb.knowledge_document d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL {('AND ' + ' AND '.join(where[:])) if where else ''}
        ORDER BY c.embedding::vector <=> $1::vector
        LIMIT $2
    """
    rows = await conn.fetch(sql, *params)
    await conn.close()
    return [{"content": r["content"], "title": r["title"], "source": r["source"],
             "doc_type": r["doc_type"], "score": float(r["score"])} for r in rows]


async def _bm25_search(
    query: str,
    top_k: int,
    source_filter: str | None,
) -> list[dict]:
    """
    全文搜索（兩階段）：
    1. BM25（PostgreSQL tsquery）— 對英文效果好
    2. ILIKE 子串匹配降級 — 對中文效果好（BM25 無中文分詞時的補救）
    """
    try:
        import asyncpg
        conn = await asyncpg.connect(DB_URL)
        source_clause = f"AND d.source = '{source_filter}'" if source_filter else ""

        # ── 階段1：BM25 ─────────────────────────────────────────────
        bm25_sql = f"""
            SELECT c.content, d.title, d.source, d.doc_type,
                   ts_rank(to_tsvector('simple', c.content),
                           plainto_tsquery('simple', $1)) AS score
            FROM chatdb.knowledge_chunk c
            JOIN chatdb.knowledge_document d ON d.id = c.document_id
            WHERE to_tsvector('simple', c.content) @@ plainto_tsquery('simple', $1)
                  {source_clause}
            ORDER BY score DESC LIMIT $2
        """
        rows = await conn.fetch(bm25_sql, query, top_k)
        results = [{"content": r["content"], "title": r["title"], "source": r["source"],
                    "doc_type": r["doc_type"], "score": float(r["score"]),
                    "search_type": "bm25"} for r in rows]

        # ── 階段2：ILIKE 降級（BM25 無結果時，特別適合中文）──────────
        if not results:
            # 取查詢的前幾個詞（每個詞獨立 ILIKE）
            keywords = [w.strip() for w in query.split() if len(w.strip()) >= 2]
            if not keywords:
                keywords = [query[:4]]  # 中文無空格時取前4字符

            ilike_conditions = " OR ".join(
                f"c.content ILIKE '%' || ${i+2} || '%'" for i, _ in enumerate(keywords)
            )
            ilike_sql = f"""
                SELECT c.content, d.title, d.source, d.doc_type,
                       0.1 AS score
                FROM chatdb.knowledge_chunk c
                JOIN chatdb.knowledge_document d ON d.id = c.document_id
                WHERE ({ilike_conditions}) {source_clause}
                ORDER BY d.created_at DESC
                LIMIT $1
            """
            ilike_rows = await conn.fetch(ilike_sql, top_k, *keywords)
            results = [{"content": r["content"], "title": r["title"], "source": r["source"],
                        "doc_type": r["doc_type"], "score": float(r["score"]),
                        "search_type": "ilike"} for r in ilike_rows]
            if results:
                logger.info("[VectorStore] BM25 無結果，ILIKE 降級找到 %d 條（適合中文）", len(results))

        await conn.close()
        return results
    except Exception as exc:
        logger.error("[VectorStore] search failed: %s", exc)
        return []


# ── 文檔索引 ──────────────────────────────────────────────────────

async def index_document(
    title:      str,
    content:    str,
    source:     str,
    doc_type:   str,
    chunk_size: int = 500,
    language:   str = "zh-HK",
) -> str:
    """
    將文檔分塊並索引到知識庫。

    Args:
        title:    文檔標題
        content:  純文本內容
        source:   來源（skill_doc | sfc_regulation | fund_doc | manual）
        doc_type: 類型（regulation | prospectus | skill | faq）

    Returns:
        document_id（UUID 字符串）
    """
    import hashlib
    import asyncpg

    content_hash = hashlib.sha256(content.encode()).hexdigest()
    doc_id = str(uuid.uuid4())
    chunks = _split_text(content, chunk_size)
    has_vec = await _has_pgvector()

    conn = await asyncpg.connect(DB_URL)
    try:
        # 已索引則跳過
        existing = await conn.fetchval(
            "SELECT id FROM chatdb.knowledge_document WHERE content_hash = $1", content_hash
        )
        if existing:
            logger.info("[VectorStore] 已索引，跳過: %s", title)
            return str(existing)

        await conn.execute(
            """INSERT INTO chatdb.knowledge_document
               (id, title, source, doc_type, language, content_hash, chunk_count, has_vectors)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            doc_id, title, source, doc_type, language, content_hash, len(chunks), False,
        )

        vectors_stored = 0
        for i, chunk_text in enumerate(chunks):
            vec = await embed(chunk_text) if has_vec or OPENAI_KEY else None

            if vec and has_vec:
                # pgvector 可用：存 vector 類型
                vec_str = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
                await conn.execute(
                    """INSERT INTO chatdb.knowledge_chunk
                       (id, document_id, chunk_index, content, embedding, token_count)
                       VALUES (gen_random_uuid(), $1, $2, $3, $4::vector, $5)""",
                    doc_id, i, chunk_text, vec_str, len(chunk_text) // 3,
                )
                vectors_stored += 1
            elif vec:
                # 有 embedding 但無 pgvector：存 JSONB
                await conn.execute(
                    """INSERT INTO chatdb.knowledge_chunk
                       (id, document_id, chunk_index, content, embedding, token_count)
                       VALUES (gen_random_uuid(), $1, $2, $3, $4::jsonb, $5)""",
                    doc_id, i, chunk_text, json.dumps(vec), len(chunk_text) // 3,
                )
            else:
                # 無 embedding：只存文本（BM25 仍可搜索）
                await conn.execute(
                    """INSERT INTO chatdb.knowledge_chunk
                       (id, document_id, chunk_index, content, token_count)
                       VALUES (gen_random_uuid(), $1, $2, $3, $4)""",
                    doc_id, i, chunk_text, len(chunk_text) // 3,
                )

        # 更新 has_vectors 標記
        await conn.execute(
            "UPDATE chatdb.knowledge_document SET has_vectors = $1 WHERE id = $2",
            vectors_stored > 0, doc_id,
        )
        logger.info("[VectorStore] 索引完成: '%s' → %d 塊%s",
                    title, len(chunks), f"（含向量）" if vectors_stored else "（純文本，BM25可搜）")
        return doc_id
    finally:
        await conn.close()


async def save_episode(
    agent_id:   str,
    model_id:   str,
    query:      str,
    summary:    str,
    tool_calls: list[dict],
    outcome:    str = "success",
    fund_id:    str | None = None,
    user_id:    str | None = None,
) -> None:
    """保存 Agent 情景記憶。"""
    try:
        import asyncpg
        conn = await asyncpg.connect(DB_URL)
        vec = await embed(query)
        await conn.execute(
            """INSERT INTO chatdb.agent_episode
               (id, user_id, agent_id, model_id, query, summary, tool_calls, embedding, outcome, fund_id)
               VALUES (gen_random_uuid(), $1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)""",
            user_id, agent_id, model_id, query, summary,
            json.dumps(tool_calls, ensure_ascii=False),
            json.dumps(vec) if vec else None,
            outcome, fund_id,
        )
        await conn.close()
    except Exception as exc:
        logger.warning("[VectorStore] save_episode failed: %s", exc)


# ── 文本分塊 ─────────────────────────────────────────────────────

def _split_text(text: str, chunk_size: int) -> list[str]:
    """按段落和句子邊界分塊。"""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) <= chunk_size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            if len(para) > chunk_size:
                sentences = para.replace("。", "。\n").replace("；", "；\n").split("\n")
                buf = ""
                for s in sentences:
                    if len(buf) + len(s) <= chunk_size:
                        buf = (buf + s).strip()
                    else:
                        if buf:
                            chunks.append(buf)
                        buf = s
                if buf:
                    chunks.append(buf)
                current = ""
            else:
                current = para
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


# ── 公共介面 ─────────────────────────────────────────────────────

class VectorStore:
    async def search(self, query: str, top_k: int = TOP_K, **kw) -> list[dict]:
        return await search(query, top_k=top_k, **kw)

    async def hybrid_search(self, query: str, top_k: int = TOP_K, **kw) -> list[dict]:
        return await hybrid_search(query, top_k=top_k, **kw)

    async def index_document(self, **kw) -> str:
        return await index_document(**kw)

    async def save_episode(self, **kw) -> None:
        return await save_episode(**kw)

    async def has_pgvector(self) -> bool:
        return await _has_pgvector()
