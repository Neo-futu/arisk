"""BoundEngine 示例运行入口 — 夹具或平台 DB 真实组合。

仓库根 ``arisk/``::

    python 3_riskengine/scripts/run_riskengine.py
    python 3_riskengine/scripts/run_riskengine.py --check
    python 3_riskengine/scripts/run_riskengine.py --book otc
    python 3_riskengine/scripts/run_riskengine.py --list-funds
    python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01
    python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01 --check

或在 ``3_riskengine/scripts`` 下：``python -m riskengine ...``
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Any

from .config import (
    BOOKS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MARKET_FALLBACK,
    DEFAULT_MARKET_FALLBACK_SOURCE,
    DEFAULT_MARKET_LOOKBACK_DAYS,
    DEFAULT_MARKET_SOURCE,
    RISKENGINE_NAME,
    build_database_url,
    list_live_portfolios,
    load_snapshot_sync,
    shock_rate,
)
from .objects import DEFAULT_SLICE, Engine, bind, verify_slice


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def demo(snapshot: Any, *, run_slice: bool = True) -> dict[str, Any]:
    """独立跑一遍引擎：市况 → 持仓路由 → 估值 → 指标 → 情景 → 优化 → XVA。"""

    engine = Engine()
    book = engine.bind(snapshot)
    status = engine.adapters_status()
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    print(
        f"{RISKENGINE_NAME} {engine.version}  fund={snapshot.fund_id}  "
        f"as_of={snapshot.as_of_date}  positions={len(snapshot.positions)}  "
        f"nav={snapshot.net_asset}"
    )
    print(
        "adapters:",
        {k: v.get("available") for k, v in status.items() if isinstance(v, dict)},
    )
    print("data_quality:", _json({k: quality.get(k) for k in list(quality)[:12]}))

    market = book.market()
    macro = dict(getattr(market, "macro", None) or {})
    print("\n-- market (unit quotes, not position MV) --")
    print(
        _json(
            {
                "date": str(market.valuation_date),
                "kind": macro.get("market_data_kind"),
                "n_prices": len(market.prices),
                "fx": dict(market.fx),
                "fallback_enabled": (macro.get("data_quality") or {}).get("fallback_enabled"),
                "fallback_source": (macro.get("data_quality") or {}).get("fallback_source"),
                "curves": sorted(k for k in market.curves if not callable(market.curves[k])),
                "sample_prices": dict(list(market.prices.items())[:8]),
                "quote_dates": dict(list((macro.get("quote_dates") or {}).items())[:8]),
                "sources": dict(list((macro.get("sources") or {}).items())[:8]),
                "fields": dict(list((macro.get("fields") or {}).items())[:8]),
                "bond_risk_sample": dict(list((macro.get("bond_risk") or {}).items())[:3]),
                "missing": macro.get("missing") or [],
                "stale": (macro.get("stale") or [])[:5],
                "abnormal": (macro.get("abnormal") or [])[:5],
            }
        )
    )
    print("-- market alerts --")
    book.print_market_alerts()

    print("\n-- products / routing --")
    for row in book.holdings_summary()[:20]:
        print(
            " ",
            row["kind"],
            row["security_code"],
            row["adapter"],
            row["model"],
            row["market_value_base"],
        )
    if len(snapshot.positions) > 20:
        print(f"  ... {len(snapshot.positions) - 20} more")

    priced = book.price()
    shocked = book.revalue((shock_rate(1.0),))
    print("\n-- valuation --")
    print(
        _json(
            {
                "base_pv": priced.base_pv,
                "net_asset": snapshot.net_asset,
                "pv_minus_nav": float(priced.base_pv) - float(snapshot.net_asset),
                "rate_1bp_pnl": shocked.pnl,
            }
        )
    )

    print("\n-- financepy df(3.5%, 5y) --")
    try:
        print(" ", book.df(0.035, 5.0))
    except Exception as exc:  # noqa: BLE001
        print(" ", type(exc).__name__, exc)

    mapping = book.ore_trades()
    print("\n-- ore trades --")
    print(
        _json(
            {
                "ore_app": mapping.get("ore_app"),
                "n_trades": len(mapping.get("trades") or []),
                "ids": [t.get("id") for t in (mapping.get("trades") or [])[:12]],
            }
        )
    )

    print("\n-- risk --")
    risk_payload: dict[str, Any] = {
        "dv01": book.dv01().get("result"),
        "scenario_fed_hike_pnl": book.scenario("fed_hike_75").get("pnl"),
        "xva_cva": book.xva().get("cva"),
    }
    try:
        risk_payload["optimize_hrp"] = book.optimize("hrp").get("weights")
    except Exception as exc:  # noqa: BLE001 — 活仓收益面板不足时仍继续
        risk_payload["optimize_error"] = f"{type(exc).__name__}: {exc}"
    print(_json(risk_payload))

    slice_report: dict[str, Any] = {"skipped": True, "passed": True}
    if run_slice:
        print("\n-- slice (BOND / DV01 / fed_hike_75; live auto-picks first bond) --")
        slice_report = verify_slice(book, DEFAULT_SLICE)
        if slice_report.get("skipped"):
            print("  skipped:", slice_report.get("reason") or slice_report.get("kinds"))
        else:
            print("  security:", slice_report.get("security_code"))
            print("  slice passed:", slice_report.get("passed"))
    return {"status": status, "base_pv": priced.base_pv, "slice": slice_report, "fund_id": snapshot.fund_id}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ARISK RiskEngine lab: fixtures or live fsi.* portfolios (FinancePy / ORE / Riskfolio).",
    )
    parser.add_argument("--book", choices=sorted(BOOKS), default="mixed", help="fixture book when not using --fund-id")
    parser.add_argument("--fund-id", default=None, help="live portfolio id from fsi.para_portfolio / balance_*")
    parser.add_argument("--as-of-date", default=None, help="YYYY-MM-DD; default today for live, fixture default for book")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument(
        "--market-source",
        choices=["db", "openbb"],
        default=DEFAULT_MARKET_SOURCE,
        help="primary market quotes source (default: db). Does not fall back unless --market-fallback",
    )
    parser.add_argument(
        "--market-fallback",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_MARKET_FALLBACK,
        help="fill primary gaps from fallback source (default: false, for market-data debug)",
    )
    parser.add_argument(
        "--market-fallback-source",
        choices=["db", "openbb"],
        default=DEFAULT_MARKET_FALLBACK_SOURCE,
        help="secondary source used only when --market-fallback (default: openbb)",
    )
    parser.add_argument("--market-lookback-days", type=int, default=DEFAULT_MARKET_LOOKBACK_DAYS)
    parser.add_argument("--database-url", default=None, help="override DATABASE_URL / POSTGRES_*")
    parser.add_argument("--list-funds", action="store_true", help="list fsi.para_portfolio and exit")
    parser.add_argument("--check", action="store_true", help="run BOND slice verification only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list_funds:
        print("database:", build_database_url(args.database_url).split("@")[-1])
        try:
            import asyncio

            funds = asyncio.run(list_live_portfolios(args.database_url))
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED to list portfolios: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        for row in funds:
            print(f"  {row.get('port_id'):<16} active={row.get('is_active')}  {row.get('port_type')}  {row.get('port_name')}")
        print(f"total: {len(funds)}")
        return 0

    as_of = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    try:
        snapshot = load_snapshot_sync(
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
        if args.fund_id:
            print("hint: check POSTGRES_* / DATABASE_URL and that NAV exists on or before as-of", file=sys.stderr)
        return 2

    if args.check:
        book = bind(snapshot)
        report = verify_slice(book)
        if report.get("skipped"):
            print("slice skipped:", report.get("reason") or report.get("kinds"))
            return 0
        print("security:", report.get("security_code"), "adapter:", report.get("adapter"))
        return 0 if report.get("passed") else 1

    report = demo(snapshot, run_slice=True)
    passed = (report.get("slice") or {}).get("passed")
    return 0 if passed is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
