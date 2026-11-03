"""3_riskengine.pnl — snapshot explain + 业绩归因模型。"""

from .api import PnLAPI, explain
from .attribution import (
    BUSINESS_MODULES as ATTRIBUTION_MODULES,
    brinson,
    campisi,
    contribution,
    fundamentals as attribution_fundamentals,
    verify_business_modules as verify_attribution_modules,
)

__all__ = [
    "ATTRIBUTION_MODULES",
    "PnLAPI",
    "attribution_fundamentals",
    "brinson",
    "campisi",
    "contribution",
    "explain",
    "verify_attribution_modules",
]
