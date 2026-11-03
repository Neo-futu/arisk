"""基本面因子与行为 + 因子风险（RiskEngine）。

两套契约分开：
- compute_factor_behavior_risk：Momentum / LowVol / Size、行业 HHI、交易拥挤度
- compute_factor_risk：RiskEngine Factor Exposure / 冲击 PnL / RC / Beta·TE
"""
from __future__ import annotations

import logging
import math
import statistics
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import (
    _benchmark_id,
    _daily_returns,
    _date_value,
    _index_history,
    _nav_daily_returns,
    _nav_history,
    _number,
    _return_between,
)

logger = logging.getLogger(__name__)


async def compute_factor_behavior_risk(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
    benchmark_id: str | None = None,
) -> dict[str, Any]:
    """基本面因子与行为：风格暴露 + 行业集中度 + 交易拥挤度。

    ``benchmark_id`` 保留兼容参数，本页不参与计算。
    """
    del benchmark_id
    holdings = await _latest_stock_holdings(db, fund_id, period_end)
    codes = [str(item["security_code"]) for item in holdings]
    quote_rows = await _stock_quotes(db, codes, period_start, period_end) if codes else []

    prices_by_security: dict[str, list[tuple[date, float]]] = defaultdict(list)
    volumes_by_security: dict[str, list[float]] = defaultdict(list)
    for row in quote_rows:
        code = str(row["security_code"])
        prices_by_security[code].append((_date_value(row["price_date"]), _number(row["close_price"])))
        volumes_by_security[code].append(_number(row["volume"]))

    total_mv = sum(_number(item["market_value"]) for item in holdings)
    momentum_exposure = 0.0
    low_vol_exposure = 0.0
    size_exposure = 0.0
    coverage_weight = 0.0
    sector_weight: dict[str, float] = defaultdict(float)
    crowding_rows: list[dict[str, Any]] = []

    for item in holdings:
        code = str(item["security_code"])
        mv = _number(item["market_value"])
        weight = mv / total_mv if total_mv else 0.0
        sector = str(item.get("sector") or "未分类")
        sector_weight[sector] += weight

        points = prices_by_security.get(code, [])
        returns = _daily_returns(points)
        period_return = _return_between(points) if points else None
        vol = statistics.stdev(list(returns.values())) if len(returns) >= 2 else None
        if period_return is not None and vol is not None:
            momentum_exposure += period_return * weight
            low_vol_exposure += (1.0 / (1.0 + vol)) * weight
            size_exposure += math.log(max(mv, 1.0)) * weight
            coverage_weight += weight

        avg_volume = statistics.mean(volumes_by_security[code]) if volumes_by_security.get(code) else 0.0
        quantity = _number(item.get("quantity"))
        crowding_rows.append(
            {
                "security_code": code,
                "security_name": item.get("security_name") or code,
                "sector": sector,
                "weight_pct": weight * 100.0,
                "avg_daily_volume": avg_volume,
                "position_quantity": quantity,
                "crowding_ratio": (quantity / avg_volume) if avg_volume else None,
            }
        )

    hhi = sum(value * value for value in sector_weight.values()) * 10000 if sector_weight else 0.0
    crowding_rows.sort(key=lambda row: _number(row.get("crowding_ratio"), -1), reverse=True)
    turnover_pct = await _equity_turnover_pct(db, fund_id, period_start, period_end)

    warnings: list[str] = []
    if not holdings:
        warnings.append("区间末无股票持仓，风格暴露与拥挤度为空")
    elif coverage_weight <= 0:
        warnings.append("持仓缺少可用行情（mktdata_quotes），风格暴露无法计算")
    if hhi > 1800:
        warnings.append("行业集中度偏高（HHI > 1800）")
    if turnover_pct is not None and turnover_pct > 120:
        warnings.append("股票换手率偏高，存在拥挤交易风险")
    top_crowding = crowding_rows[0].get("crowding_ratio") if crowding_rows else None
    if top_crowding is not None and top_crowding > 0.25:
        warnings.append("头部持仓相对日均成交量偏高，可能存在踩踏风险")

    style_buckets = await _equity_style_buckets(db, fund_id, period_end)

    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "as_of_date": period_end,
        "source": "holdings_quotes",
        "style_exposure": {
            "momentum_exposure": momentum_exposure if coverage_weight else None,
            "low_volatility_exposure": low_vol_exposure if coverage_weight else None,
            "size_exposure": size_exposure if coverage_weight else None,
            "coverage_weight": coverage_weight * 100.0,
            "value_weight_pct": style_buckets.get("value_weight_pct"),
            "growth_weight_pct": style_buckets.get("growth_weight_pct"),
            "large_weight_pct": style_buckets.get("large_weight_pct"),
            "small_weight_pct": style_buckets.get("small_weight_pct"),
        },
        "sector_concentration": {
            "hhi": hhi,
            "weights": [
                {"sector": sector, "weight_pct": weight * 100.0}
                for sector, weight in sorted(sector_weight.items(), key=lambda item: item[1], reverse=True)
            ],
        },
        "trading_behavior": {
            "turnover_pct": turnover_pct,
            "crowding_top": crowding_rows[:20],
        },
        "warnings": warnings,
        "logic": {
            "title": "基本面因子与行为实现逻辑",
            "steps": [
                "取区间末股票持仓（balance_stock），行业优先用 mktdata_stock_industry（GICS）",
                "用区间 mktdata_quotes 收盘价计算个券区间收益与日波动，按市值权重合成 Momentum / LowVol / Size",
                "Size = Σ w_i · ln(MV_i)；LowVol = Σ w_i / (1+σ_i)；Momentum = Σ w_i · R_i",
                "行业 HHI = Σ w_s² × 10000；拥挤比 = 持仓量 / 区间日均成交量",
                "换手率取区间股票买卖单边较小值 / 平均持仓市值",
                "可选补充：mktdata_equity_style 的价值/成长、大盘/小盘权重",
            ],
        },
        "formulas": {
            "momentum": "Σ w_i · (P_end / P_start - 1)",
            "low_volatility": "Σ w_i / (1 + σ_i)",
            "size": "Σ w_i · ln(max(MV_i, 1))",
            "hhi": "Σ w_sector² × 10000",
            "crowding": "quantity / avg_daily_volume",
        },
    }


