"""Index / benchmark path: mktdata_index_quotes wiring + Beta / TE."""
from __future__ import annotations

from datetime import date, timedelta
from importlib import import_module


def test_market_tables_include_index_quotes() -> None:
    market = import_module("3_riskengine.market")
    assert "fsi.mktdata_index_quotes" in market.MARKET_TABLES


def test_daily_returns_from_index_levels() -> None:
    market = import_module("3_riskengine.market")
    start = date(2026, 1, 1)
    levels = [(start + timedelta(days=i), 100.0 + i) for i in range(5)]
    returns = market.daily_returns(levels)
    assert len(returns) == 4
    assert returns[0][1] == (101.0 / 100.0) - 1.0


def test_attach_benchmark_feeds_kpis() -> None:
    market = import_module("3_riskengine.market")
    fx = import_module("3_riskengine.tests.fixtures")
    snapshot = fx.sample_snapshot()
    pack = {
        "benchmark_id": "HSI",
        "index_levels": list(snapshot.index_levels),
        "benchmark_returns": list(zip((d for d, _ in snapshot.nav_returns), snapshot.benchmark_returns)),
        "source_table": "fsi.mktdata_index_quotes",
        "warnings": [],
    }
    # Clear then re-attach via public helper.
    snapshot.benchmark_id = None
    snapshot.benchmark_returns = []
    market.attach_benchmark(snapshot, pack)
    assert snapshot.benchmark_id == "HSI"
    assert len(snapshot.benchmark_returns) == len(snapshot.nav_returns)

    bound = import_module("3_riskengine").RiskEngine().bind(snapshot)
    market_obj = bound.market()
    assert market_obj.macro.get("benchmark_id") == "HSI"
    pack_kpi = bound.risk().kpis()
    assert pack_kpi["benchmark_id"] == "HSI"
    beta = pack_kpi["kpis"]["Beta"]["result"]["beta"]
    te = pack_kpi["kpis"]["Tracking Error"]["result"]["annualized"]
    assert beta is not None
    assert te is not None
    assert pack_kpi["kpis"]["Beta"]["input"]["paired"] >= 3
