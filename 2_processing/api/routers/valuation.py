"""Portfolio valuation & P&L APIs (Module 4 — the validation loop).

Read-only reporting computed from editable balance tables:
- daily valuation report from ``fsi.balance_valuation_sheet`` (+ NAV summary),
- period P&L from the ``fsi.balance_portfolio_nav`` daily history, with
  subject-level attribution when two valuation snapshots exist in range.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

TRADING_DAYS = 252


# ── Pure, unit-testable P&L math ─────────────────────────────────
def _cumulative_return(day_returns: list[float]) -> float:
    """Compound a list of daily returns into a cumulative return."""
    product = 1.0
    for r in day_returns:
        product *= 1.0 + r
    return product - 1.0


def _nav_index(day_returns: list[float]) -> list[float]:
    """Compounding index starting at 1.0 (one point per daily return)."""
    index = []
    level = 1.0
    for r in day_returns:
        level *= 1.0 + r
        index.append(level)
    return index


def _max_drawdown(index_series: list[float]) -> float:
    """Largest peak-to-trough drop of a level series (returned as a negative fraction)."""
    peak = float("-inf")
    worst = 0.0
    for level in index_series:
        peak = max(peak, level)
        if peak > 0:
            worst = min(worst, level / peak - 1.0)
    return worst


def _volatility(day_returns: list[float]) -> float:
    """Annualized standard deviation of daily returns (sample stdev)."""
    n = len(day_returns)
    if n < 2:
        return 0.0
    mean = sum(day_returns) / n
    variance = sum((r - mean) ** 2 for r in day_returns) / (n - 1)
    return (variance ** 0.5) * (TRADING_DAYS ** 0.5)


def _annualize(cumulative: float, n_days: int) -> float:
    """Annualize a cumulative return observed over n_days daily observations."""
    if n_days <= 0:
        return 0.0
    return (1.0 + cumulative) ** (TRADING_DAYS / n_days) - 1.0


def _f(value: Any) -> float | None:
    return None if value is None else float(value)


@router.get("/report/{fund_id}", summary="每日估值報表")
async def valuation_report(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT subject_code, subject_name, currency, quantity, unit_price,
                       cost, market_value, weight_pct, data_source, memo
                FROM fsi.balance_valuation_sheet
                WHERE port_id = :fid AND evaluate_date = :d
                ORDER BY market_value DESC NULLS LAST, subject_code
                """
            ),
            {"fid": fund_id, "d": as_of_date},
        )
    ).mappings().all()

    subjects: list[dict[str, Any]] = []
    total_mv = 0.0
    total_cost = 0.0
    for row in rows:
        mv = _f(row["market_value"]) or 0.0
        cost = _f(row["cost"])
        unrealized = None if cost is None else mv - cost
        return_pct = None if not cost else unrealized / cost * 100
        total_mv += mv
        total_cost += cost or 0.0
        subjects.append(
            {
                "subject_code": row["subject_code"],
                "subject_name": row["subject_name"],
                "currency": str(row["currency"]).strip(),
                "quantity": _f(row["quantity"]),
                "unit_price": _f(row["unit_price"]),
                "cost": cost,
                "market_value": mv,
                "weight_pct": _f(row["weight_pct"]),
                "unrealized_pnl": unrealized,
                "return_pct": return_pct,
                "data_source": row["data_source"],
                "memo": row["memo"],
            }
        )

    nav = (
        await db.execute(
            text(
                """
                SELECT currency, net_asset, unit_nav, acc_unit_nav, day_return,
                       total_asset, total_liability
                FROM fsi.balance_portfolio_nav
                WHERE port_id = :fid AND evaluate_date = :d
                ORDER BY currency
                LIMIT 1
                """
            ),
            {"fid": fund_id, "d": as_of_date},
        )
    ).mappings().first()

    available = [
        row[0]
        for row in (
            await db.execute(
                text(
                    """
                    SELECT DISTINCT evaluate_date FROM fsi.balance_valuation_sheet
                    WHERE port_id = :fid ORDER BY evaluate_date DESC LIMIT 120
                    """
                ),
                {"fid": fund_id},
            )
        ).all()
    ]

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "subjects": subjects,
        "totals": {
            "total_market_value": total_mv,
            "total_cost": total_cost,
            "total_unrealized_pnl": total_mv - total_cost,
            "subject_count": len(subjects),
        },
        "nav_summary": None
        if not nav
        else {
            "currency": str(nav["currency"]).strip(),
            "net_asset": _f(nav["net_asset"]),
            "unit_nav": _f(nav["unit_nav"]),
            "acc_unit_nav": _f(nav["acc_unit_nav"]),
            "day_return": _f(nav["day_return"]),
            "total_asset": _f(nav["total_asset"]),
            "total_liability": _f(nav["total_liability"]),
        },
        "available_dates": [d.isoformat() for d in available],
    }