async def compute_factor_risk(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
    benchmark_id: str | None = None,
) -> dict[str, Any]:
    """因子风险：RiskEngine Factor Exposure / 标准因子冲击 / RC / Beta·TE。"""
    from importlib import import_module

    loader = import_module("2_processing.tools.risk_testing.loader")
    engine_mod = import_module("3_riskengine")
    kpis = import_module("3_riskengine.risk.kpis")
    domains = import_module("4_business.investment_risk.domains")

    chosen_benchmark = (benchmark_id or "").strip() or await _benchmark_id(db, fund_id, period_end)
    fund_returns, bench_returns, bench_meta = await _aligned_return_pair(
        db, fund_id, chosen_benchmark, period_start, period_end
    )

    snapshot = await loader.load_portfolio_snapshot(fund_id, period_end, db, lookback_days=500)
    bound = engine_mod.RiskEngine().bind(snapshot)

    factor_domain = domains.analyze_domain(
        "factor_risk",
        snapshot,
        confidence=0.99,
        benchmark_returns=bench_returns or None,
    )
    try:
        portfolio_pack = bound.portfolio().risk(confidence=0.99)
    except Exception:
        logger.exception("RiskEngine portfolio.risk failed for %s", fund_id)
        portfolio_pack = {
            "error": "portfolio_risk_unavailable",
            "risk_contribution": {"factor_pnl": {"factors": []}, "by_asset_class": {}},
        }

    exposure_kpi = factor_domain["kpis"].get("Factor Exposure") or kpis.kpi_factor_exposure(snapshot)
    beta_result = _compute_beta(fund_returns, bench_returns)
    te_result = _compute_tracking_error(fund_returns, bench_returns)

    factor_exposure = _present_factor_exposure(exposure_kpi.get("result") or {})
    factor_shocks = _present_factor_shocks(
        ((portfolio_pack.get("risk_contribution") or {}).get("factor_pnl") or {}).get("factors") or [],
        float(getattr(snapshot, "net_asset", 0.0) or 0.0),
    )
    rc_by_class = _present_rc_by_class(
        (portfolio_pack.get("risk_contribution") or {}).get("by_asset_class") or {}
    )

    quality = dict(getattr(snapshot, "data_quality", {}) or {})
    warnings: list[str] = []
    if not chosen_benchmark:
        warnings.append("未配置基准：Beta / Tracking Error 无法计算，请选择指数后点击计算")
    elif bench_meta["quote_count"] < 3:
        warnings.append(f"基准 {chosen_benchmark} 在区间内指数行情不足（mktdata_index_quotes）")
    elif beta_result["paired_observations"] < 3:
        warnings.append(f"基准 {chosen_benchmark} 与组合 NAV 可对齐交易日不足")

    adapters = engine_mod.RiskEngine().adapters_status()
    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "as_of_date": period_end,
        "benchmark_id": chosen_benchmark,
        "benchmark": bench_meta,
        "source": "riskengine",
        "engine": adapters.get("engine") or "ARISK RiskEngine",
        "engine_version": adapters.get("engine_version"),
        "adapters": adapters,
        "factor_risk": {
            "factor_exposure": factor_exposure,
            "factor_shocks": factor_shocks,
            "risk_contribution_by_asset_class": rc_by_class,
            "beta": beta_result,
            "tracking_error": te_result,
            "var_cvar": portfolio_pack.get("var_cvar") or {},
            "data_quality": {
                "effective_date": quality.get("effective_date"),
                "source_position_count": quality.get("source_position_count"),
                "source_risk_coverage_pct": quality.get("source_risk_coverage_pct"),
                "unmapped_balance": _number(quality.get("unmapped_balance")),
            },
            "formulas": {
                "factor_exposure": exposure_kpi.get("formula") or "FE_f = Σ_{i∈f} |MV_i| / NAV",
                "beta": "β = Cov(R_p, R_b) / Var(R_b)（交易日对齐）",
                "tracking_error": "TE = stdev(R_p - R_b) × √252（交易日对齐）",
                "factor_shock": "PnL_f = PV(shock_f) - PV(base)；RC 按 |PnL| 归一",
            },
        },
        "warnings": warnings,
        "logic": {
            "title": "RiskEngine 业务实现逻辑",
            "steps": [
                "从 fsi.balance_* / mktdata_* 组装 PortfolioSnapshot（risk_testing.loader）",
                "RiskEngine.bind(snapshot) → LOOK_THROUGH 组合视图",
                "Factor Exposure：classify 归入 RATE_CREDIT / EQUITY / FUND / MMF / CASH，外币叠加 FX",
                "标准因子冲击：rate+1bp、equity+1%、fx+1%、cs+1bp、vol+10%，FinancePy/ORE 再估值",
                "风险贡献：各冲击 |PnL| 汇总后归一到资产类别",
                "Beta / Tracking Error：组合 NAV 日收益对主基准指数收益",
            ],
        },
    }


