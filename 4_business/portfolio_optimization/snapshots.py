"""Map proposed weights onto the existing ARISK snapshot contract.

Does not create a second holdings master store and never writes fsi.balance_*.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from importlib import import_module
from typing import Any, Mapping

models = import_module("2_processing.tools.risk_testing.models")
Position = models.Position
PortfolioSnapshot = models.PortfolioSnapshot


def current_weights(snapshot: Any) -> dict[str, float]:
    nav = float(snapshot.net_asset or 0.0)
    if nav <= 0:
        nav = sum(abs(float(p.market_value_base)) for p in snapshot.positions)
    if nav <= 0:
        n = max(len(snapshot.positions), 1)
        return {p.security_code: 1.0 / n for p in snapshot.positions}
    return {p.security_code: float(p.market_value_base) / nav for p in snapshot.positions}


def apply_weights(snapshot: Any, weights: Mapping[str, float]) -> Any:
    nav = float(snapshot.net_asset)
    existing = {p.security_code: p for p in snapshot.positions}
    positions = []
    for code, weight in weights.items():
        market_value_base = float(weight) * nav
        if code in existing:
            position = existing[code]
            fx = float(position.fx_rate or 1.0) or 1.0
            positions.append(
                Position(
                    security_code=position.security_code,
                    security_name=position.security_name,
                    asset_class=position.asset_class,
                    currency=position.currency,
                    market_value=market_value_base / fx,
                    market_value_base=market_value_base,
                    duration=position.duration,
                    convexity=position.convexity,
                    ytm=position.ytm,
                    coupon_rate=position.coupon_rate,
                    maturity_date=position.maturity_date,
                    fx_rate=position.fx_rate,
                    metadata=dict(position.metadata),
                )
            )
        else:
            positions.append(
                Position(
                    security_code=str(code),
                    security_name=str(code),
                    asset_class="EQUITY",
                    currency=snapshot.reporting_currency,
                    market_value=market_value_base,
                    market_value_base=market_value_base,
                )
            )
    quality = dict(snapshot.data_quality or {})
    quality["source"] = "simulation_proposal"
    quality["is_live"] = False
    return PortfolioSnapshot(
        fund_id=snapshot.fund_id,
        as_of_date=snapshot.as_of_date,
        reporting_currency=snapshot.reporting_currency,
        net_asset=nav,
        positions=positions,
        nav_returns=list(snapshot.nav_returns),
        data_quality=quality,
    )


def snapshot_from_weights(
    weights: Mapping[str, float],
    *,
    fund_id: str = "SIM",
    as_of: date | None = None,
    nav: float = 1_000_000.0,
    reporting_currency: str = "HKD",
) -> Any:
    as_of_date = as_of or date(2026, 9, 1)
    positions = [
        Position(
            security_code=str(code),
            security_name=str(code),
            asset_class="CASH" if str(code).upper() == "CASH" else "EQUITY",
            currency=reporting_currency,
            market_value=float(weight) * nav,
            market_value_base=float(weight) * nav,
        )
        for code, weight in weights.items()
    ]
    returns = []
    for index in range(120):
        value = ((index % 11) - 5) * 0.0004
        returns.append((as_of_date - timedelta(days=119 - index), value))
    return PortfolioSnapshot(
        fund_id=fund_id,
        as_of_date=as_of_date,
        reporting_currency=reporting_currency,
        net_asset=nav,
        positions=positions,
        nav_returns=returns,
        data_quality={"position_count": len(positions), "source": "weight_construction", "is_live": False},
    )


def clone_snapshot(snapshot: Any, *, fund_id: str | None = None) -> Any:
    cloned = deepcopy(snapshot)
    if fund_id is not None:
        cloned.fund_id = fund_id
    quality = dict(cloned.data_quality or {})
    quality["is_live"] = False
    quality["cloned_from"] = snapshot.fund_id
    cloned.data_quality = quality
    return cloned
