"""Six-category risk metric board — aggregates existing analytics + fills gaps.

Avoids duplicating detailed domain UIs: returns a compact catalog of metrics
with status computed | derived | unavailable.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import Date, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_attribution import compute_performance_attribution
from .investment_analysis_common import (
    _benchmark_id,
    _daily_returns,
    _date_value,
    _index_history,
    _nav_daily_returns,
    _nav_history,
    _number,
    _resolve_nav_period,
)
from .investment_analysis_factor import compute_factor_behavior_risk
from .investment_analysis_liquidity_stress import compute_liquidity_stress_testing
from .investment_analysis_overview import compute_portfolio_overview
from .investment_analysis_rates_credit import compute_rates_credit_sensitivity
from .investment_analysis_risk_indicators import compute_risk_indicators
from ..risk.exposure_engine import compute_exposure
from ..risk.exposure_domain import ExposureResult

# Ratings at or below AA+ treated as "low rating" for credit-bond concentration.
_LOW_RATINGS = {
    "AA+", "AA", "AA-", "A+", "A", "A-",
    "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
    "B+", "B", "B-", "CCC", "CC", "C", "D", "NR",
}

_HIGH_LIQUIDITY = {"CASH", "DEPOSIT", "REPO", "REV_REPO", "CD", "BOND_GOVT", "FUND_ETF"}
_RATE_BOND = {"BOND_GOVT"}
_CREDIT_BOND = {"BOND_CORP", "BOND_CONVERT", "BOND_ABS", "CP"}


def _metric(
    metric_id: str,
    name: str,
    *,
    value: float | int | str | None = None,
    unit: str | None = None,
    status: str = "computed",
    note: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "name": name,
        "value": value,
        "unit": unit,
        "status": status,  # computed | derived | unavailable
        "note": note,
        "detail": detail,
    }


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), digits)


async def _latest_balance_date(
    db: AsyncSession,
    table: str,
    fund_id: str,
    as_of_date: date,
) -> date | None:
    result = await db.execute(
        text(
            f"""
            SELECT MAX(evaluate_date) AS value
            FROM fsi.{table}
            WHERE port_id = :fund_id AND evaluate_date <= :as_of_date
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    return result.scalar_one_or_none()


async def _active_return_series(
    db: AsyncSession,
    fund_id: str,
    start: date,
    end: date,
) -> tuple[list[float], list[float], str | None]:
    """Aligned fund / benchmark daily returns for Sharpe / IR / TE."""
    history = await _nav_history(db, fund_id, end, start)
    fund_returns = _nav_daily_returns(history)
    benchmark_id = await _benchmark_id(db, fund_id, end)
    if not benchmark_id:
        return list(fund_returns.values()), [], None
    bench_points = await _index_history(db, benchmark_id, start, end)
    bench_returns = _daily_returns(bench_points)
    common = sorted(set(fund_returns) & set(bench_returns))
    return (
        [fund_returns[d] for d in common],
        [bench_returns[d] for d in common],
        benchmark_id,
    )


async def _tracking_error_limit(db: AsyncSession, fund_id: str, as_of: date) -> float | None:
    """组合委托里的年化跟踪误差上限（%）。"""
    result = await db.execute(
        text(
            """
            SELECT limit_value
            FROM fsi.para_risk_limit_regulatory
            WHERE port_id = :fund_id
              AND rule_code = 'MAX_TRACKING_ERROR'
              AND is_active = TRUE
              AND effective_date <= :as_of
              AND (expiry_date IS NULL OR expiry_date >= :as_of)
            ORDER BY effective_date DESC
            LIMIT 1
            """
        ),
        {"fund_id": fund_id, "as_of": as_of},
    )
    value = result.scalar_one_or_none()
    return float(value) if value is not None else None


async def _bond_extensions(
    db: AsyncSession,
    fund_id: str,
    snapshot: date,
) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT COALESCE(security_code, '') AS security_code,
                   COALESCE(security_name, security_code) AS security_name,
                   COALESCE(issuer_name, 'UNKNOWN') AS issuer_name,
                   COALESCE(debt_rating, issuer_rating, 'NR') AS rating,
                   maturity_date,
                   COALESCE(duration, 0) AS duration,
                   COALESCE(convexity, 0) AS convexity,
                   COALESCE(ytm, 0) AS ytm,
                   COALESCE(market_value_base, market_value, 0) AS market_value
            FROM fsi.balance_bond
            WHERE port_id = :fund_id AND evaluate_date = :snapshot
            """
        ),
        {"fund_id": fund_id, "snapshot": snapshot},
    )
    bonds = [dict(row) for row in result.mappings().all()]
    total = sum(_number(b["market_value"]) for b in bonds)
    if not total:
        return {
            "weighted_convexity": None,
            "avg_remaining_years": None,
            "max_remaining_days": None,
            "modified_duration": None,
            "credit_spread_proxy_pct": None,
            "low_rating_pct": None,
            "unrated_pct": None,
            "top5_bond_pct": None,
            "top10_bond_pct": None,
            "top_issuer_pct": None,
        }

    w_conv = sum(_number(b["market_value"]) * _number(b["convexity"]) for b in bonds) / total
    w_dur = sum(_number(b["market_value"]) * _number(b["duration"]) for b in bonds) / total
    remaining_years = []
    remaining_days_list: list[int] = []
    for b in bonds:
        mat = b.get("maturity_date")
        if mat is None:
            continue
        try:
            days = max((_date_value(mat) - snapshot).days, 0)
            remaining_years.append((_number(b["market_value"]), days / 365.25))
            remaining_days_list.append(days)
        except Exception:
            continue
    avg_rem = (
        sum(mv * y for mv, y in remaining_years) / sum(mv for mv, _ in remaining_years)
        if remaining_years
        else None
    )
    max_remaining_days = max(remaining_days_list) if remaining_days_list else None
    # YTM - duration-weighted proxy vs risk-free-ish 2% for credit spread
    w_ytm = sum(_number(b["market_value"]) * _number(b["ytm"]) for b in bonds) / total
    credit_spread = (w_ytm - 2.0) if w_ytm else None

    low_mv = sum(
        _number(b["market_value"])
        for b in bonds
        if str(b.get("rating") or "NR").upper() in _LOW_RATINGS
    )
    unrated_mv = sum(
        _number(b["market_value"])
        for b in bonds
        if str(b.get("rating") or "NR").upper() in {"NR", "N/A", "", "UNRATED"}
    )

    by_code = sorted(
        ((_number(b["market_value"]), str(b["security_code"])) for b in bonds),
        reverse=True,
    )
    top5 = sum(mv for mv, _ in by_code[:5]) / total * 100.0
    top10 = sum(mv for mv, _ in by_code[:10]) / total * 100.0
    issuer_mv: dict[str, float] = defaultdict(float)
    for b in bonds:
        issuer_mv[str(b["issuer_name"])] += _number(b["market_value"])
    top_issuer = max(issuer_mv.values()) / total * 100.0 if issuer_mv else None

    return {
        "weighted_convexity": _round(w_conv, 4),
        "avg_remaining_years": _round(avg_rem, 3),
        "max_remaining_days": max_remaining_days,
        "modified_duration": _round(w_dur, 3),
        "credit_spread_proxy_pct": _round(credit_spread, 3),
        "low_rating_pct": _round(low_mv / total * 100.0, 2),
        "unrated_pct": _round(unrated_mv / total * 100.0, 2),
        "top5_bond_pct": _round(top5, 2),
        "top10_bond_pct": _round(top10, 2),
        "top_issuer_pct": _round(top_issuer, 2),
    }


async def _asset_structure(
    db: AsyncSession,
    fund_id: str,
    snapshot: date,
    nav: float,
) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT asset_class::text AS asset_class,
                   SUM(COALESCE(market_value_base, market_value, 0)) AS market_value
            FROM fsi.balance_portfolio_asset
            WHERE port_id = :fund_id AND evaluate_date = :snapshot
            GROUP BY asset_class::text
            """
        ),
        {"fund_id": fund_id, "snapshot": snapshot},
    )
    rows = [dict(r) for r in result.mappings().all()]
    total_assets = sum(_number(r["market_value"]) for r in rows)
    by_class = {str(r["asset_class"]): _number(r["market_value"]) for r in rows}

    def pct(keys: set[str]) -> float | None:
        if not nav:
            return None
        return _round(sum(by_class.get(k, 0.0) for k in keys) / nav * 100.0, 2)

    cash_pct = pct({"CASH", "DEPOSIT"})
    high_liq_pct = pct(_HIGH_LIQUIDITY)
    rate_bond_pct = pct(_RATE_BOND)
    credit_bond_pct = pct(_CREDIT_BOND)
    repo_liab = by_class.get("REPO", 0.0)
    # Repo treated as funding liability contribution when positive market value encoding
    leverage = _round(total_assets / nav, 3) if nav else None
    repo_pct = _round(abs(repo_liab) / nav * 100.0, 2) if nav else None
    return {
        "total_assets": total_assets,
        "cash_pct_nav": cash_pct,
        "high_liquidity_pct_nav": high_liq_pct,
        "rate_bond_pct_nav": rate_bond_pct,
        "credit_bond_pct_nav": credit_bond_pct,
        "leverage_ratio": leverage,
        "repo_liability_pct_nav": repo_pct,
        "by_class": by_class,
    }


async def _equity_concentration(
    db: AsyncSession,
    fund_id: str,
    snapshot: date | None,
) -> dict[str, Any]:
    if snapshot is None:
        return {"top5_pct": None, "top10_pct": None, "largest_pct": None, "hhi": None}
    result = await db.execute(
        text(
            """
            SELECT COALESCE(weight_pct, 0) AS weight_pct,
                   COALESCE(market_value_base, market_value, 0) AS market_value
            FROM fsi.balance_stock
            WHERE port_id = :fund_id AND evaluate_date = :snapshot
            """
        ),
        {"fund_id": fund_id, "snapshot": snapshot},
    )
    rows = [dict(r) for r in result.mappings().all()]
    if not rows:
        return {"top5_pct": None, "top10_pct": None, "largest_pct": None, "hhi": None}
    weights = sorted((_number(r["weight_pct"]) for r in rows), reverse=True)
    # If weight_pct missing, fall back to MV share
    if sum(weights) <= 0:
        total = sum(_number(r["market_value"]) for r in rows) or 1.0
        weights = sorted((_number(r["market_value"]) / total * 100.0 for r in rows), reverse=True)
    hhi = sum((w / 100.0) ** 2 for w in weights) * 10000
    return {
        "top5_pct": _round(sum(weights[:5]), 2),
        "top10_pct": _round(sum(weights[:10]), 2),
        "largest_pct": _round(weights[0] if weights else None, 2),
        "hhi": _round(hhi, 1),
    }


