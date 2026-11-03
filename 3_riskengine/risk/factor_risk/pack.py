"""投资风险 · 因子风险页业务模块。

页面对应 ``/investment-risk/factor-risk``。业务能力（非 UI）：

1. **KPI 面板** — 组合 Beta、跟踪误差（交易日对齐）
2. **摘要三卡** — 主导因子敞口 / Beta / TE
3. **风险因子敞口** — RATE_CREDIT / EQUITY / CASH / FX … %NAV
4. **标准因子冲击 PnL** — rate+1bp / equity+1% / fx+1% / cs+1bp / vol+10%
5. **因子风险贡献** — 按资产类别归一（冲击 |PnL|）

模型相对独立：本包不读库、不 import ``2_processing``；基准收益经
``meta.benchmark_returns`` / ``meta.fund_returns`` 注入（与 NAV 交易日对齐后的序列）。
底层复用 ``kpi_factor_exposure``、``portfolio.measures.factor_pnl_contribution`` /
``portfolio_risk``，不另造估值路径。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from ...core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ...portfolio.measures import FACTOR_SHOCKS, factor_pnl_contribution, portfolio_risk
from .. import kpis as K

BUSINESS_MODULES = (
    "kpi_panel",
    "summary",
    "factor_exposure",
    "factor_shocks",
    "rc_by_asset_class",
)

FORMULAS = {
    "factor_exposure": "FE_f = Σ_{i∈f} |MV_i| / NAV",
    "beta": "β = Cov(R_p, R_b) / Var(R_b)（交易日对齐）",
    "tracking_error": "TE = stdev(R_p - R_b) × √252（交易日对齐）",
    "factor_shock": "PnL_f = PV(shock_f) - PV(base)；RC 按 |PnL| 归一",
}

LOGIC_STEPS = (
    "LOOK_THROUGH 组合视图：持仓归入 RATE_CREDIT / EQUITY / FUND / MMF / CASH，外币叠加 FX",
    "Factor Exposure：绝对市值按因子桶汇总 / NAV",
    "标准因子冲击：rate+1bp、equity+1%、fx+1%、cs+1bp、vol+10%，统一再估值得因子 PnL",
    "风险贡献：各冲击 |PnL| 汇总后归一到资产类别；有收益面板时叠加统计 RC",
    "Beta / Tracking Error：组合 NAV 日收益对主基准指数收益（交易日对齐）",
)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _series(raw: Sequence[float] | None) -> list[float]:
    if not raw:
        return []
    out: list[float] = []
    for item in raw:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            continue
    return out


def compute_beta(fund_returns: Sequence[float], bench_returns: Sequence[float]) -> dict[str, Any]:
    a = _series(fund_returns)
    b = _series(bench_returns)
    n = min(len(a), len(b))
    if n < 3:
        return {"beta": None, "paired_observations": n}
    x = np.asarray(a[-n:], dtype=float)
    y = np.asarray(b[-n:], dtype=float)
    var_b = float(np.var(y, ddof=1))
    value = float(np.cov(x, y, ddof=1)[0, 1] / var_b) if var_b > 0 else None
    return {"beta": value, "paired_observations": n}


def compute_tracking_error(fund_returns: Sequence[float], bench_returns: Sequence[float]) -> dict[str, Any]:
    a = _series(fund_returns)
    b = _series(bench_returns)
    n = min(len(a), len(b))
    if n < 3:
        return {"annualized": None, "annualized_pct": None, "paired_observations": n}
    active = np.asarray(a[-n:], dtype=float) - np.asarray(b[-n:], dtype=float)
    te = float(np.std(active, ddof=1) * np.sqrt(252))
    return {
        "annualized": te,
        "annualized_pct": te * 100.0,
        "paired_observations": n,
    }


def present_factor_exposure(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for factor, payload in (result or {}).items():
        if isinstance(payload, dict):
            rows.append(
                {
                    "factor": str(factor),
                    "amount": _num(payload.get("amount")),
                    "pct_nav": _num(payload.get("pct_nav")),
                }
            )
    rows.sort(key=lambda row: abs(row["pct_nav"]), reverse=True)
    return rows


def present_factor_shocks(factors: Sequence[Mapping[str, Any]], nav: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in factors:
        pnl = _num(item.get("pnl"))
        rows.append(
            {
                "factor": str(item.get("factor") or ""),
                "pnl": pnl,
                "pnl_pct_nav": (pnl / nav * 100.0) if nav else None,
                "security_count": len(item.get("rows") or []),
            }
        )
    rows.sort(key=lambda row: abs(row["pnl"]), reverse=True)
    return rows


def present_rc_by_class(by_class: Mapping[str, float]) -> list[dict[str, Any]]:
    rows = [
        {"asset_class": str(klass), "share_pct": float(share) * 100.0}
        for klass, share in (by_class or {}).items()
    ]
    rows.sort(key=lambda row: abs(row["share_pct"]), reverse=True)
    return rows


def module_kpi_panel(beta: Mapping[str, Any], te: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "module": "kpi_panel",
        "rows": [
            {
                "kpi": "组合 Beta",
                "kpi_id": "beta",
                "result": beta.get("beta"),
                "formula": FORMULAS["beta"],
                "paired_observations": beta.get("paired_observations"),
            },
            {
                "kpi": "跟踪误差",
                "kpi_id": "tracking_error",
                "result": te.get("annualized_pct"),
                "unit": "%",
                "formula": FORMULAS["tracking_error"],
                "paired_observations": te.get("paired_observations"),
            },
        ],
        "beta": dict(beta),
        "tracking_error": dict(te),
    }


def module_summary(
    exposure_rows: Sequence[Mapping[str, Any]],
    beta: Mapping[str, Any],
    te: Mapping[str, Any],
) -> dict[str, Any]:
    top = exposure_rows[0] if exposure_rows else None
    return {
        "module": "summary",
        "dominant_factor": None if not top else top.get("factor"),
        "dominant_factor_pct_nav": None if not top else top.get("pct_nav"),
        "beta": beta.get("beta"),
        "tracking_error_pct": te.get("annualized_pct"),
    }


def module_factor_exposure(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "module": "factor_exposure",
        "rows": list(rows),
        "formula": FORMULAS["factor_exposure"],
        "count": len(rows),
    }


def module_factor_shocks(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "module": "factor_shocks",
        "rows": list(rows),
        "shock_catalog": [
            {
                "label": shock.label,
                "factor_type": str(getattr(shock.factor_type, "value", shock.factor_type)),
                "value": float(shock.value),
                "mode": str(getattr(shock.mode, "value", shock.mode)),
            }
            for shock in FACTOR_SHOCKS
        ],
        "formula": FORMULAS["factor_shock"],
        "count": len(rows),
    }


def module_rc_by_asset_class(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "module": "rc_by_asset_class",
        "rows": list(rows),
        "formula": "RC_c = Σ_{i∈c} |PnL_i| / Σ_j |PnL_j|（跨标准因子冲击）",
        "count": len(rows),
    }


def _resolve_return_pair(snapshot: Any, meta: Mapping[str, Any]) -> tuple[list[float], list[float]]:
    fund = _series(meta.get("fund_returns"))
    bench = _series(meta.get("benchmark_returns"))
    if fund and bench:
        return fund, bench
    # 回退：snapshot NAV 收益尾部对齐 meta/属性基准序列
    nav = []
    for item in getattr(snapshot, "nav_returns", ()) or ():
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            nav.append(float(item[1]))
        else:
            try:
                nav.append(float(item))
            except (TypeError, ValueError):
                continue
    if not bench:
        bench = _series(getattr(snapshot, "benchmark_returns", None))
    if not fund:
        fund = nav
    return fund, bench


def fundamentals(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    confidence: float = 0.99,
    include_portfolio_risk: bool = True,
) -> dict[str, Any]:
    """因子风险页五大业务模块打包。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    fund_returns, bench_returns = _resolve_return_pair(snapshot, info)
    benchmark_id = str(info.get("benchmark_id") or getattr(snapshot, "benchmark_id", None) or "") or None

    exposure_kpi = K.kpi_factor_exposure(snapshot)
    exposure_rows = present_factor_exposure(exposure_kpi.get("result") or {})

    beta = compute_beta(fund_returns, bench_returns)
    te = compute_tracking_error(fund_returns, bench_returns)

    portfolio_pack: dict[str, Any] = {}
    factor_block: dict[str, Any] = {"factors": [], "by_asset_class": {}}
    if include_portfolio_risk:
        try:
            portfolio_pack = portfolio_risk(bound, confidence=confidence)
            factor_block = (portfolio_pack.get("risk_contribution") or {}).get("factor_pnl") or factor_block
        except Exception as exc:  # pragma: no cover - 估值适配器缺失时保底
            portfolio_pack = {"error": str(exc), "risk_contribution": {"factor_pnl": factor_block}}
            try:
                factor_block = factor_pnl_contribution(bound)
            except Exception:
                factor_block = {"factors": [], "by_asset_class": {}}

    nav = float(getattr(snapshot, "net_asset", 0.0) or portfolio_pack.get("nav") or 0.0)
    shock_rows = present_factor_shocks(factor_block.get("factors") or [], nav)
    # 优先因子冲击 |PnL| 归类；统计 RC 作补充（与 processing 展示口径一致：页面用 by_asset_class）
    rc_source = (portfolio_pack.get("risk_contribution") or {}).get("by_asset_class") or factor_block.get(
        "by_asset_class"
    ) or {}
    rc_rows = present_rc_by_class(rc_source)

    kpi = module_kpi_panel(beta, te)
    summary = module_summary(exposure_rows, beta, te)
    exposure = module_factor_exposure(exposure_rows)
    shocks = module_factor_shocks(shock_rows)
    rc = module_rc_by_asset_class(rc_rows)

    warnings: list[str] = []
    if not benchmark_id:
        warnings.append("未配置基准：Beta / Tracking Error 无法计算，请选择指数后点击计算")
    elif beta.get("paired_observations", 0) < 3:
        warnings.append(f"基准 {benchmark_id} 与组合 NAV 可对齐交易日不足")

    quality = dict(getattr(snapshot, "data_quality", None) or {})

    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/investment-risk/factor-risk",
        "tab": "factor-risk",
        "fund_id": str(snapshot.fund_id),
        "period_start": info.get("period_start"),
        "period_end": info.get("period_end") or snapshot.as_of_date.isoformat(),
        "as_of_date": snapshot.as_of_date.isoformat(),
        "benchmark_id": benchmark_id,
        "benchmark": dict(info.get("benchmark") or {"benchmark_id": benchmark_id}),
        "business_modules": list(BUSINESS_MODULES),
        "modules": {
            "kpi_panel": kpi,
            "summary": summary,
            "factor_exposure": exposure,
            "factor_shocks": shocks,
            "rc_by_asset_class": rc,
        },
        # HTTP FactorRiskResult.factor_risk 同形
        "factor_risk": {
            "factor_exposure": exposure_rows,
            "factor_shocks": shock_rows,
            "risk_contribution_by_asset_class": rc_rows,
            "beta": beta,
            "tracking_error": te,
            "var_cvar": portfolio_pack.get("var_cvar") or {},
            "data_quality": {
                "effective_date": quality.get("effective_date"),
                "source_position_count": quality.get("source_position_count")
                or quality.get("position_count"),
                "source_risk_coverage_pct": quality.get("source_risk_coverage_pct"),
                "unmapped_balance": quality.get("unmapped_balance"),
            },
            "formulas": dict(FORMULAS),
        },
        "warnings": warnings,
        "logic": {"title": "RiskEngine 因子风险实现逻辑", "steps": list(LOGIC_STEPS)},
        "source": "riskengine",
        "adapters": bound.engine.adapters_status(),
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing {name}")
    kpi = modules.get("kpi_panel") or {}
    if len(kpi.get("rows") or []) < 2:
        errors.append("kpi_panel.rows")
    summary = modules.get("summary") or {}
    for key in ("dominant_factor", "beta", "tracking_error_pct"):
        if key not in summary:
            errors.append(f"summary.{key}")
    if "rows" not in (modules.get("factor_exposure") or {}):
        errors.append("factor_exposure.rows")
    shocks = modules.get("factor_shocks") or {}
    if "rows" not in shocks:
        errors.append("factor_shocks.rows")
    catalog = {item.get("label") for item in (shocks.get("shock_catalog") or [])}
    for label in ("rate_1bp", "equity_1pct", "fx_1pct", "cs_1bp", "vol_10pct"):
        if label not in catalog:
            errors.append(f"factor_shocks.catalog.{label}")
    if "rows" not in (modules.get("rc_by_asset_class") or {}):
        errors.append("rc_by_asset_class.rows")
    fr = pack.get("factor_risk") or {}
    for key in ("factor_exposure", "factor_shocks", "risk_contribution_by_asset_class", "beta", "tracking_error"):
        if key not in fr:
            errors.append(f"factor_risk.{key}")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
