"""Built-in historical and hypothetical stress scenario catalogue."""
from __future__ import annotations

from importlib import import_module

_catalog = import_module("3_riskengine.scenario.catalog")
SCENARIOS = _catalog.SCENARIOS
scenario_catalog = _catalog.scenario_catalog