async def _security_pnl_summary(
    attribution: dict[str, Any],
) -> dict[str, Any]:
    winners = attribution.get("top_winners") or []
    losers = attribution.get("top_losers") or []
    period_pnl = sum(_number(r.get("net_pnl")) for r in winners) + sum(
        _number(r.get("net_pnl")) for r in losers
    )
    return {
        "top_winner_pnl": _number(winners[0]["net_pnl"]) if winners else None,
        "top_loser_pnl": _number(losers[0]["net_pnl"]) if losers else None,
        "sample_security_pnl": _round(period_pnl, 0),
    }


def _liquidity_bucket_pcts(ladder: list[dict[str, Any]], nav: float) -> dict[str, Any]:
    if not nav:
        return {
            "avg_ttl_days": None,
            "over_10d_pct": None,
            "over_40d_pct": None,
            "stock_ttl": None,
            "bond_ttl": None,
        }
    total_mv = sum(_number(r.get("market_value")) for r in ladder) or 1.0
    avg_ttl = sum(_number(r.get("market_value")) * _number(r.get("ttl_days")) for r in ladder) / total_mv
    over_10 = sum(_number(r.get("market_value")) for r in ladder if _number(r.get("ttl_days")) > 10)
    over_40 = sum(_number(r.get("market_value")) for r in ladder if _number(r.get("ttl_days")) > 40)
    stock_rows = [r for r in ladder if str(r.get("asset_class")) == "STOCK"]
    bond_rows = [r for r in ladder if str(r.get("asset_class", "")).startswith("BOND")]
    stock_ttl = (
        sum(_number(r["market_value"]) * _number(r["ttl_days"]) for r in stock_rows)
        / sum(_number(r["market_value"]) for r in stock_rows)
        if stock_rows
        else None
    )
    bond_ttl = (
        sum(_number(r["market_value"]) * _number(r["ttl_days"]) for r in bond_rows)
        / sum(_number(r["market_value"]) for r in bond_rows)
        if bond_rows
        else None
    )
    return {
        "avg_ttl_days": _round(avg_ttl, 1),
        "over_10d_pct": _round(over_10 / nav * 100.0, 2),
        "over_40d_pct": _round(over_40 / nav * 100.0, 2),
        "stock_ttl": _round(stock_ttl, 1),
        "bond_ttl": _round(bond_ttl, 1),
    }


