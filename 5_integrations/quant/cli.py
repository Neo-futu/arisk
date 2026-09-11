"""In-process Quant CLI (no HTTP). Existing 6_entry/cli/run.py HTTP commands stay."""
from __future__ import annotations

import argparse
import json
from importlib import import_module


def _snapshot():
    po = import_module("4_business.portfolio_optimization.service")
    return po.snapshot_from_weights({"BOND5Y": 0.6, "US_EQ": 0.3, "CASH": 0.1}, fund_id="QUANT")


def main(argv: list[str] | None = None) -> int:
    quant = import_module("5_integrations.quant")
    parser = argparse.ArgumentParser(prog="arisk-quant", description="ARISK Quant API")
    sub = parser.add_subparsers(dest="ns", required=True)
    for namespace, methods in quant.QUANT_CONTRACT.items():
        if namespace == "channels":
            continue
        ns_parser = sub.add_parser(namespace)
        ns_parser.add_argument("method", choices=list(methods))
        ns_parser.add_argument("--method-name", dest="opt_method", default="hrp")
    args = parser.parse_args(argv)
    snapshot = _snapshot()
    kwargs = {}
    if args.ns == "portfolio" and args.method == "optimize":
        kwargs["method"] = args.opt_method
    result = getattr(getattr(quant, args.ns), args.method)(snapshot, **kwargs)
    print(json.dumps(result, default=str, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
