"""风险预算与前置试算：经 RiskEngine（FinancePy / Riskfolio / ORE·QuantLib）。

口径委托 ``3_riskengine.risk.pretrade`` 独立模型包；本层只负责：
- 装载 PortfolioSnapshot
- 从规则引擎加载前置限额
- 从持仓表汇总发行人 / 债券久期统计（与限额口径一致）
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..risk.rule_limits import load_effective_pretrade_limits
from .investment_analysis_common import _number

logger = logging.getLogger(__name__)


async def compute_pretrade_risk_budget(
    fund_id: str,
    as_of_date: date,
    trade_amount: float,
    trade_side: str,
    asset_class: str,
    duration_years: float,
    issuer_name: str,
    db: AsyncSession,
) -> dict[str, Any]:
    from importlib import import_module

    loader = import_module("2_processing.tools.risk_testing.loader")
    engine_mod = import_module("3_riskengine")

    snapshot = await loader.load_portfolio_snapshot(fund_id, as_of_date, db, lookback_days=500)
    nav, bond_stats = await _bond_issuer_stats(db, fund_id, as_of_date, snapshot.net_asset)

    configured_limits, applied_rules = await load_effective_pretrade_limits(
        db=db,
        fund_id=fund_id,
        as_of_date=as_of_date,
        asset_class=asset_class,
        trade_side=str(trade_side or "BUY").upper(),
    )

    pack = (
        engine_mod.RiskEngine()
        .bind(snapshot)
        .risk()
        .pretrade_budget(
            trade_amount=trade_amount,
            trade_side=trade_side,
            asset_class=asset_class,
            duration_years=duration_years,
            issuer_name=issuer_name,
            limits=configured_limits,
            bond_stats=bond_stats,
            nav=nav,
            confidence=0.99,
            applied_rules=applied_rules,
        )
    )
    pack["fund_id"] = fund_id
    pack["as_of_date"] = as_of_date
    return pack


async def _bond_issuer_stats(
    db: AsyncSession,
    fund_id: str,
    as_of: date,
    fallback_nav: float,
) -> tuple[float, dict[str, Any]]:
    nav_result = await db.execute(
        text(
            """
            SELECT net_asset
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id AND evaluate_date <= :as_of_date
            ORDER BY evaluate_date DESC
            LIMIT 1
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of},
    )
    nav = _number(nav_result.scalar_one_or_none(), fallback_nav)

    bonds_result = await db.execute(
        text(
            """
            WITH latest AS (
                SELECT MAX(evaluate_date) AS value
                FROM fsi.balance_bond
                WHERE port_id = :fund_id AND evaluate_date <= :as_of_date
            )
            SELECT COALESCE(issuer_name, 'UNKNOWN_ISSUER') AS issuer_name,
                   COALESCE(market_value_base, market_value, 0) AS market_value,
                   COALESCE(duration, 0) AS duration
            FROM fsi.balance_bond
            WHERE port_id = :fund_id AND evaluate_date = (SELECT value FROM latest)
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of},
    )
    bonds = [dict(row) for row in bonds_result.mappings().all()]
    bond_mv = sum(_number(row["market_value"]) for row in bonds)
    duration_num = sum(_number(row["market_value"]) * _number(row["duration"]) for row in bonds)
    duration = duration_num / bond_mv if bond_mv else 0.0
    issuer_mv: dict[str, float] = defaultdict(float)
    for row in bonds:
        issuer_mv[str(row["issuer_name"])] += _number(row["market_value"])
    return nav, {
        "bond_mv": bond_mv,
        "duration": duration,
        "duration_num": duration_num,
        "issuer_mv": issuer_mv,
    }
