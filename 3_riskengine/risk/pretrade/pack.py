"""风险预算与前置试算业务包（页面模块，非 UI）。

页面对应 ``/investment-risk/pretrade-budget#risk-budget``。

业务模块（非页面壳）：
1. trade_inputs — 交易参数
2. decision_cards — 决策 / 剩余久期·VaR 预算 / DV01
3. kpi_panel — KPI 表
4. risk_budget — 按资产类别风险贡献
5. projected_budget — 试算后风险贡献
6. rp_reference — Riskfolio 风险平价参考权重
7. decision_summary — 前置试算决策摘要
8. factor_shock_compare — 标准因子冲击当前 vs 试算后
9. limit_comparison — 限额对比
10. methodology — 适配器分工 + 业务流水线

模型相对独立：不 import ``2_processing`` / ``4_business``；拟成交用本包
``apply_proposed_trade``；KPI 复用 Duration/DV01 + ``portfolio().risk()``。
输出与 HTTP ``PretradeRiskResult`` 同形，供 processing / 前端直接消费。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from ...core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from .. import kpis as K
from .proposed import apply_proposed_trade

BUSINESS_MODULES = (
    "trade_inputs",
    "decision_cards",
    "kpi_panel",
    "risk_budget",
    "projected_budget",
    "rp_reference",
    "decision_summary",
    "factor_shock_compare",
    "limit_comparison",
    "methodology",
)

ADAPTER_NOTES = {
    "financepy": "Duration / DV01 / 标准利率·信用利差冲击再估值",
    "riskfolio": "VaR / CVaR 与风险平价（RP）参考权重",
    "ore": "复杂债券与衍生品再估值（QuantLib/ORE 路径）",
}

LOGIC_STEPS = (
    "load_portfolio_snapshot → RiskEngine.bind（FinancePy / ORE 估值曲线）",
    "当前组合：Duration/DV01（FinancePy/ORE）+ portfolio().risk()（Riskfolio VaR/CVaR、因子冲击 PnL、资产类别 RC）",
    "风险预算：资产类别风险贡献占比；Riskfolio risk_parity 给出 RP 参考权重对照",
    "前置试算：apply_proposed_trade 克隆持仓（不写库）后重算同一套 KPI/风险包与预算结构",
    "对照 para_risk_* 前置限额与预算利用率 → ALLOW / ALLOW_WITH_WARNING / BLOCK",
)

FORMULA = "RiskEngine 前置试算 = 限额闸门 × 风险预算贡献 × 试算后 Duration/DV01/VaR"

DEFAULT_LIMITS = {
    "duration_years": 4.0,
    "issuer_pct_nav": 10.0,
    "tracking_error_proxy_pct": 5.0,
    "var_pct_nav": 2.0,
}

_ASSET_ALIASES = {
    "BOND": "BOND",
    "BOND_CORP": "BOND",
    "BOND_GOVT": "BOND",
    "BOND_FLOAT": "BOND",
    "CD": "CD",
    "DEPOSIT": "DEPOSIT",
    "EQUITY": "EQUITY",
    "STOCK": "EQUITY",
    "FUND": "FUND",
    "ETF": "FUND",
    "CASH": "CASH",
    "MMF": "MMF",
}

_SELECTED = ("Duration", "DV01", "VaR", "CVaR", "Gross Exposure", "Concentration", "Risk Contribution")


def _num(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_asset_class(raw: str) -> str:
    key = str(raw or "BOND").strip().upper()
    return _ASSET_ALIASES.get(key, key if key else "BOND")


def _safe_portfolio_risk(bound: Any, *, confidence: float = 0.99) -> dict[str, Any]:
    try:
        return bound.portfolio().risk(confidence=confidence)
    except Exception:
        return {"error": "portfolio_risk_unavailable", "risk_contribution": {}, "var_cvar": {}}


def _kpi_num(selected: Mapping[str, Any], name: str, key: str) -> float | None:
    result = (selected.get(name) or {}).get("result")
    if isinstance(result, dict) and result.get(key) is not None:
        return float(result[key])
    if isinstance(result, (int, float)):
        return float(result)
    return None


def _var_pct(pack: Mapping[str, Any], selected: Mapping[str, Any], nav: float) -> float | None:
    vc = pack.get("var_cvar") or {}
    if isinstance(vc.get("var_pct_nav"), (int, float)):
        return float(vc["var_pct_nav"])
    if isinstance(vc.get("var_return"), (int, float)):
        return abs(float(vc["var_return"])) * 100.0
    if isinstance(vc.get("var_amount"), (int, float)) and nav:
        return abs(float(vc["var_amount"])) / nav * 100.0
    result = (selected.get("VaR") or {}).get("result")
    if isinstance(result, dict):
        if result.get("pct_nav") is not None:
            return float(result["pct_nav"])
        if result.get("return") is not None:
            return abs(float(result["return"])) * 100.0
        if result.get("amount") is not None and nav:
            return abs(float(result["amount"])) / nav * 100.0
    return None


def _cvar_pct(pack: Mapping[str, Any], selected: Mapping[str, Any], nav: float) -> float | None:
    vc = pack.get("var_cvar") or {}
    if isinstance(vc.get("cvar_pct_nav"), (int, float)):
        return float(vc["cvar_pct_nav"])
    if isinstance(vc.get("cvar_return"), (int, float)):
        return abs(float(vc["cvar_return"])) * 100.0
    if isinstance(vc.get("cvar_amount"), (int, float)) and nav:
        return abs(float(vc["cvar_amount"])) / nav * 100.0
    result = (selected.get("CVaR") or {}).get("result")
    if isinstance(result, dict):
        if result.get("pct_nav") is not None:
            return float(result["pct_nav"])
        if result.get("return") is not None:
            return abs(float(result["return"])) * 100.0
        if result.get("amount") is not None and nav:
            return abs(float(result["amount"])) / nav * 100.0
    return None


def _bond_stats_from_snapshot(snapshot: Any) -> dict[str, Any]:
    bond_mv = 0.0
    duration_num = 0.0
    issuer_mv: dict[str, float] = defaultdict(float)
    for p in getattr(snapshot, "positions", ()) or ():
        ac = str(getattr(p, "asset_class", "") or "").upper()
        if ac not in {"BOND", "CD", "DEPOSIT", "BOND_CORP", "BOND_GOVT", "BOND_FLOAT"}:
            continue
        mv = float(getattr(p, "market_value_base", 0.0) or 0.0)
        dur = float(getattr(p, "duration", 0.0) or 0.0)
        bond_mv += mv
        duration_num += mv * dur
        meta = dict(getattr(p, "metadata", None) or {})
        issuer = str(meta.get("issuer") or meta.get("issuer_name") or "UNKNOWN_ISSUER")
        issuer_mv[issuer] += mv
    duration = duration_num / bond_mv if bond_mv else 0.0
    return {
        "bond_mv": bond_mv,
        "duration": duration,
        "duration_num": duration_num,
        "issuer_mv": dict(issuer_mv),
    }


def _present_risk_budget(
    bound: Any,
    pack: Mapping[str, Any],
    nav: float,
    snapshot: Any,
) -> dict[str, Any]:
    rc = pack.get("risk_contribution") or {}
    by_class = dict(rc.get("by_asset_class") or {})
    if not by_class:
        factor = (rc.get("factor_pnl") or {}).get("by_asset_class") or {}
        by_class = dict(factor)
    if not by_class:
        buckets: dict[str, float] = defaultdict(float)
        for position in getattr(snapshot, "positions", []) or []:
            klass = str(getattr(position, "asset_class", None) or "OTHER")
            buckets[klass] += abs(float(getattr(position, "market_value_base", 0.0) or 0.0))
        total = sum(buckets.values()) or 1.0
        by_class = {klass: value / total for klass, value in buckets.items()}

    rows = [
        {
            "asset_class": str(klass),
            "share_pct": float(share) * 100.0 if abs(float(share)) <= 1.5 else float(share),
        }
        for klass, share in by_class.items()
    ]
    rows.sort(key=lambda row: abs(row["share_pct"]), reverse=True)

    optimize: dict[str, Any] = {}
    try:
        optimize = bound.portfolio().optimize("risk_parity") or {}
    except Exception:
        optimize = {"status": "unavailable", "available": False, "weights": {}, "risk_contribution": {}}

    weights = dict(optimize.get("weights") or {})
    rp_rc = dict(optimize.get("risk_contribution") or {})
    rp_rows = [
        {
            "asset_class": str(code),
            "weight_pct": float(weight) * 100.0 if abs(float(weight)) <= 1.5 else float(weight),
            "rc_pct": (
                float(rp_rc.get(code, 0.0)) * 100.0
                if abs(float(rp_rc.get(code, 0.0) or 0.0)) <= 1.5
                else float(rp_rc.get(code, 0.0) or 0.0)
            ),
        }
        for code, weight in weights.items()
    ]
    rp_rows.sort(key=lambda row: abs(row["weight_pct"]), reverse=True)

    used_var = _var_pct(pack, {}, nav)
    top = rows[0] if rows else None
    riskfolio_ok = bool(getattr(getattr(bound, "engine", None), "riskfolio", None) and bound.engine.riskfolio.available)

    return {
        "by_asset_class": rows,
        "used_var_pct_nav": used_var,
        "dominant_bucket": top["asset_class"] if top else None,
        "dominant_share_pct": top["share_pct"] if top else None,
        "riskfolio_available": riskfolio_ok,
        "rp_reference": {
            "method": optimize.get("method") or "risk_parity",
            "status": optimize.get("status") or ("PROPOSAL" if weights else "unavailable"),
            "engine": optimize.get("engine"),
            "weights": weights,
            "risk_contribution": rp_rc,
            "rows": rp_rows[:20],
            "note": "Riskfolio-Lib 风险平价参考权重（非交易指令）",
        },
    }


def _top_rc_rows(selected: Mapping[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    result = (selected.get("Risk Contribution") or {}).get("result") or {}
    rows = list(result.get("rows") or [])
    rows.sort(key=lambda row: abs(float(row.get("contribution_pct") or 0.0)), reverse=True)
    out = []
    for row in rows[:limit]:
        out.append(
            {
                "security_code": str(row.get("security_code") or ""),
                "pnl": _num(row.get("pnl")),
                "contribution_pct": _num(row.get("contribution_pct")),
            }
        )
    return out


def _factor_shocks(pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    factors = (((pack.get("risk_contribution") or {}).get("factor_pnl") or {}).get("factors")) or []
    rows = []
    for item in factors:
        rows.append({"factor": str(item.get("factor") or ""), "pnl": _num(item.get("pnl")) or 0.0})
    rows.sort(key=lambda row: abs(row["pnl"]), reverse=True)
    return rows


def _slim_pack(pack: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "nav": pack.get("nav"),
        "var_cvar": pack.get("var_cvar") or {},
        "by_asset_class": pack.get("by_asset_class") or {},
        "riskfolio_available": pack.get("riskfolio_available"),
        "error": pack.get("error"),
    }


def _build_decision_summary(
    *,
    decision: str,
    breaches: list[str],
    side: str,
    amount: float,
    asset: str,
    issuer: str,
    current_duration: float,
    projected_duration: float,
    duration_limit: float,
    current_var: float | None,
    projected_var: float | None,
    var_limit_pct: float,
    trade_impact_pct: float | None,
    risk_budget: Mapping[str, Any],
    nav: float,
) -> dict[str, Any]:
    dominant = risk_budget.get("dominant_bucket") or "—"
    dominant_share = risk_budget.get("dominant_share_pct")
    used_var = risk_budget.get("used_var_pct_nav")
    remaining_var = None
    if used_var is not None:
        remaining_var = max(var_limit_pct - float(used_var), 0.0)
    duration_budget = max(duration_limit - projected_duration, 0.0)

    if decision == "ALLOW":
        headline = "建议放行：试算后风险指标仍在风险预算与前置限额内"
        recommendation = (
            "本笔交易对组合久期、发行人集中度与 VaR 的边际影响可控，"
            "可按既定投资指引执行；建议成交后复核当日风险贡献结构。"
        )
    elif decision == "ALLOW_WITH_WARNING":
        headline = "有条件放行：触及单项风险预算预警，需投资经理确认"
        recommendation = (
            "建议缩小名义金额、缩短久期或更换发行人后再下单；"
            "若坚持执行，应履行例外审批并在交易备忘中记录风险接受理由。"
        )
    else:
        headline = "建议拦截：试算结果突破多项/关键风险限额"
        recommendation = (
            "不建议在当前组合状态下执行该指令；请先调仓释放风险预算"
            "（降低主导风险桶敞口或压缩久期）后再重新试算。"
        )

    rationale = [
        f"指令：{side} {asset} / {issuer}，名义 {amount:,.0f}（约占 NAV {trade_impact_pct:.2f}%）"
        if trade_impact_pct is not None
        else f"指令：{side} {asset} / {issuer}，名义 {amount:,.0f}",
        (
            f"风险预算结构：主导风险桶 {dominant}"
            + (f"（贡献 {dominant_share:.1f}%）" if dominant_share is not None else "")
            + "；贡献按因子冲击 |PnL| / 市值权重归一"
        ),
        (
            f"久期试算：{current_duration:.3f} → {projected_duration:.3f} 年"
            f"（限额 {duration_limit:.2f}，剩余久期预算 {duration_budget:.3f} 年）"
        ),
        (
            f"市场风险：VaR "
            f"{'—' if current_var is None else f'{current_var:.3f}%'} → "
            f"{'—' if projected_var is None else f'{projected_var:.3f}%'} NAV"
            f"（限额 {var_limit_pct:.2f}%"
            + (f"，剩余 VaR 预算 {remaining_var:.3f}%" if remaining_var is not None else "")
            + "）"
        ),
    ]
    if breaches:
        rationale.append("超限项：" + "；".join(breaches))
    else:
        rationale.append("未触发久期 / 发行人 / 冲击 / VaR 前置硬限额。")

    return {
        "headline": headline,
        "recommendation": recommendation,
        "rationale": rationale,
        "model": FORMULA,
        "nav": nav,
    }


def _modules_view(result: Mapping[str, Any]) -> dict[str, Any]:
    """把 HTTP 同形结果映射为页面业务模块视图。"""

    trade = result.get("trade") or {}
    current = result.get("current") or {}
    projected = result.get("projected") or {}
    limits = result.get("limits") or {}
    util = result.get("budget_utilization") or {}
    risk_budget = result.get("risk_budget") or {}
    projected_budget = result.get("projected_risk_budget") or {}
    summary = result.get("decision_summary") or {}
    metrics = result.get("engine_metrics") or {}
    shocks_c = list(metrics.get("factor_shocks_current") or [])
    shocks_p = list(metrics.get("factor_shocks_projected") or [])
    shock_map: dict[str, dict[str, Any]] = {}
    for row in shocks_c:
        shock_map[str(row.get("factor"))] = {
            "factor": str(row.get("factor")),
            "current": float(row.get("pnl") or 0.0),
            "projected": 0.0,
        }
    for row in shocks_p:
        key = str(row.get("factor"))
        prev = shock_map.get(key) or {"factor": key, "current": 0.0, "projected": 0.0}
        prev["projected"] = float(row.get("pnl") or 0.0)
        shock_map[key] = prev
    shock_rows = []
    for item in shock_map.values():
        shock_rows.append(
            {
                **item,
                "delta": item["projected"] - item["current"],
            }
        )
    shock_rows.sort(key=lambda r: abs(r["projected"] or r["current"]), reverse=True)

    top_rc = list(metrics.get("top_risk_contributors") or [])
    top_rc_text = (
        " · ".join(
            f"{r.get('security_code')} {float(r.get('contribution_pct') or 0.0):.1f}%"
            for r in top_rc[:3]
        )
        or "—"
    )
    decision = str(result.get("decision") or "ALLOW")
    decision_label = {
        "ALLOW": "放行（ALLOW）",
        "ALLOW_WITH_WARNING": "有条件放行（ALLOW_WITH_WARNING）",
        "BLOCK": "阻断（BLOCK）",
    }.get(decision, decision)

    kpi_rows = [
        {"kpi": "决策", "result": decision_label, "formula": "限额闸门 × 风险预算剩余空间"},
        {
            "kpi": "当前久期",
            "result": f"{float(current.get('duration_years') or 0.0):.3f}",
            "formula": "市值加权修正久期（FinancePy/ORE）",
        },
        {
            "kpi": "试算后久期",
            "result": f"{float(projected.get('duration_years') or 0.0):.3f}",
            "formula": "试算持仓后市值加权久期",
        },
        {
            "kpi": "VaR % NAV",
            "result": f"{float(current.get('var_pct_nav') or 0.0):.3f}%",
            "formula": "历史分位 VaR_α = -Q_α(R)×NAV（Riskfolio）",
        },
        {
            "kpi": "CVaR % NAV",
            "result": f"{float(current.get('cvar_pct_nav') or 0.0):.3f}%",
            "formula": "CVaR_α = -E[R | R≤−VaR]（Riskfolio）",
        },
        {
            "kpi": "Δ VaR % NAV",
            "result": f"{float(projected.get('var_delta_pct_nav') or 0.0):.3f}%",
            "formula": "试算后 VaR − 当前 VaR",
        },
        {
            "kpi": "总敞口 % NAV",
            "result": f"{float(current.get('gross_exposure_pct') or 0.0):.2f}%",
            "formula": "Gross = Σ|MV_i| / NAV",
        },
        {"kpi": "风险贡献（Top）", "result": top_rc_text, "formula": "RC_i = PnL_i(shock) / Σ PnL_j"},
        {
            "kpi": "交易冲击",
            "result": f"{float(projected.get('tracking_error_proxy_pct') or 0.0):.2f}%",
            "formula": "|交易名义| / NAV",
        },
    ]

    limit_rows = [
        {
            "metric": "久期(年)",
            "current": current.get("duration_years"),
            "projected": projected.get("duration_years"),
            "limit": limits.get("duration_years"),
        },
        {
            "metric": "Issuer 占 NAV",
            "current": current.get("issuer_pct_nav"),
            "projected": projected.get("issuer_pct_nav"),
            "limit": limits.get("issuer_pct_nav"),
        },
        {
            "metric": "VaR % NAV",
            "current": current.get("var_pct_nav"),
            "projected": projected.get("var_pct_nav"),
            "limit": limits.get("var_pct_nav"),
        },
        {
            "metric": "CVaR % NAV",
            "current": current.get("cvar_pct_nav"),
            "projected": projected.get("cvar_pct_nav"),
            "limit": None,
        },
        {
            "metric": "DV01",
            "current": current.get("portfolio_dv01"),
            "projected": projected.get("portfolio_dv01"),
            "limit": None,
        },
        {
            "metric": "交易冲击",
            "current": None,
            "projected": projected.get("tracking_error_proxy_pct"),
            "limit": limits.get("tracking_error_proxy_pct"),
        },
    ]

    return {
        "trade_inputs": {
            "module": "trade_inputs",
            "side": trade.get("trade_side"),
            "amount": trade.get("trade_amount"),
            "asset_class": trade.get("normalized_asset_class") or trade.get("asset_class"),
            "duration": trade.get("duration_years"),
            "issuer": trade.get("issuer_name"),
            "security_code": trade.get("security_code"),
        },
        "decision_cards": {
            "module": "decision_cards",
            "decision": decision,
            "decision_label": decision_label,
            "remaining_duration_budget": util.get("duration_remaining_years"),
            "duration_used_pct": util.get("duration_used_pct"),
            "remaining_var_budget": util.get("var_remaining_pct_nav"),
            "var_used_pct": util.get("var_used_pct"),
            "dv01": projected.get("portfolio_dv01"),
            "dv01_from": current.get("portfolio_dv01"),
            "dv01_to": projected.get("portfolio_dv01"),
        },
        "kpi_panel": {"module": "kpi_panel", "rows": kpi_rows},
        "risk_budget": {
            "module": "risk_budget",
            "by_asset_class": risk_budget.get("by_asset_class") or [],
            "dominant_bucket": risk_budget.get("dominant_bucket"),
            "dominant_share_pct": risk_budget.get("dominant_share_pct"),
            "note": "贡献按因子冲击 |PnL| / 市值权重归一",
        },
        "projected_budget": {
            "module": "projected_budget",
            "by_asset_class": projected_budget.get("by_asset_class") or [],
            "dominant_bucket": projected_budget.get("dominant_bucket"),
            "dominant_share_pct": projected_budget.get("dominant_share_pct"),
        },
        "rp_reference": {
            "module": "rp_reference",
            **dict(risk_budget.get("rp_reference") or {}),
            "title": "Riskfolio-Lib 风险平价参考权重（非交易指令）",
        },
        "decision_summary": {
            "module": "decision_summary",
            "headline": summary.get("headline"),
            "recommendation": summary.get("recommendation"),
            "rationale": list(summary.get("rationale") or []),
            "model": summary.get("model") or FORMULA,
            "exportable": True,
        },
        "factor_shock_compare": {
            "module": "factor_shock_compare",
            "title": "标准因子冲击 PnL（FinancePy / ORE）",
            "subtitle": "rate 1bp / equity 1% / fx 1% / cs 1bp / vol 10%：当前 vs 试算后",
            "rows": shock_rows,
        },
        "limit_comparison": {
            "module": "limit_comparison",
            "title": "限额对比",
            "subtitle": "风险试算：当前组合 vs 拟成交后组合，对照前置风险限额（含 VaR）",
            "rows": limit_rows,
        },
        "methodology": {
            "module": "methodology",
            "adapters": dict(result.get("adapter_usage") or ADAPTER_NOTES),
            "logic": {"title": "RiskEngine 业务实现逻辑", "steps": list(LOGIC_STEPS)},
            "formula": FORMULA,
        },
    }


def fundamentals(
    bound: Any,
    *,
    trade_amount: float = 10_000_000.0,
    trade_side: str = "BUY",
    asset_class: str = "BOND",
    duration_years: float = 2.0,
    issuer_name: str = "UNKNOWN_ISSUER",
    limits: Mapping[str, Any] | None = None,
    bond_stats: Mapping[str, Any] | None = None,
    nav: float | None = None,
    confidence: float = 0.99,
    applied_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """完整前置试算与风险预算（页面全部功能模块）。

    Parameters
    ----------
    limits:
        前置限额；缺省 DEFAULT_LIMITS。processing 可注入 para_risk_* 生效值。
    bond_stats:
        ``{bond_mv, duration, duration_num, issuer_mv}``；缺省从 snapshot 推导。
    """

    snapshot = bound.snapshot
    engine = bound.engine
    adapters = engine.adapters_status() if hasattr(engine, "adapters_status") else {}

    side = str(trade_side or "BUY").upper()
    asset = _normalize_asset_class(asset_class)
    issuer = str(issuer_name or "UNKNOWN_ISSUER").strip() or "UNKNOWN_ISSUER"
    amount = abs(float(trade_amount or 0.0))

    lim = {**DEFAULT_LIMITS, **dict(limits or {})}
    stats = dict(bond_stats or _bond_stats_from_snapshot(snapshot))
    nav_value = float(nav if nav is not None else getattr(snapshot, "net_asset", 0.0) or 0.0) or 1.0

    current_pack = _safe_portfolio_risk(bound, confidence=confidence)
    current_selected = K.compute_selected(snapshot, _SELECTED, confidence=confidence)

    order = {
        "security_code": f"PRETRADE_{issuer}",
        "security_name": f"前置试算·{issuer}",
        "side": side,
        "amount": amount,
        "asset_class": asset,
        "duration": float(duration_years or 0.0),
        "issuer": issuer,
        "issuer_name": issuer,
        "currency": getattr(snapshot, "reporting_currency", "HKD"),
    }
    proposed = apply_proposed_trade(snapshot, order)
    prop_bound = engine.bind(proposed)
    projected_pack = _safe_portfolio_risk(prop_bound, confidence=confidence)
    projected_selected = K.compute_selected(proposed, _SELECTED, confidence=confidence)

    sign = 1.0 if side == "BUY" else -1.0
    bond_trade = sign * amount if asset in {"BOND", "CD", "DEPOSIT"} else 0.0
    issuer_mv_map = dict(stats.get("issuer_mv") or {})
    current_issuer_mv = float(issuer_mv_map.get(issuer, 0.0) or 0.0)
    projected_issuer_mv = max(current_issuer_mv + bond_trade, 0.0)
    current_issuer_pct = current_issuer_mv / nav_value * 100.0 if nav_value else None
    projected_issuer_pct = projected_issuer_mv / nav_value * 100.0 if nav_value else None

    kpi_duration = _kpi_num(current_selected, "Duration", "weighted_years")
    bond_duration = float(stats.get("duration") or 0.0)
    current_duration = (
        float(kpi_duration)
        if kpi_duration is not None and float(kpi_duration) > 0
        else bond_duration
    )
    projected_duration = _kpi_num(projected_selected, "Duration", "weighted_years")
    total_bond = max(float(stats.get("bond_mv") or 0.0) + bond_trade, 0.0)
    fallback_projected = (
        (float(stats.get("duration_num") or 0.0) + bond_trade * float(duration_years or 0.0)) / total_bond
        if total_bond
        else float(duration_years or 0.0)
    )
    if projected_duration is None or (bond_trade and float(projected_duration) <= 0 and fallback_projected > 0):
        projected_duration = fallback_projected
    projected_duration = float(projected_duration or 0.0)

    current_dv01 = _kpi_num(current_selected, "DV01", "reval_pnl")
    if current_dv01 is not None:
        current_dv01 = abs(float(current_dv01))
    else:
        current_dv01 = float(stats.get("bond_mv") or 0.0) * bond_duration * 0.0001
    projected_dv01 = _kpi_num(projected_selected, "DV01", "reval_pnl")
    if projected_dv01 is not None:
        projected_dv01 = abs(float(projected_dv01))
    else:
        projected_bond_mv = max(float(stats.get("bond_mv") or 0.0) + bond_trade, 0.0)
        projected_dv01 = projected_bond_mv * projected_duration * 0.0001

    current_var = _var_pct(current_pack, current_selected, nav_value)
    projected_var = _var_pct(projected_pack, projected_selected, nav_value)
    current_cvar = _cvar_pct(current_pack, current_selected, nav_value)
    projected_cvar = _cvar_pct(projected_pack, projected_selected, nav_value)
    trade_impact_pct = abs(amount) / nav_value * 100.0 if nav_value else None
    var_delta_pct = None
    if current_var is not None and projected_var is not None:
        var_delta_pct = projected_var - current_var
    cvar_delta_pct = None
    if current_cvar is not None and projected_cvar is not None:
        cvar_delta_pct = projected_cvar - current_cvar

    duration_limit = float(lim["duration_years"])
    issuer_limit_pct = float(lim["issuer_pct_nav"])
    te_limit_pct = float(lim["tracking_error_proxy_pct"])
    var_limit_pct = float(lim["var_pct_nav"])

    breaches: list[str] = []
    if projected_duration > duration_limit:
        breaches.append(f"组合修正久期超限（试算 {projected_duration:.2f} > 限额 {duration_limit:.1f} 年）")
    if projected_issuer_pct is not None and projected_issuer_pct > issuer_limit_pct:
        breaches.append(f"单一发行人敞口超限（试算 {projected_issuer_pct:.2f}% > 限额 {issuer_limit_pct:.1f}% NAV）")
    if trade_impact_pct is not None and trade_impact_pct > te_limit_pct:
        breaches.append(f"单笔名义冲击超限（{trade_impact_pct:.2f}% > 限额 {te_limit_pct:.1f}% NAV）")
    if projected_var is not None and projected_var > var_limit_pct:
        breaches.append(f"组合 VaR 超限（试算 {projected_var:.3f}% > 限额 {var_limit_pct:.2f}% NAV）")
    elif var_delta_pct is not None and abs(var_delta_pct) > te_limit_pct:
        breaches.append(f"VaR 边际变动偏大（Δ {var_delta_pct:+.3f}% NAV）")

    decision = "ALLOW"
    if breaches:
        decision = "ALLOW_WITH_WARNING" if len(breaches) == 1 else "BLOCK"

    risk_budget = _present_risk_budget(bound, current_pack, nav_value, snapshot)
    projected_budget = _present_risk_budget(prop_bound, projected_pack, nav_value, proposed)
    decision_summary = _build_decision_summary(
        decision=decision,
        breaches=breaches,
        side=side,
        amount=amount,
        asset=asset,
        issuer=issuer,
        current_duration=float(current_duration or 0.0),
        projected_duration=projected_duration,
        duration_limit=duration_limit,
        current_var=current_var,
        projected_var=projected_var,
        var_limit_pct=var_limit_pct,
        trade_impact_pct=trade_impact_pct,
        risk_budget=risk_budget,
        nav=nav_value,
    )

    result: dict[str, Any] = {
        "fund_id": str(getattr(snapshot, "fund_id", "")),
        "as_of_date": getattr(snapshot, "as_of_date", None),
        "source": "riskengine",
        "engine": adapters.get("engine") or RISKENGINE_NAME,
        "engine_version": adapters.get("engine_version") or RISKENGINE_VERSION,
        "adapters": adapters,
        "page": "/investment-risk/pretrade-budget",
        "tab": "risk-budget",
        "business_modules": list(BUSINESS_MODULES),
        "trade": {
            "trade_amount": amount,
            "trade_side": side,
            "asset_class": asset_class,
            "normalized_asset_class": asset,
            "duration_years": float(duration_years or 0.0),
            "issuer_name": issuer,
            "security_code": order["security_code"],
        },
        "current": {
            "net_asset": nav_value,
            "bond_market_value": float(stats.get("bond_mv") or 0.0),
            "duration_years": float(current_duration or 0.0),
            "issuer_pct_nav": current_issuer_pct,
            "portfolio_dv01": float(current_dv01 or 0.0),
            "var_pct_nav": current_var,
            "cvar_pct_nav": current_cvar,
            "gross_exposure_pct": _kpi_num(current_selected, "Gross Exposure", "pct_nav"),
        },
        "projected": {
            "bond_market_value": max(float(stats.get("bond_mv") or 0.0) + bond_trade, 0.0),
            "duration_years": projected_duration,
            "issuer_pct_nav": projected_issuer_pct,
            "portfolio_dv01": float(projected_dv01 or 0.0),
            "tracking_error_proxy_pct": trade_impact_pct,
            "var_pct_nav": projected_var,
            "var_delta_pct_nav": var_delta_pct,
            "cvar_pct_nav": projected_cvar,
            "cvar_delta_pct_nav": cvar_delta_pct,
            "gross_exposure_pct": _kpi_num(projected_selected, "Gross Exposure", "pct_nav"),
        },
        "limits": {
            "duration_years": duration_limit,
            "issuer_pct_nav": issuer_limit_pct,
            "tracking_error_proxy_pct": te_limit_pct,
            "var_pct_nav": var_limit_pct,
        },
        "budget_utilization": {
            "duration_used_pct": (
                projected_duration / duration_limit * 100.0 if duration_limit else None
            ),
            "duration_remaining_years": max(duration_limit - projected_duration, 0.0),
            "var_used_pct": (
                float(projected_var) / var_limit_pct * 100.0
                if projected_var is not None and var_limit_pct
                else None
            ),
            "var_remaining_pct_nav": (
                max(var_limit_pct - float(projected_var), 0.0) if projected_var is not None else None
            ),
            "issuer_used_pct": (
                float(projected_issuer_pct) / issuer_limit_pct * 100.0
                if projected_issuer_pct is not None and issuer_limit_pct
                else None
            ),
        },
        "risk_budget": risk_budget,
        "projected_risk_budget": {
            "by_asset_class": projected_budget.get("by_asset_class") or [],
            "dominant_bucket": projected_budget.get("dominant_bucket"),
            "dominant_share_pct": projected_budget.get("dominant_share_pct"),
        },
        "decision_summary": decision_summary,
        "engine_metrics": {
            "current": _slim_pack(current_pack),
            "projected": _slim_pack(projected_pack),
            "factor_shocks_current": _factor_shocks(current_pack),
            "factor_shocks_projected": _factor_shocks(projected_pack),
            "top_risk_contributors": _top_rc_rows(current_selected),
            "top_risk_contributors_projected": _top_rc_rows(projected_selected),
        },
        "adapter_usage": dict(ADAPTER_NOTES),
        "applied_rules": list(applied_rules or []),
        "breach_flags": breaches,
        "decision": decision,
        "logic": {"title": "RiskEngine 业务实现逻辑", "steps": list(LOGIC_STEPS)},
        "formulas": {
            "duration": "D = Σ (MV_i × D_i) / Σ MV_i",
            "dv01": "DV01 ≈ PV(r+1bp) - PV(r)；proxy = Σ MV×D×0.0001",
            "var": "VaR_α = -Q_α(R)×NAV（Riskfolio 历史分位）",
            "cvar": "CVaR_α = -E[R | R≤−VaR]",
            "rc": "RC_i = |PnL_i(shock)| / Σ |PnL_j|",
            "gate": FORMULA,
        },
    }
    result["modules"] = _modules_view(result)
    return result


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for key in BUSINESS_MODULES:
        if key not in modules:
            errors.append(f"modules.{key}")
    for key in (
        "trade",
        "current",
        "projected",
        "limits",
        "budget_utilization",
        "risk_budget",
        "projected_risk_budget",
        "decision_summary",
        "engine_metrics",
        "decision",
        "breach_flags",
    ):
        if key not in pack:
            errors.append(key)
    if pack.get("decision") not in {"ALLOW", "ALLOW_WITH_WARNING", "BLOCK"}:
        errors.append("decision.invalid")
    rb = pack.get("risk_budget") or {}
    if not isinstance(rb.get("by_asset_class"), list):
        errors.append("risk_budget.by_asset_class")
    return {"passed": not errors, "errors": errors}