async def _extension_metrics(
    db: AsyncSession,
    fund_id: str,
    period_start: date,
    period_end: date,
    bond_date: date | None,
    stock_date: date | None,
    nav: float,
    base_currency: str,
    liquid_within_7d: float,
) -> dict[str, Any]:
    """Fill metrics from market data, sponsor, news and related-party tables."""
    out: dict[str, Any] = {}
    params = {
        "fund_id": fund_id,
        "start": period_start,
        "end": period_end,
        "bond_date": bond_date,
        "stock_date": stock_date,
        "base": base_currency,
    }

    def _sql(statement: str):
        names = ("start", "end", "bond_date", "stock_date")
        binds = [bindparam(name, type_=Date) for name in names if f":{name}" in statement]
        clause = text(statement)
        return clause.bindparams(*binds) if binds else clause

    if stock_date is not None:
        pe_row = (
            await db.execute(
                _sql(
                    """
                    WITH holdings AS (
                        SELECT security_code,
                               COALESCE(market_value_base, market_value, 0) AS mv,
                               quantity
                        FROM fsi.balance_stock
                        WHERE port_id = :fund_id AND evaluate_date = :stock_date
                    ), quotes AS (
                        SELECT DISTINCT ON (security_code)
                               security_code, pe_ratio, pb_ratio
                        FROM fsi.mktdata_quotes
                        WHERE price_type = 'CLOSE' AND price_date <= :end
                        ORDER BY security_code, price_date DESC
                    )
                    SELECT SUM(h.mv * q.pe_ratio) / NULLIF(SUM(h.mv) FILTER (WHERE q.pe_ratio > 0), 0) AS pe,
                           SUM(h.mv * q.pb_ratio) / NULLIF(SUM(h.mv) FILTER (WHERE q.pb_ratio > 0), 0) AS pb,
                           MAX(h.quantity / NULLIF(st.shares_outstanding, 0)) * 100 AS of_shares,
                           MAX(h.quantity / NULLIF(st.free_float_shares, 0)) * 100 AS of_float
                    FROM holdings h
                    LEFT JOIN quotes q ON q.security_code = h.security_code
                    LEFT JOIN fsi.mktdata_stock_static st ON st.security_code = h.security_code
                    """
                ),
                params,
            )
        ).mappings().first()
        if pe_row:
            out["avg_pe"] = _round(_number(pe_row["pe"]) if pe_row["pe"] is not None else None, 2)
            out["avg_pb"] = _round(_number(pe_row["pb"]) if pe_row["pb"] is not None else None, 2)
            out["equity_of_float"] = _round(
                _number(pe_row["of_float"]) if pe_row["of_float"] is not None else None, 4
            )
            out["equity_of_shares"] = _round(
                _number(pe_row["of_shares"]) if pe_row["of_shares"] is not None else None, 4
            )

        style_row = (
            await db.execute(
                _sql(
                    """
                    SELECT SUM(COALESCE(s.market_value_base, s.market_value, 0))
                               FILTER (WHERE es.style_bucket = 'GROWTH') AS growth_mv,
                           SUM(COALESCE(s.market_value_base, s.market_value, 0))
                               FILTER (WHERE es.style_bucket = 'VALUE') AS value_mv,
                           SUM(COALESCE(s.market_value_base, s.market_value, 0))
                               FILTER (WHERE es.size_bucket = 'LARGE') AS large_mv,
                           SUM(COALESCE(s.market_value_base, s.market_value, 0))
                               FILTER (WHERE es.size_bucket = 'SMALL') AS small_mv,
                           SUM(COALESCE(s.market_value_base, s.market_value, 0)) AS total_mv,
                           SUM(COALESCE(s.market_value_base, s.market_value, 0))
                               FILTER (WHERE s.is_sellable = FALSE OR h.is_halted) AS restricted_mv
                    FROM fsi.balance_stock s
                    LEFT JOIN LATERAL (
                        SELECT size_bucket, style_bucket
                        FROM fsi.mktdata_equity_style
                        WHERE security_code = s.security_code AND as_of_date <= s.evaluate_date
                        ORDER BY as_of_date DESC
                        LIMIT 1
                    ) es ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT TRUE AS is_halted
                        FROM fsi.mktdata_security_halt
                        WHERE security_code = s.security_code
                          AND asset_class = 'EQUITY'
                          AND is_halted
                          AND halt_date <= s.evaluate_date
                          AND (resume_date IS NULL OR resume_date > s.evaluate_date)
                        ORDER BY halt_date DESC
                        LIMIT 1
                    ) h ON TRUE
                    WHERE s.port_id = :fund_id AND s.evaluate_date = :stock_date
                    """
                ),
                params,
            )
        ).mappings().first()
        if style_row and _number(style_row["total_mv"]):
            total = _number(style_row["total_mv"])
            growth = _number(style_row["growth_mv"]) / total * 100.0
            value = _number(style_row["value_mv"]) / total * 100.0
            large = _number(style_row["large_mv"]) / total * 100.0
            small = _number(style_row["small_mv"]) / total * 100.0
            out["style_deviation"] = _round(growth - value, 2)
            out["style_detail"] = f"成长 {growth:.1f}% / 价值 {value:.1f}% / 大盘 {large:.1f}% / 小盘 {small:.1f}%"
            out["restricted_pct"] = _round(_number(style_row["restricted_mv"]) / nav * 100.0, 2) if nav else 0.0

    country_rows = (
        await db.execute(
            _sql(
                """
                SELECT country, SUM(mv) AS mv
                FROM (
                    SELECT COALESCE(country, 'UN') AS country,
                           COALESCE(market_value_base, market_value, 0) AS mv
                    FROM fsi.balance_stock
                    WHERE port_id = :fund_id AND evaluate_date = :stock_date
                    UNION ALL
                    SELECT COALESCE(country, 'UN') AS country,
                           COALESCE(market_value_base, market_value, 0) AS mv
                    FROM fsi.balance_bond
                    WHERE port_id = :fund_id AND evaluate_date = :bond_date
                    UNION ALL
                    SELECT CASE currency WHEN 'CNY' THEN 'CN' WHEN 'USD' THEN 'US' ELSE 'HK' END,
                           COALESCE(total_value_base, total_value, principal, 0)
                    FROM fsi.balance_deposit
                    WHERE port_id = :fund_id AND evaluate_date = COALESCE(:bond_date, :stock_date, :end)
                ) u
                GROUP BY country
                """
            ),
            params,
        )
    ).mappings().all()
    country_total = sum(_number(row["mv"]) for row in country_rows)
    if country_total:
        top = max(country_rows, key=lambda row: _number(row["mv"]))
        out["country_conc"] = _round(_number(top["mv"]) / country_total * 100.0, 2)
        out["country_detail"] = ", ".join(
            f"{row['country']} {_number(row['mv']) / country_total * 100:.1f}%"
            for row in sorted(country_rows, key=lambda item: _number(item["mv"]), reverse=True)[:4]
        )

    fx_row = (
        await db.execute(
            _sql(
                """
                SELECT SUM(mv) FILTER (WHERE currency <> :base) AS fx_mv,
                       SUM(mv) AS total_mv
                FROM (
                    SELECT currency, COALESCE(market_value_base, market_value, 0) AS mv
                    FROM fsi.balance_stock
                    WHERE port_id = :fund_id AND evaluate_date = :stock_date
                    UNION ALL
                    SELECT currency, COALESCE(market_value_base, market_value, 0)
                    FROM fsi.balance_bond
                    WHERE port_id = :fund_id AND evaluate_date = :bond_date
                    UNION ALL
                    SELECT currency, COALESCE(total_value_base, total_value, principal, 0)
                    FROM fsi.balance_deposit
                    WHERE port_id = :fund_id AND evaluate_date = COALESCE(:bond_date, :stock_date, :end)
                    UNION ALL
                    SELECT currency, COALESCE(amount_base_ccy, amount, 0)
                    FROM fsi.balance_cash
                    WHERE port_id = :fund_id AND evaluate_date = COALESCE(:bond_date, :stock_date, :end)
                ) u
                """
            ),
            params,
        )
    ).mappings().first()
    if fx_row and _number(fx_row["total_mv"]):
        out["fx_exposure"] = _round(_number(fx_row["fx_mv"]) / _number(fx_row["total_mv"]) * 100.0, 2)
        out["non_cny_pct"] = out["fx_exposure"] if base_currency == "CNY" else _round(
            100.0 - (_number(fx_row["fx_mv"]) / _number(fx_row["total_mv"]) * 100.0 if base_currency != "CNY" else 0),
            2,
        )
        # 境外非人民币：本位币不是 CNY 时，非 CNY 资产占比
        cny_row = (
            await db.execute(
                _sql(
                    """
                    SELECT SUM(mv) FILTER (WHERE currency = 'CNY') AS cny_mv, SUM(mv) AS total_mv
                    FROM (
                        SELECT currency, COALESCE(market_value_base, market_value, 0) AS mv
                        FROM fsi.balance_stock
                        WHERE port_id = :fund_id AND evaluate_date = :stock_date
                        UNION ALL
                        SELECT currency, COALESCE(market_value_base, market_value, 0)
                        FROM fsi.balance_bond
                        WHERE port_id = :fund_id AND evaluate_date = :bond_date
                    ) u
                    """
                ),
                params,
            )
        ).mappings().first()
        if cny_row and _number(cny_row["total_mv"]):
            out["non_cny_pct"] = _round(
                (1.0 - _number(cny_row["cny_mv"]) / _number(cny_row["total_mv"])) * 100.0, 2
            )

    if bond_date is not None:
        ctrl_rows = (
            await db.execute(
                _sql(
                    """
                    SELECT COALESCE(p.actual_controller_id, g.group_id, b.issuer_group, b.issuer_id, 'UNKNOWN') AS ctrl,
                           SUM(COALESCE(b.market_value_base, b.market_value, 0)) AS mv
                    FROM fsi.balance_bond b
                    LEFT JOIN LATERAL (
                        SELECT actual_controller_id
                        FROM fsi.mktdata_issuer_profile
                        WHERE issuer_id = b.issuer_id AND as_of_date <= b.evaluate_date
                        ORDER BY as_of_date DESC
                        LIMIT 1
                    ) p ON TRUE
                    LEFT JOIN fsi.mktdata_institution_group g ON g.member_id = b.issuer_id
                    WHERE b.port_id = :fund_id AND b.evaluate_date = :bond_date
                    GROUP BY 1
                    """
                ),
                params,
            )
        ).mappings().all()
        ctrl_total = sum(_number(row["mv"]) for row in ctrl_rows)
        if ctrl_total:
            top_ctrl = max(ctrl_rows, key=lambda row: _number(row["mv"]))
            out["controller_conc"] = _round(_number(top_ctrl["mv"]) / ctrl_total * 100.0, 2)
            out["controller_detail"] = str(top_ctrl["ctrl"])

        credit_row = (
            await db.execute(
                _sql(
                    """
                    WITH book AS (
                        SELECT SUM(COALESCE(market_value_base, market_value, 0)) AS total_mv
                        FROM fsi.balance_bond
                        WHERE port_id = :fund_id AND evaluate_date = :bond_date
                    ), by_issuer AS (
                        SELECT issuer_id, SUM(COALESCE(market_value_base, market_value, 0)) AS mv
                        FROM fsi.balance_bond
                        WHERE port_id = :fund_id AND evaluate_date = :bond_date AND issuer_id IS NOT NULL
                        GROUP BY issuer_id
                    )
                    SELECT MAX(i.mv / NULLIF(p.outstanding_credit_bond, 0)) * 100 AS vs_outstanding,
                           MAX(i.mv / NULLIF(p.net_assets, 0)) * 100 AS vs_equity,
                           MAX(i.mv / NULLIF(book.total_mv, 0)) * 100 AS vs_book
                    FROM by_issuer i
                    JOIN LATERAL (
                        SELECT net_assets, outstanding_credit_bond
                        FROM fsi.mktdata_issuer_profile
                        WHERE issuer_id = i.issuer_id AND as_of_date <= :bond_date
                        ORDER BY as_of_date DESC
                        LIMIT 1
                    ) p ON TRUE
                    CROSS JOIN book
                    """
                ),
                params,
            )
        ).mappings().first()
        if credit_row and any(credit_row[k] is not None for k in ("vs_outstanding", "vs_equity", "vs_book")):
            candidates = [
                _number(credit_row["vs_outstanding"]) if credit_row["vs_outstanding"] is not None else None,
                _number(credit_row["vs_equity"]) if credit_row["vs_equity"] is not None else None,
            ]
            present = [v for v in candidates if v is not None]
            out["unified_credit"] = _round(max(present), 3) if present else None
            out["unified_detail"] = (
                f"占存续信用债 { _round(_number(credit_row['vs_outstanding']) if credit_row['vs_outstanding'] is not None else None, 3) }% / "
                f"占净资产 { _round(_number(credit_row['vs_equity']) if credit_row['vs_equity'] is not None else None, 4) }% / "
                f"占组合信用债 { _round(_number(credit_row['vs_book']) if credit_row['vs_book'] is not None else None, 2) }%"
            )

        pd_row = (
            await db.execute(
                _sql(
                    """
                    SELECT SUM(COALESCE(b.market_value_base, b.market_value, 0) * c.implied_pd)
                               / NULLIF(SUM(COALESCE(b.market_value_base, b.market_value, 0))
                                        FILTER (WHERE c.implied_pd IS NOT NULL), 0) AS wpd,
                           SUM(COALESCE(b.market_value_base, b.market_value, 0) * c.credit_spread)
                               / NULLIF(SUM(COALESCE(b.market_value_base, b.market_value, 0))
                                        FILTER (WHERE c.credit_spread IS NOT NULL), 0) AS spread,
                           COUNT(*) FILTER (WHERE h.is_halted OR cv.triggered) AS event_count,
                           SUM(COALESCE(b.market_value_base, b.market_value, 0))
                               FILTER (WHERE h.is_halted OR cv.triggered) AS event_mv
                    FROM fsi.balance_bond b
                    LEFT JOIN LATERAL (
                        SELECT implied_pd, credit_spread
                        FROM fsi.mktdata_fi_credit
                        WHERE security_code = b.security_code AND price_date <= b.evaluate_date
                        ORDER BY price_date DESC
                        LIMIT 1
                    ) c ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT TRUE AS is_halted
                        FROM fsi.mktdata_security_halt
                        WHERE security_code = b.security_code
                          AND asset_class = 'BOND'
                          AND is_halted
                          AND halt_date <= b.evaluate_date
                          AND (resume_date IS NULL OR resume_date > b.evaluate_date)
                        LIMIT 1
                    ) h ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT TRUE AS triggered
                        FROM fsi.mktdata_bond_covenant
                        WHERE security_code = b.security_code
                          AND triggered
                          AND effective_date <= b.evaluate_date
                        LIMIT 1
                    ) cv ON TRUE
                    WHERE b.port_id = :fund_id AND b.evaluate_date = :bond_date
                    """
                ),
                params,
            )
        ).mappings().first()
        if pd_row:
            if pd_row["wpd"] is not None:
                out["implied_pd"] = _round(_number(pd_row["wpd"]) * 100.0, 4)
            if pd_row["spread"] is not None:
                out["credit_spread"] = _round(_number(pd_row["spread"]) * 100.0, 3)
            out["bond_suspend"] = int(pd_row["event_count"] or 0)
            if nav:
                out["bond_suspend_pct"] = _round(_number(pd_row["event_mv"]) / nav * 100.0, 2)

        related = (
            await db.execute(
                _sql(
                    """
                    SELECT COALESCE(SUM(src.mv), 0) AS mv
                    FROM (
                        SELECT COALESCE(b.market_value_base, b.market_value, 0) AS mv
                        FROM fsi.balance_bond b
                        JOIN fsi.para_port_related_party r
                          ON r.port_id = b.port_id AND r.institution_id = b.issuer_id
                         AND r.begin_date <= :end
                         AND (r.end_date IS NULL OR r.end_date >= :end)
                        WHERE b.port_id = :fund_id AND b.evaluate_date = :bond_date
                        UNION ALL
                        SELECT COALESCE(d.total_value_base, d.total_value, d.principal, 0)
                        FROM fsi.balance_deposit d
                        JOIN fsi.para_port_related_party r
                          ON r.port_id = d.port_id AND r.institution_id = d.bank_id
                         AND r.begin_date <= :end
                         AND (r.end_date IS NULL OR r.end_date >= :end)
                        WHERE d.port_id = :fund_id
                          AND d.evaluate_date = COALESCE(:bond_date, :end)
                    ) src
                    """
                ),
                params,
            )
        ).scalar_one()
        if nav:
            out["related_party"] = _round(_number(related) / nav * 100.0, 2)

    news_count = (
        await db.execute(
            _sql(
                """
                SELECT COUNT(*)
                FROM fsi.mktdata_issuer_news n
                WHERE n.severity IN ('NEGATIVE', 'SEVERE')
                  AND n.news_date BETWEEN :start AND :end
                  AND (
                    n.issuer_id IN (
                        SELECT issuer_id FROM fsi.balance_bond
                        WHERE port_id = :fund_id AND evaluate_date = :bond_date AND issuer_id IS NOT NULL
                        UNION
                        SELECT bank_id FROM fsi.balance_deposit
                        WHERE port_id = :fund_id AND evaluate_date = COALESCE(:bond_date, :end) AND bank_id IS NOT NULL
                    )
                    OR n.security_code IN (
                        SELECT security_code FROM fsi.balance_bond
                        WHERE port_id = :fund_id AND evaluate_date = :bond_date
                        UNION
                        SELECT security_code FROM fsi.balance_stock
                        WHERE port_id = :fund_id AND evaluate_date = :stock_date
                    )
                  )
                """
            ),
            params,
        )
    ).scalar_one()
    out["neg_news"] = int(news_count or 0)

    flow = (
        await db.execute(
            _sql(
                """
                SELECT SUM(COALESCE(redemption, 0)) AS redemption,
                       SUM(COALESCE(purchase, 0)) AS purchase,
                       SUM(COALESCE(redemption, 0) - COALESCE(purchase, 0)) AS net_redemption
                FROM fsi.transact_portfolio_cashflow
                WHERE port_id = :fund_id AND evaluate_date BETWEEN :start AND :end
                """
            ),
            params,
        )
    ).mappings().first()
    begin_nav = (
        await db.execute(
            _sql(
                """
                SELECT net_asset
                FROM fsi.balance_portfolio_nav
                WHERE port_id = :fund_id AND evaluate_date BETWEEN :start AND :end
                ORDER BY evaluate_date
                LIMIT 1
                """
            ),
            params,
        )
    ).scalar_one_or_none()
    if flow and flow["net_redemption"] is not None:
        net_red = _number(flow["net_redemption"])
        begin = _number(begin_nav)
        out["net_redemption_amt"] = _round(net_red, 0)
        out["net_redemption"] = _round(net_red / begin * 100.0, 3) if begin else None

    holder = (
        await db.execute(
            _sql(
                """
                WITH latest AS (
                    SELECT MAX(confirm_date) AS confirm_date
                    FROM fsi.balance_holder_rank
                    WHERE port_id = :fund_id AND confirm_date <= :end
                )
                SELECT SUM(r.pct_of_total) FILTER (WHERE r.rank_no <= 5) AS top5,
                       SUM(r.pct_of_total) FILTER (WHERE r.rank_no <= 10) AS top10,
                       SUM(r.pct_of_total) FILTER (WHERE r.rank_no <= 20) AS top20,
                       SUM(r.pct_of_total) FILTER (WHERE s.sponsor_type = 'INSTITUTIONAL') AS inst_pct
                FROM fsi.balance_holder_rank r
                LEFT JOIN fsi.para_sponsor s ON s.sponsor_id = r.sponsor_id
                WHERE r.port_id = :fund_id
                  AND r.confirm_date = (SELECT confirm_date FROM latest)
                """
            ),
            params,
        )
    ).mappings().first()
    if holder and holder["top10"] is not None:
        out["investor_top5"] = _round(_number(holder["top5"]), 2)
        out["investor_top10"] = _round(_number(holder["top10"]), 2)
        out["investor_top20"] = _round(_number(holder["top20"]), 2)
        out["investor_inst"] = _round(_number(holder["inst_pct"]), 2)
        if nav and holder["top5"] is not None and liquid_within_7d:
            redeem_need = nav * _number(holder["top5"]) / 100.0
            out["top5_cover"] = _round(liquid_within_7d / redeem_need, 2) if redeem_need else None

    cpty = (
        await db.execute(
            _sql(
                """
                SELECT MAX(COALESCE(r.principal, 0) / NULLIF(c.credit_limit, 0)) * 100 AS util
                FROM fsi.balance_repo r
                JOIN fsi.para_counterparty c ON c.counterparty_id = r.counterparty_id
                WHERE r.port_id = :fund_id
                  AND r.evaluate_date = COALESCE(:bond_date, :stock_date, :end)
                """
            ),
            params,
        )
    ).scalar_one_or_none()
    if cpty is not None:
        out["counterparty"] = _round(_number(cpty), 2)

    bank = (
        await db.execute(
            _sql(
                """
                SELECT MAX(COALESCE(d.total_value_base, d.total_value, d.principal, 0) / NULLIF(c.credit_limit, 0)) * 100 AS util
                FROM fsi.balance_deposit d
                JOIN fsi.para_counterparty c ON c.counterparty_id = d.bank_id
                WHERE d.port_id = :fund_id
                  AND d.evaluate_date = COALESCE(:bond_date, :stock_date, :end)
                """
            ),
            params,
        )
    ).scalar_one_or_none()
    if bank is not None:
        out["bank_limit"] = _round(_number(bank), 2)

    breaches = (
        await db.execute(
            _sql(
                """
                SELECT COUNT(*)
                FROM fsi.para_risk_limit_regulatory lim
                WHERE lim.port_id = :fund_id
                  AND lim.is_active
                  AND lim.effective_date <= :end
                  AND (lim.expiry_date IS NULL OR lim.expiry_date >= :end)
                  AND lim.rule_code = 'MMF_SINGLE_ISSUER'
                  AND lim.limit_value < COALESCE((
                        SELECT MAX(weight_pct)
                        FROM fsi.balance_bond
                        WHERE port_id = :fund_id AND evaluate_date = :bond_date
                  ), 0)
                """
            ),
            params,
        )
    ).scalar_one()
    out["scope_breach"] = int(breaches or 0)

    ops = (
        await db.execute(
            _sql(
                """
                SELECT COUNT(*)
                FROM fsi.svc_wf_review_request
                WHERE port_id = :fund_id
                  AND status::text IN ('PENDING', 'IN_REVIEW', 'REJECTED')
                """
            ),
            params,
        )
    ).scalar_one()
    out["ops_anomaly"] = int(ops or 0)
    return out


