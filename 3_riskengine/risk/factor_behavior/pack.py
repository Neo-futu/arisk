"""投资风险 · 基本面因子与行为风险页业务模块。

页面对应 ``/investment-risk/factor-behavior``。业务能力（非 UI）：

1. **摘要四卡** — Momentum / LowVol / Size / Sector HHI（附换手）
2. **风格因子暴露** — Momentum·LowVol·Size·Coverage + 价值/成长/大小盘
3. **行业集中度** — HHI 与行业权重结构
4. **交易行为** — 换手率 + 拥挤度 Top
5. **方法论** — 实现逻辑步骤与公式

模型相对独立：本包不读库、不 import ``2_processing``；股票持仓、区间行情、
换手与风格分桶经 ``meta`` 注入（或从 snapshot 权益持仓推导）。
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from ...core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ...instruments.classify import EQUITY_LIKE

BUSINESS_MODULES = (
    "summary",
    "style_exposure",
    "sector_concentration",
    "trading_behavior",
    "methodology",
)

FORMULAS = {
    "momentum": "Σ w_i · (P_end / P_start - 1)",
    "low_volatility": "Σ w_i / (1 + σ_i)",
    "size": "Σ w_i · ln(max(MV_i, 1))",
    "hhi": "Σ w_sector² × 10000",
    "crowding": "quantity / avg_daily_volume",
}

LOGIC_STEPS = (
    "取区间末股票持仓（balance_stock），行业优先用 mktdata_stock_industry（GICS）",
    "用区间 mktdata_quotes 收盘价计算个券区间收益与日波动，按市值权重合成 Momentum / LowVol / Size",
    "Size = Σ w_i · ln(MV_i)；LowVol = Σ w_i / (1+σ_i)；Momentum = Σ w_i · R_i",
    "行业 HHI = Σ w_s² × 10000；拥挤比 = 持仓量 / 区间日均成交量",
    "换手率取区间股票买卖单边较小值 / 平均持仓市值",
    "可选补充：mktdata_equity_style 的价值/成长、大盘/小盘权重",
)

HHI_WARN_THRESHOLD = 1800.0
TURNOVER_WARN_PCT = 120.0
CROWDING_WARN_RATIO = 0.25


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def daily_returns(points: Sequence[tuple[date, float]]) -> dict[date, float]:
    ordered = sorted(((d, float(p)) for d, p in points if p), key=lambda item: item[0])
    out: dict[date, float] = {}
    for index in range(1, len(ordered)):
        prev_d, prev_p = ordered[index - 1]
        cur_d, cur_p = ordered[index]
        if prev_p > 0:
            out[cur_d] = cur_p / prev_p - 1.0
    return out


def period_return(points: Sequence[tuple[date, float]]) -> float | None:
    ordered = sorted(((d, float(p)) for d, p in points if p), key=lambda item: item[0])
    if len(ordered) < 2 or ordered[0][1] <= 0:
        return None
    return ordered[-1][1] / ordered[0][1] - 1.0


def _holdings_from_meta(meta: Mapping[str, Any], snapshot: Any) -> list[dict[str, Any]]:
    if "holdings" in meta:
        return [dict(row) for row in (meta.get("holdings") or ())]
    rows: list[dict[str, Any]] = []
    for position in getattr(snapshot, "positions", ()) or ():
        klass = str(getattr(position, "asset_class", "") or "").upper()
        if klass not in EQUITY_LIKE and klass not in {"EQUITY", "STOCK"}:
            continue
        m = dict(getattr(position, "metadata", None) or {})
        rows.append(
            {
                "security_code": str(getattr(position, "security_code", "") or ""),
                "security_name": str(getattr(position, "security_name", "") or ""),
                "sector": str(m.get("sector") or "未分类"),
                "quantity": float(getattr(position, "quantity", 0.0) or m.get("quantity") or 0.0),
                "market_value": float(getattr(position, "market_value_base", 0.0) or 0.0),
                "weight_pct": m.get("weight_pct"),
            }
        )
    return rows


def _quotes_by_security(meta: Mapping[str, Any]) -> tuple[dict[str, list[tuple[date, float]]], dict[str, list[float]]]:
    prices: dict[str, list[tuple[date, float]]] = defaultdict(list)
    volumes: dict[str, list[float]] = defaultdict(list)
    for row in meta.get("quotes") or ():
        code = str(row.get("security_code") or "")
        if not code:
            continue
        day = _as_date(row.get("price_date") or row.get("date"))
        px = _num(row.get("close_price") or row.get("price"), default=float("nan"))
        if day is None or not math.isfinite(px):
            continue
        prices[code].append((day, px))
        vol = row.get("volume")
        if vol is not None and vol != "":
            volumes[code].append(_num(vol))
    # 也可直接注入已整理结构
    for code, series in (meta.get("prices_by_security") or {}).items():
        for item in series:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                day = _as_date(item[0])
                if day is not None:
                    prices[str(code)].append((day, _num(item[1])))
    for code, vols in (meta.get("volumes_by_security") or {}).items():
        volumes[str(code)].extend(_num(v) for v in vols)
    return prices, volumes


def analyze_book(
    holdings: Sequence[Mapping[str, Any]],
    *,
    prices_by_security: Mapping[str, Sequence[tuple[date, float]]] | None = None,
    volumes_by_security: Mapping[str, Sequence[float]] | None = None,
    style_buckets: Mapping[str, Any] | None = None,
    turnover_pct: float | None = None,
    crowding_top_n: int = 20,
) -> dict[str, Any]:
    """纯计算：风格暴露 / 行业 HHI / 拥挤度（无 DB）。"""

    prices_map = {str(k): list(v) for k, v in (prices_by_security or {}).items()}
    volumes_map = {str(k): list(v) for k, v in (volumes_by_security or {}).items()}
    total_mv = sum(_num(item.get("market_value")) for item in holdings)
    momentum = 0.0
    low_vol = 0.0
    size = 0.0
    coverage_weight = 0.0
    sector_weight: dict[str, float] = defaultdict(float)
    crowding_rows: list[dict[str, Any]] = []

    for item in holdings:
        code = str(item.get("security_code") or "")
        mv = _num(item.get("market_value"))
        weight = mv / total_mv if total_mv else 0.0
        sector = str(item.get("sector") or "未分类")
        sector_weight[sector] += weight

        points = prices_map.get(code, [])
        rets = daily_returns(points)
        period_r = period_return(points) if points else None
        vol = statistics.stdev(list(rets.values())) if len(rets) >= 2 else None
        if period_r is not None and vol is not None:
            momentum += period_r * weight
            low_vol += (1.0 / (1.0 + vol)) * weight
            size += math.log(max(mv, 1.0)) * weight
            coverage_weight += weight

        vols = volumes_map.get(code, [])
        avg_volume = statistics.mean(vols) if vols else 0.0
        quantity = _num(item.get("quantity"))
        crowding_rows.append(
            {
                "security_code": code,
                "security_name": str(item.get("security_name") or code),
                "sector": sector,
                "weight_pct": weight * 100.0,
                "avg_daily_volume": avg_volume,
                "position_quantity": quantity,
                "crowding_ratio": (quantity / avg_volume) if avg_volume else None,
            }
        )

    hhi = sum(value * value for value in sector_weight.values()) * 10000.0 if sector_weight else 0.0
    crowding_rows.sort(key=lambda row: _num(row.get("crowding_ratio"), -1.0), reverse=True)
    buckets = dict(style_buckets or {})

    warnings: list[str] = []
    if not holdings:
        warnings.append("区间末无股票持仓，风格暴露与拥挤度为空")
    elif coverage_weight <= 0:
        warnings.append("持仓缺少可用行情（mktdata_quotes），风格暴露无法计算")
    if hhi > HHI_WARN_THRESHOLD:
        warnings.append("行业集中度偏高（HHI > 1800）")
    if turnover_pct is not None and turnover_pct > TURNOVER_WARN_PCT:
        warnings.append("股票换手率偏高，存在拥挤交易风险")
    top_crowding = crowding_rows[0].get("crowding_ratio") if crowding_rows else None
    if top_crowding is not None and top_crowding > CROWDING_WARN_RATIO:
        warnings.append("头部持仓相对日均成交量偏高，可能存在踩踏风险")

    style_exposure = {
        "momentum_exposure": momentum if coverage_weight else None,
        "low_volatility_exposure": low_vol if coverage_weight else None,
        "size_exposure": size if coverage_weight else None,
        "coverage_weight": coverage_weight * 100.0,
        "value_weight_pct": buckets.get("value_weight_pct"),
        "growth_weight_pct": buckets.get("growth_weight_pct"),
        "large_weight_pct": buckets.get("large_weight_pct"),
        "small_weight_pct": buckets.get("small_weight_pct"),
    }
    sector_concentration = {
        "hhi": hhi,
        "weights": [
            {"sector": sector, "weight_pct": weight * 100.0}
            for sector, weight in sorted(sector_weight.items(), key=lambda item: item[1], reverse=True)
        ],
    }
    trading_behavior = {
        "turnover_pct": turnover_pct,
        "crowding_top": crowding_rows[:crowding_top_n],
    }
    return {
        "style_exposure": style_exposure,
        "sector_concentration": sector_concentration,
        "trading_behavior": trading_behavior,
        "warnings": warnings,
        "holding_count": len(holdings),
        "total_equity_market_value": total_mv,
    }


def module_summary(core: Mapping[str, Any]) -> dict[str, Any]:
    style = core.get("style_exposure") or {}
    sector = core.get("sector_concentration") or {}
    trading = core.get("trading_behavior") or {}
    return {
        "module": "summary",
        "momentum_exposure": style.get("momentum_exposure"),
        "low_volatility_exposure": style.get("low_volatility_exposure"),
        "size_exposure": style.get("size_exposure"),
        "sector_hhi": sector.get("hhi"),
        "turnover_pct": trading.get("turnover_pct"),
    }


def module_style_exposure(core: Mapping[str, Any]) -> dict[str, Any]:
    style = dict(core.get("style_exposure") or {})
    bars = [
        {"factor": "Momentum", "value": abs(_num(style.get("momentum_exposure")))},
        {"factor": "LowVol", "value": abs(_num(style.get("low_volatility_exposure")))},
        {"factor": "Size", "value": abs(_num(style.get("size_exposure")))},
        {"factor": "Coverage", "value": abs(_num(style.get("coverage_weight")))},
    ]
    return {
        "module": "style_exposure",
        **style,
        "bars": bars,
        "formulas": {
            "momentum": FORMULAS["momentum"],
            "low_volatility": FORMULAS["low_volatility"],
            "size": FORMULAS["size"],
        },
    }


def module_sector_concentration(core: Mapping[str, Any]) -> dict[str, Any]:
    sector = dict(core.get("sector_concentration") or {})
    return {
        "module": "sector_concentration",
        "hhi": sector.get("hhi", 0.0),
        "weights": list(sector.get("weights") or []),
        "warn_threshold": HHI_WARN_THRESHOLD,
        "formula": FORMULAS["hhi"],
    }


def module_trading_behavior(core: Mapping[str, Any]) -> dict[str, Any]:
    trading = dict(core.get("trading_behavior") or {})
    return {
        "module": "trading_behavior",
        "turnover_pct": trading.get("turnover_pct"),
        "crowding_top": list(trading.get("crowding_top") or []),
        "crowding_count": len(trading.get("crowding_top") or []),
        "formula": FORMULAS["crowding"],
        "warn_ratio": CROWDING_WARN_RATIO,
    }


def module_methodology() -> dict[str, Any]:
    return {
        "module": "methodology",
        "logic": {"title": "基本面因子与行为实现逻辑", "steps": list(LOGIC_STEPS)},
        "formulas": dict(FORMULAS),
    }


def fundamentals(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    crowding_top_n: int = 20,
) -> dict[str, Any]:
    """基本面因子与行为风险页五大业务模块打包。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    holdings = _holdings_from_meta(info, snapshot)
    prices_map, volumes_map = _quotes_by_security(info)
    turnover = info.get("turnover_pct")
    turnover_pct = None if turnover is None else _num(turnover)
    style_buckets = {
        "value_weight_pct": info.get("value_weight_pct"),
        "growth_weight_pct": info.get("growth_weight_pct"),
        "large_weight_pct": info.get("large_weight_pct"),
        "small_weight_pct": info.get("small_weight_pct"),
    }
    if info.get("style_buckets"):
        style_buckets.update(dict(info["style_buckets"]))

    core = analyze_book(
        holdings,
        prices_by_security=prices_map,
        volumes_by_security=volumes_map,
        style_buckets=style_buckets,
        turnover_pct=turnover_pct,
        crowding_top_n=crowding_top_n,
    )

    summary = module_summary(core)
    style = module_style_exposure(core)
    sector = module_sector_concentration(core)
    trading = module_trading_behavior(core)
    methodology = module_methodology()

    period_start = info.get("period_start")
    period_end = info.get("period_end") or snapshot.as_of_date.isoformat()

    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/investment-risk/factor-behavior",
        "tab": "factor-behavior",
        "fund_id": str(info.get("fund_id") or snapshot.fund_id),
        "period_start": period_start,
        "period_end": period_end,
        "as_of_date": str(period_end),
        "source": "holdings_quotes",
        "business_modules": list(BUSINESS_MODULES),
        "modules": {
            "summary": summary,
            "style_exposure": style,
            "sector_concentration": sector,
            "trading_behavior": trading,
            "methodology": methodology,
        },
        # HTTP FactorBehaviorResult 同形
        "style_exposure": core["style_exposure"],
        "sector_concentration": core["sector_concentration"],
        "trading_behavior": core["trading_behavior"],
        "warnings": core["warnings"],
        "logic": methodology["logic"],
        "formulas": methodology["formulas"],
        "holding_count": core["holding_count"],
        "total_equity_market_value": core["total_equity_market_value"],
        "adapters": bound.engine.adapters_status(),
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing {name}")
    summary = modules.get("summary") or {}
    for key in ("momentum_exposure", "low_volatility_exposure", "size_exposure", "sector_hhi"):
        if key not in summary:
            errors.append(f"summary.{key}")
    style = modules.get("style_exposure") or {}
    if "bars" not in style or "coverage_weight" not in style:
        errors.append("style_exposure.bars")
    sector = modules.get("sector_concentration") or {}
    if "hhi" not in sector or "weights" not in sector:
        errors.append("sector_concentration")
    trading = modules.get("trading_behavior") or {}
    if "crowding_top" not in trading:
        errors.append("trading_behavior.crowding_top")
    method = modules.get("methodology") or {}
    if not (method.get("logic") or {}).get("steps"):
        errors.append("methodology.logic")
    if not method.get("formulas"):
        errors.append("methodology.formulas")
    for key in ("style_exposure", "sector_concentration", "trading_behavior", "warnings"):
        if key not in pack:
            errors.append(f"http.{key}")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
