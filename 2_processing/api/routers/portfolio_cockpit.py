"""组合驾驶舱：组合基本信息（类型、AUM、净值、收益）及净值历史。

只读 ``fsi.para_portfolio`` / ``fsi.balance_portfolio_nav`` / ``fsi.balance_portfolio_mmf``。
驾驶舱页面不展示合规；接口仍附带货基限额字段，供其他调用方使用。
"""
from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

SPARKLINE_POINTS = 30
_sfc = import_module("3_riskengine.limits.sfc")
DEVIATION_BREACH_BP = _sfc.DEVIATION_BREACH_BP
DEVIATION_WARN_BP = _sfc.DEVIATION_WARN_BP
LIMIT_WARN_RATIO = _sfc.LIMIT_WARN_RATIO
Status = _sfc.Status


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
    """MMF cockpit status. Canonical 口径 is RiskEngine ``limits.sfc``."""

    return _sfc.compliance_status(is_mmf, wam_days, wal_days, wam_limit, wal_limit, deviation_bp)


@router.get("/overview", summary="組合列表與駕駛艙總覽")
async def overview(
    port_ids: str | None = Query(default=None, description="逗號分隔；省略=全部 active"),
    start_date: date | None = Query(default=None, description="區間開始"),
    end_date: date | None = Query(default=None, description="區間結束"),
    as_of_date: date | None = Query(default=None, description="兼容舊參數，等同結束日期"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ids = [p.strip().upper() for p in port_ids.split(",") if p.strip()] if port_ids else None
    ended = end_date or as_of_date

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
                    WHERE (CAST(:ended AS date) IS NULL OR n.evaluate_date <= CAST(:ended AS date))
                      AND (CAST(:started AS date) IS NULL OR n.evaluate_date >= CAST(:started AS date))
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
            {"ids": ids, "started": start_date, "ended": ended},
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
                "period_return": None,
                "wam_days": wam,
                "wal_days": wal,
                "wam_limit_days": wam_limit,
                "wal_limit_days": wal_limit,
                "nav_deviation": deviation,
                "income_per_10k": _f(r["income_per_10k"]),
                "status": status,
                "has_data": r["evaluate_date"] is not None,
                "sparkline": [],
                "history": [],
            }
        )

    by_id = {p["port_id"]: p for p in portfolios}
    if by_id:
        spark_rows = (
            await db.execute(
                text(
                    """
                    SELECT port_id, evaluate_date, net_asset, unit_nav, day_return FROM (
                        SELECT n.port_id, n.evaluate_date, n.net_asset, n.unit_nav, n.day_return,
                               ROW_NUMBER() OVER (PARTITION BY n.port_id ORDER BY n.evaluate_date DESC) AS rn
                        FROM fsi.balance_portfolio_nav n
                        WHERE n.port_id = ANY(:ids)
                          AND (CAST(:started AS date) IS NULL OR n.evaluate_date >= CAST(:started AS date))
                          AND (CAST(:ended AS date) IS NULL OR n.evaluate_date <= CAST(:ended AS date))
                    ) t
                    WHERE t.rn <= :limit
                    ORDER BY port_id, evaluate_date
                    """
                ),
                {
                    "ids": list(by_id),
                    "started": start_date,
                    "ended": ended,
                    "limit": 366 if start_date is not None else SPARKLINE_POINTS,
                },
            )
        ).mappings().all()
        for sr in spark_rows:
            net_asset = _f(sr["net_asset"])
            point = {
                "date": sr["evaluate_date"].isoformat() if sr["evaluate_date"] else None,
                "net_asset": net_asset,
                "unit_nav": _f(sr["unit_nav"]),
                "day_return": _f(sr["day_return"]),
            }
            by_id[sr["port_id"]]["history"].append(point)
            if net_asset is not None:
                by_id[sr["port_id"]]["sparkline"].append(net_asset)
        cockpit_math = import_module("3_riskengine.portfolio.cockpit")
        for portfolio in portfolios:
            portfolio["period_return"] = cockpit_math.period_return(portfolio["history"])
            portfolio["indexed_nav"] = cockpit_math.indexed_nav_series(portfolio["history"])

    by_type: dict[str, int] = {}
    for p in portfolios:
        by_type[p["port_type"]] = by_type.get(p["port_type"], 0) + 1
    total_aum: dict[str, float] = {}
    for p in portfolios:
        if p["net_asset"] is not None:
            total_aum[p["base_currency"]] = total_aum.get(p["base_currency"], 0.0) + p["net_asset"]

    cockpit_math = import_module("3_riskengine.portfolio.cockpit")
    charts = cockpit_math.charts_payload(portfolios)
    return {
        "as_of_date": ended.isoformat() if ended else None,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": ended.isoformat() if ended else None,
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
        "charts": charts,
        "business_modules": list(cockpit_math.BUSINESS_MODULES),
        "page": {
            "path": "/portfolio-cockpit",
            "table_columns": list(cockpit_math.TABLE_COLUMNS),
            "chart_ids": list(cockpit_math.LEGACY_CHART_IDS),
            "business_modules": list(cockpit_math.BUSINESS_MODULES),
        },
        "engine": "ARISK RiskEngine",
        "engine_version": import_module("3_riskengine.core.lineage").RISKENGINE_VERSION,
    }
