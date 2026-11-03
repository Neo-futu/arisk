"""Wave 9 platform presentation: menu contract, UI shell, no frontend finance calc."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAV = (ROOT / "frontend" / "src" / "platform" / "nav.ts").read_text(encoding="utf-8")
SIDEBAR = (ROOT / "frontend" / "src" / "components" / "Sidebar" / "AppSidebar.tsx").read_text(encoding="utf-8")
FRONTEND_SRC = ROOT / "frontend" / "src"

IR_IDS = (
    "investment-overview",
    "risk-exposure",
    "factor-risk",
    "factor-behavior",
)
PO_IDS = (
    "portfolio-opt-home",
    "risk-budget",
)
RT_IDS = (
    "sensitivity",
    "stress",
    "scenario",
    "reverse-stress",
    "tail-risk",
    "krd",
    "pnl-explain",
    "historical-backtest",
    "var-backtest",
    "xva",
)
GOV_IDS = (
    "risk-limits",
    "risk-alerts",
    "risk-breaches",
    "exception-management",
    "escalation-disposition",
    "risk-policy",
    "model-validation",
    "valuation-control",
    "liquidity-governance",
    "compliance",
    "risk-reports",
)
FORBIDDEN_IMPORTS = (
    "import financepy",
    "from financepy",
    "import riskfolio",
    "from riskfolio",
    "import QuantLib",
    "from QuantLib",
    "import yfinance",
    "from yfinance",
)


def test_nav_contract_covers_wave9_views() -> None:
    for item_id in IR_IDS + PO_IDS + RT_IDS + GOV_IDS:
        assert f'id: "{item_id}"' in NAV
    assert 'path: "/investment-risk/pretrade-budget#risk-budget"' in NAV
    assert "WORKBENCH_FLOW" in NAV
    assert "Parameter" in NAV
    assert "Ask AI" in NAV
    assert 'path: "/risk-governance#model-validation"' in NAV
    assert 'path: "/risk-governance#liquidity"' in NAV


def test_sidebar_uses_platform_nav() -> None:
    assert 'from "@/platform/nav"' in SIDEBAR
    for item_id in ("dashboard", "portfolio-cockpit", "investment-risk", "agent-ai", "system-management", "trading", "risk-governance"):
        assert f'id: "{item_id}"' in SIDEBAR


def test_sidebar_groups_do_not_borrow_foreign_paths() -> None:
    forbidden = (
        'path: "/autorisk#alerts"',
        'path: "/autorisk#workflow"',
        'path: "/investment-risk/validation"',
        'path: "/investment-risk/liquidity-stress"',
        'path: "/data-management?section=trades"',
        'path: "/data-management?section=market"',
        'path: "/valuation#control"',
        'path: "/reports", permissionPath: "/reports"',
    )
    for token in forbidden:
        assert token not in SIDEBAR, token
    assert 'path: "/trading"' in SIDEBAR
    assert "RISK_GOVERNANCE_NAV" in SIDEBAR


def test_frontend_does_not_import_pricing_libraries() -> None:
    offenders: list[str] = []
    for path in list(FRONTEND_SRC.rglob("*.ts")) + list(FRONTEND_SRC.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_IMPORTS:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)}: {token}")
    assert not offenders, offenders


def test_workbench_and_copilot_exist() -> None:
    workbench = (FRONTEND_SRC / "platform" / "Workbench.tsx").read_text(encoding="utf-8")
    copilot = (FRONTEND_SRC / "components" / "FloatingAiChat.tsx").read_text(encoding="utf-8")
    context = (FRONTEND_SRC / "platform" / "page-context.tsx").read_text(encoding="utf-8")
    assert 'data-testid="platform-workbench"' in workbench
    assert "formatPageContext" in context
    assert "Current Module" in context
    assert "Risk Metrics" in context
    assert "streamAgentChat" in copilot
    assert "platform-copilot" in copilot
    assert "copilot-model-selector" in copilot
    assert "FALLBACK_MODELS" in copilot