def _ams_breached(value: float | None, limit: float, op: str) -> bool | None:
    if value is None:
        return None
    if op == "<=":
        return value > limit
    if op == "<":
        return value >= limit
    if op == ">=":
        return value < limit
    if op == ">":
        return value <= limit
    return None


def _ams_limit_metric(
    metric_id: str,
    name: str,
    value: float | int | None,
    *,
    limit: float | None,
    op: str,
    unit: str,
    ams_code: str,
    hard: bool = True,
    scheme: str = "BAMUSDMMF风控001",
    extra: str | None = None,
) -> dict[str, Any]:
    """AMS / Wind 合规限额行：数值 + 限额对照 + 合规/超限/待数据。"""
    hard_label = "硬指标" if hard else "内部从严"
    limit_txt = f"{op}{limit}{unit}" if limit is not None else "—"
    note = f"AMS {ams_code} · {scheme} · {hard_label} · 限额 {limit_txt}"
    if extra:
        note = f"{note} · {extra}"
    if value is None or limit is None:
        return _metric(metric_id, name, value=value, unit=unit, status="unavailable", note=note, detail="待数据")
    breached = _ams_breached(float(value), float(limit), op)
    detail = "超限" if breached else "合规"
    return _metric(
        metric_id,
        name,
        value=_round(float(value), 2) if isinstance(value, float) or (isinstance(value, int) and unit != "条") else value,
        unit=unit,
        status="derived",
        note=note,
        detail=detail,
    )


def _pct_of_nav(mv: float, nav: float) -> float | None:
    if not nav:
        return None
    return _round(mv / nav * 100.0, 2)


