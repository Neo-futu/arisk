"""小富 AI 審核員：由 Claude 驅動的智能審核助手。

小富是平台內建的 AI 審核顧問，負責：
- 自動分析每個審核請求
- 提供結構化的風險評估和建議
- 識別潛在問題和合規風險
- 為人工審核員提供決策參考

重要：小富是建議者，不是決策者。
- COMPLIANCE_BREACH / HIGH_RISK：小富永遠建議人工審核，從不自動批准
- REPORT_PUBLISH / DATA_LOAD（無違規）：小富可建議自動批准，人工可接受或覆蓋
- 所有最終決策記錄都標明「人工審核」或「採納小富建議」
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import anthropic
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# 小富永遠要求人工審核的類別（不允許 AI 自動批准）
ALWAYS_HUMAN_CATEGORIES = {"COMPLIANCE_BREACH", "HIGH_RISK"}

# 小富的角色描述
XIAO_FU_SYSTEM_PROMPT = """你是「小富」，FSI Risk Platform 的 AI 審核顧問。
你是一個專業、謹慎、友好的金融風控助手。

你的職責：
1. 分析提交的審核請求，評估風險等級
2. 識別合規問題（特別是 SFC 守則第8.2章）
3. 提供結構化的審核建議
4. 為人工審核員提供清晰的決策依據

你的原則：
- 永遠謹慎：不確定時傾向保守建議
- COMPLIANCE_BREACH 和 HIGH_RISK 類別：必須建議人工審核，你絕不自動批准
- 提供具體的守則條款引用
- 說明批准或拒絕的後果
- 用繁體中文回覆

你的輸出必須是嚴格的 JSON，符合 AiReviewResult 結構。
"""


class AiReviewResult(BaseModel):
    risk_level: str          # LOW / MEDIUM / HIGH / CRITICAL
    recommendation: str      # APPROVE / REJECT / ESCALATE / REQUIRE_HUMAN
    confidence: float        # 0.0–1.0
    reasoning: str           # 小富的分析推理（1-3段）
    key_concerns: list[str]  # 主要關切點（bullet 形式）
    suggested_actions: list[str]  # 建議採取的行動
    regulatory_refs: list[str]    # 相關守則條款引用
    auto_approvable: bool    # 是否可以自動批准（COMPLIANCE_BREACH/HIGH_RISK 永遠 False）
    reviewer_note: str       # 給人工審核員的提示


async def run_ai_review(
    db: AsyncSession,
    review_id: str,
    review_data: dict,
) -> AiReviewResult:
    """
    小富執行 AI 審核分析。由 create_review_request 在提交後自動觸發。

    分析完成後，結果寫入 fsi.review_requests.ai_review_result，
    並在 Web UI 的審核收件箱中以「🤖 小富審核」標籤展示。
    """
    category = review_data.get("category", "")
    payload = review_data.get("payload", {})

    # 構建分析提示
    user_prompt = _build_analysis_prompt(review_data)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=XIAO_FU_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text

        # 解析 JSON 輸出
        result_dict = _parse_ai_response(raw)

        # 強制規則：COMPLIANCE_BREACH / HIGH_RISK 不允許自動批准
        if category in ALWAYS_HUMAN_CATEGORIES:
            result_dict["auto_approvable"] = False
            result_dict["recommendation"] = "REQUIRE_HUMAN"
            if result_dict.get("risk_level") not in ("HIGH", "CRITICAL"):
                result_dict["risk_level"] = "HIGH"

        result = AiReviewResult(**result_dict)

    except Exception as e:
        logger.error("小富 AI 審核失敗 [%s]: %s", review_id, e)
        # fallback：保守建議人工審核
        result = AiReviewResult(
            risk_level="UNKNOWN",
            recommendation="REQUIRE_HUMAN",
            confidence=0.0,
            reasoning=f"AI 審核分析失敗（{e}），建議人工審核。",
            key_concerns=["AI 審核服務暫時不可用"],
            suggested_actions=["人工審核員請直接審查原始 payload"],
            regulatory_refs=[],
            auto_approvable=False,
            reviewer_note="⚠️ 小富本次無法完成分析，請人工審核員謹慎決策。",
        )

    # 寫回 DB
    await db.execute(
        text("""
            UPDATE fsi.review_requests
            SET ai_review_result = :result,
                ai_review_at     = NOW(),
                ai_reviewer      = '小富',
                ai_recommendation = :rec,
                ai_risk_level    = :risk
            WHERE review_id = :rid
        """),
        {
            "result": json.dumps(result.model_dump(), ensure_ascii=False),
            "rec": result.recommendation,
            "risk": result.risk_level,
            "rid": review_id,
        },
    )
    await db.commit()

    logger.info(
        "小富審核完成 [%s]: risk=%s rec=%s auto=%s",
        review_id[:8], result.risk_level, result.recommendation, result.auto_approvable,
    )
    return result


def _build_analysis_prompt(review_data: dict) -> str:
    """構建送給小富的分析提示。"""
    category    = review_data.get("category", "UNKNOWN")
    title       = review_data.get("title", "")
    summary     = review_data.get("summary", "")
    fund_id     = review_data.get("fund_id", "N/A")
    as_of_date  = review_data.get("as_of_date", "N/A")
    triggered   = review_data.get("triggered_by", "N/A")
    payload     = review_data.get("payload", {})

    # 格式化 payload 摘要（避免 token 過多）
    payload_summary = json.dumps(
        {k: v for k, v in payload.items() if k in (
            "breach_flags", "wam_days", "wal_days", "daily_liquid_pct",
            "weekly_liquid_pct", "var_pct_nav", "total_nav_hkd",
            "is_compliant", "risk_result",
        )},
        ensure_ascii=False, indent=2,
    )

    return f"""請以「小富」AI 審核員身份分析以下審核請求，並輸出嚴格 JSON：

## 審核請求基本資訊
- 類別 (category): {category}
- 標題: {title}
- 基金: {fund_id}  日期: {as_of_date}
- 觸發方: {triggered}

## 摘要
{summary}

## 關鍵數據
```json
{payload_summary}
```

## 分析要求
1. 評估此請求的風險等級（LOW/MEDIUM/HIGH/CRITICAL）
2. 識別任何 SFC《單位信託及互惠基金守則》第8.2章違規
3. 建議批准/拒絕/升級/要求人工審核
4. 如類別為 COMPLIANCE_BREACH 或 HIGH_RISK，必須 recommendation="REQUIRE_HUMAN"

## 輸出格式（嚴格 JSON）
{{
  "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "recommendation": "APPROVE|REJECT|ESCALATE|REQUIRE_HUMAN",
  "confidence": 0.0-1.0,
  "reasoning": "分析推理（2-3段，繁體中文）",
  "key_concerns": ["關切點1", "關切點2"],
  "suggested_actions": ["建議行動1", "建議行動2"],
  "regulatory_refs": ["第8.2(f)條", "第8.2(g)條"],
  "auto_approvable": true/false,
  "reviewer_note": "給人工審核員的提示（繁體中文）"
}}
"""


def _parse_ai_response(raw: str) -> dict:
    """解析小富的 JSON 輸出，處理 markdown code block 等情況。"""
    text = raw.strip()
    # 移除 ```json ... ``` 包裝
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 嘗試提取第一個 {...} 塊
        import re
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"無法解析小富輸出：{text[:200]}")
