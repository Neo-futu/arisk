#!/usr/bin/env python
"""ARISK 机构投资与风险闭环 — 编排入口。

量化全部嵌入 ``riskengine`` 包（``config`` / ``objects`` / ``main``）。
本文件只做：加载快照、按闭环调引擎、以及 4_business 的仿真/预交易/交易。

闭环::

    Market Data → Portfolio/Position → Valuation → Investment Risk
      → Portfolio Optimization → Simulation → Risk Testing → Limits
      → Pre-Trade → Trading → Position → Valuation → Continuous Risk

在仓库根 ``arisk/``::

    python -m riskengine                              # 先单独开发/验证引擎（夹具）
    python -m riskengine --fund-id BHMMF001 --as-of-date 2026-09-01
    python 3_riskengine/scripts/platform_workflow.py  # 再嵌入闭环
    python 3_riskengine/scripts/platform_workflow.py --fund-id BHMMF001 --as-of-date 2026-09-01
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importlib import import_module

import riskengine as re

_ir = import_module("4_business.investment_risk.service")
_opt = import_module("4_business.portfolio_optimization.service")
_pre = import_module("4_business.risk_governance.pre_trade")
_trade = import_module("4_business.trading.lifecycle")
_sim_store = import_module("4_business.portfolio_optimization.simulation.store")
_proposed = import_module("4_business.trading.proposed")

Engine = re.Engine
BoundEngine = re.BoundEngine
SliceSpec = re.SliceSpec
DEFAULT_SLICE = re.DEFAULT_SLICE
CANONICAL_TABLES = re.CANONICAL_TABLES

DEMO_ORDER = {
    "security_code": "BOND5Y",
    "side": "BUY",
    "amount": 10_000.0,
    "asset_class": "BOND",
    "currency": "HKD",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def _header(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _demo_order(book: BoundEngine) -> dict[str, Any]:
    """夹具用 BOND5Y；活仓用第一只持仓做小额拟买。"""

    codes = {p.security_code for p in book.snapshot.positions}
    if DEMO_ORDER["security_code"] in codes:
        return dict(DEMO_ORDER)
    first = book.snapshot.positions[0]
    return {
        "security_code": first.security_code,
        "side": "BUY",
        "amount": min(10_000.0, abs(float(first.market_value_base)) * 0.01 or 1_000.0),
        "asset_class": first.asset_class,
        "currency": first.currency,
    }


def step_market(book: BoundEngine) -> dict[str, Any]:
    market = book.market()
    macro = dict(getattr(market, "macro", None) or {})
    payload = {
        "valuation_date": str(market.valuation_date),
        "kind": macro.get("market_data_kind"),
        "prices": dict(list(market.prices.items())[:12]),
        "n_prices": len(market.prices),
        "fx": dict(market.fx),
        "quote_dates": dict(list((macro.get("quote_dates") or {}).items())[:8]),
        "sources": dict(list((macro.get("sources") or {}).items())[:8]),
        "missing": macro.get("missing") or [],
        "stale": (macro.get("stale") or [])[:5],
        "abnormal": (macro.get("abnormal") or [])[:5],
        "warnings": (macro.get("warnings") or [])[:12],
        "curve_keys": sorted(k for k in market.curves.keys() if not callable(market.curves[k])),
        "nav_points": len(getattr(book.snapshot, "nav_returns", ()) or ()),
        "tables": CANONICAL_TABLES,
    }
    _header("1. Market Data  (riskengine / fsi.mktdata_* + optional OpenBB)")
    print(_json({k: v for k, v in payload.items() if k != "tables"}))
    print("  canonical tables:", payload["tables"])
    book.print_market_alerts()
    return payload


def step_position(book: BoundEngine) -> dict[str, Any]:
    snapshot = book.snapshot
    rows = book.holdings_summary()
    payload = {
        "fund_id": snapshot.fund_id,
        "as_of_date": str(snapshot.as_of_date),
        "reporting_currency": snapshot.reporting_currency,
        "net_asset": snapshot.net_asset,
        "data_quality": dict(snapshot.data_quality or {}),
        "positions": rows[:30],
        "n_positions": len(rows),
        "product_view": [p.kind.value for p in book.products("PRODUCT")],
        "trade_ids": [t.trade_id for t in book.trades()][:30],
    }
    _header("2. Portfolio / Position  (riskengine)")
    print(_json(payload))
    return payload


def step_valuation(book: BoundEngine, slice_spec: SliceSpec = DEFAULT_SLICE) -> dict[str, Any]:
    priced = book.price("LOOK_THROUGH")
    revalued = book.revalue((slice_spec.shock,))
    flows = book.cashflows("LOOK_THROUGH")
    by_code = {row["security_code"]: row for row in priced.trade_values}
    shocked = {row["security_code"]: row for row in revalued.trade_values}
    payload = {
        "base_pv": priced.base_pv,
        "net_asset": book.snapshot.net_asset,
        "engine": priced.context.get("engine"),
        "rows": [
            {
                "security_code": code,
                "asset_class": row.get("asset_class"),
                "engine": row.get("engine"),
                "base_pv": row.get("base_pv"),
                "shocked_pv": shocked.get(code, {}).get("shocked_pv"),
                "pnl": shocked.get(code, {}).get("pnl"),
            }
            for code, row in list(by_code.items())[:20]
        ],
        "cashflow_products": len(flows.get("products") or []),
    }
    _header("3. Valuation  (riskengine)")
    print(_json(payload))
    return payload


def step_investment_risk(book: BoundEngine) -> dict[str, Any]:
    kpis = book.kpis()
    platform_pack = _ir.compute_kpi_pack(book.snapshot)
    selected = {
        name: pack.get("result")
        for name, pack in (kpis.get("kpis") or {}).items()
        if name in {"VaR", "CVaR", "Duration", "DV01", "KRD", "Gross Exposure", "Liquidity"}
    }
    payload = {
        "engine": kpis.get("engine"),
        "kpis": selected,
        "liquidity_buckets": (book.liquidity_buckets() or {}).get("buckets"),
        "counterparty_cva": book.xva().get("cva"),
        "platform_kpi_engine": platform_pack.get("engine"),
    }
    _header("4. Investment Risk  (riskengine + 4_business catalog)")
    print(_json(payload))
    return payload


def step_optimize(book: BoundEngine) -> dict[str, Any]:
    hrp = book.optimize("hrp")
    governed = _opt.optimize_and_govern(book.snapshot, "hrp")
    payload = {
        "book_method": hrp.get("method") or hrp.get("analytic"),
        "book_weights": dict(list((hrp.get("weights") or {}).items())[:12]),
        "ready_for_review": governed.get("ready_for_review"),
        "is_trade_instruction": governed.get("is_trade_instruction"),
        "limit_state": (governed.get("limits") or {}).get("state"),
    }
    _header("5. Portfolio Optimization  (riskengine Riskfolio + 4_business gate)")
    print(_json(payload))
    return payload


def step_simulation(book: BoundEngine) -> dict[str, Any]:
    store = _sim_store.SimulationStore()
    cloned = _opt.clone_live(book.snapshot, label="workflow-dev", store=store)
    payload = {
        "sim_id": cloned.get("sim_id"),
        "kind": cloned.get("kind"),
        "live_fund_id": cloned.get("live_fund_id"),
        "is_trade_instruction": cloned.get("is_trade_instruction", False),
    }
    _header("6. Simulation  (4_business, no live write)")
    print(_json(payload))
    return payload


def step_risk_testing(book: BoundEngine, slice_spec: SliceSpec = DEFAULT_SLICE) -> dict[str, Any]:
    sensitivity = book.sensitivity((re.shock_rate(1.0), re.shock_equity(0.01)))
    payload = {
        "sensitivity": sensitivity,
        "scenario": book.scenario(slice_spec.scenario_id),
        "stress": book.stress("gfc_2008"),
        "krd": book.krd(1.0),
        "xva": book.xva(),
        "var_backtest": book.var_backtest(0.99, 60) if book.snapshot.nav_returns else None,
    }
    if book.snapshot.fund_id == "TEST001":
        previous = re.load_book("mixed", date(2026, 8, 1), equity_value=280_000.0)
        payload["pnl_explain"] = book.pnl_explain(previous)
    brief = {
        "sensitivity_analytic": payload["sensitivity"].get("analytic"),
        "scenario_id": slice_spec.scenario_id,
        "scenario_pnl": payload["scenario"].get("pnl"),
        "stress_pnl": payload["stress"].get("pnl"),
        "krd_portfolio_pv01": payload["krd"].get("portfolio_pv01"),
        "xva_cva": payload["xva"].get("cva"),
        "var_backtest_status": (payload["var_backtest"] or {}).get("status"),
        "ore_app": payload["xva"].get("ore_app"),
    }
    _header("7. Risk Testing  (riskengine)")
    print(_json(brief))
    return payload


def step_limits(book: BoundEngine) -> dict[str, Any]:
    limits = book.limits()
    review = book.governance()
    payload = {
        "limit_state": limits.get("state"),
        "passed": limits.get("passed"),
        "governance_passed": review.get("passed"),
        "is_trade_instruction": review.get("is_trade_instruction"),
        "pricing_status": book.validation_pricing().status,
    }
    try:
        cross = book.cross_engine()
        payload["cross_engine_status"] = cross.status
        payload["cross_engine_checks"] = [
            {"name": item.get("name"), "passed": item.get("passed")} for item in cross.checks
        ]
    except Exception as exc:  # noqa: BLE001
        payload["cross_engine_error"] = str(exc)
    _header("8. Limits / Governance  (riskengine)")
    print(_json(payload))
    return payload


def step_pre_trade(book: BoundEngine, order: dict[str, Any] | None = None) -> dict[str, Any]:
    order = order or _demo_order(book)
    report = _pre.run_pre_trade(book.snapshot, order)
    payload = {
        "decision": report.get("decision"),
        "state": report.get("state"),
        "is_trade_instruction": report.get("is_trade_instruction"),
        "order": report.get("order"),
        "proposed_nav": (report.get("proposed") or {}).get("net_asset"),
        "valuation_pv": (report.get("valuation") or {}).get("base_pv"),
    }
    _header("9. Pre-Trade  (4_business → riskengine)")
    print(_json(payload))
    return report


def step_trading(book: BoundEngine, order: dict[str, Any] | None = None) -> dict[str, Any]:
    order = order or _demo_order(book)
    submitted = _trade.submit_order(book.snapshot, order)
    post = _trade.post_trade(book.snapshot, order)
    position = _trade.current_position(book.snapshot)
    payload = {
        "submit_status": submitted.get("status"),
        "is_trade_instruction": submitted.get("is_trade_instruction"),
        "post_decision": post.get("decision"),
        "post_state": post.get("state"),
        "pms": position,
    }
    _header("10. Trading / Position  (4_business adapters)")
    print(_json(payload))
    return {"submit": submitted, "post": post, "position": position}


def step_continuous(book: BoundEngine, order: dict[str, Any] | None = None) -> dict[str, Any]:
    order = order or _demo_order(book)
    proposed = _proposed.apply_proposed_trade(book.snapshot, order)
    after = Engine().bind(proposed)
    priced = after.price()
    payload = {
        "proposed_positions": len(proposed.positions),
        "proposed_base_pv": priced.base_pv,
        "dv01": after.dv01().get("result"),
        "is_live": (proposed.data_quality or {}).get("is_live"),
    }
    _header("11. Continuous Risk  (riskengine on proposed book)")
    print(_json(payload))
    return payload


def step_slice(book: BoundEngine, slice_spec: SliceSpec = DEFAULT_SLICE) -> dict[str, Any]:
    _header(
        f"Slice  {slice_spec.asset_class} / {slice_spec.product_kind} / "
        f"{slice_spec.kpi} / {slice_spec.scenario_id}  (riskengine.verify_slice)"
    )
    print(f"  {re.RISKENGINE_NAME} {re.RISKENGINE_VERSION}")
    report = re.verify_slice(book, slice_spec)
    if report.get("skipped"):
        print(f"  skip: {report.get('reason') or report.get('kinds')}")
        return report
    print("  security:", report.get("security_code"))
    print("  slice passed:" if report.get("passed") else "  slice FAILED")
    return report


STAGES: dict[str, str] = {
    "market": "Market Data",
    "position": "Portfolio / Position",
    "valuation": "Valuation",
    "investment-risk": "Investment Risk",
    "optimize": "Portfolio Optimization",
    "simulation": "Simulation",
    "risk-testing": "Risk Testing",
    "limits": "Limits / Governance",
    "pre-trade": "Pre-Trade",
    "trading": "Trading / Position",
    "continuous": "Continuous Risk",
    "slice": "Single-cell verification",
    "all": "Full closed loop",
}


def run_stage(name: str, book: BoundEngine, slice_spec: SliceSpec) -> Any:
    runners: dict[str, Callable[..., Any]] = {
        "market": lambda: step_market(book),
        "position": lambda: step_position(book),
        "valuation": lambda: step_valuation(book, slice_spec),
        "investment-risk": lambda: step_investment_risk(book),
        "optimize": lambda: step_optimize(book),
        "simulation": lambda: step_simulation(book),
        "risk-testing": lambda: step_risk_testing(book, slice_spec),
        "limits": lambda: step_limits(book),
        "pre-trade": lambda: step_pre_trade(book),
        "trading": lambda: step_trading(book),
        "continuous": lambda: step_continuous(book),
        "slice": lambda: step_slice(book, slice_spec),
    }
    if name not in runners:
        raise SystemExit(f"unknown stage {name!r}; choose from {sorted(STAGES)}")
    return runners[name]()


def run_all(book: BoundEngine, slice_spec: SliceSpec) -> dict[str, Any]:
    results = {}
    for name in (
        "market",
        "position",
        "valuation",
        "investment-risk",
        "optimize",
        "simulation",
        "risk-testing",
        "limits",
        "pre-trade",
        "trading",
        "continuous",
        "slice",
    ):
        results[name] = run_stage(name, book, slice_spec)
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ARISK platform closed loop; quant engine is riskengine package.")
    parser.add_argument("--book", choices=sorted(re.BOOKS), default="mixed")
    parser.add_argument("--fund-id", default=None, help="live portfolio from fsi.*; overrides --book")
    parser.add_argument("--as-of-date", default=None, help="YYYY-MM-DD for live load")
    parser.add_argument("--lookback-days", type=int, default=re.DEFAULT_LOOKBACK_DAYS)
    parser.add_argument(
        "--market-source",
        choices=["db", "openbb"],
        default=re.DEFAULT_MARKET_SOURCE,
        help="primary unit quotes: db | openbb (no auto-fallback)",
    )
    parser.add_argument(
        "--market-fallback",
        action=argparse.BooleanOptionalAction,
        default=re.DEFAULT_MARKET_FALLBACK,
        help="fill primary gaps from fallback source (default: false)",
    )
    parser.add_argument(
        "--market-fallback-source",
        choices=["db", "openbb"],
        default=re.DEFAULT_MARKET_FALLBACK_SOURCE,
        help="secondary source when --market-fallback (default: openbb)",
    )
    parser.add_argument("--market-lookback-days", type=int, default=re.DEFAULT_MARKET_LOOKBACK_DAYS)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--stage", choices=sorted(STAGES), default="all")
    parser.add_argument("--list", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list:
        for key, title in STAGES.items():
            print(f"{key:16} {title}")
        return 0

    as_of = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    try:
        snapshot = re.load_snapshot_sync(
            book=None if args.fund_id else args.book,
            fund_id=args.fund_id,
            as_of=as_of,
            lookback_days=args.lookback_days,
            database_url=args.database_url,
            market_source=args.market_source,
            market_lookback_days=args.market_lookback_days,
            market_fallback=args.market_fallback,
            market_fallback_source=args.market_fallback_source,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to load snapshot: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    engine = Engine()
    book = engine.bind(snapshot)
    print(
        f"{re.RISKENGINE_NAME} {engine.version}  "
        f"fund={snapshot.fund_id}  as_of={snapshot.as_of_date}  "
        f"source={'live' if args.fund_id else 'fixture:' + args.book}"
    )
    print(
        "adapters:",
        {k: v.get("available") for k, v in engine.adapters_status().items() if isinstance(v, dict)},
    )

    if args.stage == "all":
        results = run_all(book, DEFAULT_SLICE)
        passed = (results.get("slice") or {}).get("passed")
        _header("closed loop done")
        print("  slice passed:", passed)
        return 0 if passed is not False else 1
    result = run_stage(args.stage, book, DEFAULT_SLICE)
    if args.stage == "slice":
        return 0 if result.get("passed") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