async def _latest_stock_holdings(db: AsyncSession, fund_id: str, as_of: date) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            WITH latest AS (
                SELECT MAX(evaluate_date) AS value
                FROM fsi.balance_stock
                WHERE port_id = :fund_id AND evaluate_date <= :as_of
            )
            SELECT b.security_code,
                   COALESCE(b.security_name, b.security_code) AS security_name,
                   COALESCE(ind.level1_name, ind.industry_name, NULLIF(b.sector, ''), '未分类') AS sector,
                   COALESCE(b.quantity, 0) AS quantity,
                   COALESCE(b.market_value_base, b.market_value, 0) AS market_value,
                   COALESCE(b.weight_pct, 0) AS weight_pct
            FROM fsi.balance_stock b
            LEFT JOIN LATERAL (
                SELECT i.industry_name, i.level1_name
                FROM fsi.v_mktdata_stock_industry_current i
                WHERE i.security_code = b.security_code
                ORDER BY (i.standard = 'GICS') DESC, i.is_primary DESC
                LIMIT 1
            ) ind ON TRUE
            WHERE b.port_id = :fund_id
              AND b.evaluate_date = (SELECT value FROM latest)
            """
        ),
        {"fund_id": fund_id, "as_of": as_of},
    )
    return [dict(row) for row in result.mappings().all()]


async def _stock_quotes(
    db: AsyncSession,
    codes: list[str],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT price_date, security_code, close_price, COALESCE(volume, 0) AS volume
            FROM fsi.mktdata_quotes
            WHERE price_type = 'CLOSE'
              AND price_date BETWEEN :start AND :end
              AND security_code IN :codes
            ORDER BY security_code, price_date
            """
        ).bindparams(bindparam("codes", expanding=True)),
        {"start": start, "end": end, "codes": codes},
    )
    return [dict(row) for row in result.mappings().all()]


