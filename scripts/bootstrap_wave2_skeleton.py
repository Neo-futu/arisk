"""Bootstrap Wave 2 architecture skeleton directories and package markers."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RISKENGINE_SUBPACKAGES = [
    "core",
    "adapters",
    "valuation",
    "instruments",
    "market",
    "risk",
    "stress",
    "scenario",
    "liquidity",
    "counterparty",
    "pnl",
    "limits",
    "validation",
    "tests",
]

BUSINESS_DOMAINS = [
    "investment_risk",
    "portfolio_optimization",
    "risk_testing",
    "portfolio_management",
    "trading",
]

AI_SUBPACKAGES = [
    "agents",
    "skills",
    "tools",
    "workflows",
    "knowledge",
]

COMPAT_ROOTS = ["legacy", "compatibility", "adapter"]


def write_init(path: Path, doc: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f'"""{doc}"""\n\n__all__: list[str] = []\n'
    path.write_text(content, encoding="utf-8")


def main() -> None:
    write_init(
        ROOT / "3_riskengine" / "__init__.py",
        "Unified quantitative and risk calculation platform (RiskEngine).",
    )

    for name in RISKENGINE_SUBPACKAGES:
        write_init(
            ROOT / "3_riskengine" / name / "__init__.py",
            f"3_riskengine.{name} — Wave 2 skeleton; algorithms migrate incrementally.",
        )

    write_init(
        ROOT / "4_business" / "__init__.py",
        "Business use-case layer — orchestrates RiskEngine and integrations.",
    )
    for domain in BUSINESS_DOMAINS:
        write_init(
            ROOT / f"4_business/{domain}" / "__init__.py",
            f"4_business.{domain} — business use cases (Wave 2 skeleton).",
        )

    write_init(
        ROOT / "7_ai" / "__init__.py",
        "Target AI layer — agents, skills, tools, workflows, knowledge.",
    )
    for name in AI_SUBPACKAGES:
        write_init(
            ROOT / "7_ai" / name / "__init__.py",
            f"7_ai.{name} — target home for AI assets (Wave 2 skeleton).",
        )

    for name in COMPAT_ROOTS:
        write_init(
            ROOT / name / "__init__.py",
            f"{name} — Strangler migration compatibility layer (Wave 2 skeleton).",
        )

    write_init(
        ROOT / "2_processing" / "compatibility" / "__init__.py",
        "2_processing.compatibility — facades from legacy tools to new layers.",
    )

    print("Wave 2 skeleton package markers created.")


if __name__ == "__main__":
    main()
