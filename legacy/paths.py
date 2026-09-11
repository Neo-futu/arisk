"""Registry of Current authoritative paths that have not yet moved."""
from __future__ import annotations

LEGACY_PATHS: dict[str, str] = {
    "risk_tools": "2_processing/tools/risk",
    "risk_testing": "2_processing/tools/risk_testing",
    "portfolio_optimizer": "2_processing/tools/performance/portfolio_optimizer.py",
    "investment_analysis": "2_processing/tools/performance/investment_analysis.py",
    "skills": "3_skills",
    "mcp": "4_mcp",
    "user_agent": "aiagent",
    "platform_agent": "platform_agent",
    "autorisk": "autorisk",
    "frontend_portfolio_opt": "frontend/src/modules/portfolio-opt",
}

__all__ = ["LEGACY_PATHS"]
