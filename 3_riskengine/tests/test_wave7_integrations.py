"""Wave 7 integration layer, Quant API, adapter guards, trading and operations."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
SYSTEMS = import_module("5_integrations").SYSTEMS
QUANT = import_module("5_integrations.quant")
BASE = import_module("5_integrations.base")


def test_quant_api_contract_methods() -> None:
    snapshot = sample_snapshot()
    catalog = QUANT.catalog()
    assert set(catalog["channels"]) == {"Python", "Jupyter", "CLI", "REST"}
    assert QUANT.risk.portfolio(snapshot)["fund_id"] == snapshot.fund_id
    assert QUANT.risk.exposure(snapshot)["analytic"] == "EXPOSURE"
    assert QUANT.risk.var(snapshot)["kpi"] == "VaR"
    assert QUANT.risk.cvar(snapshot)["kpi"] == "CVaR"
    assert QUANT.risk.stress(snapshot)["analytic"] == "STRESS"
    assert QUANT.risk.liquidity(snapshot)["kpi"] == "Liquidity"
    assert QUANT.risk.counterparty(snapshot)["kpi"] == "Counterparty Exposure"
    opt = QUANT.portfolio.optimize(snapshot, "construction")
    assert opt["is_trade_instruction"] is False
    sim = QUANT.portfolio.simulate(snapshot)
    assert sim["is_live"] is False
    assert QUANT.valuation.price(snapshot)["base_pv"] > 0
    ran = QUANT.testing.run(snapshot)
    assert ran["analytic"] == "SENSITIVITY"
    jupyter = import_module("5_integrations.quant.jupyter")
    assert "Python" in jupyter.contract()["channels"]


def test_quant_cli_and_rest_routes() -> None:
    cli = import_module("5_integrations.quant.cli")
    assert cli.main(["risk", "var"]) == 0
    router = import_module("2_processing.api.routers.quant")
    paths = {route.path for route in router.router.routes}
    assert "/catalog" in paths
    assert "/{namespace}/{method}" in paths
    processing = import_module("2_processing.api.main")
    mounted = {getattr(route, "path", "") for route in processing.app.routes}
    assert any("/quant" in path for path in mounted)


def test_all_external_adapters_map_to_contract() -> None:
    registry = import_module("5_integrations.registry")
    ctx = BASE.AdapterContext()
    for system in SYSTEMS:
        if system == "quant":
            continue
        adapter = registry.get_adapter(system)
        result = adapter.pull({"fund_id": "TEST001"}, context=ctx)
        assert result.ok is True
        record = result.record
        assert record.source == system
        contracts = import_module("5_integrations.contracts")
        assert contracts.verify_integrity(record) is True


def test_adapter_auth_and_permission() -> None:
    oms = import_module("5_integrations.oms").OMSAdapter()
    denied = oms.push(
        {"security_code": "US_EQ", "amount": 1},
        context=BASE.AdapterContext(authorized=False),
    )
    assert denied.ok is False
    assert denied.error["code"] == "AUTH"
    forbidden = oms.push(
        {"security_code": "US_EQ", "amount": 1},
        context=BASE.AdapterContext(authorized=True, permissions=frozenset({"portfolio.view"})),
    )
    assert forbidden.ok is False
    assert forbidden.error["code"] == "PERMISSION"


def test_data_integrity_and_failure_and_retry() -> None:
    md = import_module("5_integrations.market_data").MarketDataAdapter()
    bad = md.pull({"_corrupt": True, "universe": ["AAA", "BBB"]})
    assert bad.ok is False
    assert bad.error["code"] == "INTEGRITY"

    timeout = import_module("5_integrations.pms").PMSAdapter(fail_mode="timeout")
    failed = timeout.pull({"fund_id": "TEST001"}, context=BASE.AdapterContext(attempts=2))
    assert failed.ok is False
    assert failed.error["code"] == "UNAVAILABLE"
    assert failed.attempts == 2

    retrying = import_module("5_integrations.pms").PMSAdapter(transient_failures=2)
    recovered = retrying.pull({"fund_id": "TEST001"}, context=BASE.AdapterContext(attempts=3))
    assert recovered.ok is True
    assert recovered.attempts == 3


def test_adapter_audit_trail() -> None:
    audit_mod = import_module("4_business.risk_governance.audit_log")
    log = audit_mod.AuditLog()
    adapter = import_module("5_integrations.custodian").CustodianAdapter(audit=log)
    adapter.pull({"fund_id": "TEST001"})
    events = log.entries("ADAPTER_PULL")
    assert events
    assert events[-1]["payload"]["system"] == "custodian"
    assert events[-1]["payload"]["ok"] is True


def test_business_does_not_call_vendor_sdks() -> None:
    trading = (ROOT / "4_business" / "trading" / "lifecycle.py").read_text(encoding="utf-8")
    operations = (ROOT / "4_business" / "operations" / "service.py").read_text(encoding="utf-8")
    for text in (trading, operations):
        assert "import yfinance" not in text
        assert "import openbb" not in text
        assert "5_integrations.registry" in text or "5_integrations" in text


def test_trading_order_execution_position_pre_post() -> None:
    trading = import_module("4_business.trading.service")
    snapshot = sample_snapshot()
    order = {"security_code": "CASH", "side": "BUY", "amount": 1.0, "asset_class": "CASH"}
    submitted = trading.submit_order(snapshot, order)
    assert submitted["status"] == "ACCEPTED_SIM"
    assert submitted["pre_trade"]["decision"] == "APPROVE"
    assert submitted["order"]["ok"] is True
    assert submitted["execution"]["ok"] is True
    assert submitted["is_trade_instruction"] is False
    pos = trading.position(snapshot)
    assert pos["ok"] is True
    post = trading.post_trade(snapshot, order)
    assert post["is_live"] is False
    rejected = trading.submit_order(
        snapshot,
        {"security_code": "BOND5Y", "side": "BUY", "amount": 200_000, "asset_class": "BOND"},
        policy={"Position": {"limit": 0.40, "hard": 1.1}},
    )
    assert rejected["status"] == "REJECTED"


def test_operations_pack_uses_adapters() -> None:
    ops = import_module("4_business.operations.service")
    pack = ops.pack(sample_snapshot())
    assert pack["valuation"]["base_pv"] > 0
    assert pack["nav"]["fund_admin"]["ok"] is True
    assert pack["custodian"]["ok"] is True
    assert pack["fund_accounting"]["ok"] is True
    assert "pnl" in pack


def test_quant_session_call() -> None:
    api = QUANT.QuantAPI(sample_snapshot())
    priced = api.call("valuation", "price")
    assert priced["base_pv"] > 0
