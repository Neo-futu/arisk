"""
platform_agent/engine/system_tools.py — Platform Agent L3: 系統運維工具集

面向 ARISK 平台系統層面的業務運維工具。
與 aiagent/engine/tools.py（用戶業務工具）完全分離。

工具清單（6個）：
  1. trigger_celery_task  — 觸發 Celery 業務任務
  2. get_task_status      — 查詢任務執行狀態
  3. check_system_health  — 服務健康檢查
  4. query_business_db    — 只讀查詢業務數據
  5. trigger_report       — 觸發報表生成
  6. get_queue_stats      — Celery 隊列統計
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROCESSING_URL = os.getenv("PROCESSING_API_URL", "http://localhost:8001")
PROCESSING_KEY = os.getenv("PROCESSING_API_KEY", "internal_key_change_me")
REDIS_URL      = os.getenv("REDIS_URL", "redis://localhost:6379/0")

PLATFORM_TOOLS: list[dict] = [
    {
        "name": "trigger_celery_task",
        "description": (
            "觸發 ARISK Celery 業務任務（風控快照、ETL、AI異常檢測等）。\n"
            "可用任務：\n"
            "  • compute_daily_risk_snapshot — 計算全部基金日終風控快照\n"
            "  • refresh_price_cache         — 刷新行情緩存\n"
            "  • load_daily_positions        — 載入當日持倉\n"
            "  • run_ai_anomaly_detection    — AI 異常檢測（需 fund_id + as_of_date）\n"
            "觸發詞：觸發任務、跑一下快照、執行ETL、刷新緩存"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_name": {
                    "type": "string",
                    "enum": ["compute_daily_risk_snapshot", "refresh_price_cache",
                             "load_daily_positions", "run_ai_anomaly_detection"],
                    "description": "任務名稱",
                },
                "kwargs": {
                    "type": "object",
                    "description": "任務參數（可選），如 {fund_id: 'BHMMF001', as_of_date: '2026-07-09'}",
                },
            },
            "required": ["task_name"],
        },
    },
    {
        "name": "get_task_status",
        "description": (
            "查詢 Celery 任務的執行狀態和結果。\n"
            "狀態：PENDING / STARTED / SUCCESS / FAILURE / RETRY\n"
            "觸發詞：任務狀態、任務完成了嗎、查詢進度"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Celery 任務 ID"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "check_system_health",
        "description": (
            "檢查 ARISK 各服務的健康狀態。\n"
            "服務：processing(8001) / entry(8010) / backend(8000) / all\n"
            "觸發詞：服務健康、系統狀態、服務是否正常"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "enum": ["processing", "entry", "backend", "all"],
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "query_business_db",
        "description": (
            "只讀查詢業務數據庫，用於數據質量驗證和運維監控。\n"
            "支持查詢 fsi schema（業務數據）和 iam schema（配置數據）。\n"
            "觸發詞：查詢數據、數據完整性、今日持倉、快照狀態"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql":   {"type": "string", "description": "SELECT 查詢語句（只讀）"},
                "limit": {"type": "integer", "description": "最多返回行數（默認 50）"},
            },
            "required": ["sql"],
        },
    },
    {
        "name": "trigger_report",
        "description": (
            "觸發 ARISK 報表生成任務。\n"
            "報表類型：\n"
            "  • report_03_mmf         — MMF 日報（SFC 合規版，Excel）\n"
            "  • report_04_mmf_monthly — MMF 月報 Factsheet（Word）\n"
            "  • report_06             — 基金詳細分析報告（Excel）\n"
            "觸發詞：生成報表、日報、月報、報告生成"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_id":  {
                    "type": "string",
                    "enum": ["report_03_mmf", "report_04_mmf_monthly", "report_06"],
                },
                "fund_id":    {"type": "string", "description": "基金 ID"},
                "as_of_date": {"type": "string", "description": "報表日期 YYYY-MM-DD"},
            },
            "required": ["report_id", "fund_id", "as_of_date"],
        },
    },
    {
        "name": "get_queue_stats",
        "description": (
            "查詢 Celery 任務隊列統計（積壓量、Worker 狀態）。\n"
            "觸發詞：隊列狀態、任務積壓、Worker 狀態"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── Layer 2: 知識庫搜索（3_skills RAG，Platform Agent 也能查業務知識）──
    {
        "name": "knowledge_search",
        "description": (
            "從 3_skills 知識庫中搜索業務領域知識（SFC規例、VaR方法、合規閾值等）。\n"
            "Platform Agent 在執行業務任務時可查詢業務規則和合規閾值。\n"
            "觸發詞：SFC 規定、合規閾值、VaR 方法、業務規則、守則條款"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":  {"type": "string", "description": "搜索問題或關鍵詞"},
                "source": {"type": "string",
                           "enum": ["skill_doc", "sfc_regulation", "fund_doc", "agent_prompt"],
                           "description": "限定知識來源（可選）"},
            },
            "required": ["query"],
        },
    },
    # ── 系統業務功能擴展工具 ────────────────────────────────────────
    {
        "name": "scaffold_system_tool",
        "description": (
            "為 aiagent 生成新系統業務工具的代碼腳手架。\n"
            "開發者審查後添加到 aiagent/engine/tools.py，"
            "擴展所有用戶可用的業務工具集。\n"
            "觸發詞：添加新工具、新業務工具、擴展工具、scaffold tool"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name":    {"type": "string", "description": "工具名稱（snake_case）"},
                "description":  {"type": "string", "description": "業務用途說明"},
                "api_endpoint": {"type": "string", "description": "對應 processing API 端點"},
                "parameters":   {"type": "object", "description": "參數定義"},
            },
            "required": ["tool_name", "description"],
        },
    },
    {
        "name": "scaffold_system_skill",
        "description": (
            "生成新系統業務技能的 SKILL.md 模板。\n"
            "可添加到 3_skills/skills/（Platform Agent 技能）"
            "或 aiagent/skills/（Chat Agent 技能）。\n"
            "觸發詞：添加新技能、新業務技能、擴展技能、scaffold skill"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name":   {"type": "string", "description": "技能名（kebab-case）"},
                "description":  {"type": "string", "description": "技能用途"},
                "layer":        {"type": "string", "enum": ["platform", "chat"], "description": "所屬層級"},
                "category":     {"type": "string", "description": "分類目錄"},
                "tools_needed": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["skill_name", "description", "layer"],
        },
    },
    {
        "name": "scaffold_agent_role",
        "description": (
            "生成新 Agent 角色的系統提示模板。\n"
            "可添加到 platform_agent/agents/（系統角色）"
            "或 aiagent/agents/（用戶業務角色）。\n"
            "觸發詞：添加新 Agent、新角色、擴展 Agent"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id":    {"type": "string", "description": "Agent ID（kebab-case）"},
                "agent_name":  {"type": "string", "description": "Agent 中文名"},
                "layer":       {"type": "string", "enum": ["platform", "chat"]},
                "description": {"type": "string", "description": "業務定位說明"},
                "tools":       {"type": "array", "items": {"type": "string"}},
            },
            "required": ["agent_id", "agent_name", "layer", "description"],
        },
    },
]


# ── 執行器 ─────────────────────────────────────────────────────────

async def execute_system_tool(name: str, tool_input: dict) -> dict[str, Any]:
    """執行 Platform Agent 系統運維工具。"""
    try:
        if name == "trigger_celery_task":
            return _trigger_celery_task(tool_input)
        elif name == "get_task_status":
            return _get_task_status(tool_input)
        elif name == "check_system_health":
            return await _check_system_health(tool_input)
        elif name == "query_business_db":
            return await _query_business_db(tool_input)
        elif name == "trigger_report":
            return await _trigger_report(tool_input)
        elif name == "get_queue_stats":
            return _get_queue_stats()
        elif name == "knowledge_search":
            return await _platform_knowledge_search(tool_input)
        elif name == "scaffold_system_tool":
            return _scaffold_system_tool(tool_input)
        elif name == "scaffold_system_skill":
            return _scaffold_system_skill(tool_input)
        elif name == "scaffold_agent_role":
            return _scaffold_agent_role(tool_input)
        else:
            return {"error": f"未知工具：{name}"}
    except Exception as exc:
        logger.error("[system_tool] %s failed: %s", name, exc)
        return {"error": str(exc)[:300]}


def _trigger_celery_task(inp: dict) -> dict:
    """通過 Celery 觸發業務任務。"""
    task_name = inp.get("task_name", "")
    kwargs    = inp.get("kwargs", {})
    try:
        import importlib
        tasks = importlib.import_module("2_processing.workers.tasks")
        task_fn = getattr(tasks, task_name, None)
        if not task_fn:
            return {"error": f"未知任務：{task_name}"}
        result = task_fn.apply_async(kwargs=kwargs)
        return {
            "task_id": result.id,
            "task_name": task_name,
            "status": "submitted",
            "message": f"任務 {task_name} 已提交，task_id: {result.id}",
        }
    except Exception as exc:
        return {"error": str(exc)[:300], "hint": "請確認 Celery Worker 已啟動"}


def _get_task_status(inp: dict) -> dict:
    """查詢 Celery 任務狀態。"""
    task_id = inp.get("task_id", "")
    try:
        from celery.result import AsyncResult
        import importlib
        celery_app = importlib.import_module("2_processing.workers.celery_app")
        result = AsyncResult(task_id, app=celery_app.app)
        info = {
            "task_id": task_id,
            "status": result.status,
            "ready":  result.ready(),
        }
        if result.ready():
            try:
                info["result"] = result.result
            except Exception:
                info["result"] = str(result.result)[:200]
        return info
    except Exception as exc:
        return {"error": str(exc)[:200]}


async def _check_system_health(inp: dict) -> dict:
    """服務健康檢查。"""
    services_map = {
        "processing": (PROCESSING_URL,        "/health"),
        "entry":      ("http://localhost:8010", "/health"),
        "backend":    ("http://localhost:8000", "/api/v1/utils/health-check/"),
    }
    target = inp.get("service", "all")
    check_list = list(services_map.items()) if target == "all" else [
        (target, services_map[target])] if target in services_map else []
    if not check_list:
        return {"error": f"未知服務：{target}"}
    results: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=5) as client:
        for svc, (base, path) in check_list:
            try:
                r = await client.get(f"{base}{path}")
                results[svc] = {"status": "ok" if r.status_code == 200 else "error",
                                "code": r.status_code}
            except Exception as exc:
                results[svc] = {"status": "unreachable", "error": str(exc)[:80]}
    all_ok = all(v.get("status") == "ok" for v in results.values())
    return {"overall": "healthy" if all_ok else "degraded", "services": results}


async def _query_business_db(inp: dict) -> dict:
    """只讀查詢業務數據（僅 SELECT）。"""
    sql   = inp.get("sql", "").strip()
    limit = min(int(inp.get("limit", 50)), 200)
    if not sql.upper().lstrip().startswith("SELECT"):
        return {"error": "安全限制：只允許 SELECT 查詢"}
    db_url = os.getenv("DATABASE_URL") or (
        f"postgresql://{os.getenv('POSTGRES_USER','postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD','postgres')}@"
        f"{os.getenv('POSTGRES_SERVER','localhost')}:5432/"
        f"{os.getenv('POSTGRES_DB','fsi_risk')}"
    )
    try:
        import asyncpg
        conn = await asyncpg.connect(db_url)
        rows = await conn.fetch(f"{sql} LIMIT {limit}")
        await conn.close()
        return {"row_count": len(rows), "rows": [dict(r) for r in rows]}
    except Exception as exc:
        return {"error": str(exc)[:300]}


async def _trigger_report(inp: dict) -> dict:
    """觸發報表生成（調用 processing API）。"""
    report_id  = inp.get("report_id", "")
    fund_id    = inp.get("fund_id", "")
    as_of_date = inp.get("as_of_date", "")
    if not all([report_id, fund_id, as_of_date]):
        return {"error": "缺少 report_id / fund_id / as_of_date"}
    try:
        async with httpx.AsyncClient(
            base_url=PROCESSING_URL,
            headers={"X-API-Key": PROCESSING_KEY},
            timeout=30,
        ) as c:
            r = await c.post("/reports/generate", json={
                "report_id": report_id, "fund_id": fund_id, "as_of_date": as_of_date,
            })
            return r.json() if r.status_code in (200, 201, 202) else {
                "error": f"HTTP {r.status_code}", "detail": r.text[:200]}
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _get_queue_stats() -> dict:
    """查詢 Celery 隊列統計。"""
    try:
        import importlib
        celery_app = importlib.import_module("2_processing.workers.celery_app")
        inspect = celery_app.app.control.inspect(timeout=3)
        stats = inspect.stats() or {}
        active = inspect.active() or {}
        return {
            "workers": list(stats.keys()),
            "active_tasks": {w: len(t) for w, t in active.items()},
            "worker_count": len(stats),
        }
    except Exception as exc:
        return {"error": str(exc)[:200], "hint": "請確認 Celery Worker 已啟動"}


async def _platform_knowledge_search(inp: dict) -> dict:
    """Platform Agent 也能搜索 3_skills 知識庫，查詢業務規則和合規閾值。"""
    query  = inp.get("query", "")
    source = inp.get("source")
    if not query:
        return {"error": "query 不能為空"}
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from aiagent.memory.vector_store import hybrid_search
        results = await hybrid_search(query, top_k=5, source_filter=source)
        if not results:
            return {"query": query, "results": [], "note": "知識庫暫無相關內容"}
        return {
            "query":   query,
            "results": [{"title": r["title"], "content": r["content"][:600],
                         "score": round(r["score"], 4)} for r in results],
        }
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _scaffold_system_tool(inp: dict) -> dict:
    name = inp.get("tool_name", "new_tool")
    desc = inp.get("description", "工具說明")
    api  = inp.get("api_endpoint", "/your/endpoint")
    return {
        "tool_name": name,
        "target_file": "aiagent/engine/tools.py",
        "scaffold": f'''
# ── 添加到 TOOLS 列表 ──────────────────────────────────────
{{
    "name": "{name}",
    "description": "{desc}\n觸發詞：[填入觸發詞]",
    "input_schema": {{
        "type": "object",
        "properties": {{
            "fund_id":    {{"type": "string", "description": "基金 ID"}},
            "as_of_date": {{"type": "string", "description": "估值日期 YYYY-MM-DD"}},
        }},
        "required": ["fund_id", "as_of_date"],
    }},
}},

# ── 添加 execute_tool dispatch ──────────────────────────────
# if name == "{name}":
#     return await _execute_{name}(tool_input)

# ── 執行函數 ───────────────────────────────────────────────
async def _execute_{name}(inp: dict) -> dict:
    """Layer 3 — {desc}"""
    fund_id    = inp.get("fund_id", "")
    as_of_date = inp.get("as_of_date", "")
    if not (fund_id and as_of_date):
        return {{"error": "缺少 fund_id 或 as_of_date"}}
    try:
        async with httpx.AsyncClient(
            base_url=PROCESSING_URL,
            headers={{"X-API-Key": PROCESSING_KEY}}, timeout=30
        ) as c:
            r = await c.get(f"{api}/{{fund_id}}", params={{"as_of_date": as_of_date}})
            return r.json() if r.status_code == 200 else {{"error": f"HTTP {{r.status_code}}"}}
    except Exception as exc:
        return {{"error": str(exc)[:200]}}
''',
        "next_steps": [
            f"1. 複制 scaffold 代碼到 aiagent/engine/tools.py",
            f"2. 在 execute_tool() 添加 dispatch: if name == '{name}': ...",
            f"3. 在 backend/app/api/routes/fsi/agent.py _STATIC_MODELS 確認工具已暴露",
            f"4. 重啟 6_entry 服務",
        ],
    }


def _scaffold_system_skill(inp: dict) -> dict:
    name     = inp.get("skill_name", "new-skill")
    desc     = inp.get("description", "技能說明")
    layer    = inp.get("layer", "chat")
    category = inp.get("category", "analysis")
    tools    = inp.get("tools_needed", [])

    base = "3_skills/skills" if layer == "platform" else "aiagent/skills"
    path = f"{base}/{category}/{name}/SKILL.md"
    return {
        "target_path": path,
        "template": f"""---
