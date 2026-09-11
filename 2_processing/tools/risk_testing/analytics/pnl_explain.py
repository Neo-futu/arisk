"""PnL Explain business module."""
from __future__ import annotations

from typing import Any

from ..engine import ProfessionalRiskEngine
from ..models import PortfolioSnapshot
from .common import implemented_by


def run(
    engine: ProfessionalRiskEngine,
    previous_snapshot: PortfolioSnapshot,
) -> dict[str, Any]:
    """Reconcile PnL into carry, rates, FX, position and residual effects."""

    return implemented_by(
        engine.pnl_explain(previous_snapshot),
        "risk_testing.analytics.pnl_explain.run",
        [],
        "snapshot-to-snapshot PnL reconciliation using FinancePy-valued position inputs",
    )