async def _equity_turnover_pct(
    db: AsyncSession,
    fund_id: str,
    start: date,
    end: date,
) -> float | None:
    result = await db.execute(
        text(
            """
            WITH trades AS (
                SELECT SUM(CASE WHEN direction::text = 'BUY'
                                THEN ABS(COALESCE(amount_base_ccy, gross_amount)) ELSE 0 END) AS buy_amount,
                       SUM(CASE WHEN direction::text = 'SELL'
                                THEN ABS(COALESCE(amount_base_ccy, gross_amount)) ELSE 0 END) AS sell_amount
                FROM fsi.transact_stock
                WHERE port_id = :fund_id
                  AND trade_date BETWEEN :start AND :end
                  AND status::text = 'CONFIRMED'
            ), bal AS (
                SELECT AVG(COALESCE(market_value_base, market_value, 0)) AS avg_balance
                FROM fsi.balance_stock
                WHERE port_id = :fund_id
                  AND evaluate_date BETWEEN :start AND :end
            )
            SELECT COALESCE(buy_amount, 0) AS buy_amount,
                   COALESCE(sell_amount, 0) AS sell_amount,
                   COALESCE(avg_balance, 0) AS avg_balance
            FROM trades, bal
            """
        ),
        {"fund_id": fund_id, "start": start, "end": end},
    )
    row = dict(result.mappings().first() or {})
    avg_balance = _number(row.get("avg_balance"))
    one_way = min(_number(row.get("buy_amount")), _number(row.get("sell_amount")))
    return one_way / avg_balance * 100.0 if avg_balance else None


async def _equity_style_buckets(db: AsyncSession, fund_id: str, as_of: date) -> dict[str, float | None]:
    result = await db.execute(
        text(
            """
            WITH latest AS (
                SELECT MAX(evaluate_date) AS value
                FROM fsi.balance_stock
                WHERE port_id = :fund_id AND evaluate_date <= :as_of
            )
            SELECT SUM(COALESCE(s.market_value_base, s.market_value, 0))
                       FILTER (WHERE es.style_bucket = 'GROWTH') AS growth_mv,
                   SUM(COALESCE(s.market_value_base, s.market_value, 0))
                       FILTER (WHERE es.style_bucket = 'VALUE') AS value_mv,
                   SUM(COALESCE(s.market_value_base, s.market_value, 0))
                       FILTER (WHERE es.size_bucket = 'LARGE') AS large_mv,
                   SUM(COALESCE(s.market_value_base, s.market_value, 0))
                       FILTER (WHERE es.size_bucket = 'SMALL') AS small_mv,
                   SUM(COALESCE(s.market_value_base, s.market_value, 0)) AS total_mv
            FROM fsi.balance_stock s
            LEFT JOIN LATERAL (
                SELECT size_bucket, style_bucket
                FROM fsi.mktdata_equity_style
                WHERE security_code = s.security_code AND as_of_date <= s.evaluate_date
                ORDER BY as_of_date DESC
                LIMIT 1
            ) es ON TRUE
            WHERE s.port_id = :fund_id AND s.evaluate_date = (SELECT value FROM latest)
            """
        ),
        {"fund_id": fund_id, "as_of": as_of},
    )
    row = dict(result.mappings().first() or {})
    total = _number(row.get("total_mv"))
    if not total:
        return {
            "value_weight_pct": None,
            "growth_weight_pct": None,
            "large_weight_pct": None,
            "small_weight_pct": None,
        }
    return {
        "value_weight_pct": _number(row.get("value_mv")) / total * 100.0,
        "growth_weight_pct": _number(row.get("growth_mv")) / total * 100.0,
        "large_weight_pct": _number(row.get("large_mv")) / total * 100.0,
        "small_weight_pct": _number(row.get("small_mv")) / total * 100.0,
    }


