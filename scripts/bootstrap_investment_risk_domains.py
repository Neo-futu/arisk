from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "4_business" / "investment_risk"
MODS = [
    "overview",
    "exposure",
    "market_risk",
    "factor_risk",
    "rates_credit",
    "fx",
    "liquidity",
    "concentration",
    "counterparty",
    "leverage",
    "pnl_attribution",
    "risk_budget",
    "macro_dynamics",
    "factor_behavior",
]

TEMPLATE = '''"""Investment Risk domain: {name}."""
from __future__ import annotations

from typing import Any

from ..domains import analyze_domain


def analyze(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    return analyze_domain("{name}", snapshot, **kwargs)
'''


def main() -> None:
    for name in MODS:
        path = ROOT / name / "__init__.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEMPLATE.format(name=name), encoding="utf-8")
    print(f"wrote {len(MODS)} domain packages")


if __name__ == "__main__":
    main()