def _build_ams_compliance_metrics(
    *,
    exposure: ExposureResult | None,
    assets: dict[str, Any],
    bond_ext: dict[str, Any],
    rates: dict[str, Any],
    ext: dict[str, Any],
    nav: float,
    base_currency: str,
) -> list[dict[str, Any]]:
    """对齐 Wind AMS《合规风控指标及AMS配置》Sheet1（BAMUSDMMF风控001/002）。"""
    by_class: dict[str, float] = assets.get("by_class") or {}
    exp_nav = float(exposure.total_nav_hkd) if exposure and exposure.total_nav_hkd else nav

    max_issuer_pct = None
    max_group_pct = None
    non_base_fx_pct = None
    china_pct = None
    if exposure and exp_nav > 0:
        if exposure.by_issuer:
            max_issuer_pct = max(v / exp_nav * 100.0 for v in exposure.by_issuer.values())
        if exposure.by_group:
            max_group_pct = max(v / exp_nav * 100.0 for v in exposure.by_group.values())
        base = (base_currency or "HKD").upper()
        if exposure.by_currency:
            non_base = sum(v for ccy, v in exposure.by_currency.items() if str(ccy).upper() != base)
            non_base_fx_pct = non_base / exp_nav * 100.0
        if exposure.by_country:
            china_keys = {"CN", "CHN", "CHINA", "CNY", "中国", "内地", "Mainland China"}
            china_mv = sum(
                v for cty, v in exposure.by_country.items() if str(cty).upper() in {k.upper() for k in china_keys}
                or "中国" in str(cty) or "内地" in str(cty)
            )
            china_pct = china_mv / exp_nav * 100.0

    debt_pct = _pct_of_nav(
        sum(by_class.get(k, 0.0) for k in (_CREDIT_BOND | _RATE_BOND | {"BOND", "CP"})),
        nav,
    )
    mm_quality_pct = _pct_of_nav(
        sum(by_class.get(k, 0.0) for k in {"CASH", "DEPOSIT", "CD", "BOND_GOVT", "CP", "REV_REPO"}),
        nav,
    )
    abs_pct = _pct_of_nav(by_class.get("BOND_ABS", 0.0) + by_class.get("ABCP", 0.0) + by_class.get("MBS", 0.0), nav)
    other_mmf_pct = _pct_of_nav(
        sum(v for k, v in by_class.items() if "MMF" in str(k).upper() or k in {"FUND_MMF", "FUND_MONEY"}),
        nav,
    )
    repo_pct = assets.get("repo_liability_pct_nav")
    rev_repo_pct = _pct_of_nav(by_class.get("REV_REPO", 0.0), nav)

    issuer_below = rates.get("issuer_below_investment_grade_pct")
    debt_below = rates.get("debt_below_investment_grade_pct")
    below_ig = None
    if issuer_below is not None or debt_below is not None:
        below_ig = max(float(issuer_below or 0), float(debt_below or 0))
    unrated_pct = bond_ext.get("unrated_pct")

    wam = float(exposure.wam_days) if exposure else None
    wal = float(exposure.wal_days) if exposure else None
    dla = float(exposure.daily_liquid_pct) if exposure else None
    wla = float(exposure.weekly_liquid_pct) if exposure else None
    max_days = bond_ext.get("max_remaining_days")

    metrics: list[dict[str, Any]] = [
        # —— AMS 001 硬性：期限与流动性 ——
        _ams_limit_metric("ams_wam", "WAM 加权平均届满期", wam, limit=60, op="<=", unit="天", ams_code="2.2", hard=True),
        _ams_limit_metric("ams_wal", "WAL 加权平均有效期／寿命", wal, limit=120, op="<=", unit="天", ams_code="2.4", hard=True),
        _ams_limit_metric("ams_dla", "DLA 每日流动资产", dla, limit=7.5, op=">=", unit="%", ams_code="2.5", hard=True),
        _ams_limit_metric("ams_wla", "WLA 每周流动资产", wla, limit=15.0, op=">=", unit="%", ams_code="2.6", hard=True),
        _ams_limit_metric(
            "ams_max_maturity",
            "单券剩余期限",
            float(max_days) if max_days is not None else None,
            limit=397,
            op="<=",
            unit="天",
            ams_code="2.7",
            hard=True,
        ),
        _ams_limit_metric(
            "ams_gov_maturity",
            "政府及其他公共证券剩余期限",
            None,
            limit=730,
            op="<=",
            unit="天",
            ams_code="2.8",
            hard=True,
            extra="单券层级；待政府/公共券标识",
        ),
        # —— AMS 001 硬性：集中度 ——
        _ams_limit_metric(
            "ams_single_issuer",
            "单一主体：工具 + 存款",
            _round(max_issuer_pct, 2) if max_issuer_pct is not None else None,
            limit=10.0,
            op="<=",
            unit="%",
            ams_code="2.3",
            hard=True,
            extra="同一集团20%暂未单独拆分",
        ),
        _ams_limit_metric(
            "ams_issuer_group",
            "同一集团集中度",
            _round(max_group_pct, 2) if max_group_pct is not None else None,
            limit=20.0,
            op="<=",
            unit="%",
            ams_code="2.3",
            hard=True,
            extra="SFC 集团口径对照",
        ),
        _ams_limit_metric(
            "ams_gov_issuer",
            "政府及其他公共证券同一发行",
            None,
            limit=30.0,
            op="<=",
            unit="%",
            ams_code="2.9",
            hard=True,
            extra="待政府券穿透标识",
        ),
        _ams_limit_metric(
            "ams_sfi_issuer",
            "具规模财务机构主体上限（可升至25%）",
            _round(max_issuer_pct, 2) if max_issuer_pct is not None else None,
            limit=25.0,
            op="<=",
            unit="%",
            ams_code="2.10",
            hard=True,
            extra="SFI认定暂用大型企业；对照股本+不可分派资本≤10%",
        ),
        # —— AMS 001 硬性：评级与禁投 ——
        _ams_limit_metric(
            "ams_below_ig",
            "低于投资级／未获评级占比",
            _round(max(float(below_ig or 0), float(unrated_pct or 0)), 2)
            if below_ig is not None or unrated_pct is not None
            else None,
            limit=0.0,
            op="<=",
            unit="%",
            ams_code="2.11",
            hard=True,
            extra="禁止未评；工具A-1+或发行人AA+",
        ),
        _metric(
            "ams_eligible_pool",
            "可投资产类别（短存+优质货币工具池）",
            value=None,
            unit="",
            status="unavailable",
            note="AMS 2.17 · BAMUSDMMF风控001 · 硬指标 · 证券池",
            detail="待证券池映射",
        ),
        _metric(
            "ams_st_rating_floor",
            "短期国际评级底线（S&P A-3 / Fitch F3 / Moody's P-3）",
            value=None,
            unit="",
            status="unavailable",
            note="AMS · 人工核对 · 硬指标",
            detail="待短期评级字段",
        ),
        # —— AMS 001 硬性：资产配置 ——
        _ams_limit_metric(
            "ams_mm_quality",
            "投资（短期存款+优质货币工具）",
            mm_quality_pct,
            limit=70.0,
            op=">=",
            unit="%",
            ams_code="2.12",
            hard=True,
            extra="建仓期可暂缓",
        ),
        _ams_limit_metric("ams_debt_pct", "债务证券（固息／浮息等）", debt_pct, limit=30.0, op="<", unit="%", ams_code="2.18", hard=True),
        _ams_limit_metric(
            "ams_fx_pct",
            "非主币种",
            _round(non_base_fx_pct, 2) if non_base_fx_pct is not None else None,
            limit=30.0,
            op="<=",
            unit="%",
            ams_code="2.19",
            hard=True,
            extra=f"主币种 {base_currency or '—'}",
        ),
        _ams_limit_metric(
            "ams_em_pct",
            "新兴市场（不含内地）",
            None,
            limit=30.0,
            op="<",
            unit="%",
            ams_code="2.20",
            hard=True,
            extra="待新兴市场国家清单",
        ),
        _ams_limit_metric(
            "ams_china_onshore",
            "内地在岸固收／债（直／间接）",
            _round(china_pct, 2) if china_pct is not None else None,
            limit=20.0,
            op="<=",
            unit="%",
            ams_code="2.21",
            hard=True,
        ),
        _ams_limit_metric(
            "ams_dimsum_lgfv",
            "点心债及／或城投债",
            None,
            limit=10.0,
            op="<",
            unit="%",
            ams_code="2.22+2.23",
            hard=True,
            extra="需彭博二次核验；合并口径",
        ),
        _ams_limit_metric("ams_abs", "ABS／MBS／ABCP", abs_pct, limit=10.0, op="<=", unit="%", ams_code="2.24", hard=True),
        _ams_limit_metric(
            "ams_other_mmf",
            "其他货基（SFC 8.2 或同等可接受）",
            other_mmf_pct,
            limit=10.0,
            op="<=",
            unit="%",
            ams_code="2.25",
            hard=True,
            extra="证券池",
        ),
        _ams_limit_metric(
            "ams_repo",
            "出售与回购（repo）所得现金合计",
            repo_pct,
            limit=10.0,
            op="<=",
            unit="%",
            ams_code="2.26",
            hard=True,
        ),
        _ams_limit_metric(
            "ams_rev_repo_cpty",
            "逆回购：向同一对手提供现金",
            rev_repo_pct if rev_repo_pct is not None else None,
            limit=15.0,
            op="<=",
            unit="%",
            ams_code="2.27",
            hard=True,
            extra="暂用逆回购合计占比近似；待对手拆分",
        ),
        _ams_limit_metric(
            "ams_fdi",
            "FDI 衍生工具风险承担净额",
            None,
            limit=50.0,
            op="<=",
            unit="%",
            ams_code="2.28",
            hard=True,
            extra="应为风险敞口，暂用合约面值近似",
        ),
        _ams_limit_metric(
            "ams_borrow",
            "借款（仅临时赎回／营运）",
            None,
            limit=10.0,
            op="<=",
            unit="%",
            ams_code="2.25+",
            hard=True,
            extra="另含禁止证券借出、长期评级底线、非OECD对手≤5%",
        ),
        # —— AMS 002 内部从严 ——
        _ams_limit_metric(
            "ams_wam_soft",
            "WAM（内部从严）",
            wam,
            limit=50,
            op="<=",
            unit="天",
            ams_code="3.29",
            hard=False,
            scheme="BAMUSDMMF风控002",
        ),
        _ams_limit_metric(
            "ams_wal_soft",
            "WAL（内部从严）",
            wal,
            limit=100,
            op="<=",
            unit="天",
            ams_code="3.30",
            hard=False,
            scheme="BAMUSDMMF风控002",
        ),
        _ams_limit_metric(
            "ams_dla_soft",
            "DLA（内部从严）",
            dla,
            limit=10.0,
            op=">=",
            unit="%",
            ams_code="3.31",
            hard=False,
            scheme="BAMUSDMMF风控002",
        ),
        _ams_limit_metric(
            "ams_wla_soft",
            "WLA（内部从严）",
            wla,
            limit=20.0,
            op=">=",
            unit="%",
            ams_code="3.32",
            hard=False,
            scheme="BAMUSDMMF风控002",
        ),
        _ams_limit_metric(
            "ams_issuer_soft",
            "单一主体：工具 + 存款（内部从严）",
            _round(max_issuer_pct, 2) if max_issuer_pct is not None else None,
            limit=9.0,
            op="<=",
            unit="%",
            ams_code="3.34",
            hard=False,
            scheme="BAMUSDMMF风控002",
        ),
        # —— 对手与运营 ——
        _ams_limit_metric(
            "ams_bank_quota",
            "存款行额度使用率",
            ext.get("bank_limit"),
            limit=100.0,
            op="<=",
            unit="%",
            ams_code="额度",
            hard=True,
            scheme="额度管理-额度设置",
            extra="交易对手／存款行",
        ),
        _metric(
            "related_party",
            "关联交易持仓占比",
            value=ext.get("related_party"),
            unit="%",
            status="computed" if ext.get("related_party") is not None else "unavailable",
            note="para_port_related_party",
        ),
        _metric(
            "counterparty",
            "交易对手限额使用率",
            value=ext.get("counterparty"),
            unit="%",
            status="computed" if ext.get("counterparty") is not None else "unavailable",
            note="回购本金 / 授信额度",
        ),
        _metric(
            "scope_breach",
            "监管红线触发数",
            value=ext.get("scope_breach"),
            unit="条",
            status="computed",
            note="单一发行人超监管上限",
        ),
        _metric(
            "ops_anomaly",
            "流程异常节点数",
            value=ext.get("ops_anomaly"),
            unit="个",
            status="computed",
            note="待处理审核请求",
        ),
        _metric(
            "ams_breach_count",
            "AMS硬性限额超限条数",
            value=None,
            unit="条",
            status="derived",
            note="按本页硬指标 detail=超限 汇总",
        ),
    ]

    # 回填硬性超限条数
    hard_breach = sum(
        1
        for m in metrics
        if m.get("detail") == "超限" and m.get("note") and "硬指标" in str(m.get("note"))
    )
    for m in metrics:
        if m["id"] == "ams_breach_count":
            m["value"] = hard_breach
            m["detail"] = "有超限" if hard_breach else "全部合规"
            break
    return metrics


_METRIC_GROUPS: dict[str, dict[str, str]] = {
    "market": {
        "nav_unit": "组合风险",
        "interval_return": "组合风险",
        "day_return": "组合风险",
        "benchmark_return": "组合风险",
        "active_return": "组合风险",
        "security_pnl": "组合风险",
        "annualized_vol": "组合风险",
        "max_drawdown": "组合风险",
        "sharpe": "组合风险",
        "info_ratio": "组合风险",
        "tracking_error": "组合风险",
        "equity_beta": "权益与风格",
        "turnover": "权益与风格",
        "style_momentum": "权益与风格",
        "style_size": "权益与风格",
        "style_deviation": "权益与风格",
        "avg_pe": "权益与风格",
        "avg_pb": "权益与风格",
        "duration": "利率与利差",
        "modified_duration": "利率与利差",
        "convexity": "利率与利差",
        "dv01": "利率与利差",
        "avg_remaining": "利率与利差",
        "credit_spread": "利率与利差",
        "country_conc": "汇率与国家",
        "fx_exposure": "汇率与国家",
        "non_cny_pct": "汇率与国家",
    },
    "credit": {
        "issuer_rating_dist": "评级与个券",
        "debt_rating_dist": "评级与个券",
        "issuer_ig_pct": "评级与个券",
        "issuer_below_ig_pct": "评级与个券",
        "debt_ig_pct": "评级与个券",
        "debt_below_ig_pct": "评级与个券",
        "low_rating_pct": "评级与个券",
        "bond_top5": "评级与个券",
        "bond_top10": "评级与个券",
        "bond_suspend": "评级与个券",
        "issuer_hhi": "发行人与实控人",
        "top_issuer_pct": "发行人与实控人",
        "controller_conc": "发行人与实控人",
        "unified_credit": "发行人与实控人",
        "cs01": "利差与舆情",
        "neg_news": "利差与舆情",
        "implied_pd": "利差与舆情",
    },
    "liquidity": {
        "ttl_10": "变现天数",
        "ttl_25": "变现天数",
        "ttl_50": "变现天数",
        "avg_ttl": "变现天数",
        "stock_ttl": "变现天数",
        "bond_ttl": "变现天数",
        "over_10d": "变现天数",
        "over_40d": "变现天数",
        "cash_pct": "流动性资产",
        "cash_only": "流动性资产",
        "lcr_15": "流动性资产",
        "rate_bond_pct": "流动性资产",
        "restricted_pct": "流动性资产",
        "net_redemption": "申赎与投资者",
        "investor_conc": "申赎与投资者",
    },
    "concentration": {
        "equity_top5": "股票集中度",
        "equity_top10": "股票集中度",
        "equity_largest": "股票集中度",
        "equity_hhi": "股票集中度",
        "equity_float": "股票集中度",
        "sector_hhi": "股票集中度",
        "bond_conc_top10": "债券与发行人",
        "issuer_top": "债券与发行人",
        "leverage": "杠杆与区域",
        "repo_pct": "杠杆与区域",
        "country_qdii": "杠杆与区域",
        "controller_eq": "杠杆与区域",
    },
    "compliance": {
        # Wind AMS 风控合规限额（001/002）合并同一表；对手与运营单独成表
        "ams_wam": "风控合规限额",
        "ams_wal": "风控合规限额",
        "ams_dla": "风控合规限额",
        "ams_wla": "风控合规限额",
        "ams_max_maturity": "风控合规限额",
        "ams_gov_maturity": "风控合规限额",
        "ams_single_issuer": "风控合规限额",
        "ams_issuer_group": "风控合规限额",
        "ams_gov_issuer": "风控合规限额",
        "ams_sfi_issuer": "风控合规限额",
        "ams_below_ig": "风控合规限额",
        "ams_eligible_pool": "风控合规限额",
        "ams_st_rating_floor": "风控合规限额",
        "ams_mm_quality": "风控合规限额",
        "ams_debt_pct": "风控合规限额",
        "ams_fx_pct": "风控合规限额",
        "ams_em_pct": "风控合规限额",
        "ams_china_onshore": "风控合规限额",
        "ams_dimsum_lgfv": "风控合规限额",
        "ams_abs": "风控合规限额",
        "ams_other_mmf": "风控合规限额",
        "ams_repo": "风控合规限额",
        "ams_rev_repo_cpty": "风控合规限额",
        "ams_fdi": "风控合规限额",
        "ams_borrow": "风控合规限额",
        "ams_wam_soft": "风控合规限额",
        "ams_wal_soft": "风控合规限额",
        "ams_dla_soft": "风控合规限额",
        "ams_wla_soft": "风控合规限额",
        "ams_issuer_soft": "风控合规限额",
        "ams_breach_count": "风控合规限额",
        "ams_bank_quota": "对手与运营",
        "related_party": "对手与运营",
        "counterparty": "对手与运营",
        "scope_breach": "对手与运营",
        "ops_anomaly": "对手与运营",
    },
    "stress": {
        "rate_shock_50": "利率冲击",
        "rate_shock_50_pct": "利率冲击",
        "redemption_15_lcr": "赎回压力",
        "redemption_20_lcr": "赎回压力",
        "top5_investor_redeem": "赎回压力",
        "market_crash_nav": "市场与信用冲击",
        "market_crash_ttl": "市场与信用冲击",
        "credit_default_3": "市场与信用冲击",
    },
}