async def _aligned_return_pair(
    db: AsyncSession,
    fund_id: str,
    benchmark_id: str | None,
    start: date,
    end: date,
) -> tuple[list[float], list[float], dict[str, Any]]:
    nav_hist = await _nav_history(db, fund_id, end, start)
    fund_ret = _nav_daily_returns(nav_hist)
    meta: dict[str, Any] = {
        "benchmark_id": benchmark_id,
        "quote_count": 0,
        "fund_return_days": len(fund_ret),
        "paired_days": 0,
        "index_start": None,
        "index_end": None,
    }
    if not benchmark_id:
        return [], [], meta

    points = await _index_history(db, benchmark_id, start, end)
    meta["quote_count"] = len(points)
    if points:
        meta["index_start"] = points[0][0].isoformat()
        meta["index_end"] = points[-1][0].isoformat()
    bench_ret = _daily_returns(points)
    days = sorted(set(fund_ret) & set(bench_ret))
    meta["paired_days"] = len(days)
    return [fund_ret[d] for d in days], [bench_ret[d] for d in days], meta


def _compute_beta(fund_returns: list[float], bench_returns: list[float]) -> dict[str, Any]:
    n = min(len(fund_returns), len(bench_returns))
    if n < 3:
        return {"beta": None, "paired_observations": n}
    try:
        import numpy as np

        a = np.asarray(fund_returns[-n:], dtype=float)
        b = np.asarray(bench_returns[-n:], dtype=float)
        var_b = float(np.var(b, ddof=1))
        value = float(np.cov(a, b, ddof=1)[0, 1] / var_b) if var_b > 0 else None
    except Exception:
        value = None
    return {"beta": value, "paired_observations": n}


def _compute_tracking_error(fund_returns: list[float], bench_returns: list[float]) -> dict[str, Any]:
    n = min(len(fund_returns), len(bench_returns))
    if n < 3:
        return {"annualized": None, "annualized_pct": None, "paired_observations": n}
    try:
        import numpy as np

        active = np.asarray(fund_returns[-n:], dtype=float) - np.asarray(bench_returns[-n:], dtype=float)
        te = float(np.std(active, ddof=1) * math.sqrt(252))
    except Exception:
        te = None
    return {
        "annualized": te,
        "annualized_pct": te * 100.0 if te is not None else None,
        "paired_observations": n,
    }


def _present_factor_exposure(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for factor, payload in (result or {}).items():
        if isinstance(payload, dict):
            rows.append(
                {
                    "factor": str(factor),
                    "amount": _number(payload.get("amount")),
                    "pct_nav": _number(payload.get("pct_nav")),
                }
            )
    rows.sort(key=lambda row: abs(row["pct_nav"]), reverse=True)
    return rows


def _present_factor_shocks(factors: list[dict[str, Any]], nav: float) -> list[dict[str, Any]]:
    rows = []
    for item in factors:
        pnl = _number(item.get("pnl"))
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


def _present_rc_by_class(by_class: dict[str, float]) -> list[dict[str, Any]]:
    rows = [
        {"asset_class": str(klass), "share_pct": float(share) * 100.0}
        for klass, share in (by_class or {}).items()
    ]
    rows.sort(key=lambda row: abs(row["share_pct"]), reverse=True)
    return rows
