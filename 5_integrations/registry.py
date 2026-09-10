"""Registry of external-system adapters. Business looks up adapters here."""
from __future__ import annotations

from typing import Any

from .accounting import AccountingAdapter
from .broker import BrokerAdapter
from .custodian import CustodianAdapter
from .ems import EMSAdapter
from .fund_admin import FundAdminAdapter
from .market_data import MarketDataAdapter
from .oms import OMSAdapter
from .pms import PMSAdapter

ADAPTERS = {
    "market_data": MarketDataAdapter,
    "pms": PMSAdapter,
    "oms": OMSAdapter,
    "ems": EMSAdapter,
    "broker": BrokerAdapter,
    "custodian": CustodianAdapter,
    "fund_admin": FundAdminAdapter,
    "accounting": AccountingAdapter,
}


def get_adapter(system: str, **kwargs: Any):
    try:
        cls = ADAPTERS[system]
    except KeyError as exc:
        known = ", ".join(sorted(ADAPTERS))
        raise KeyError(f"Unknown external system {system!r}. Known: {known}") from exc
    return cls(**kwargs)