def _stamp_groups(categories: list[dict[str, Any]]) -> None:
    for category in categories:
        mapping = _METRIC_GROUPS.get(str(category.get("id")), {})
        for metric in category.get("metrics") or []:
            metric["group"] = mapping.get(str(metric.get("id")), "其他")


def _split_metric_value(value: Any) -> tuple[float | None, str | None]:
    if isinstance(value, bool) or value is None:
        return None, None
    if isinstance(value, (int, float)):
        return float(value), None
    return None, str(value)


async def _fund_latest_nav(db: AsyncSession, fund_id: str) -> date | None:
    result = await db.execute(
        text(
            """
            SELECT MAX(evaluate_date)
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id
            """
        ),
        {"fund_id": fund_id},
    )
    return result.scalar_one_or_none()


def _board_from_rows(
    fund_id: str,
    period_start: date,
    period_end: date,
    header: dict[str, Any],
    rows: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    categories: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        category_id = str(row["category_id"])
        category = by_id.get(category_id)
        if category is None:
            category = {
                "id": category_id,
                "name": row["category_name"],
                "name_en": row.get("category_name_en"),
                "metrics": [],
            }
            by_id[category_id] = category
            categories.append(category)
        number, text_value = row.get("metric_value"), row.get("value_text")
        category["metrics"].append(
            {
                "id": row["metric_id"],
                "name": row["metric_name"],
                "group": row.get("group_name") or "其他",
                "value": float(number) if number is not None else text_value,
                "unit": row.get("unit"),
                "status": row.get("status") or "computed",
                "note": row.get("note"),
                "detail": row.get("detail"),
            }
        )
    computed = sum(1 for c in categories for m in c["metrics"] if m["status"] == "computed")
    derived = sum(1 for c in categories for m in c["metrics"] if m["status"] == "derived")
    unavailable = sum(1 for c in categories for m in c["metrics"] if m["status"] == "unavailable")
    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "resolved_period_start": header.get("resolved_period_start"),
        "resolved_period_end": header.get("resolved_period_end"),
        "data_as_of": header.get("data_as_of"),
        "benchmark_id": header.get("benchmark_id"),
        "source": source,
        "summary": {
            "computed": computed,
            "derived": derived,
            "unavailable": unavailable,
            "total": computed + derived + unavailable,
        },
        "categories": categories,
        "message": header.get("message"),
    }


async def _load_metric_report(
    db: AsyncSession,
    fund_id: str,
    period_start: date,
    period_end: date,
) -> dict[str, Any] | None:
    header = (
        await db.execute(
            text(
                """
                SELECT resolved_period_start, resolved_period_end, data_as_of,
                       benchmark_id, message
                FROM fsi.svc_risk_metric_report
                WHERE port_id = :fund_id
                  AND period_start = :period_start
                  AND period_end = :period_end
                """
            ),
            {"fund_id": fund_id, "period_start": period_start, "period_end": period_end},
        )
    ).mappings().first()
    if header is None:
        return None
    rows = (
        await db.execute(
            text(
                """
                SELECT category_id, category_name, category_name_en, group_name,
                       metric_id, metric_name, metric_value, value_text,
                       unit, status, note, detail
                FROM fsi.svc_risk_metric
                WHERE port_id = :fund_id
                  AND period_start = :period_start
                  AND period_end = :period_end
                ORDER BY sort_no
                """
            ),
            {"fund_id": fund_id, "period_start": period_start, "period_end": period_end},
        )
    ).mappings().all()
    if not rows:
        return None
    payload = _board_from_rows(fund_id, period_start, period_end, dict(header), [dict(row) for row in rows], "report")
    _stamp_groups(payload["categories"])
    return payload


async def _save_metric_report(db: AsyncSession, payload: dict[str, Any]) -> None:
    await db.execute(
        text(
            """
            INSERT INTO fsi.svc_risk_metric_report (
                port_id, period_start, period_end,
                resolved_period_start, resolved_period_end, data_as_of,
                benchmark_id, message
            ) VALUES (
                :fund_id, :period_start, :period_end,
                :resolved_start, :resolved_end, :data_as_of,
                :benchmark_id, :message
            )
            ON CONFLICT (port_id, period_start, period_end) DO UPDATE
                SET resolved_period_start = EXCLUDED.resolved_period_start,
                    resolved_period_end = EXCLUDED.resolved_period_end,
                    data_as_of = EXCLUDED.data_as_of,
                    benchmark_id = EXCLUDED.benchmark_id,
                    message = EXCLUDED.message,
                    calc_ts = NOW()
            """
        ),
        {
            "fund_id": payload["fund_id"],
            "period_start": payload["period_start"],
            "period_end": payload["period_end"],
            "resolved_start": payload.get("resolved_period_start"),
            "resolved_end": payload.get("resolved_period_end"),
            "data_as_of": payload.get("data_as_of"),
            "benchmark_id": payload.get("benchmark_id"),
            "message": payload.get("message"),
        },
    )
    await db.execute(
        text(
            """
            DELETE FROM fsi.svc_risk_metric
            WHERE port_id = :fund_id
              AND period_start = :period_start
              AND period_end = :period_end
            """
        ),
        {
            "fund_id": payload["fund_id"],
            "period_start": payload["period_start"],
            "period_end": payload["period_end"],
        },
    )
    sort_no = 0
    for category in payload.get("categories") or []:
        for metric in category.get("metrics") or []:
            number, text_value = _split_metric_value(metric.get("value"))
            await db.execute(
                text(
                    """
                    INSERT INTO fsi.svc_risk_metric (
                        port_id, period_start, period_end,
                        category_id, category_name, category_name_en,
                        group_name, metric_id, metric_name,
                        metric_value, value_text, unit, status, note, detail, sort_no
                    ) VALUES (
                        :fund_id, :period_start, :period_end,
                        :category_id, :category_name, :category_name_en,
                        :group_name, :metric_id, :metric_name,
                        :metric_value, :value_text, :unit, :status, :note, :detail, :sort_no
                    )
                    """
                ),
                {
                    "fund_id": payload["fund_id"],
                    "period_start": payload["period_start"],
                    "period_end": payload["period_end"],
                    "category_id": category["id"],
                    "category_name": category["name"],
                    "category_name_en": category.get("name_en"),
                    "group_name": metric.get("group") or "其他",
                    "metric_id": metric["id"],
                    "metric_name": metric["name"],
                    "metric_value": number,
                    "value_text": text_value,
                    "unit": metric.get("unit"),
                    "status": metric.get("status"),
                    "note": metric.get("note"),
                    "detail": metric.get("detail"),
                    "sort_no": sort_no,
                },
            )
            sort_no += 1
    await db.commit()


