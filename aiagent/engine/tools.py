"""
aiagent/engine/tools.py — FSI 業務工具定義

參考 claude-risk-agent 的工具模式（MCP 工具抽象），
將 2_processing FastAPI 端點封裝為 Claude tool_use 可調用的工具。

兩種調用路徑（由 AGENT_TOOL_MODE 環境變量控制）：
  A. direct      — 直接調用 processing:8001（默認，低延遲）
  B. via_backend — 通過 backend:8000 調用（統一認證，需 JWT token）

詳見 aiagent/README.md 的「工具調用路徑」章節。
"""
from __future__ import annotations

import json
import logging
import os
import importlib
from datetime import date
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


async def _call_internal_mcp(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """透過 4_mcp/internal MCP server 讀取內部資料。"""
    try:
        client_mod = importlib.import_module("4_mcp.client")
        return await client_mod.call_internal_tool(tool_name, arguments)
    except Exception as exc:
        logger.error("[mcp] internal %s failed: %s", tool_name, exc)
        return {"error": str(exc)[:200], "tool": tool_name}

# ── 調用路徑配置 ───────────────────────────────────────────────────
TOOL_MODE        = os.getenv("AGENT_TOOL_MODE", "direct")          # direct | via_backend
PROCESSING_URL   = os.getenv("PROCESSING_API_URL", "http://localhost:8001")
PROCESSING_KEY   = os.getenv("PROCESSING_API_KEY", "internal_key_change_me")
BACKEND_URL      = os.getenv("BACKEND_URL", "http://localhost:8000")
REVIEW_REQUIRED  = os.getenv("SKILL_EXTRACTION_REVIEW_REQUIRED", "true").lower() in {"1", "true", "yes", "on"}


async def _request_skill_extraction_approval(
    *,
    channel: str,
    fund_id: str | None,
    as_of_date: str | None,
    skill_name: str | None,
    query: str | None,
    triggered_by: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    在提取專家知識或執行技能前先走審批 gate。

    gate 由 Processing 層實現（requires_review + checkpoint），
    本函數只負責把請求送入 gate 並等待審批結果。
    """
    if not REVIEW_REQUIRED:
        return {"approved": True, "review_bypassed": True}

    params = {}
    if fund_id:
        params["fund_id"] = fund_id
    if as_of_date:
        params["as_of_date"] = as_of_date

    body = {
        "channel": channel,
        "skill_name": skill_name,
        "query": query,
        "triggered_by": triggered_by,
        "payload": payload or {},
    }

    try:
        async with httpx.AsyncClient(
            base_url=PROCESSING_URL,
            headers={"X-API-Key": PROCESSING_KEY},
            timeout=930,
        ) as client:
            resp = await client.post("/review/gates/skill-extraction", params=params, json=body)

        if resp.status_code == 200:
            return resp.json()

        detail = resp.text[:300]
        return {
            "approved": False,
            "status_code": resp.status_code,
            "error": f"技能提取未通過審批（HTTP {resp.status_code}）：{detail}",
        }
    except Exception as exc:
        logger.error("[review-gate] skill extraction approval call failed: %s", exc)
        return {
            "approved": False,
            "status_code": 500,
            "error": f"技能提取審批調用失敗：{str(exc)[:200]}",
        }

# ── Claude tool_use 格式工具定義 ───────────────────────────────────
# 參考 claude-risk-agent/plugins/vertical-plugins/financial-analysis/ 的 Skill 模式
TOOLS: list[dict] = [
    {
        "name": "get_exposure",
        "description": (
            "查詢基金指定日期的風險暴露分析，包含 WAM（加權平均期限）、WAL（加權平均有效期）、"
            "每日流動資產比例（DLA）、每週流動資產比例（WLA）、資產配置分佈、"
            "發行人集中度，以及 SFC 第 8.2 章合規狀態（含違規標記）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id":    {"type": "string", "description": "基金 ID，如 BHMMF001"},
                "as_of_date": {"type": "string", "description": "估值日期 YYYY-MM-DD"},
            },
            "required": ["fund_id", "as_of_date"],
        },
    },
    {
        "name": "get_var",
        "description": (
            "計算基金的風險價值（VaR）和條件風險價值（CVaR）。"
            "支持三種方法：historical（歷史模擬法）、monte_carlo（蒙特卡洛）、"
            "distribution（參數法/正態分佈假設）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id":      {"type": "string", "description": "基金 ID"},
                "as_of_date":   {"type": "string", "description": "估值日期 YYYY-MM-DD"},
                "method":       {"type": "string", "enum": ["historical", "monte_carlo", "distribution"],
                                 "description": "計算方法，默認 historical"},
                "confidence":   {"type": "number", "description": "置信度，0.95 或 0.99，默認 0.99"},
                "horizon_days": {"type": "integer", "description": "持有期天數，默認 1"},
            },
            "required": ["fund_id", "as_of_date"],
        },
    },
    {
        "name": "get_var_compare",
        "description": "並行計算三種方法的 VaR 並返回對比結果，同時標出最保守值。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id":    {"type": "string"},
                "as_of_date": {"type": "string", "description": "估值日期 YYYY-MM-DD"},
                "confidence": {"type": "number", "description": "置信度，默認 0.99"},
            },
            "required": ["fund_id", "as_of_date"],
        },
    },
    {
        "name": "get_positions",
        "description": (
            "查詢基金當日持倉明細，按市值降序排列。"
            "可按資產類別過濾（bond/cd/deposit/repo/cash）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id":    {"type": "string"},
                "as_of_date": {"type": "string", "description": "估值日期 YYYY-MM-DD"},
                "asset_type": {"type": "string",
                               "enum": ["bond", "cd", "deposit", "repo", "cash"],
                               "description": "可選：按資產類別過濾"},
            },
            "required": ["fund_id", "as_of_date"],
        },
    },
    {
        "name": "get_nav_history",
        "description": "查詢基金在一段時間內的每日淨值（NAV）歷史，用於業績分析和趨勢判斷。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id":    {"type": "string"},
                "start_date": {"type": "string", "description": "開始日期 YYYY-MM-DD"},
                "end_date":   {"type": "string", "description": "結束日期 YYYY-MM-DD"},
            },
            "required": ["fund_id", "start_date", "end_date"],
        },
    },
    {
        "name": "get_system_info",
        "description": (
            "查詢系統基礎信息：當前日期、所有在管基金的 fund_id 與基金全名。"
            "當用戶提及基金序號（如1號、第一只）或未指定基金時，應先調用此工具確認正確的 fund_id。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── market-researcher 技能：sector_overview ──────────────────────
    # 整合自 claude-risk-agent/plugins/agent-plugins/market-researcher/skills/sector-overview
    # 將 SKILL.md 的結構化研究流程封裝為 Claude tool_use 可調用的工具
    {
        "name": "sector_overview",
        "description": (
            "執行香港貨幣市場/信用市場的行業概覽研究（sector-overview 技能）。"
            "整合自 claude-risk-agent/market-researcher，針對 HK MMF 場景定制。\n"
            "返回結構化研究筆記，涵蓋：\n"
            "  • 利率環境（HIBOR 走勢、短端利率）\n"
            "  • 信用市場格局（香港銀行業評級、CD 發行人）\n"
            "  • MMF 行業競爭格局\n"
            "  • 關鍵主題與風險\n"
            "觸發詞：行業概覽、市場分析、sector overview、信用環境、HIBOR、發行人分析。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "研究主題，如：'香港銀行業 CD 發行人信用分析'、"
                        "'HIBOR 利率走勢與 MMF 收益影響'、"
                        "'香港 MMF 市場競爭格局'"
                    ),
                },
                "depth": {
                    "type": "string",
                    "enum": ["brief", "standard", "deep"],
                    "description": "研究深度：brief=概覽段落, standard=結構化報告, deep=完整深度分析",
                },
                "fund_id": {
                    "type": "string",
                    "description": "可選：關聯基金 ID，用於將研究結果與當前持倉對比",
                },
                "as_of_date": {
                    "type": "string",
                    "description": "可選：估值日期 YYYY-MM-DD，用於持倉對比",
                },
            },
            "required": ["topic"],
        },
    },
    # ── Layer 2: 知識庫搜索（RAG） ───────────────────────────────────
    {
        "name": "knowledge_search",
        "description": (
            "從知識庫中搜索相關信息（支持中英文，自動 BM25+ILIKE 搜索）。\n"
            "知識庫包含：SFC規例、基金文件、公司制度、專家上傳文檔、業務技能說明。\n"
            "適用場景：\n"
            "  • 查詢 SFC 守則具體條款\n"
            "  • 搜索公司內部制度文件（如氣候風險管理、投資政策等）\n"
            "  • 檢索業務技能知識\n"
            "重要：不要指定 source 過濾，除非明確知道文檔來源類型，否則搜不到結果。\n"
            "觸發詞：制度、守則、規定、條款、知識庫、參考文件"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索問題或關鍵詞（中英文均可，無需完全匹配）",
                },
                "source": {
                    "type": "string",
                    "description": (
                        "可選：限定來源（skill_doc / agent_prompt / expert_chat / "
                        "sfc_regulation / fund_doc / manual）。"
                        "不確定時留空，搜索所有來源。"
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回結果數量，默認 5，最大 10",
                },
            },
            "required": ["query"],
        },
    },
    # ── Layer 2+3: 技能執行工具（從 3_skills RAG 加載技能並指導執行） ──
    {
        "name": "execute_skill",
        "description": (
            "從 3_skills 知識庫加載指定業務技能的執行指南，"
            "獲取技能的執行步驟、工具調用順序和輸出格式。\n"
            "調用後，按返回的步驟依次調用相應業務工具完成任務。\n"
            "可用技能：\n"
            "  • mmf-compliance  — SFC 守則第8.2章合規核查\n"
            "  • risk-analysis   — 風控指標全面分析（WAM/WAL/VaR/集中度）\n"
            "  • var-analysis    — VaR 三方法詳細計算與對比\n"
            "  • performance-report — 業績報告生成\n"
            "  • human-review    — 人工審核流程\n"
            "觸發詞：按技能執行、用XXX技能分析、complete skill、run skill"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "enum": ["mmf-compliance", "risk-analysis", "var-analysis",
                             "performance-report", "human-review", "xlsx-report"],
                    "description": "3_skills 中的技能名稱",
                },
                "fund_id": {
                    "type": "string",
                    "description": "基金 ID（執行時傳入，如 BHMMF001）",
                },
                "as_of_date": {
                    "type": "string",
                    "description": "估值日期 YYYY-MM-DD",
                },
            },
            "required": ["skill_name"],
        },
    },
    # ── Layer 3: 報表生成工具（AI → 2_processing 報表引擎） ──────────
    {
        "name": "generate_report",
        "description": (
            "觸發生成基金報表並返回任務狀態。支持三種報表類型：\n"
            "  • report_03_mmf       — MMF 日報（SFC 合規版，Excel）\n"
            "  • report_04_mmf_monthly — MMF 月報 Factsheet（Word）\n"
            "  • report_06           — 基金詳細分析報告（Excel）\n"
            "任務異步執行，返回 task_id 可供輪詢進度。\n"
            "觸發詞：生成報告、生成報表、輸出報表、製作日報、製作月報"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_id": {
                    "type": "string",
                    "enum": ["report_03_mmf", "report_04_mmf_monthly", "report_06"],
                    "description": "報表類型 ID",
                },
                "fund_id": {
                    "type": "string",
                    "description": "基金 ID，如 BHMMF001",
                },
                "as_of_date": {
                    "type": "string",
                    "description": "報表日期 YYYY-MM-DD",
                },
            },
            "required": ["report_id", "fund_id", "as_of_date"],
        },
    },
    # ── Layer 3: 內部數據庫直查工具（AI → 4_mcp 內部 MCP） ──────────
    {
        "name": "query_internal_db",
        "description": (
            "直接查詢內部數據庫的原始數據，用於深度分析。\n"
            "支持查詢類型：\n"
            "  • fund_list      — 查詢所有在管基金列表\n"
            "  • nav_history    — 查詢基金 NAV 歷史（需 fund_id + start_date + end_date）\n"
            "  • risk_snapshot  — 查詢最新風控快照數據（需 fund_id）\n"
            "  • var_series     — 查詢 VaR 歷史序列（需 fund_id + start_date）\n"
            "觸發詞：原始數據、歷史序列、數據庫查詢、VAR趨勢、NAV走勢"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["fund_list", "nav_history", "risk_snapshot", "var_series"],
                    "description": "查詢類型",
                },
                "fund_id":    {"type": "string", "description": "基金 ID（多數查詢需要）"},
                "start_date": {"type": "string", "description": "開始日期 YYYY-MM-DD"},
                "end_date":   {"type": "string", "description": "結束日期 YYYY-MM-DD"},
            },
            "required": ["query_type"],
        },
    },
]


# ── 工具執行器 ────────────────────────────────────────────────────
async def execute_tool(
    name: str,
    tool_input: dict,
    jwt_token: str | None = None,
) -> dict[str, Any]:
    """
    執行 FSI 業務工具。

    路徑 A（direct）：直接調用 processing:8001，帶 X-API-Key 頭
    路徑 B（via_backend）：調用 backend:8000，帶 Bearer JWT

    返回工具結果 dict，供 Claude tool_result 使用。
    """
    if name == "get_system_info":
        return await _execute_get_system_info()

    if name == "knowledge_search":
        return await _execute_knowledge_search(tool_input)

    if name == "execute_skill":
        return await _execute_skill(tool_input)

    if name == "generate_report":
        return await _execute_generate_report(tool_input)

    if name == "query_internal_db":
        return await _execute_query_internal_db(tool_input)

    # 用戶自定義工具（動態 HTTP 調用）
    if tool_input.get("_user_tool"):
        return await _execute_user_custom_tool(name, tool_input)

    # sector_overview 是本地技能（SKILL.md），不調用外部 API
    if name == "sector_overview":
        return await _execute_sector_overview(tool_input)

    try:
        if TOOL_MODE == "via_backend" and jwt_token:
            return await _call_via_backend(name, tool_input, jwt_token)
        return await _call_direct(name, tool_input)
    except Exception as exc:
        logger.error("[tool] %s failed: %s", name, exc)
        return {"error": str(exc), "tool": name}


async def _execute_skill(inp: dict) -> dict:
    """
    Layer 2+3 — 從 3_skills RAG 加載技能執行指南。

    流程：
      1. 從 fsi.knowledge_chunk 搜索技能名稱
      2. 返回技能的執行步驟、工具調用清單、輸出格式
      3. LLM 接收後按步驟依次調用業務工具完成任務

    這是 3_skills → RAG → Chat Agent 工具執行 的關鍵橋樑。
    """
    skill_name = inp.get("skill_name", "")
    fund_id    = inp.get("fund_id", "")
    as_of_date = inp.get("as_of_date", "")

    if not skill_name:
        return {"error": "缺少 skill_name"}

    gate = await _request_skill_extraction_approval(
        channel="agentchat-skill",
        fund_id=fund_id or None,
        as_of_date=as_of_date or None,
        skill_name=skill_name,
        query=None,
        triggered_by="aiagent.execute_skill",
        payload={"tool": "execute_skill", "input": inp},
    )
    if not gate.get("approved", False):
        return {
            "error": gate.get("error", "技能提取審批未通過"),
            "review_required": True,
            "action": "請到 /review-ui/inbox 完成審批後重試",
        }

    # 先嘗試直接讀取 SKILL.md 文件（最準確）
    try:
        from pathlib import Path
        repo_root = Path(__file__).parent.parent.parent
        # 搜索 3_skills 目錄中的對應技能
        skill_path = None
        for p in repo_root.rglob(f"{skill_name}/SKILL.md"):
            if "3_skills" in str(p) or "aiagent/skills" in str(p):
                skill_path = p
                break

        if skill_path and skill_path.exists():
            import re
            raw = skill_path.read_text(encoding="utf-8")
            # 去掉 frontmatter
            content = re.sub(r"^---\n.*?\n---\n", "", raw, flags=re.DOTALL).strip()
            return {
                "skill_name":  skill_name,
                "source":      "3_skills/" + str(skill_path.relative_to(repo_root)),
                "content":     content,
                "fund_id":     fund_id,
                "as_of_date":  as_of_date,
                "instruction": (
                    f"已加載技能「{skill_name}」的完整執行指南。\n"
                    f"請按上方 content 中的「執行步驟」依次調用對應工具：\n"
                    f"  基金 ID：{fund_id or '請先調用 get_system_info 確認'}\n"
                    f"  估值日期：{as_of_date or '請先調用 get_system_info 確認'}\n"
                    f"執行完所有步驟後，按「輸出格式」輸出最終結果。"
                ),
            }
    except Exception as exc:
        logger.warning("[execute_skill] direct file read failed: %s", exc)

    # 降級：從 RAG 搜索
    try:
        from aiagent.memory.vector_store import hybrid_search
        results = await hybrid_search(skill_name, top_k=5)
        if results:
            combined = "\n\n---\n\n".join(r["content"] for r in results[:3])
            return {
                "skill_name":  skill_name,
                "source":      "RAG knowledge_chunk",
                "content":     combined,
                "fund_id":     fund_id,
                "as_of_date":  as_of_date,
                "instruction": (
                    f"已從知識庫搜索到「{skill_name}」相關執行指南。\n"
                    f"請按 content 中的步驟執行，基金={fund_id}，日期={as_of_date}。"
                ),
            }
    except Exception as exc:
        logger.error("[execute_skill] RAG fallback failed: %s", exc)

    return {
        "error": f"技能「{skill_name}」未找到，請確認技能名稱或先運行知識庫索引",
        "available_skills": ["mmf-compliance", "risk-analysis", "var-analysis",
                             "performance-report", "human-review"],
    }


async def _execute_user_custom_tool(tool_name: str, inp: dict) -> dict:
    """
    執行用戶自定義工具（動態 HTTP 調用）。
    endpoint 和 method 由 runner 從 DB 加載後注入 tool_input。
    """
    endpoint = inp.get("_endpoint", "")
    method   = inp.get("_method", "GET").upper()
    # 過濾掉內部字段，只傳業務參數
    params   = {k: v for k, v in inp.items() if not k.startswith("_")}
    if not endpoint:
        return {"error": f"用戶工具 '{tool_name}' 缺少 endpoint 配置"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            if method == "GET":
                r = await c.get(endpoint, params=params)
            else:
                r = await c.post(endpoint, json=params)
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    return {"content": r.text[:500]}
            return {"error": f"HTTP {r.status_code}", "detail": r.text[:200]}
    except Exception as exc:
        return {"error": str(exc)[:200]}


async def _execute_knowledge_search(inp: dict) -> dict:
    """Layer 2 — RAG 知識庫搜索：調用 vector_store 的混合搜索。"""
    query  = inp.get("query", "")
    source = inp.get("source")
    top_k  = min(int(inp.get("top_k", 5)), 10)

    if not query:
        return {"error": "query 不能為空"}

    source_value = (source or "").strip().lower()
    requires_gate = source_value in {"skill_doc", "agent_prompt", "expert_chat"}

    if requires_gate:
        gate = await _request_skill_extraction_approval(
            channel="expert-knowledge",
            fund_id=inp.get("fund_id"),
            as_of_date=inp.get("as_of_date"),
            skill_name=None,
            query=query,
            triggered_by="aiagent.knowledge_search",
            payload={"tool": "knowledge_search", "source": source, "top_k": top_k},
        )
        if not gate.get("approved", False):
            return {
                "error": gate.get("error", "專家知識提取審批未通過"),
                "review_required": True,
                "action": "請到 /review-ui/inbox 完成審批後重試",
            }

    try:
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from aiagent.memory.vector_store import hybrid_search
        results = await hybrid_search(query, top_k=top_k, source_filter=source)
        if not results:
            return {
                "query":   query,
                "results": [],
                "note":    "知識庫中未找到相關內容。請嘗試不同的關鍵詞，或考慮知識庫尚未收錄此類文件。",
            }
        return {
            "query":   query,
            "results": [
                {
                    "title":    r["title"],
                    "source":   r["source"],
                    "content":  r["content"][:800],   # 截斷避免 context 過長
                    "score":    round(r["score"], 4),
                }
                for r in results
            ],
        }
    except Exception as exc:
        logger.error("[tool] knowledge_search failed: %s", exc)
        return {"error": f"知識庫搜索失敗：{str(exc)[:200]}"}


async def _execute_generate_report(inp: dict) -> dict:
    """
    Layer 3 — 觸發報表生成（AI → 2_processing 報表引擎）。
    調用 processing API POST /reports/generate，異步任務。
    """
    report_id  = inp.get("report_id", "")
    fund_id    = inp.get("fund_id", "")
    as_of_date = inp.get("as_of_date", "")
    if not all([report_id, fund_id, as_of_date]):
        return {"error": "缺少必要參數：report_id / fund_id / as_of_date"}

    try:
        async with httpx.AsyncClient(
            base_url=PROCESSING_URL,
            headers={"X-API-Key": PROCESSING_KEY},
            timeout=30,
        ) as c:
            r = await c.post("/reports/generate", json={
                "report_id":  report_id,
                "fund_id":    fund_id,
                "as_of_date": as_of_date,
            })
            if r.status_code not in (200, 201, 202):
                return {"error": f"HTTP {r.status_code}", "detail": r.text[:200]}
            data = r.json()
            return {
                "task_id":   data.get("task_id"),
                "status":    data.get("status", "queued"),
                "message":   f"報表生成任務已提交（{report_id} / {fund_id} / {as_of_date}）",
                "poll_hint": "任務異步執行，通常需要 10-60 秒，請稍後查詢結果",
            }
    except Exception as exc:
        logger.error("[tool] generate_report failed: %s", exc)
        return {"error": str(exc)[:200]}


async def _execute_query_internal_db(inp: dict) -> dict:
    """
    Layer 3 — 查詢內部數據庫（AI → 4_mcp 內部 MCP 查詢邏輯）。
    優先走 4_mcp/internal 的只讀 MCP tool。
    """
    qtype    = inp.get("query_type", "")
    fund_id  = inp.get("fund_id", "")
    start    = inp.get("start_date", "")
    end      = inp.get("end_date", "")

    if qtype == "fund_list":
        return await _call_internal_mcp("get_fund_list", {})

    if qtype == "nav_history":
        if not (fund_id and start):
            return {"error": "nav_history 需要 fund_id 和 start_date"}
        return await _call_internal_mcp("get_nav_history", {
            "fund_id": fund_id,
            "start_date": start,
            "end_date": end or start,
        })

    if qtype == "risk_snapshot":
        if not fund_id:
            return {"error": "risk_snapshot 需要 fund_id"}
        return await _call_internal_mcp("get_risk_snapshot", {
            "fund_id": fund_id,
            "as_of_date": end or date.today().isoformat(),
        })

    if qtype == "var_series":
        if not (fund_id and start):
            return {"error": "var_series 需要 fund_id 和 start_date"}
        return await _call_internal_mcp("get_var_three_methods", {
            "fund_id": fund_id,
            "as_of_date": end or start,
        })

    try:
        async with httpx.AsyncClient(
            base_url=PROCESSING_URL,
            headers={"X-API-Key": PROCESSING_KEY},
            timeout=20,
        ) as c:
            if qtype == "risk_snapshot":
                if not fund_id:
                    return {"error": "risk_snapshot 需要 fund_id"}
                today = date.today().isoformat()
                r = await c.get(f"/risk/exposure/{fund_id}", params={"as_of_date": end or today})
                return r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}", "detail": r.text[:200]}

            return {"error": f"未知查詢類型：{qtype}"}
    except Exception as exc:
        logger.error("[tool] query_internal_db failed: %s", exc)
        return {"error": str(exc)[:200]}


async def _execute_get_system_info() -> dict:
    """優先調用 4_mcp/internal 的 get_context，再降級到 processing /context。"""
    result = await _call_internal_mcp("get_context", {})
    if result and not result.get("error"):
        return result

    try:
        async with httpx.AsyncClient(
            base_url=PROCESSING_URL,
            headers={"X-API-Key": PROCESSING_KEY},
            timeout=10,
        ) as c:
            r = await c.get("/context")
            if r.status_code == 200:
                return r.json()
            return {"error": f"HTTP {r.status_code}", "detail": r.text[:200]}
    except Exception as exc:
        return {"error": str(exc)}


async def _execute_sector_overview(inp: dict) -> dict:
    """
    執行 sector-overview 技能。
    整合自 claude-risk-agent/market-researcher/skills/sector-overview/SKILL.md。

    策略：返回技能框架 + 觸發上下文，讓 Claude 的下一輪用自身知識填充研究內容。
    如果傳入 fund_id，同時拉取持倉數據作為市場分析的基礎。
    """
    topic      = inp.get("topic", "香港貨幣市場")
    depth      = inp.get("depth", "standard")
    fund_id    = inp.get("fund_id")
    as_of_date = inp.get("as_of_date")

    # 讀取 SKILL.md 框架
    skill_path = Path(__file__).parent.parent / "skills" / "sector-overview" / "SKILL.md"
    skill_template = ""
    if skill_path.exists():
        skill_template = skill_path.read_text(encoding="utf-8")

    result: dict[str, Any] = {
        "skill":    "sector-overview",
        "topic":    topic,
        "depth":    depth,
        "template": skill_template,
        "instruction": (
            f"請使用 sector-overview 技能框架，針對主題「{topic}」輸出"
            f"{'概覽段落' if depth == 'brief' else '結構化研究報告' if depth == 'standard' else '完整深度分析'}。"
            "基於 ARISK 的香港 MMF 業務背景，關注信用質量、利率環境和流動性。"
        ),
    }

    # 若傳入基金，拉取持倉作為研究基礎
    if fund_id and as_of_date:
        try:
            exposure = await _call_direct("get_exposure", {"fund_id": fund_id, "as_of_date": as_of_date})
            result["portfolio_context"] = {
                "fund_id":      fund_id,
                "as_of_date":   as_of_date,
                "top_issuers":  exposure.get("top_issuers", [])[:5],
                "by_asset_type": exposure.get("by_asset_type", {}),
                "wam_days":     exposure.get("wam_days"),
                "is_compliant": exposure.get("is_compliant"),
            }
        except Exception as exc:
            result["portfolio_context"] = {"error": str(exc)}

    return result


async def _call_direct(name: str, inp: dict) -> dict:
    """路徑 A：直接調用 processing:8001"""
    if name == "get_positions":
        return await _call_internal_mcp("get_positions", {
            "fund_id": inp.get("fund_id", ""),
            "as_of_date": inp.get("as_of_date", ""),
            "asset_type": inp.get("asset_type"),
            "limit": inp.get("limit", 50),
        })

    if name == "get_nav_history":
        return await _call_internal_mcp("get_nav_history", {
            "fund_id": inp.get("fund_id", ""),
            "start_date": inp.get("start_date", ""),
            "end_date": inp.get("end_date", ""),
        })

    if name == "get_var_compare":
        result = await _call_internal_mcp("get_var_three_methods", {
            "fund_id": inp.get("fund_id", ""),
            "as_of_date": inp.get("as_of_date", ""),
            "confidence": inp.get("confidence", 0.99),
            "horizon_days": inp.get("horizon_days", 1),
            "lookback_days": inp.get("lookback_days", 252),
            "min_observations": inp.get("min_observations", 30),
            "simulations": inp.get("simulations", 10000),
        })
        if result.get("error"):
            return result
        raw_results = result.get("results", [])
        if isinstance(raw_results, list):
            max_var = max(float(r.get("var_pct_nav") or 0) for r in raw_results if isinstance(r, dict)) if raw_results else 0
            result["max_var_pct_nav"] = max_var
        return result

    if name == "get_var":
        result = await _call_internal_mcp("get_var_three_methods", {
            "fund_id": inp.get("fund_id", ""),
            "as_of_date": inp.get("as_of_date", ""),
            "confidence": inp.get("confidence", 0.99),
            "horizon_days": inp.get("horizon_days", 1),
            "lookback_days": inp.get("lookback_days", 252),
            "min_observations": inp.get("min_observations", 30),
            "simulations": inp.get("simulations", 10000),
        })
        if result.get("error"):
            return result
        method = str(inp.get("method", "historical"))
        method_map = {
            "historical": "HISTORICAL_SIMULATION",
            "monte_carlo": "MONTE_CARLO",
            "distribution": "DISTRIBUTION_FORMULA",
        }
        desired = method_map.get(method, "HISTORICAL_SIMULATION")
        chosen = None
        for item in result.get("results", []):
            if isinstance(item, dict) and item.get("method") == desired:
                chosen = item
                break
        if chosen is None and isinstance(result.get("results"), list) and result["results"]:
            chosen = result["results"][0]
        if isinstance(chosen, dict):
            return {
                "fund_id": result.get("fund_id", inp.get("fund_id", "")),
                "as_of_date": result.get("as_of_date", inp.get("as_of_date", "")),
                "confidence": result.get("confidence", inp.get("confidence", 0.99)),
                "horizon_days": result.get("horizon_days", inp.get("horizon_days", 1)),
                "var_hkd": chosen.get("var_hkd", 0),
                "var_pct_nav": chosen.get("var_pct_nav", 0),
                "cvar_hkd": chosen.get("cvar_hkd", 0),
                "method": chosen.get("method", desired),
                "sample_size": chosen.get("sample_size", 0),
                "method_requested": method,
            }
        return result

    headers = {"X-API-Key": PROCESSING_KEY}
    fund_id = inp.get("fund_id", "")

    async with httpx.AsyncClient(base_url=PROCESSING_URL, headers=headers, timeout=30) as c:
        if name == "get_exposure":
            r = await c.get(f"/risk/exposure/{fund_id}",
                            params={"as_of_date": inp["as_of_date"]})
        elif name == "get_var":
            r = await c.get(f"/risk/var/{fund_id}", params={
                "as_of_date": inp["as_of_date"],
                "method":       inp.get("method", "historical"),
                "confidence":   inp.get("confidence", 0.99),
                "horizon_days": inp.get("horizon_days", 1),
            })
        elif name == "get_var_compare":
            r = await c.get(f"/risk/var-compare/{fund_id}", params={
                "as_of_date": inp["as_of_date"],
                "confidence": inp.get("confidence", 0.99),
            })
        elif name == "get_positions":
            params: dict = {"as_of_date": inp["as_of_date"]}
            if inp.get("asset_type"):
                params["asset_type"] = inp["asset_type"]
            r = await c.get(f"/positions/{fund_id}", params=params)
        elif name == "get_nav_history":
            r = await c.get(f"/positions/{fund_id}/nav",
                            params={"start": inp["start_date"], "end": inp["end_date"]})
        else:
            return {"error": f"未知工具：{name}"}

        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "detail": r.text[:300]}
        return r.json()


async def _call_via_backend(name: str, inp: dict, token: str) -> dict:
    """路徑 B：通過 backend:8000（帶 Bearer JWT 認證）"""
    headers = {"Authorization": f"Bearer {token}"}
    fund_id = inp.get("fund_id", "")

    async with httpx.AsyncClient(base_url=BACKEND_URL, headers=headers, timeout=30) as c:
        prefix = "/api/v1/fsi"
        if name == "get_exposure":
            r = await c.get(f"{prefix}/risk/exposure/{fund_id}",
                            params={"as_of_date": inp["as_of_date"]})
        elif name == "get_var":
            r = await c.get(f"{prefix}/risk/var/{fund_id}", params={
                "as_of_date": inp["as_of_date"],
                "method":       inp.get("method", "historical"),
                "confidence":   inp.get("confidence", 0.99),
            })
        elif name == "get_var_compare":
            r = await c.get(f"{prefix}/risk/var-compare/{fund_id}", params={
                "as_of_date": inp["as_of_date"],
                "confidence": inp.get("confidence", 0.99),
            })
        elif name == "get_positions":
            params: dict = {"as_of_date": inp["as_of_date"]}
            if inp.get("asset_type"):
                params["asset_type"] = inp["asset_type"]
            r = await c.get(f"{prefix}/positions/{fund_id}", params=params)
        else:
            return {"error": f"未知工具：{name}（via_backend 模式）"}

        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "detail": r.text[:300]}
        return r.json()