async def _nav_bounds(db: AsyncSession, fund_id: str) -> tuple[date, date] | None:
    row = (
        await db.execute(
            text(
                "SELECT MIN(evaluate_date), MAX(evaluate_date) FROM fsi.balance_portfolio_nav WHERE port_id = :fid"
            ),
            {"fid": fund_id},
        )
    ).first()
    if not row or row[0] is None:
        return None
    return row[0], row[1]


@router.get("/pnl/{fund_id}", summary="階段損益分析")
async def pnl_analysis(
    fund_id: str,
    start: date | None = None,
    end: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must not be later than end")
    if not (start and end):
        bounds = await _nav_bounds(db, fund_id)
        if not bounds:
            raise HTTPException(status_code=404, detail="No NAV history for this portfolio")
        start = start or bounds[0]
        end = end or bounds[1]

    nav_rows = (
        await db.execute(
            text(
                """
                SELECT evaluate_date, currency, net_asset, unit_nav, day_return
                FROM fsi.balance_portfolio_nav
                WHERE port_id = :fid AND evaluate_date BETWEEN :start AND :end
                ORDER BY evaluate_date
                """
            ),
            {"fid": fund_id, "start": start, "end": end},
        )
    ).mappings().all()

    if not nav_rows:
        raise HTTPException(status_code=404, detail="No NAV history in the selected range")

    day_returns = [(_f(r["day_return"]) or 0.0) for r in nav_rows]
    index = _nav_index(day_returns)
    cumulative = _cumulative_return(day_returns)
    n = len(nav_rows)
    net_start = _f(nav_rows[0]["net_asset"]) or 0.0
    net_end = _f(nav_rows[-1]["net_asset"]) or 0.0
    positive_days = sum(1 for r in day_returns if r > 0)
    best = max(day_returns) if day_returns else 0.0
    worst = min(day_returns) if day_returns else 0.0

    timeseries = []
    for i, row in enumerate(nav_rows):
        timeseries.append(
            {
                "date": row["evaluate_date"].isoformat(),
                "net_asset": _f(row["net_asset"]),
                "unit_nav": _f(row["unit_nav"]),
                "cum_return_pct": (index[i] - 1.0) * 100,
            }
        )

    attribution = await _subject_attribution(db, fund_id, start, end)

    return {
        "fund_id": fund_id,
        "start": start,
        "end": end,
        "summary": {
            "days": n,
            "net_asset_start": net_start,
            "net_asset_end": net_end,
            "net_asset_change": net_end - net_start,
            "cumulative_return_pct": cumulative * 100,
            "annualized_return_pct": _annualize(cumulative, n) * 100,
            "avg_daily_return_pct": (sum(day_returns) / n * 100) if n else 0.0,
            "volatility_pct": _volatility(day_returns) * 100,
            "max_drawdown_pct": _max_drawdown(index) * 100,
            "best_day_pct": best * 100,
            "worst_day_pct": worst * 100,
            "positive_day_ratio": (positive_days / n) if n else 0.0,
            "unit_nav_start": _f(nav_rows[0]["unit_nav"]),
            "unit_nav_end": _f(nav_rows[-1]["unit_nav"]),
            "currency": str(nav_rows[0]["currency"]).strip(),
        },
        "timeseries": timeseries,
        "attribution": attribution,
    }


async def _subject_attribution(
    db: AsyncSession, fund_id: str, start: date, end: date
) -> dict[str, Any]:
    """Period attribution when two valuation snapshots bracket the range; else the
    latest snapshot's unrealized-P&L composition."""
    snap_dates = [
        row[0]
        for row in (
            await db.execute(
                text(
                    """
                    SELECT DISTINCT evaluate_date FROM fsi.balance_valuation_sheet
                    WHERE port_id = :fid AND evaluate_date BETWEEN :start AND :end
                    ORDER BY evaluate_date
                    """
                ),
                {"fid": fund_id, "start": start, "end": end},
            )
        ).all()
    ]

    if len(snap_dates) >= 2:
        first, last = snap_dates[0], snap_dates[-1]
        rows = (
            await db.execute(
                text(
                    """
                    SELECT s.subject_code, s.subject_name,
                           SUM(CASE WHEN s.evaluate_date = :first THEN s.market_value ELSE 0 END) AS mv_start,
                           SUM(CASE WHEN s.evaluate_date = :last  THEN s.market_value ELSE 0 END) AS mv_end
                    FROM fsi.balance_valuation_sheet s
                    WHERE s.port_id = :fid AND s.evaluate_date IN (:first, :last)
                    GROUP BY s.subject_code, s.subject_name
                    ORDER BY (SUM(CASE WHEN s.evaluate_date = :last THEN s.market_value ELSE 0 END)
                            - SUM(CASE WHEN s.evaluate_date = :first THEN s.market_value ELSE 0 END)) DESC
                    """
                ),
                {"fid": fund_id, "first": first, "last": last},
            )
        ).mappings().all()
        return {
            "mode": "period",
            "start_date": first.isoformat(),
            "end_date": last.isoformat(),
            "items": [
                {
                    "subject_code": r["subject_code"],
                    "subject_name": r["subject_name"],
                    "mv_start": _f(r["mv_start"]),
                    "mv_end": _f(r["mv_end"]),
                    "contribution": (_f(r["mv_end"]) or 0.0) - (_f(r["mv_start"]) or 0.0),
                }
                for r in rows
            ],
        }

    snapshot = snap_dates[-1] if snap_dates else None
    if snapshot is None:
        snap = (
            await db.execute(
                text(
                    """
                    SELECT MAX(evaluate_date) FROM fsi.balance_valuation_sheet
                    WHERE port_id = :fid AND evaluate_date <= :end
                    """
                ),
                {"fid": fund_id, "end": end},
            )
        ).scalar()
        snapshot = snap
    if snapshot is None:
        return {"mode": "unrealized", "snapshot_date": None, "items": []}

    rows = (
        await db.execute(
            text(
                """
                SELECT subject_code, subject_name, market_value, cost
                FROM fsi.balance_valuation_sheet
                WHERE port_id = :fid AND evaluate_date = :d
                ORDER BY (market_value - COALESCE(cost, market_value)) DESC
                """
            ),
            {"fid": fund_id, "d": snapshot},
        )
    ).mappings().all()
    return {
        "mode": "unrealized",
        "snapshot_date": snapshot.isoformat(),
        "items": [
            {
                "subject_code": r["subject_code"],
                "subject_name": r["subject_name"],
                "market_value": _f(r["market_value"]),
                "cost": _f(r["cost"]),
                "contribution": (_f(r["market_value"]) or 0.0) - (_f(r["cost"]) or 0.0),
            }
            for r in rows
        ],
    }