async def compute_risk_metric_board(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> dict[str, Any]:
    """Build six-category risk metric board for the indicators page."""
    resolved = await _resolve_nav_period(db, fund_id, period_start, period_end)
    effective_start = period_start
    effective_end = period_end
    latest_nav_date = period_end
    if resolved:
        effective_start, effective_end, latest_nav_date = resolved

    fund_latest = await _fund_latest_nav(db, fund_id)
    is_current = fund_latest is None or period_end >= fund_latest
    if not is_current:
        cached = await _load_metric_report(db, fund_id, period_start, period_end)
        if cached is not None:
            return cached

    risk = await compute_risk_indicators(fund_id, period_start, period_end, db)
    overview = await compute_portfolio_overview(fund_id, effective_end, db)
    attribution = await compute_performance_attribution(fund_id, period_start, period_end, db)
    factor = await compute_factor_behavior_risk(fund_id, period_start, period_end, db)

    bond_date = await _latest_balance_date(db, "balance_bond", fund_id, effective_end)
    asset_date = await _latest_balance_date(db, "balance_portfolio_asset", fund_id, effective_end)
    stock_date = await _latest_balance_date(db, "balance_stock", fund_id, effective_end)
    rates_asof = bond_date or effective_end
    liq_asof = asset_date or effective_end

    rates = await compute_rates_credit_sensitivity(fund_id, rates_asof, db)
    liq = await compute_liquidity_stress_testing(
        fund_id, liq_asof, redemption_pct=15.0, rate_shock_bps=50.0, db=db
    )
    liq_extreme = await compute_liquidity_stress_testing(
        fund_id, liq_asof, redemption_pct=20.0, rate_shock_bps=50.0, db=db
    )

    nav = _number(overview.get("portfolio", {}).get("net_asset") or rates.get("net_asset") or liq.get("net_asset"))
    bond_ext = await _bond_extensions(db, fund_id, rates_asof) if bond_date else {
        "weighted_convexity": None,
        "avg_remaining_years": None,
        "max_remaining_days": None,
        "modified_duration": None,
        "credit_spread_proxy_pct": None,
        "low_rating_pct": None,
        "unrated_pct": None,
        "top5_bond_pct": None,
        "top10_bond_pct": None,
        "top_issuer_pct": None,
    }

    exposure: ExposureResult | None = None
    try:
        exposure = await compute_exposure(fund_id, liq_asof, db)
    except Exception:
        exposure = None
    assets = await _asset_structure(db, fund_id, asset_date or effective_end, nav) if asset_date else {
        "total_assets": 0.0,
        "cash_pct_nav": None,
        "high_liquidity_pct_nav": None,
        "rate_bond_pct_nav": None,
        "credit_bond_pct_nav": None,
        "leverage_ratio": None,
        "repo_liability_pct_nav": None,
        "by_class": {},
    }
    equity_conc = await _equity_concentration(db, fund_id, stock_date)
    pnl_sum = await _security_pnl_summary(attribution)
    ttl_buckets = _liquidity_bucket_pcts(liq.get("liquidity_ladder") or [], nav)

    fund_rets, bench_rets, bench_id = await _active_return_series(
        db, fund_id, effective_start, effective_end
    )
    bench_note = f"基准 {bench_id}" if bench_id else None
    sharpe = None
    info_ratio = None
    tracking_error = None
    if len(fund_rets) >= 2:
        vol = statistics.stdev(fund_rets)
        mean_r = statistics.mean(fund_rets)
        if vol > 0:
            sharpe = (mean_r / vol) * math.sqrt(252)
    if len(fund_rets) >= 2 and len(bench_rets) >= 2 and len(fund_rets) == len(bench_rets):
        active = [f - b for f, b in zip(fund_rets, bench_rets)]
        if len(active) >= 2:
            te = statistics.stdev(active) * math.sqrt(252)
            tracking_error = te * 100.0
            if te > 0:
                info_ratio = (statistics.mean(active) / statistics.stdev(active)) * math.sqrt(252)

    day_return = overview.get("portfolio", {}).get("day_return")
    day_return_pct = _number(day_return) * 100.0 if day_return is not None else None

    issuer_rating_dist = rates.get("issuer_rating_distribution") or []
    debt_rating_dist = rates.get("debt_rating_distribution") or []
    sector_hhi = (factor.get("sector_concentration") or {}).get("hhi")
    style = factor.get("style_exposure") or {}

    # Stress: rate +50bp already in liq; credit default 3% loss on credit bonds
    credit_mv = sum(assets["by_class"].get(k, 0.0) for k in _CREDIT_BOND)
    default_loss = credit_mv * 0.03
    default_nav_impact = _round(default_loss / nav * 100.0, 3) if nav else None
    rate_loss = _number((liq.get("stress_summary") or {}).get("stressed_bond_loss"))
    rate_impact_pct = _round(rate_loss / nav * 100.0, 3) if nav and rate_loss else None
    beta_value = (risk.get("equity_beta") or {}).get("value")
    market_crash_proxy = _round(beta_value * (-20.0), 2) if beta_value is not None else None

    ext = await _extension_metrics(
        db,
        fund_id,
        effective_start,
        effective_end,
        bond_date,
        stock_date,
        nav,
        str(overview.get("portfolio", {}).get("base_currency") or "HKD"),
        _number((liq.get("stress_summary") or {}).get("liquid_within_7d")),
    )

    base_currency = str(overview.get("portfolio", {}).get("base_currency") or "HKD")

    categories = [
        {
            "id": "market",
            "name": "市场风险",
            "name_en": "Market Risk",
            "metrics": [
                _metric("nav_unit", "单位净值", value=_round(_number(overview.get("portfolio", {}).get("unit_nav")), 4), unit="", status="derived", note="组合概况"),
                _metric("interval_return", "区间收益率", value=_round(risk.get("interval_return_pct"), 3), unit="%", status="derived", note="核心风险指标"),
                _metric("day_return", "涨跌幅（日）", value=_round(day_return_pct, 3), unit="%", status="computed"),
                _metric("benchmark_return", "基准收益率", value=_round((attribution.get("summary") or {}).get("benchmark_return_pct"), 3), unit="%", status="derived", note="业绩归因"),
                _metric("active_return", "超额收益率", value=_round((attribution.get("summary") or {}).get("active_return_pct"), 3), unit="%", status="derived", note="业绩归因"),
                _metric("annualized_vol", "年化波动率", value=_round(risk.get("annualized_volatility_pct"), 3), unit="%", status="derived", note="核心风险指标"),
                _metric("max_drawdown", "最大回撤", value=_round(risk.get("max_drawdown_pct"), 3), unit="%", status="derived", note="核心风险指标"),
                _metric("security_pnl", "个券期间盈亏（样本合计）", value=pnl_sum["sample_security_pnl"], unit="", status="derived", note="业绩归因 top winners/losers"),
                _metric("equity_beta", "组合 Beta", value=_round((risk.get("equity_beta") or {}).get("value"), 3), unit="", status="derived", note="核心风险指标 / 业绩归因明细"),
                _metric("sharpe", "夏普比率", value=_round(sharpe, 3), unit="", status="computed"),
                _metric("info_ratio", "信息比率", value=_round(info_ratio, 3), unit="", status="computed" if info_ratio is not None else "unavailable", note=bench_note),
                _metric("tracking_error", "跟踪误差（年化）", value=_round(tracking_error, 3), unit="%", status="computed" if tracking_error is not None else "unavailable", note=bench_note),
                _metric("duration", "组合久期", value=_round(rates.get("weighted_duration_years"), 3), unit="年", status="derived", note="利率信用"),
                _metric("modified_duration", "修正久期（代理）", value=bond_ext["modified_duration"], unit="年", status="computed" if bond_date else "unavailable"),
                _metric("convexity", "凸性", value=bond_ext["weighted_convexity"], unit="", status="computed" if bond_date else "unavailable"),
                _metric("dv01", "DV01", value=_round(rates.get("portfolio_dv01"), 0), unit="", status="derived", note="利率信用"),
                _metric("avg_remaining", "平均剩余期限", value=bond_ext["avg_remaining_years"], unit="年", status="computed" if bond_date else "unavailable"),
                _metric(
                    "credit_spread",
                    "信用利差",
                    value=ext.get("credit_spread") if ext.get("credit_spread") is not None else bond_ext["credit_spread_proxy_pct"],
                    unit="%",
                    status="computed" if (ext.get("credit_spread") is not None or bond_date) else "unavailable",
                    note="mktdata_fi_credit" if ext.get("credit_spread") is not None else "加权YTM−2%",
                ),
                _metric("turnover", "股票年化换手率", value=_round((risk.get("equity_turnover") or {}).get("annualized_turnover_pct"), 2), unit="%", status="derived", note="核心风险指标"),
                _metric("style_momentum", "风格暴露·动量", value=_round(style.get("momentum_exposure"), 3), unit="", status="derived", note="因子行为"),
                _metric("style_size", "风格暴露·规模", value=_round(style.get("size_exposure"), 3), unit="", status="derived", note="因子行为"),
                _metric(
                    "style_deviation",
                    "投资风格偏离（成长−价值）",
                    value=ext.get("style_deviation"),
                    unit="pct",
                    status="computed" if ext.get("style_deviation") is not None else "unavailable",
                    detail=ext.get("style_detail"),
                    note="mktdata_equity_style",
                ),
                _metric("avg_pe", "平均市盈率 PE", value=ext.get("avg_pe"), unit="", status="computed" if ext.get("avg_pe") is not None else "unavailable", note="mktdata_quotes"),
                _metric("avg_pb", "平均市净率 PB", value=ext.get("avg_pb"), unit="", status="computed" if ext.get("avg_pb") is not None else "unavailable", note="mktdata_quotes"),
                _metric("country_conc", "国家/地区集中度", value=ext.get("country_conc"), unit="%", status="computed" if ext.get("country_conc") is not None else "unavailable", detail=ext.get("country_detail")),
                _metric("fx_exposure", "汇率风险敞口占比", value=ext.get("fx_exposure"), unit="%", status="computed" if ext.get("fx_exposure") is not None else "unavailable", note="非本位币资产"),
                _metric("non_cny_pct", "境外非人民币资产占比", value=ext.get("non_cny_pct"), unit="%", status="computed" if ext.get("non_cny_pct") is not None else "unavailable"),
            ],
        },
        {
            "id": "credit",
            "name": "信用风险",
            "name_en": "Credit Risk",
            "metrics": [
                _metric(
                    "issuer_rating_dist",
                    "主体评级档位数",
                    value=len(issuer_rating_dist),
                    unit="档",
                    status="derived" if bond_date else "unavailable",
                    note="issuer_rating",
                    detail=", ".join(
                        f"{r.get('rating')}:{_round(r.get('weight_pct'), 1)}%"
                        for r in issuer_rating_dist
                    ) or None,
                ),
                _metric(
                    "debt_rating_dist",
                    "债项评级档位数",
                    value=len(debt_rating_dist),
                    unit="档",
                    status="derived" if bond_date else "unavailable",
                    note="debt_rating",
                    detail=", ".join(
                        f"{r.get('rating')}:{_round(r.get('weight_pct'), 1)}%"
                        for r in debt_rating_dist
                    ) or None,
                ),
                _metric(
                    "issuer_ig_pct",
                    "主体评级·投资级占比",
                    value=_round(rates.get("issuer_investment_grade_pct"), 2),
                    unit="%",
                    status="derived" if rates.get("issuer_investment_grade_pct") is not None else "unavailable",
                    note="BBB-及以上 · 占债券市值",
                ),
                _metric(
                    "issuer_below_ig_pct",
                    "主体评级·低于投资级占比",
                    value=_round(rates.get("issuer_below_investment_grade_pct"), 2),
                    unit="%",
                    status="derived" if rates.get("issuer_below_investment_grade_pct") is not None else "unavailable",
                    note="含 NR",
                ),
                _metric(
                    "debt_ig_pct",
                    "债项评级·投资级占比",
                    value=_round(rates.get("debt_investment_grade_pct"), 2),
                    unit="%",
                    status="derived" if rates.get("debt_investment_grade_pct") is not None else "unavailable",
                    note="BBB-及以上 · 占债券市值",
                ),
                _metric(
                    "debt_below_ig_pct",
                    "债项评级·低于投资级占比",
                    value=_round(rates.get("debt_below_investment_grade_pct"), 2),
                    unit="%",
                    status="derived" if rates.get("debt_below_investment_grade_pct") is not None else "unavailable",
                    note="含 NR",
                ),
                _metric("low_rating_pct", "低评级债占比（AA+及以下）", value=bond_ext["low_rating_pct"], unit="%", status="computed" if bond_date else "unavailable"),
                _metric("issuer_hhi", "发行人集中度 HHI", value=_round((rates.get("issuer_concentration") or {}).get("hhi"), 1), unit="", status="derived", note="利率信用"),
                _metric("top_issuer_pct", "最大发行人占比", value=bond_ext["top_issuer_pct"], unit="%", status="computed" if bond_date else "unavailable"),
                _metric("bond_top5", "前五大个券集中度", value=bond_ext["top5_bond_pct"], unit="%", status="computed" if bond_date else "unavailable"),
                _metric("bond_top10", "前十大个券集中度", value=bond_ext["top10_bond_pct"], unit="%", status="computed" if bond_date else "unavailable"),
                _metric("cs01", "CS01", value=_round(rates.get("portfolio_cs01"), 0), unit="", status="derived", note="利率信用"),
                _metric("controller_conc", "同一实际控制人集中度", value=ext.get("controller_conc"), unit="%", status="computed" if ext.get("controller_conc") is not None else "unavailable", detail=ext.get("controller_detail"), note="机构集团穿透"),
                _metric("unified_credit", "统一信用风险敞口", value=ext.get("unified_credit"), unit="%", status="computed" if ext.get("unified_credit") is not None else "unavailable", detail=ext.get("unified_detail"), note="占存续债/净资产/组合信用债"),
                _metric("neg_news", "负面舆情条数", value=ext.get("neg_news"), unit="条", status="computed", note="mktdata_issuer_news"),
                _metric("implied_pd", "隐含违约率", value=ext.get("implied_pd"), unit="%", status="computed" if ext.get("implied_pd") is not None else "unavailable", note="mktdata_fi_credit"),
                _metric("bond_suspend", "债券停牌/保护条款触发", value=ext.get("bond_suspend"), unit="只", status="computed", detail=f"占净值 {ext.get('bond_suspend_pct')}%" if ext.get("bond_suspend_pct") is not None else None),
            ],
        },
        {
            "id": "liquidity",
            "name": "流动性风险",
            "name_en": "Liquidity Risk",
            "metrics": [
                _metric("ttl_10", "变现天数 TTL 10%", value=_round((liq.get("ttl_snapshot") or {}).get("ttl_10pct_days"), 1), unit="天", status="derived", note="流动性压测"),
                _metric("ttl_25", "变现天数 TTL 25%", value=_round((liq.get("ttl_snapshot") or {}).get("ttl_25pct_days"), 1), unit="天", status="derived", note="流动性压测"),
                _metric("ttl_50", "变现天数 TTL 50%", value=_round((liq.get("ttl_snapshot") or {}).get("ttl_50pct_days"), 1), unit="天", status="derived", note="流动性压测"),
                _metric("avg_ttl", "平均变现天数", value=ttl_buckets["avg_ttl_days"], unit="天", status="computed"),
                _metric("stock_ttl", "股票变现天数", value=ttl_buckets["stock_ttl"], unit="天", status="computed"),
                _metric("bond_ttl", "债券变现天数", value=ttl_buckets["bond_ttl"], unit="天", status="computed"),
                _metric("over_10d", "变现超10天资产占比", value=ttl_buckets["over_10d_pct"], unit="%", status="computed"),
                _metric("over_40d", "变现超40天资产占比", value=ttl_buckets["over_40d_pct"], unit="%", status="computed"),
                _metric("cash_pct", "现金及高流动性资产占比", value=assets["high_liquidity_pct_nav"], unit="%", status="computed"),
                _metric("cash_only", "现金及存款占比", value=assets["cash_pct_nav"], unit="%", status="computed"),
                _metric("lcr_15", "高流动性资产覆盖率（赎回15%）", value=_round((liq.get("stress_summary") or {}).get("liquidity_coverage_ratio"), 2), unit="x", status="derived", note="流动性压测"),
                _metric("rate_bond_pct", "国债/利率债占比", value=assets["rate_bond_pct_nav"], unit="%", status="computed"),
                _metric("restricted_pct", "流动受限资产占比", value=ext.get("restricted_pct"), unit="%", status="computed" if ext.get("restricted_pct") is not None else "unavailable", note="停牌或不可卖出股票"),
                _metric("net_redemption", "净赎回占期初净值", value=ext.get("net_redemption"), unit="%", status="computed" if ext.get("net_redemption") is not None else "unavailable", detail=f"净赎回金额 {ext.get('net_redemption_amt')}" if ext.get("net_redemption_amt") is not None else None, note="transact_portfolio_cashflow"),
                _metric("investor_conc", "前十大投资者集中度", value=ext.get("investor_top10"), unit="%", status="computed" if ext.get("investor_top10") is not None else "unavailable", detail=f"前5 {ext.get('investor_top5')}% / 前20 {ext.get('investor_top20')}% / 机构 {ext.get('investor_inst')}%", note="para_sponsor + holder_rank"),
            ],
        },
        {
            "id": "concentration",
            "name": "集中度与杠杆",
            "name_en": "Concentration & Leverage",
            "metrics": [
                _metric("equity_top5", "前五大重仓股占比", value=equity_conc["top5_pct"], unit="%", status="computed" if stock_date else "unavailable"),
                _metric("equity_top10", "前十大重仓股占比", value=equity_conc["top10_pct"], unit="%", status="computed" if stock_date else "unavailable"),
                _metric("equity_largest", "最大个股占比", value=equity_conc["largest_pct"], unit="%", status="computed" if stock_date else "unavailable"),
                _metric("equity_hhi", "个股集中度 HHI", value=equity_conc["hhi"], unit="", status="computed" if stock_date else "unavailable"),
                _metric("sector_hhi", "行业集中度 HHI", value=_round(sector_hhi, 1), unit="", status="derived", note="因子行为"),
                _metric("bond_conc_top10", "前十大重仓债占比", value=bond_ext["top10_bond_pct"], unit="%", status="computed" if bond_date else "unavailable"),
                _metric("issuer_top", "最大发行人占比（债）", value=bond_ext["top_issuer_pct"], unit="%", status="computed" if bond_date else "unavailable"),
                _metric("leverage", "杠杆倍数（资产/净值）", value=assets["leverage_ratio"], unit="x", status="computed"),
                _metric("repo_pct", "正回购负债占比", value=assets["repo_liability_pct_nav"], unit="%", status="computed"),
                _metric("country_qdii", "国家/地区集中度", value=ext.get("country_conc"), unit="%", status="computed" if ext.get("country_conc") is not None else "unavailable", detail=ext.get("country_detail")),
                _metric("controller_eq", "同一实际控制人集中度", value=ext.get("controller_conc"), unit="%", status="computed" if ext.get("controller_conc") is not None else "unavailable", detail=ext.get("controller_detail")),
                _metric("equity_float", "最大个股占流通股", value=ext.get("equity_of_float"), unit="%", status="computed" if ext.get("equity_of_float") is not None else "unavailable", detail=f"占总股本 {ext.get('equity_of_shares')}%" if ext.get("equity_of_shares") is not None else None, note="mktdata_stock_static"),
            ],
        },
        {
            "id": "compliance",
            "name": "投资合规与操作风险",
            "name_en": "Compliance & Operational Risk",
            "metrics": _build_ams_compliance_metrics(
                exposure=exposure,
                assets=assets,
                bond_ext=bond_ext,
                rates=rates,
                ext=ext,
                nav=nav,
                base_currency=base_currency,
            ),
        },
        {
            "id": "stress",
            "name": "产品压力测试",
            "name_en": "Stress Testing",
            "metrics": [
                _metric("rate_shock_50", "利率+50BP 偏离金额", value=_round(rate_loss, 0), unit="", status="derived", note="流动性压测"),
                _metric("rate_shock_50_pct", "利率+50BP 偏离占比", value=rate_impact_pct, unit="%", status="computed"),
                _metric(
                    "redemption_15_lcr",
                    "极端赎回15%·高流动性覆盖率",
                    value=_round((liq.get("stress_summary") or {}).get("liquidity_coverage_ratio"), 2),
                    unit="x",
                    status="derived",
                    note="流动性压测（赎回15%）",
                ),
                _metric(
                    "redemption_20_lcr",
                    "赎回20%·高流动性覆盖率",
                    value=_round((liq_extreme.get("stress_summary") or {}).get("liquidity_coverage_ratio"), 2),
                    unit="x",
                    status="derived",
                    note="流动性压测",
                ),
                _metric("market_crash_nav", "股指极端下跌·净值跌幅代理（β×-20%）", value=market_crash_proxy, unit="%", status="computed" if market_crash_proxy is not None else "unavailable", note=bench_note),
                _metric("market_crash_ttl", "可流通股票变现天数", value=ttl_buckets["stock_ttl"], unit="天", status="computed"),
                _metric("credit_default_3", "信用违约3%·净值损失预测", value=default_nav_impact, unit="%", status="computed"),
                _metric("top5_investor_redeem", "前五大投资者全部赎回覆盖率", value=ext.get("top5_cover"), unit="x", status="computed" if ext.get("top5_cover") is not None else "unavailable", note="7日可变现 / 前五大持仓金额"),
            ],
        },
    ]

    computed = sum(1 for c in categories for m in c["metrics"] if m["status"] == "computed")
    derived = sum(1 for c in categories for m in c["metrics"] if m["status"] == "derived")
    unavailable = sum(1 for c in categories for m in c["metrics"] if m["status"] == "unavailable")
    _stamp_groups(categories)

    payload = {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "resolved_period_start": effective_start,
        "resolved_period_end": effective_end,
        "data_as_of": latest_nav_date,
        "benchmark_id": bench_id or (risk.get("equity_beta") or {}).get("benchmark_id"),
        "source": "computed",
        "summary": {
            "computed": computed,
            "derived": derived,
            "unavailable": unavailable,
            "total": computed + derived + unavailable,
        },
        "categories": categories,
        "message": risk.get("message"),
        "credit_rating_detail": {
            "as_of_date": rates_asof.isoformat() if hasattr(rates_asof, "isoformat") else str(rates_asof),
            "total_bond_market_value": rates.get("total_bond_market_value"),
            "bond_count": rates.get("bond_count"),
            "issuer_rating_distribution": issuer_rating_dist,
            "debt_rating_distribution": debt_rating_dist,
            "issuer_investment_grade_pct": rates.get("issuer_investment_grade_pct"),
            "issuer_below_investment_grade_pct": rates.get("issuer_below_investment_grade_pct"),
            "debt_investment_grade_pct": rates.get("debt_investment_grade_pct"),
            "debt_below_investment_grade_pct": rates.get("debt_below_investment_grade_pct"),
        },
    }
    await _save_metric_report(db, payload)
    return payload
