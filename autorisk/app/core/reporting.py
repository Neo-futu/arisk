from __future__ import annotations

from ..schemas import AIRecommendation, AssessRequest, RuleViolation, Severity


def recommend_ai_action(
    severity: Severity,
    violations: list[RuleViolation],
) -> tuple[AIRecommendation, float]:
    if severity == Severity.GREEN:
        return AIRecommendation.APPROVE, 0.99
    if severity == Severity.YELLOW:
        return AIRecommendation.APPROVE, 0.92
    return AIRecommendation.REJECT, 0.99


def build_commentary(
    req: AssessRequest,
    severity: Severity,
    violations: list[RuleViolation],
) -> str:
    if not violations:
        return (
            f"基金 {req.fund_code} 觸發 {req.trigger_source.value} 風控評估，規則引擎未命中紅黃燈。"
            "系統已生成評估草案，進入 AI 雙重覆核。"
        )

    top = "；".join(item.description for item in violations[:3])
    if severity == Severity.RED:
        return (
            f"基金 {req.fund_code} 觸發 {req.trigger_source.value} 風控評估，命中紅燈規則：{top}。"
            "依照先評估後執行原則，系統生成阻斷型風控評估報告並交由兩級 AI 獨立覆核。"
        )
    return (
        f"基金 {req.fund_code} 觸發 {req.trigger_source.value} 風控評估，命中黃燈規則：{top}。"
        "系統生成預警型風控評估報告，AI 雙簽通過後可帶警告放行。"
    )


def render_report_markdown(report: dict) -> str:
    indicators = report.get("risk_indicators", {})
    violations = report.get("rule_violations", [])
    ai_reviews = report.get("ai_reviews", [])
    lines = [
        f"# 風控評估報告 {report.get('report_id')}",
        "",
        f"- 請求編號：{report.get('request_id')}",
        f"- 基金：{report.get('fund_code')} / {report.get('fund_name')}",
        f"- 觸發來源：{report.get('trigger_source')}",
        f"- 規則版本：{report.get('rule_version')}",
        f"- 工作流：{report.get('workflow_mode')}",
        f"- 狀態：{report.get('status')}",
        f"- 風險等級：{report.get('severity')}",
        f"- 執行決策：{report.get('execution_decision')}",
        "",
        "## 結構化風險指標",
    ]
    for key, value in indicators.items():
        lines.append(f"- {key}: {value}")

    lines += ["", "## 規則命中"]
    if violations:
        for item in violations:
            lines.append(
                f"- [{item.get('severity')}] {item.get('rule_id')} {item.get('description')} "
                f"({item.get('regulatory_ref', '')})"
            )
    else:
        lines.append("- 無")

    lines += ["", "## 自動生成評語", report.get("auto_commentary", "")]
    lines += ["", "## AI 雙重覆核"]
    for review in ai_reviews:
        lines.append(
            f"- {review.get('stage')} / {review.get('reviewer_id')}: "
            f"{review.get('recommendation')}（信心度 {review.get('confidence')}）— "
            f"{review.get('reasoning')}"
        )

    lines += ["", "## 簽章"]
    for label, key in (("初審", "first_sign"), ("終審", "second_sign")):
        sign = report.get(key)
        if sign:
            lines.append(
                f"- {label}: {sign.get('signer_id')} / {sign.get('signer_role')} / "
                f"{sign.get('decision')} / signature={sign.get('signature')}"
            )
        else:
            lines.append(f"- {label}: 待簽")

    lines += [
        "",
        "## 最終結論",
        report.get("final_commentary", ""),
        "",
        f"內容哈希：{report.get('content_hash', '')}",
    ]
    return "\n".join(lines)
