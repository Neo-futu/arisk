"""Wave 6 Limit Engine, governance, pre-trade, authorization and audit tests."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
LIMIT_IDS = import_module("3_riskengine.limits").LIMIT_IDS
STATES = import_module("3_riskengine.limits").STATES


def _limits():
    return import_module("3_riskengine.limits")


def test_limit_catalog_covers_required_dimensions() -> None:
    catalog = _limits().catalog()
    assert tuple(catalog["limit_ids"]) == LIMIT_IDS
    assert catalog["states"] == list(STATES)
    for limit_id in (
        "Position",
        "Issuer",
        "Sector",
        "Country",
        "Currency",
        "Counterparty",
        "Gross Exposure",
        "Net Exposure",
        "Leverage",
        "Liquidity",
        "VaR",
        "CVaR",
        "Drawdown",
        "Derivative Exposure",
    ):
        assert limit_id in catalog["limit_ids"]


def test_sample_snapshot_is_green_under_default_policy() -> None:
    report = _limits().evaluate(sample_snapshot())
    assert report["state"] == "GREEN"
    assert report["passed"] is True
    assert set(report["limits"]) == set(LIMIT_IDS)


def test_boundary_at_limit_is_warning_not_breach() -> None:
    snapshot = sample_snapshot()
    # BOND5Y is 60% NAV; sitting exactly on the limit is still inside.
    report = _limits().evaluate(snapshot, policy={"Position": 0.60})
    assert report["limits"]["Position"]["utilization"] == pytest.approx(1.0)
    assert report["limits"]["Position"]["state"] == "WARNING"
    assert report["state"] == "WARNING"


def test_warning_band_before_limit() -> None:
    report = _limits().evaluate(sample_snapshot(), policy={"Position": 0.70})
    util = report["limits"]["Position"]["utilization"]
    assert 0.8 <= util <= 1.0
    assert report["limits"]["Position"]["state"] == "WARNING"


def test_breach_just_over_limit() -> None:
    report = _limits().evaluate(sample_snapshot(), policy={"Position": {"limit": 0.59, "hard": 1.5}})
    assert report["limits"]["Position"]["utilization"] > 1.0
    assert report["limits"]["Position"]["state"] == "BREACH"
    assert report["state"] == "BREACH"
    assert report["passed"] is False


def test_hard_breach() -> None:
    report = _limits().evaluate(sample_snapshot(), policy={"Position": {"limit": 0.40, "hard": 1.1}})
    assert report["limits"]["Position"]["state"] == "HARD_BREACH"
    assert report["state"] == "HARD_BREACH"
    assert report["passed"] is False


def test_liquidity_min_breach() -> None:
    # Sample cash/liquid is 10% NAV.
    report = _limits().evaluate(
        sample_snapshot(),
        policy={"Liquidity": {"limit": 0.20, "direction": "MIN", "hard": 3.0}},
    )
    assert report["limits"]["Liquidity"]["state"] == "BREACH"


def test_same_limit_engine_used_by_three_businesses() -> None:
    snapshot = sample_snapshot()
    policy = {"Position": {"limit": 0.50, "hard": 1.5}}
    engine_report = _limits().evaluate(snapshot, policy=policy)
    ir = import_module("4_business.investment_risk.service").compute_kpi_pack(snapshot)
    assert ir["limit_engine"] == "3_riskengine.limits"
    assert ir["limits"]["state"] == "GREEN"  # default policy on KPI pack
    po = import_module("4_business.portfolio_optimization.service")
    review = po.optimize_and_govern(snapshot, "construction")
    assert review["limits"]["engine"] == ir["limits"]["engine"]
    assert "portfolio" in review["limits"]
    rt = import_module("4_business.risk_testing.service")
    stamped = rt._stamp_riskengine({"analytic": "SENSITIVITY"}, snapshot, "SENSITIVITY")
    assert stamped["limit_engine"] == "3_riskengine.limits"
    assert stamped["limits"]["limit_ids"] == engine_report["limit_ids"]
    gov = import_module("4_business.risk_governance.limits")
    assert gov.run(snapshot, policy=policy)["state"] == engine_report["state"]


def test_pre_trade_approve_warning_reject() -> None:
    pre = import_module("4_business.risk_governance.pre_trade")
    snapshot = sample_snapshot()
    modest = pre.run_pre_trade(
        snapshot,
        {"security_code": "CASH", "side": "BUY", "amount": 1.0, "asset_class": "CASH"},
    )
    assert modest["decision"] == "APPROVE"
    assert modest["gate"][-1] == "limit"
    assert modest["is_trade_instruction"] is False
    assert modest["valuation"]["base_pv"] > 0
    assert modest["risk"]["analytic"] == "SENSITIVITY"
    assert modest["stress"]["analytic"] == "STRESS"

    warning = pre.run_pre_trade(
        snapshot,
        {"security_code": "BOND5Y", "side": "BUY", "amount": 1_000.0, "asset_class": "BOND"},
        policy={"Position": 0.70},
    )
    assert warning["decision"] == "WARNING"

    reject = pre.run_pre_trade(
        snapshot,
        {"security_code": "BOND5Y", "side": "BUY", "amount": 50_000.0, "asset_class": "BOND"},
        policy={"Position": {"limit": 0.50, "hard": 1.5}},
    )
    assert reject["decision"] == "REJECT"
    assert reject["state"] == "BREACH"

    hard = pre.run_pre_trade(
        snapshot,
        {"security_code": "BOND5Y", "side": "BUY", "amount": 200_000.0, "asset_class": "BOND"},
        policy={"Position": {"limit": 0.40, "hard": 1.1}},
        exception_approved=True,
    )
    assert hard["state"] == "HARD_BREACH"
    assert hard["decision"] == "REJECT"


def test_authorization_blocks_unsigned_governance() -> None:
    gov = import_module("4_business.risk_governance.service")
    cases = gov.GovernanceCases()
    evaluation = _limits().evaluate(sample_snapshot(), policy={"Position": {"limit": 0.50, "hard": 1.5}})
    opened = cases.open_from_evaluation(evaluation, fund_id="TEST001")
    with pytest.raises(gov.Unauthorized):
        cases.request_exception(opened["case_id"], "desk request", authorized=False)
    with pytest.raises(gov.Unauthorized):
        cases.approve(opened["case_id"], authorized=False)
    with pytest.raises(gov.Unauthorized):
        cases.close(opened["case_id"], authorized=False)
    cases.request_exception(opened["case_id"], "desk request", authorized=True)
    cases.approve(opened["case_id"], authorized=True)
    cases.close(opened["case_id"], authorized=True)
    assert cases.get(opened["case_id"])["closed"] is True


def test_hard_breach_cannot_be_excepted() -> None:
    gov = import_module("4_business.risk_governance.service")
    cases = gov.GovernanceCases()
    evaluation = _limits().evaluate(sample_snapshot(), policy={"Position": {"limit": 0.40, "hard": 1.1}})
    opened = cases.open_from_evaluation(evaluation)
    with pytest.raises(gov.HardBreachLocked):
        cases.request_exception(opened["case_id"], "please", authorized=True)


def test_audit_records_and_persists(tmp_path: Path) -> None:
    audit_mod = import_module("4_business.risk_governance.audit_log")
    path = tmp_path / "audit.json"
    log = audit_mod.AuditLog(path)
    pre = import_module("4_business.risk_governance.pre_trade")
    pre.run_pre_trade(
        sample_snapshot(),
        {"security_code": "CASH", "side": "BUY", "amount": 1.0, "asset_class": "CASH"},
        audit=log,
        actor="tester",
    )
    assert log.entries("PRE_TRADE")
    log.persist()
    reloaded = audit_mod.AuditLog(path)
    assert reloaded.entries("PRE_TRADE")[0]["actor"] == "tester"


def test_governance_modules_importable() -> None:
    domains = import_module("4_business.risk_governance.domains")
    for name in domains.MODULES:
        assert import_module(f"4_business.risk_governance.{name}") is not None
    policy = import_module("4_business.risk_governance.policy").run()
    assert policy["engine"] == "3_riskengine.limits"


def test_pre_trade_route_exists_without_breaking_var() -> None:
    router = import_module("2_processing.api.routers.risk")
    paths = {route.path for route in router.router.routes}
    assert "/var/{fund_id}" in paths
    assert "/exposure/{fund_id}" in paths
    assert "/pre-trade" in paths
    assert "/limits/catalog" in paths


def test_proposed_trade_does_not_mutate_live() -> None:
    proposed_mod = import_module("4_business.trading.proposed")
    live = sample_snapshot()
    cash_before = next(p.market_value_base for p in live.positions if p.asset_class == "CASH")
    cloned = proposed_mod.apply_proposed_trade(
        live,
        {"security_code": "US_EQ", "side": "BUY", "amount": 10_000, "asset_class": "EQUITY"},
    )
    cash_after_live = next(p.market_value_base for p in live.positions if p.asset_class == "CASH")
    cash_after_sim = next(p.market_value_base for p in cloned.positions if p.asset_class == "CASH")
    assert cash_after_live == pytest.approx(cash_before)
    assert cash_after_sim == pytest.approx(cash_before - 10_000)
