"""
knowledge.py — 知識庫管理 API

Expert Chat 使用這些端點將專家知識攝取到 chatdb.knowledge_chunk：

  POST /api/v1/knowledge/ingest        — 攝取文本內容到知識庫
  POST /api/v1/knowledge/ingest-file   — 上傳文件並攝取（PDF/Word/MD/TXT）
  POST /api/v1/knowledge/extract-skill — AI 從對話中提取結構化技能（SKILL.md 格式）
  POST /api/v1/knowledge/save-skill    — 保存提取的技能為 3_skills/SKILL.md 文件 + 索引入庫
  GET  /api/v1/knowledge/documents     — 查詢已索引文檔列表
  DELETE /api/v1/knowledge/{doc_id}    — 刪除文檔（含所有 chunks）

知識庫三個來源：
  Platform Agent  → 系統層業務 AI 相關知識
  3_skills/       → 專家級業務技能（SKILL.md）
  aiagent/        → 用戶層業務 AI 相關知識

知識流向：
  Expert Chat 對話 → extract-skill → SKILL.md 格式知識
                  → ingest → chatdb.knowledge_chunk
                  → knowledge_search 工具可搜索
                  → Chat Agent 用戶受益
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep

router = APIRouter()

# 知識來源選項
VALID_SOURCES = ["skill_doc", "sfc_regulation", "fund_doc", "manual", "expert_chat"]
VALID_DOC_TYPES = ["regulation", "prospectus", "skill", "faq", "experience", "analysis"]


# ── Pydantic ──────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    title:    str
    content:  str
    source:   str = "expert_chat"
    doc_type: str = "experience"
    language: str = "zh-HK"


class ExtractSkillRequest(BaseModel):
    conversation: list[dict]   # [{role, content}, ...]
    topic:        str          # 技能主題描述
    layer:        str = "chat" # chat | platform
    model_id:     str = ""     # 使用的模型 ID，空字符串則自動選擇可用模型


class IngestResponse(BaseModel):
    document_id:  str
    chunk_count:  int
    has_vectors:  bool
    search_mode:  str   # "vector+bm25" | "bm25"
    message:      str


# ── 攝取文本 ──────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
async def ingest_text(
    body:         IngestRequest,
    current_user: CurrentUser,
) -> Any:
    """
    攝取文本內容到知識庫。

    Expert Chat 使用場景：
    - 專家描述業務知識後，前端自動調用此接口保存
    - 批量導入 SFC 守則條款
    """
    if body.source not in VALID_SOURCES:
        raise HTTPException(400, f"來源必須是：{VALID_SOURCES}")
    if body.doc_type not in VALID_DOC_TYPES:
        raise HTTPException(400, f"類型必須是：{VALID_DOC_TYPES}")
    if len(body.content) < 50:
        raise HTTPException(400, "內容太短（< 50 字符），無法索引")

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
    from aiagent.memory.vector_store import index_document, _has_pgvector

    doc_id = await index_document(
        title=body.title,
        content=body.content,
        source=body.source,
        doc_type=body.doc_type,
        language=body.language,
    )

    # 計算實際 chunk 數
    import asyncpg
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/fsi_risk")
    conn = await asyncpg.connect(db_url.replace("+asyncpg", ""))
    chunk_count = await conn.fetchval(
        "SELECT COUNT(*) FROM chatdb.knowledge_chunk WHERE document_id = $1::uuid", doc_id
    )
    has_vec = await conn.fetchval(
        "SELECT has_vectors FROM chatdb.knowledge_document WHERE id = $1::uuid", doc_id
    )
    await conn.close()

    has_pgvec = await _has_pgvector()
    return IngestResponse(
        document_id=doc_id,
        chunk_count=int(chunk_count or 0),
        has_vectors=bool(has_vec),
        search_mode="vector+bm25" if has_pgvec else "bm25",
        message=f"已索引 {chunk_count} 個文本塊，{'向量+BM25 搜索' if has_pgvec else 'BM25 全文搜索'}可用",
    )


@router.post("/ingest-file", response_model=IngestResponse)
async def ingest_file(
    current_user: CurrentUser,
    file:         UploadFile = File(...),
    source:       str = "expert_chat",
    doc_type:     str = "experience",
) -> Any:
    """
    上傳文件並攝取到知識庫。
    支持：.txt .md .pdf（基礎提取）.docx（基礎提取）
    """
    content = await file.read()
    filename = file.filename or "uploaded"
    text = ""

    if filename.endswith(".txt") or filename.endswith(".md"):
        text = content.decode("utf-8", errors="replace")
    elif filename.endswith(".pdf"):
        try:
            import io
            import pdfminer.high_level as pdf
            text = pdf.extract_text(io.BytesIO(content))
        except ImportError:
            raise HTTPException(422, "解析 PDF 需安裝：pip install pdfminer.six")
    elif filename.endswith(".docx"):
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            raise HTTPException(422, "解析 Word 需安裝：pip install python-docx")
    else:
        raise HTTPException(415, f"不支持的文件類型：{filename}。支持：.txt .md .pdf .docx")

    if len(text.strip()) < 50:
        raise HTTPException(422, "文件內容提取失敗或內容過少")

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
    from aiagent.memory.vector_store import index_document, _has_pgvector

    doc_id = await index_document(
        title=filename,
        content=text,
        source=source,
        doc_type=doc_type,
    )

    import asyncpg
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/fsi_risk")
    conn = await asyncpg.connect(db_url.replace("+asyncpg", ""))
    chunk_count = await conn.fetchval(
        "SELECT COUNT(*) FROM chatdb.knowledge_chunk WHERE document_id = $1::uuid", doc_id
    )
    await conn.close()

    has_pgvec = await _has_pgvector()
    return IngestResponse(
        document_id=doc_id,
        chunk_count=int(chunk_count or 0),
        has_vectors=False,
        search_mode="vector+bm25" if has_pgvec else "bm25",
        message=f"文件 '{filename}' 已索引 {chunk_count} 個文本塊",
    )


@router.post("/extract-skill")
async def extract_skill(
    body:         ExtractSkillRequest,
    current_user: CurrentUser,
) -> Any:
    """
    從 Expert Chat 對話中提取結構化業務技能（SKILL.md 格式）。
    根據 model_id 自動路由到對應的 LLM API：
      - x-ai/grok-* → OpenRouter
      - claude-*     → Anthropic
      - gpt-*        → OpenAI
      - 未指定       → 按優先級自動選擇可用的 API
    """
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in body.conversation
        if m.get("content")
    )
    layer_desc = "用戶業務技能（Chat Agent 使用）" if body.layer == "chat" else "系統業務技能（3_skills 使用）"
    prompt = f"""從以下專家對話中，提取結構化的業務技能文檔（SKILL.md 格式）。

