"""
aiagent/memory/knowledge_indexer.py — Layer 2: 知識庫索引器

將現有的業務文檔批量索引到 pgvector 知識庫（chatdb.knowledge_chunk）：
  • 3_skills/skills/**/*.md    — 技能框架文檔（風控分析、合規審查等）
  • aiagent/agents/*.md        — Agent 系統提示（包含業務規則和流程）
  • aiagent/agents/commons.md  — 通用上下文

用法：
  # 一次性初始化（項目啟動後運行一次）
  python -m aiagent.memory.knowledge_indexer

  # 增量更新（添加新文檔後運行）
  python -m aiagent.memory.knowledge_indexer --path docs/sfc_code.txt --source sfc_regulation
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent

# ── 知識庫來源（只有 3_skills/ 進入知識庫）────────────────────────
KNOWLEDGE_SKILLS_DIR = REPO_ROOT / "3_skills" / "skills"   # skill_doc
KNOWLEDGE_AGENTS_DIR = REPO_ROOT / "3_skills" / "agents"   # agent_prompt

# ── 私有目錄（不索引，不進知識庫）──────────────────────────────────
# aiagent/agents/   → Chat Agent 私有系統提示
# aiagent/skills/   → Chat Agent 私有操作指南
# platform_agent/   → Platform Agent 全部私有

# ── 兩種知識類型 ─────────────────────────────────────────────────
# skill_doc    = 業務技能定義（HOW）
#               說明執行某類業務的步驟、規則、輸出格式
#               來源：3_skills/skills/**/*.md
#
# agent_prompt = 系統級 Agent 知識（WHO）
#               說明某類 Agent 的定位、能力邊界、適用場景
#               來源：3_skills/agents/**/*.md（系統公開的 Agent 知識）
#               注意：aiagent/agents/ 是私有系統提示，不在此


# ── 文檔掃描 ──────────────────────────────────────────────────────

def _collect_skill_docs() -> list[dict]:
    """
    收集 3_skills/skills/**/*.md → skill_doc 類型。
    業務技能定義（HOW：步驟 + 規則 + 輸出格式）。
    """
    docs = []
    if not KNOWLEDGE_SKILLS_DIR.exists():
        logger.warning("3_skills/skills/ 不存在，跳過")
        return docs

    for md_path in KNOWLEDGE_SKILLS_DIR.rglob("*.md"):
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        name_match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        title = name_match.group(1).strip() if name_match else md_path.stem
        clean = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()
        if len(clean) < 50:
            continue
        docs.append({
            "title":    f"[系統技能] {title}",
            "content":  clean,
            "source":   "skill_doc",
            "doc_type": md_path.parent.name,
        })
        logger.info("  skill_doc: %s", md_path.relative_to(REPO_ROOT))
    return docs


def _collect_agent_prompt_docs() -> list[dict]:
    """
    收集 3_skills/agents/**/*.md → agent_prompt 類型。
    系統公開的 Agent 知識（WHO：定位 + 能力邊界 + 適用場景）。
    注意：aiagent/agents/ 是私有系統提示，不在此索引。
    """
    docs = []
    if not KNOWLEDGE_AGENTS_DIR.exists():
        logger.info("  3_skills/agents/ 目錄不存在，跳過")
        return docs

    for md_path in KNOWLEDGE_AGENTS_DIR.rglob("*.md"):
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        name_match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        title = name_match.group(1).strip() if name_match else md_path.stem
        clean = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()
        if len(clean) < 50:
            continue
        docs.append({
            "title":    f"[Agent 知識] {title}",
            "content":  clean,
            "source":   "agent_prompt",
            "doc_type": "agent_knowledge",
        })
        logger.info("  agent_prompt: %s", md_path.relative_to(REPO_ROOT))
    return docs


def _collect_custom_doc(file_path: str, source: str, doc_type: str) -> dict | None:
    """收集單個自定義文檔（從命令行指定）。"""
    p = Path(file_path)
    if not p.exists():
        logger.error("文件不存在：%s", file_path)
        return None
    text = p.read_text(encoding="utf-8", errors="ignore")
    return {
        "title":    p.stem,
        "content":  text,
        "source":   source,
        "doc_type": doc_type,
    }


# ── 批量索引 ──────────────────────────────────────────────────────

async def index_all(docs: list[dict]) -> int:
    """將文檔列表批量索引到 vector store。返回成功索引的文檔數。"""
    from .vector_store import index_document
    success = 0
    for doc in docs:
        try:
            await index_document(
                title    = doc["title"],
                content  = doc["content"],
                source   = doc["source"],
                doc_type = doc["doc_type"],
            )
            success += 1
        except Exception as exc:
            logger.error("  索引失敗 [%s]: %s", doc["title"], exc)
    return success


async def run_default_indexing() -> None:
    """
    默認索引任務：只索引 3_skills/ 目錄。

    知識庫來源（公開共享）：
      skill_doc    ← 3_skills/skills/**/*.md  （系統專家技能）
      agent_prompt ← 3_skills/agents/**/*.md  （系統 Agent 知識）

    私有目錄（不索引）：
      aiagent/agents/   → Chat Agent 私有系統提示
      aiagent/skills/   → Chat Agent 私有操作指南
      platform_agent/   → Platform Agent 全部私有
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=" * 60)
    logger.info("ARISK Knowledge Indexer")
    logger.info("  來源：只索引 3_skills/（公開共享）")
    logger.info("  私有：aiagent/ 和 platform_agent/ 不索引")
    logger.info("=" * 60)

    docs: list[dict] = []

    logger.info("\n[1/2] 3_skills/skills/ → skill_doc（業務技能）...")
    docs.extend(_collect_skill_docs())

    logger.info("\n[2/2] 3_skills/agents/ → agent_prompt（Agent 知識）...")
    docs.extend(_collect_agent_prompt_docs())

    if not docs:
        logger.warning("\n未找到文檔。")
        return

    logger.info("\n開始索引 %d 個文檔...", len(docs))
    success = await index_all(docs)

    by_type: dict[str, int] = {}
    for d in docs:
        by_type[d["source"]] = by_type.get(d["source"], 0) + 1

    logger.info("\n✅ %d / %d 文檔索引成功", success, len(docs))
    for src, cnt in by_type.items():
        logger.info("  %s: %d 個", src, cnt)


# ── CLI 入口 ─────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ARISK Knowledge Indexer — 知識庫文檔索引工具")
    parser.add_argument("--path",     type=str, help="單個文件路徑（可選，不指定則掃描默認目錄）")
    parser.add_argument("--source",   type=str, default="manual",       help="來源標識（sfc_regulation|fund_doc|analysis|manual）")
    parser.add_argument("--doc-type", type=str, default="document",     help="文檔類型")
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT))

    if args.path:
        doc = _collect_custom_doc(args.path, args.source, args.doc_type)
        if doc:
            async def _single():
                n = await index_all([doc])
                logging.basicConfig(level=logging.INFO, format="%(message)s")
                logger.info("✅ 索引完成：%d 個文檔", n)
            asyncio.run(_single())
    else:
        asyncio.run(run_default_indexing())


if __name__ == "__main__":
    main()
