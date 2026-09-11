"""Explicit FinancePy valuation adapter — compatibility re-export.

Wave 3 moved the vendor import into ``3_riskengine.adapters.financepy``.
This module keeps the historical import path used by Risk Testing reports.
"""
from __future__ import annotations

from importlib import import_module

_fp = import_module("3_riskengine.adapters.financepy")

FinancePyValuationAdapter = _fp.FinancePyValuationAdapter
FinancePyAdapter = _fp.FinancePyAdapter
FINANCEPY_FLAT_CURVE_CLASS = _fp.FINANCEPY_FLAT_CURVE_CLASS
FINANCEPY_CORE_CALLS = _fp.FINANCEPY_CORE_CALLS
financepy_usage = _fp.financepy_usage

__all__ = [
    "FINANCEPY_CORE_CALLS",
    "FINANCEPY_FLAT_CURVE_CLASS",
    "FinancePyAdapter",
    "FinancePyValuationAdapter",
    "financepy_usage",
]
