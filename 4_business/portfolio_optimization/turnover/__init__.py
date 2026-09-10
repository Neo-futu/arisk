"""Turnover versus the live / current allocation."""
from __future__ import annotations

from typing import Mapping

from importlib import import_module

_opt = import_module("3_riskengine.adapters.riskfolio.optimizer")


def measure(new_weights: Mapping[str, float], old_weights: Mapping[str, float]) -> float:
    return _opt.turnover(new_weights, old_weights)
