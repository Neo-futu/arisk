"""Portfolio cockpit APIs (Module 2.1 — 组合列表与驾驶舱).

Read-only Bloomberg-PORT-style fundamentals cockpit over existing master + balance
tables: per-portfolio type / currency / AUM / unit NAV / day return / MMF metrics
(7-day yield, WAM/WAL vs limits, shadow-price deviation) + status + NAV sparkline.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

SPARKLINE_POINTS = 30
# SFC MMF shadow-price deviation action threshold is 0.5% = 50bp; warn nearing it.
DEVIATION_BREACH_BP = 50.0
DEVIATION_WARN_BP = 40.0
LIMIT_WARN_RATIO = 0.9

Status = Literal["ok", "warn", "breach"]


def _f(value: Any) -> float | None:
    return None if value is None else float(value)


def _compliance_status(
    is_mmf: bool,
    wam_days: float | None,
    wal_days: float | None,
    wam_limit: float | None,
    wal_limit: float | None,
    deviation_bp: float | None,
) -> Status:
    """Derive an MMF cockpit status. Non-MMF (or no metrics) → ok.

    breach: any hard SFC limit exceeded (WAM>limit, WAL>limit, |deviation|>50bp).
    warn:   nearing a limit (≥90% of WAM/WAL limit, or |deviation|≥40bp).
    """
    if not is_mmf:
        return "ok"
    breach = False
    warn = False
    for value, limit in ((wam_days, wam_limit), (wal_days, wal_limit)):
        if value is None or limit is None or limit <= 0:
            continue
        if value > limit:
            breach = True
        elif value >= limit * LIMIT_WARN_RATIO:
            warn = True
    if deviation_bp is not None:
        abs_dev = abs(deviation_bp)
        if abs_dev > DEVIATION_BREACH_BP:
            breach = True
        elif abs_dev >= DEVIATION_WARN_BP:
            warn = True
    if breach:
        return "breach"
    if warn:
        return "warn"
    return "ok"


@router.get("/overview", summary="組合列表與駕駛艙總覽")
async def overview(
    port_ids: str | None = Query(default=None, description="逗號分隔；省略=全部 active"),
    as_of_date: date | None = Query(default=None, description="省略=各組合最新"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ids = [p.strip().upper() for p in port_ids.split(",") if p.strip()] if port_ids else None

    rows = (
        await db.execute(
            text(
                """
                WITH pf AS (
                    SELECT port_id, port_name, port_name_en, port_type::text AS port_type,
                           base_currency, is_mmf, inception_date, sfc_code,
                           mmf_wam_limit_days, mmf_wal_limit_days, mgmt_fee_bps
                    FROM fsi.para_portfolio
                    WHERE is_active = TRUE
                      AND (CAST(:ids AS text[]) IS NULL OR port_id = ANY(CAST(:ids AS text[])))
                ),
                nav AS (
                    SELECT DISTINCT ON (n.port_id)
                           n.port_id, n.evaluate_date, n.net_asset, n.unit_nav,
                           n.acc_unit_nav, n.day_return, n.currency
                    FROM fsi.balance_portfolio_nav n
                    JOIN pf ON pf.port_id = n.port_id
                    WHERE (CAST(:as_of AS date) IS NULL OR n.evaluate_date <= CAST(:as_of AS date))
                    ORDER BY n.port_id, n.evaluate_date DESC
                )
                SELECT pf.*, nav.evaluate_date, nav.net_asset, nav.unit_nav,
                       nav.acc_unit_nav, nav.day_return, nav.currency AS nav_currency,
                       m.return_rate_7d, m.wam_days, m.wal_days, m.nav_deviation, m.income_per_10k
                FROM pf
                LEFT JOIN nav ON nav.port_id = pf.port_id
                LEFT JOIN fsi.balance_portfolio_mmf m
                       ON m.port_id = pf.port_id AND m.evaluate_date = nav.evaluate_date
                ORDER BY pf.is_mmf DESC, pf.port_id
                """
            ),
            {"ids": ids, "as_of": as_of_date},
        )
    ).mappings().all()

    portfolios: list[dict[str, Any]] = []
    for r in rows:
        is_mmf = bool(r["is_mmf"])
        wam, wal = _f(r["wam_days"]), _f(r["wal_days"])
        wam_limit, wal_limit = _f(r["mmf_wam_limit_days"]), _f(r["mmf_wal_limit_days"])
        deviation = _f(r["nav_deviation"])
        status = _compliance_status(is_mmf, wam, wal, wam_limit, wal_limit, deviation)
        portfolios.append(
            {
                "port_id": r["port_id"],
                "port_name": r["port_name"],
                "port_name_en": r["port_name_en"],
                "port_type": r["port_type"],
                "base_currency": str(r["base_currency"]).strip(),
                "is_mmf": is_mmf,
                "inception_date": r["inception_date"].isoformat() if r["inception_date"] else None,
                "sfc_code": r["sfc_code"],
                "mgmt_fee_bps": _f(r["mgmt_fee_bps"]),
                "as_of_date": r["evaluate_date"].isoformat() if r["evaluate_date"] else None,
                "net_asset": _f(r["net_asset"]),
                "unit_nav": _f(r["unit_nav"]),
                "acc_unit_nav": _f(r["acc_unit_nav"]),
                "day_return": _f(r["day_return"]),
                "return_rate_7d": _f(r["return_rate_7d"]),
                "wam_days": wam,
                "wal_days": wal,
                "wam_limit_days": wam_limit,
                "wal_limit_days": wal_limit,
                "nav_deviation": deviation,
                "income_per_10k": _f(r["income_per_10k"]),
                "status": status,
                "has_data": r["evaluate_date"] is not None,
                "sparkline": [],
            }
        )

    # NAV sparklines (last N net_asset points per portfolio, ascending for charting).
    by_id = {p["port_id"]: p for p in portfolios}
    if by_id:
        spark_rows = (
            await db.execute(
                text(
                    """
                    SELECT port_id, evaluate_date, net_asset FROM (
                        SELECT n.port_id, n.evaluate_date, n.net_asset,
                               ROW_NUMBER() OVER (PARTITION BY n.port_id ORDER BY n.evaluate_date DESC) AS rn
                        FROM fsi.balance_portfolio_nav n
                        WHERE n.port_id = ANY(:ids)
                          AND (CAST(:as_of AS date) IS NULL OR n.evaluate_date <= CAST(:as_of AS date))
                    ) t
                    WHERE t.rn <= :limit
                    ORDER BY port_id, evaluate_date
                    """
                ),
                {"ids": list(by_id), "as_of": as_of_date, "limit": SPARKLINE_POINTS},
            )
        ).mappings().all()
        for sr in spark_rows:
            by_id[sr["port_id"]]["sparkline"].append(_f(sr["net_asset"]))

    by_type: dict[str, int] = {}
    for p in portfolios:
        by_type[p["port_type"]] = by_type.get(p["port_type"], 0) + 1
    total_aum: dict[str, float] = {}
    for p in portfolios:
        if p["net_asset"] is not None:
            total_aum[p["base_currency"]] = total_aum.get(p["base_currency"], 0.0) + p["net_asset"]

    return {
        "as_of_date": as_of_date.isoformat() if as_of_date else None,
        "summary": {
            "total_portfolios": len(portfolios),
            "with_data": sum(1 for p in portfolios if p["has_data"]),
            "mmf_count": sum(1 for p in portfolios if p["is_mmf"]),
            "breached": sum(1 for p in portfolios if p["status"] == "breach"),
            "warned": sum(1 for p in portfolios if p["status"] == "warn"),
            "by_type": by_type,
            "total_aum": total_aum,
        },
        "portfolios": portfolios,
    }
