"""Jupyter helper. Same Quant API as Python; load with %load_ext 5_integrations.quant.jupyter"""
from __future__ import annotations

from .api import QUANT_CONTRACT, catalog, portfolio, risk, testing, valuation


def load_ipython_extension(ipython) -> None:
    ipython.push(
        {
            "risk": risk,
            "portfolio": portfolio,
            "valuation": valuation,
            "testing": testing,
            "quant_catalog": catalog,
        }
    )


def contract() -> dict:
    return dict(QUANT_CONTRACT)
