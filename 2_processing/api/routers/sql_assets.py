"""SQL asset library — expose 2_processing/sql/* as a viewable, API-callable,
AI-context-ready catalog (SQL 资产化).

The reference SQL under ``2_processing/sql/{indicators,mmf}/`` is not executed here
(execution stays with the calculators/tools); this router asset-izes it: catalog,
single-asset body, and an AI-context Markdown bundle for LLM reference.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

# .../2_processing/api/routers/sql_assets.py → parents[2] = 2_processing
SQL_DIR = (Path(__file__).resolve().parents[2] / "sql")

# AI-context bundle is bounded so an over-broad filter can't produce a huge payload.
MAX_CONTEXT_ASSETS = 40

_cache: dict[str, Any] = {"sig": None, "items": []}


def _parse_header(text: str) -> tuple[str | None, str]:
    """Extract (title, description) from a SQL file's leading comment block.

    Convention: line 1 = filename, line 2 = ``中文标题 (English)``, following
    comment lines (说明/notes) = description. Falls back gracefully when absent.
    """
    comments: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            comments.append(stripped[2:].strip())
        elif stripped == "":
            if comments:
                break
            continue
        else:
            break
    title = comments[1] if len(comments) >= 2 else (comments[0] if comments else None)
    description = " ".join(c for c in comments[2:] if c)
    return title, description


def _category(group: str, filename: str, rel: str = "") -> str:
    if group == "mmf":
        parts = rel.split("/") if rel else []
        # mmf/report_06/01_xxx.sql → 貨幣基金報表/report_06
        if len(parts) >= 2 and parts[1].startswith("report_"):
            return f"貨幣基金報表/{parts[1]}"
        return "貨幣基金報表"
    name = filename.lower()
    if name.startswith("atomic_"):
        return "原子指標"
    if name.startswith(("brinson_", "campisi_")):
        return "業績歸因"
    if name.startswith("position_exposure"):
        return "暴露分析"
    if name.startswith("absolute_return"):
        return "收益計算"
    return "其他"


def _scan() -> list[dict[str, Any]]:
    """Scan the SQL tree, cached by the tree's max mtime."""
    if not SQL_DIR.exists():
        return []
    files = sorted(SQL_DIR.rglob("*.sql"))
    sig = max((f.stat().st_mtime for f in files), default=0.0), len(files)
    if _cache["sig"] == sig and _cache["items"]:
        return _cache["items"]

    items: list[dict[str, Any]] = []
    for path in files:
        rel = path.relative_to(SQL_DIR).as_posix()
        group = rel.split("/", 1)[0] if "/" in rel else "root"
        text = path.read_text(encoding="utf-8", errors="replace")
        title, description = _parse_header(text)
        items.append(
            {
                "id": rel,
                "filename": path.name,
                "group": group,
                "category": _category(group, path.name, rel),
                "package": rel.split("/")[1] if group == "mmf" and "/" in rel else group,
                "title": title or path.name,
                "description": description,
                "line_count": text.count("\n") + 1,
                "sql": text,
            }
        )
    _cache.update({"sig": sig, "items": items})
    return items


def _resolve(asset_id: str) -> dict[str, Any]:
    # Guard against path traversal; only serve files under SQL_DIR.
    target = (SQL_DIR / asset_id).resolve()
    if SQL_DIR.resolve() not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid asset id")
    for item in _scan():
        if item["id"] == asset_id:
            return item
    raise HTTPException(status_code=404, detail="SQL asset not found")


@router.get("/catalog", summary="SQL 資產目錄")
def catalog(
    group: str | None = None,
    category: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    items = _scan()
    needle = search.strip().lower() if search and search.strip() else None
    group_scoped = [item for item in items if group is None or item["group"] == group]
    filtered = [
        {k: v for k, v in item.items() if k != "sql"}
        for item in group_scoped
        if (category is None or item["category"] == category)
        and (
            needle is None
            or needle in item["id"].lower()
            or needle in (item["title"] or "").lower()
            or needle in (item["description"] or "").lower()
        )
    ]
    return {
        "items": filtered,
        "count": len(filtered),
        "groups": sorted({item["group"] for item in items}),
        "categories": sorted({item["category"] for item in group_scoped}),
    }


@router.get("/asset", summary="單個 SQL 資產（含正文）")
def asset(id: str = Query(description="相對 sql/ 的路徑，如 indicators/atomic_portfolio_wam.sql")) -> dict[str, Any]:
    return _resolve(id)


@router.get("/context", summary="AI 上下文包（Markdown）")
def context(
    group: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    items = [
        item
        for item in _scan()
        if (group is None or item["group"] == group)
        and (category is None or item["category"] == category)
    ]
    truncated = len(items) > MAX_CONTEXT_ASSETS
    selected = items[:MAX_CONTEXT_ASSETS]
    blocks: list[str] = []
    for item in selected:
        header = f"### {item['title']}  \n`{item['id']}` · {item['category']}"
        if item["description"]:
            header += f"  \n{item['description']}"
        blocks.append(f"{header}\n\n```sql\n{item['sql']}\n```")
    return {
        "markdown": "\n\n---\n\n".join(blocks),
        "asset_count": len(selected),
        "truncated": truncated,
    }
