"""Built-in historical and hypothetical stress scenarios.

Shocks are 3_riskengine contracts. 2_processing.tools.risk_testing.scenarios
re-exports these for the existing HTTP/GUI catalogue.
"""
from __future__ import annotations

from ..core.contracts import RiskFactorType, Scenario, Shock, ShockMode

SCENARIOS: dict[str, Scenario] = {
    "gfc_2008": Scenario(
        "gfc_2008",
        "2008 全球金融危机",
        "historical",
        (
            Shock(RiskFactorType.EQUITY, -0.37, ShockMode.RELATIVE, label="全球股票下跌37%"),
            Shock(RiskFactorType.CREDIT_SPREAD, 0.035, ShockMode.ABSOLUTE, label="信用利差扩大350bps"),
            Shock(RiskFactorType.VOLATILITY, 1.20, ShockMode.RELATIVE, label="波动率上升120%"),
            Shock(RiskFactorType.FX, 0.08, ShockMode.RELATIVE, label="非本位币波动8%"),
        ),
        "基于全球金融危机量级的多因子联合冲击，参数为透明可编辑基准，并非逐日历史重放。",
    ),
    "fed_hike_75": Scenario(
        "fed_hike_75",
        "美联储单次加息75bps",
        "hypothetical",
        (
            Shock(RiskFactorType.RATE, 0.0075, ShockMode.ABSOLUTE, label="收益率曲线平行上移75bps"),
            Shock(RiskFactorType.EQUITY, -0.06, ShockMode.RELATIVE, label="股票下跌6%"),
            Shock(RiskFactorType.VOLATILITY, 0.20, ShockMode.RELATIVE, label="波动率上升20%"),
        ),
        "紧缩政策冲击：利率、权益与波动率同步变化。",
    ),
    "covid_2020": Scenario(
        "covid_2020",
        "2020 流动性危机",
        "historical",
        (
            Shock(RiskFactorType.EQUITY, -0.30, ShockMode.RELATIVE, label="股票下跌30%"),
            Shock(RiskFactorType.CREDIT_SPREAD, 0.020, ShockMode.ABSOLUTE, label="信用利差扩大200bps"),
            Shock(RiskFactorType.VOLATILITY, 1.50, ShockMode.RELATIVE, label="波动率上升150%"),
            Shock(RiskFactorType.RATE, -0.010, ShockMode.ABSOLUTE, label="无风险利率下移100bps"),
        ),
        "疫情初期风险资产抛售、信用利差走阔和政策利率下行的联合情景。",
    ),
    "stagflation": Scenario(
        "stagflation",
        "滞胀与信用恶化",
        "hypothetical",
        (
            Shock(RiskFactorType.RATE, 0.015, ShockMode.ABSOLUTE, label="利率上移150bps"),
            Shock(RiskFactorType.CREDIT_SPREAD, 0.010, ShockMode.ABSOLUTE, label="信用利差扩大100bps"),
            Shock(RiskFactorType.EQUITY, -0.18, ShockMode.RELATIVE, label="股票下跌18%"),
            Shock(RiskFactorType.FX, 0.05, ShockMode.RELATIVE, label="非本位币波动5%"),
        ),
        "通胀粘性、紧货币与信用质量转弱的假设情景。",
    ),
}


def scenario_catalog() -> list[dict[str, object]]:
    return [
        {
            "scenario_id": item.scenario_id,
            "name": item.name,
            "category": item.category,
            "description": item.description,
            "shocks": [
                {
                    "factor_type": shock.factor_type.value,
                    "value": shock.value,
                    "mode": shock.mode.value,
                    "tenor": shock.tenor,
                    "currency": shock.currency,
                    "label": shock.label,
                }
                for shock in item.shocks
            ],
        }
        for item in SCENARIOS.values()
    ]
