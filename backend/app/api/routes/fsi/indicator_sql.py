"""Serve the verification-doc SQL snippets ("View SQL") as a live catalog.

The verification document (docs/investment_risk_page_module_verification.md) is the
single source of truth for each module's SQL. This router parses its
`### SQL-XX-NN 标题` headers with their fenced ```sql``` blocks so the UI can show,
per module, the exact SQL behind an indicator. Parsed result is cached and
invalidated when the file's mtime changes.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser

router = APIRouter()

# backend/app/api/routes/fsi/indicator_sql.py → parents[5] = repo root
_DOC_PATH = (
    Path(__file__).resolve().parents[5]
    / "docs"
    / "investment_risk_page_module_verification.md"
)

# `### SQL-RI-01 風險指標基礎` followed (eventually) by a ```sql ... ``` fence.
_BLOCK_RE = re.compile(
    r"^###\s+(?P<id>SQL-[A-Z]+-\d+)\s+(?P<title>.*?)\s*$"
    r".*?```sql\s*\n(?P<sql>.*?)\n```",
    re.DOTALL | re.MULTILINE,
)

_cache: dict[str, Any] = {"mtime": None, "items": [], "by_id": {}}


def _load_catalog() -> dict[str, Any]:
    if not _DOC_PATH.exists():
        return {"items": [], "by_id": {}}

    mtime = _DOC_PATH.stat().st_mtime
    if _cache["mtime"] == mtime and _cache["items"]:
        return _cache

    text = _DOC_PATH.read_text(encoding="utf-8")
    items: list[dict[str, str]] = []
    by_id: dict[str, dict[str, str]] = {}
    for match in _BLOCK_RE.finditer(text):
        entry = {
            "id": match.group("id"),
            "title": match.group("title").strip(),
            "sql": match.group("sql").strip(),
        }
        # First occurrence wins if an id appears twice.
        if entry["id"] not in by_id:
            items.append(entry)
            by_id[entry["id"]] = entry

    _cache.update({"mtime": mtime, "items": items, "by_id": by_id})
    return _cache


@router.get("/", summary="风控指标 SQL 片段目录")
def list_indicator_sql(_user: CurrentUser) -> dict[str, Any]:
    catalog = _load_catalog()
    return {"items": catalog["items"]}


@router.get("/{sql_id}", summary="按 ID 查询单个 SQL 片段")
def get_indicator_sql(sql_id: str, _user: CurrentUser) -> dict[str, str]:
    catalog = _load_catalog()
    entry = catalog["by_id"].get(sql_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"SQL snippet {sql_id} not found")
    return entry
