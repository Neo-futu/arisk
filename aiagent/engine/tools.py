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
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── 調用路徑配置 ───────────────────────────────────────────────────
TOOL_MODE        = os.getenv("AGENT_TOOL_MODE", "direct")          # direct | via_backend
PROCESSING_URL   = os.getenv("PROCESSING_API_URL", "http://localhost:8001")
PROCESSING_KEY   = os.getenv("PROCESSING_API_KEY", "internal_key_change_me")
BACKEND_URL      = os.getenv("BACKEND_URL", "http://localhost:8000")

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


async def _execute_get_system_info() -> dict:
    """調用 processing /context 端點，返回基金列表 + 當前日期。"""
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