name: {name}
category: {category}
layer: {layer}
description: {desc}
tools: {", ".join(tools) if tools else "get_system_info, get_exposure"}
version: "1.0"
---

# {desc}

## 觸發條件

- [填入觸發關鍵詞]

## 執行步驟

1. **確認參數** — `get_system_info()` 確認基金 ID 和日期
2. **數據獲取** — [調用相關工具]
3. **分析計算** — [業務邏輯]
4. **輸出結果** — [結構化輸出]

## 輸出格式

```markdown
## [技能名稱] 結果

[輸出模板]
```
""",
        "next_steps": [
            f"1. 創建目錄: mkdir -p {path.rsplit('/', 1)[0]}",
            f"2. 寫入模板到 {path}",
            f"3. 如是 platform 技能，在 3_skills/README.md 更新索引",
            f"4. 如是 chat 技能，在 knowledge_indexer.py 重新索引",
        ],
    }


def _scaffold_agent_role(inp: dict) -> dict:
    agent_id   = inp.get("agent_id", "new-agent")
    agent_name = inp.get("agent_name", "新 Agent")
    layer      = inp.get("layer", "chat")
    desc       = inp.get("description", "角色定位")
    tools      = inp.get("tools", [])

    base = "platform_agent/agents" if layer == "platform" else "aiagent/agents"
    path = f"{base}/{agent_id}.md"
    template = f"""---
name: {agent_id}
role: {agent_name}
layer: {layer}
tools: {", ".join(tools) if tools else "get_system_info"}
---

# 角色：{agent_name}

{desc}

## 核心職責

- [主要職責1]
- [主要職責2]

## 工作流程

1. 確認參數（基金 ID、日期）
2. 調用相關工具獲取數據
3. 分析並輸出結果

## 輸出規範

- 用繁體中文回覆
- 數字必須來自工具數據
"""
    next_steps = [
        f"1. 將模板寫入 {path}",
    ]
    if layer == "chat":
        next_steps += [
            f"2. 在 aiagent/engine/runner.py AGENT_NAMES 添加: '{agent_id}': '{agent_name}'",
            f"3. 在 backend/app/api/routes/fsi/agent.py _STATIC_AGENTS 添加同樣條目",
            f"4. 重啟 6_entry 和 backend 服務",
        ]
    else:
        next_steps += [
            f"2. 在 platform_agent/engine/platform_runner.py PLATFORM_AGENT_NAMES 添加: '{agent_id}': '{agent_name}'",
            f"3. 重啟 6_entry 服務",
        ]
    return {"target_path": path, "template": template, "next_steps": next_steps}
