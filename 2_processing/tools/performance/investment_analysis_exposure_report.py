"""整体风险敞口：只读报表层 svc_risk_exposure / svc_risk_snapshot。

缺记录时用持仓表做一次轻量汇总并写入报表层，不走 RiskEngine KPI 包。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _number


def _kpi(name: str, formula: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "kpi": name,
        "engine": "svc_risk_exposure",
        "formula": formula,
        "result": result,
    }


async def _report_date(db: AsyncSession, fund_id: str, as_of_date: date) -> date | None:
    result = await db.execute(
        text(
            """
            SELECT MAX(as_of_date)
            FROM fsi.svc_risk_exposure
            WHERE port_id = :fund_id
              AND as_of_date <= :as_of_date
              AND dimension = 'ASSET_CLASS'
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    return result.scalar_one_or_none()


async def _materialize(db: AsyncSession, fund_id: str, as_of_date: date) -> date | None:
    """从持仓汇总写入报表层。返回实际快照日。"""
    snap = await db.execute(
        text(
            """
            SELECT MAX(evaluate_date)
            FROM fsi.balance_portfolio_asset
            WHERE port_id = :fund_id AND evaluate_date <= :as_of_date
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    snapshot = snap.scalar_one_or_none()
    if snapshot is None:
        return None

    nav_row = await db.execute(
        text(
            """
            SELECT net_asset
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id AND evaluate_date <= :snapshot
            ORDER BY evaluate_date DESC
            LIMIT 1
            """
        ),
        {"fund_id": fund_id, "snapshot": snapshot},
    )
    nav = nav_row.scalar_one_or_none()

    await db.execute(
        text(
            """
            INSERT INTO fsi.svc_risk_exposure (
                port_id, as_of_date, dimension, category, currency,
                market_value, market_value_base, weight_pct, item_count
            )
            SELECT CAST(:fund_id AS VARCHAR(16)), :snapshot, 'ASSET_CLASS', asset_class::text, NULL,
                   SUM(COALESCE(market_value, market_value_base, 0)),
                   SUM(COALESCE(market_value_base, market_value, 0)),
                   SUM(COALESCE(weight_pct, 0)),
                   COUNT(*)
            FROM fsi.balance_portfolio_asset
            WHERE port_id = :fund_id AND evaluate_date = :snapshot
            GROUP BY asset_class::text
            ON CONFLICT (port_id, as_of_date, dimension, category) DO UPDATE
                SET market_value = EXCLUDED.market_value,
                    market_value_base = EXCLUDED.market_value_base,
                    weight_pct = EXCLUDED.weight_pct,
                    item_count = EXCLUDED.item_count
            """
        ),
        {"fund_id": fund_id, "snapshot": snapshot},
    )

    dur = await db.execute(
        text(
            """
            SELECT SUM(COALESCE(market_value_base, market_value, 0)) AS fi_mv,
                   SUM(COALESCE(market_value_base, market_value, 0) * COALESCE(duration, 0))
                       / NULLIF(SUM(COALESCE(market_value_base, market_value, 0)), 0) AS w_dur,
                   SUM(COALESCE(dv01_base, dv01, COALESCE(market_value_base, market_value, 0) * COALESCE(duration, 0) * 0.0001)) AS dv01
            FROM fsi.balance_bond
            WHERE port_id = :fund_id AND evaluate_date = :snapshot
            """
        ),
        {"fund_id": fund_id, "snapshot": snapshot},
    )
    bond = dur.mappings().first() or {}
    await db.execute(
        text(
            """
            INSERT INTO fsi.svc_risk_snapshot (
                port_id, as_of_date, total_nav_base, portfolio_duration, portfolio_dv01_base
            ) VALUES (:fund_id, :snapshot, :nav, :duration, :dv01)
            ON CONFLICT (port_id, as_of_date) DO UPDATE
                SET total_nav_base = EXCLUDED.total_nav_base,
                    portfolio_duration = EXCLUDED.portfolio_duration,
                    portfolio_dv01_base = EXCLUDED.portfolio_dv01_base,
                    calc_ts = NOW()
            """
        ),
        {
            "fund_id": fund_id,
            "snapshot": snapshot,
            "nav": nav,
            "duration": bond.get("w_dur"),
            "dv01": bond.get("dv01"),
        },
    )
    await db.commit()
    return snapshot


async def read_reported_exposure(fund_id: str, as_of_date: date, db: AsyncSession) -> dict[str, Any]:
    report_date = await _report_date(db, fund_id, as_of_date)
    source = "svc_risk_exposure"
    if report_date is None:
        report_date = await _materialize(db, fund_id, as_of_date)
        source = "materialized"
    if report_date is None:
        return {
            "fund_id": fund_id,
            "as_of_date": as_of_date,
            "report_date": None,
            "source": source,
            "kpis": [],
        }

    rows = (
        await db.execute(
            text(
                """
                SELECT category,
                       COALESCE(market_value_base, market_value, 0) AS mv
                FROM fsi.svc_risk_exposure
                WHERE port_id = :fund_id
                  AND as_of_date = :report_date
                  AND dimension = 'ASSET_CLASS'
                """
            ),
            {"fund_id": fund_id, "report_date": report_date},
        )
    ).mappings().all()
    snap = (
        await db.execute(
            text(
                """
                SELECT total_nav_base, portfolio_duration, portfolio_dv01_base
                FROM fsi.svc_risk_snapshot
                WHERE port_id = :fund_id AND as_of_date = :report_date
                """
            ),
            {"fund_id": fund_id, "report_date": report_date},
        )
    ).mappings().first() or {}

    gross = sum(abs(_number(row["mv"])) for row in rows)
    net = sum(_number(row["mv"]) for row in rows)
    nav = _number(snap.get("total_nav_base"))
    if not nav:
        nav_row = await db.execute(
            text(
                """
                SELECT net_asset FROM fsi.balance_portfolio_nav
                WHERE port_id = :fund_id AND evaluate_date <= :report_date
                ORDER BY evaluate_date DESC LIMIT 1
                """
            ),
            {"fund_id": fund_id, "report_date": report_date},
        )
        nav = _number(nav_row.scalar_one_or_none())
    ratio = gross / nav if nav else None
    net_ratio = net / nav if nav else None
    duration = snap.get("portfolio_duration")
    fi_mv = sum(_number(row["mv"]) for row in rows if str(row["category"]).startswith("BOND"))

    kpis = [
        _kpi(
            "Gross Exposure",
            "Gross = Σ |MV_i| / NAV",
            {"amount": gross, "ratio": ratio, "pct_nav": ratio * 100.0 if ratio is not None else None},
        ),
        _kpi(
            "Net Exposure",
            "Net = Σ MV_i / NAV",
            {"amount": net, "ratio": net_ratio, "pct_nav": net_ratio * 100.0 if net_ratio is not None else None},
        ),
        _kpi(
            "Leverage",
            "Leverage = Σ |MV_i| / NAV",
            {"ratio": ratio, "pct": ratio * 100.0 if ratio is not None else None},
        ),
        _kpi(
            "Duration",
            "D = Σ (MV_i × D_i) / Σ MV_i",
            {
                "weighted_years": float(duration) if duration is not None else None,
                "fixed_income_mv": fi_mv,
            },
        ),
    ]
    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "report_date": report_date,
        "source": source,
        "kpis": kpis,
    }