主題：{body.topic}
層級：{body.layer}（{layer_desc}）

對話內容：
{conversation_text[:4000]}

請生成符合以下格式的 SKILL.md 文檔：

```markdown
---
name: [kebab-case技能名]
category: [分類]
layer: {body.layer}
description: [一句話描述]
tools: [可能需要的工具列表]
version: "1.0"
---

# [技能標題]

## 觸發條件
[何時使用此技能]

## 核心知識
[從對話中提取的關鍵知識點，用列表呈現]

## 執行步驟
[步驟化的操作流程]

## 注意事項
[重要提醒和邊界條件]
```

只輸出 markdown 代碼塊內的內容，不要其他說明。"""

    # 根據 model_id 路由到對應 API
    skill_content = await _call_llm_for_skill(body.model_id, prompt)
    if skill_content is None:
        raise HTTPException(503,
            "無可用的 LLM API。請確認以下至少一個 API Key 已設置：\n"
            "  OPENROUTER_API_KEY（支持 Grok/Qwen 等，推薦）\n"
            "  ANTHROPIC_API_KEY（支持 Claude）\n"
            "  OPENAI_API_KEY（支持 GPT）"
        )

    # 去掉 markdown 代碼圍欄
    if skill_content.startswith("```"):
        lines = skill_content.split("\n")
        skill_content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    return {
        "topic":         body.topic,
        "layer":         body.layer,
        "model_used":    body.model_id or "auto",
        "skill_content": skill_content,
        "message":       "技能提取成功，請審查後保存",
        "suggested_path": f"aiagent/skills/{body.topic.replace(' ', '-').lower()}/SKILL.md"
                          if body.layer == "chat"
                          else f"3_skills/skills/{body.topic.replace(' ', '-').lower()}/SKILL.md",
    }


class SaveSkillRequest(BaseModel):
    skill_name:    str              # kebab-case，如 credit-analysis
    skill_content: str              # SKILL.md 完整內容
    layer:         str = "expert"   # expert → 3_skills; chat → aiagent/skills
    also_index:    bool = True      # 同時索引到知識庫


def _extract_skill_frontmatter_name(skill_content: str) -> str | None:
    import re

    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", skill_content, flags=re.DOTALL)
    if not m:
        return None
    for line in m.group(1).splitlines():
        if line.startswith("name:"):
            value = line.split(":", 1)[1].strip()
            return value or None
    return None


async def _call_llm_for_skill(model_id: str, prompt: str) -> str | None:
    """
    根據 model_id 路由到對應 LLM API，執行技能提取。
    優先級：指定模型 → OpenRouter → Anthropic → OpenAI
    任何一個可用即返回結果，全部不可用返回 None。
    """
    # 判斷 Provider
    def detect(m: str) -> str:
        if not m:
            return "auto"
        m = m.lower()
        # vendor/model → OpenRouter（含 anthropic/claude-*、openai/gpt-*）
        if "/" in m or m.startswith("x-ai/") or m.startswith("grok") or m.startswith("qwen") or m.startswith("mistral"):
            return "openrouter"
        if m.startswith("claude"):
            return "anthropic"
        if m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3"):
            return "openai"
        if m.startswith("moonshot"):
            return "moonshot"
        if m.startswith("deepseek"):
            return "deepseek"
        return "openrouter"  # 未知模型默認嘗試 OpenRouter

    provider = detect(model_id)
    messages = [{"role": "user", "content": prompt}]

    # 嘗試列表（指定 provider 優先，其次按可用 key 順序）
    attempts: list[tuple[str, str, str, str]] = []  # (provider, base_url, api_key, model)

    or_key  = os.getenv("OPENROUTER_API_KEY", "")
    ant_key = os.getenv("ANTHROPIC_API_KEY", "")
    oai_key = os.getenv("OPENAI_API_KEY", "")

    if provider == "openrouter" and or_key:
        attempts.append(("openrouter", "https://openrouter.ai/api/v1", or_key, model_id or "x-ai/grok-4.20"))
    elif provider == "anthropic" and ant_key:
        attempts.append(("anthropic", "", ant_key, model_id or "claude-haiku-4-5-20251001"))
    elif provider == "openai" and oai_key:
        attempts.append(("openai", "", oai_key, model_id or "gpt-4o-mini"))
    elif provider == "moonshot" and os.getenv("MOONSHOT_API_KEY", ""):
        attempts.append(("openai", "https://api.moonshot.cn/v1", os.getenv("MOONSHOT_API_KEY", ""), model_id))
    elif provider == "deepseek" and os.getenv("DEEPSEEK_API_KEY", ""):
        attempts.append(("openai", "https://api.deepseek.com/v1", os.getenv("DEEPSEEK_API_KEY", ""), model_id))

    # 補充 fallback（若指定 provider 的 key 不存在）
    if not attempts or provider == "auto":
        if or_key:
            attempts.append(("openrouter", "https://openrouter.ai/api/v1", or_key, "x-ai/grok-4.20"))
        if ant_key:
            attempts.append(("anthropic", "", ant_key, "claude-haiku-4-5-20251001"))
        if oai_key:
            attempts.append(("openai", "", oai_key, "gpt-4o-mini"))

    if not attempts:
        return None

    for prov, base_url, api_key, use_model in attempts:
        try:
            if prov == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model=use_model,
                    messages=messages,
                    max_tokens=1500,
                )
                return resp.content[0].text if resp.content else ""
            else:
                # OpenAI-compatible（OpenRouter / OpenAI / Moonshot / DeepSeek）
                import openai
                client = openai.OpenAI(api_key=api_key, base_url=base_url or None)
                resp = client.chat.completions.create(
                    model=use_model,
                    messages=messages,
                    max_tokens=1500,
                )
                return resp.choices[0].message.content or ""
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "[extract-skill] %s/%s failed: %s", prov, use_model, str(exc)[:100]
            )
            continue  # 嘗試下一個

    return None


@router.post("/save-skill")
async def save_skill_to_file(
    body:         SaveSkillRequest,
    current_user: CurrentUser,
) -> Any:
    """
    將 Expert Chat 提取的技能保存為真實的 SKILL.md 文件。

    layer="expert"  → 保存到 3_skills/skills/{skill_name}/SKILL.md（專家級業務技能）
    layer="chat"    → 保存到 aiagent/skills/user-skills/{skill_name}/SKILL.md

    also_index=True → 同時將文件內容索引到 chatdb.knowledge_chunk（知識庫）

    這樣 Expert Chat 生成的技能就正式成為 3_skills 的一部分，
    後台開發者可以直接在代碼庫中看到和維護。
    """
    import re
    from pathlib import Path

    # 安全校驗技能名（只允許 kebab-case）
    skill_name = re.sub(r"[^a-z0-9-]", "", body.skill_name.lower().replace(" ", "-").replace("_", "-"))
    if not skill_name:
        raise HTTPException(400, "技能名稱無效（只允許小寫字母、數字、連字符）")

    expert_skill_name = _extract_skill_frontmatter_name(body.skill_content) if body.layer == "expert" else None
    if expert_skill_name:
        skill_name = re.sub(r"[^a-z0-9-]", "", expert_skill_name.lower().replace(" ", "-").replace("_", "-")) or skill_name

    repo_root = Path(__file__).parent.parent.parent.parent.parent

    # 確定目標路徑
    if body.layer == "expert":
        target_dir  = repo_root / "3_skills" / "skills" / skill_name
        target_path = target_dir / "SKILL.md"
        skill_layer = "expert"
        source      = "skill_doc"
    else:
        target_dir  = repo_root / "aiagent" / "skills" / "user-skills" / skill_name
        target_path = target_dir / "SKILL.md"
        skill_layer = "chat"
        source      = "skill_doc"

    # 創建目錄並寫入文件
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path.write_text(body.skill_content, encoding="utf-8")

    result = {
        "skill_name":  skill_name,
        "layer":       skill_layer,
        "file_path":   str(target_path.relative_to(repo_root)),
        "indexed":     False,
        "message":     f"技能文件已保存：{target_path.relative_to(repo_root)}",
    }

    # 同時索引到知識庫
    if body.also_index:
        try:
            import sys
            sys.path.insert(0, str(repo_root))
            from aiagent.memory.vector_store import index_document
            title_name = skill_name if body.layer != "expert" else skill_name
            doc_id = await index_document(
                title    = f"[專家技能] {title_name}",
                content  = body.skill_content,
                source   = source,
                doc_type = "skill",
            )
            result["indexed"]    = True
            result["document_id"] = doc_id
            result["message"]   += f"，並已索引到知識庫（document_id: {doc_id[:8]}...）"
        except Exception as exc:
            result["index_error"] = str(exc)[:200]
            result["message"]    += "（知識庫索引失敗，技能文件已保存）"

    if body.layer == "expert":
        try:
            import sys
            sys.path.insert(0, str(repo_root))
            from aiagent.memory.knowledge_indexer import refresh_skill_docs

            refresh_result = await refresh_skill_docs()
            result["refreshed"] = True
            result["refresh_scanned"] = refresh_result["scanned"]
            result["refresh_indexed"] = refresh_result["indexed"]
            result["message"] += f"，並已刷新 3_skills（{refresh_result['indexed']}/{refresh_result['scanned']}）"
        except Exception as exc:
            result["refreshed"] = False
            result["refresh_error"] = str(exc)[:200]
            result["message"] += "（3_skills 刷新失敗）"

    return result


@router.post("/refresh-skills")
async def refresh_skills(current_user: CurrentUser) -> Any:
    """
    重新掃描 3_skills/skills/，讓 Chat 進入時能自動載入新建立的 expert skills。
    """
    import sys
    from pathlib import Path

    repo_root = Path(__file__).parent.parent.parent.parent.parent
    sys.path.insert(0, str(repo_root))

    from aiagent.memory.knowledge_indexer import refresh_skill_docs

    result = await refresh_skill_docs()
    return {
        "ok": True,
        "scanned": result["scanned"],
        "indexed": result["indexed"],
        "message": f"已重新掃描 3_skills/skills：{result['indexed']} / {result['scanned']} 個技能",
    }


# ── 查詢和刪除 ────────────────────────────────────────────────────

@router.get("/documents")
async def list_documents(
    current_user: CurrentUser,
    source:  str | None = None,
    limit:   int = 50,
) -> Any:
    """查詢已索引的知識文檔列表。"""
    import asyncpg
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/fsi_risk")
    conn = await asyncpg.connect(db_url.replace("+asyncpg", ""))
    where = f"WHERE source = '{source}'" if source else ""
    rows = await conn.fetch(f"""
        SELECT id, title, source, doc_type, chunk_count, has_vectors, created_at
        FROM chatdb.knowledge_document
        {where}
        ORDER BY created_at DESC
        LIMIT {limit}
    """)
    await conn.close()
    return [dict(r) for r in rows]


@router.delete("/{document_id}")
async def delete_document(document_id: str, current_user: CurrentUser) -> Any:
    """刪除知識文檔（含所有 chunks）。"""
    if not current_user.is_superuser:
        raise HTTPException(403, "需要超管權限")
    import asyncpg
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/fsi_risk")
    conn = await asyncpg.connect(db_url.replace("+asyncpg", ""))
    # chunks 通過 CASCADE 自動刪除
    result = await conn.execute(
        "DELETE FROM chatdb.knowledge_document WHERE id = $1::uuid", document_id
    )
    await conn.close()
    if result == "DELETE 0":
        raise HTTPException(404, "文檔不存在")
    return {"deleted": document_id}
