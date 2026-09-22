"""Engine / BoundEngine / SliceSpec — 基于 FinancePy / ORE / Riskfolio 的开发对象。

职责::

    FinancePy  → 产品 / 市场 / 曲线 / 固收与权益现货
    ORE        → Trade 描述符 / FX·IRS·期权·CDS / XVA（无 OREApp XML）
    Riskfolio  → 组合 VaR/CVaR / HRP·HERC·CVaR·RP 优化

默认委托 ``3_riskengine``（三库已在 ``adapters/``）。
复刻某一产品或指标：改 ``BoundEngine`` 对应方法，再嵌入 ``platform_workflow``。
不要在此 ``import financepy|ORE|QuantLib|riskfolio``。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from .config import (
    EQUITY_OFF,
    RISKENGINE_NAME,
    RISKENGINE_VERSION,
    SCENARIOS,
    PlatformRiskEngine,
    Shock,
    factor_family,
    kpi_dv01,
    product_kind_of,
    shock_rate,
)


@dataclass(frozen=True)
class SliceSpec:
    """一次只验一格：资产类 × 产品 × 冲击 × 指标 × 情景。"""

    asset_class: str
    product_kind: str
    security_code: str
    shock: Shock
    kpi: str
    scenario_id: str
    expected_adapter: str = "financepy"


DEFAULT_SLICE = SliceSpec(
    asset_class="BOND",
    product_kind="BOND",
    security_code="BOND5Y",
    shock=shock_rate(1.0),
    kpi="DV01",
    scenario_id="fed_hike_75",
    expected_adapter="financepy",
)


class Engine:
    """你要持续开发的 RiskEngine。

    三库入口（adapter）::

        self.financepy   # FlatDiscountCurve / df_t / bump / 修正久期
        self.ore         # Trade 映射、OTC 再定价、XVA
        self.riskfolio   # VaR/CVaR、optimize、risk_contribution
    """

    def __init__(self) -> None:
        self._platform = PlatformRiskEngine()
        self.financepy = self._platform.financepy
        self.ore = self._platform.ore
        self.riskfolio = self._platform.riskfolio

    @property
    def version(self) -> str:
        return RISKENGINE_VERSION

    def adapters_status(self) -> dict[str, Any]:
        return self._platform.adapters_status()

    def resolve(self, product: Any, analytic: str = "PRICE") -> Any:
        """product + analytic → {adapter, model, fallback}。业务不要自己选库。"""

        return self._platform.resolve(product, analytic)

    def bind(self, snapshot: Any) -> "BoundEngine":
        return BoundEngine(self, snapshot)


class BoundEngine:
    """绑定一份持仓+行情快照后的计算面。``platform_workflow`` / ``main`` 只依赖这里。"""

    def __init__(self, engine: Engine, snapshot: Any) -> None:
        self.engine = engine
        self.snapshot = snapshot
        self._core = engine._platform.bind(snapshot)

    # -- 对象 --

    def market(self) -> Any:
        """单位行情 / FX / 曲线（``fsi.mktdata_*`` 或第三方补齐；非持仓市值）。"""

        return self._core.market()

    def market_quality(self) -> dict[str, Any]:
        """行情覆盖 / 缺失 / 陈旧 / 异常提示。"""

        market = self.market()
        macro = dict(getattr(market, "macro", None) or {})
        return dict(macro.get("data_quality") or {})

    def print_market_alerts(self) -> list[str]:
        """打印并返回行情警告（缺失、陈旧、异常）。"""

        market = self.market()
        macro = dict(getattr(market, "macro", None) or {})
        warnings = list(macro.get("warnings") or [])
        for line in warnings:
            print(f"  [MARKET] {line}")
        if not warnings:
            print("  [MARKET] ok — no missing/stale/abnormal alerts")
        return warnings

    def products(self, view: str = "LOOK_THROUGH") -> list[Any]:
        return self._core.products(view=view)

    def trades(self, view: str = "LOOK_THROUGH") -> list[Any]:
        return self._core.trades(view=view)

    def classify(self, position: Any) -> str:
        return product_kind_of(position).value

    def family(self, position: Any) -> str:
        return factor_family(position, self.snapshot.reporting_currency)

    def route_price(self, product: Any) -> dict[str, str]:
        ref = self.engine.resolve(product, "PRICE")
        return {"adapter": ref.adapter, "model": ref.model, "fallback": str(ref.fallback)}

    def holdings_summary(self) -> list[dict[str, Any]]:
        """平台持仓行 → kind / 路由 / 账面，便于对照 DB 与夹具。"""

        rows = []
        for position, product in zip(self.snapshot.positions, self.products("LOOK_THROUGH")):
            ref = self.route_price(product)
            rows.append(
                {
                    "security_code": position.security_code,
                    "security_name": getattr(position, "security_name", ""),
                    "asset_class": position.asset_class,
                    "kind": product.kind.value,
                    "family": self.family(position),
                    "currency": position.currency,
                    "market_value_base": position.market_value_base,
                    "ytm": getattr(position, "ytm", None),
                    "duration": getattr(position, "duration", None),
                    "maturity_date": str(getattr(position, "maturity_date", None) or ""),
                    **ref,
                }
            )
        return rows

    # -- 估值（FinancePy 固收/权益；ORE 复杂产品） --

    def price(self, view: str = "LOOK_THROUGH") -> Any:
        """零冲击 PV = 平台账面。改定价公式时动 Product.sensitivity / adapter，不要改 kernel。"""

        return self._core.valuation().price(view=view)

    def revalue(self, shocks: Iterable[Any], view: str = "LOOK_THROUGH") -> Any:
        return self._core.valuation().revalue(tuple(shocks), view=view)

    def greeks(self, shocks: Iterable[Any], view: str = "LOOK_THROUGH") -> dict[str, Any]:
        return self._core.valuation().greeks(tuple(shocks), view=view)

    def cashflows(self, view: str = "LOOK_THROUGH") -> dict[str, Any]:
        return self._core.valuation().cashflows(view=view)

    def pnl(self, shocks: Iterable[Any]) -> dict[str, Any]:
        return self._core.valuation().pnl(tuple(shocks))

    def df(self, zero_rate: float, years: float) -> float:
        """FinancePy 贴现因子。熟悉曲线时从这里改/对照。"""

        return float(self.engine.financepy.discount_factor(zero_rate, years, self.snapshot.as_of_date))

    def ore_trades(self) -> dict[str, Any]:
        """ORE Trade 描述符。``ore_app`` 必须为 False。"""

        return self.engine.ore.map_snapshot(self.snapshot)

    # -- 风险 / 情景 / 优化 --

    def kpis(self) -> dict[str, Any]:
        return self._core.risk().kpis()

    def dv01(self) -> dict[str, Any]:
        return kpi_dv01(self.snapshot)

    def krd(self, bump_bps: float = 1.0) -> dict[str, Any]:
        return self._core.risk().krd(bump_bps)

    def exposure(self) -> dict[str, Any]:
        return self._core.risk().exposure()

    def sensitivity(self, shocks: Iterable[Any]) -> dict[str, Any]:
        return self._core.risk().sensitivity(tuple(shocks))

    def scenario(self, scenario_id: str) -> dict[str, Any]:
        return self._core.scenario().named(scenario_id)

    def stress(self, scenario_id: str = "gfc_2008") -> dict[str, Any]:
        return self._core.stress().run(SCENARIOS[scenario_id])

    def reverse_stress(self, scenario_id: str, target_loss_pct_nav: float, max_scale: float = 20.0) -> dict[str, Any]:
        return self._core.stress().reverse(SCENARIOS[scenario_id], target_loss_pct_nav, max_scale)

    def var_backtest(self, confidence: float = 0.99, window: int = 60) -> dict[str, Any]:
        return self._core.risk().var_backtest(confidence, window)

    def historical_backtest(self) -> dict[str, Any]:
        return self._core.risk().historical_backtest()

    def pnl_explain(self, previous: Any) -> dict[str, Any]:
        return self._core.pnl().explain(previous)

    def xva(self) -> dict[str, Any]:
        return self._core.counterparty().xva()

    def counterparty(self) -> dict[str, Any]:
        return self._core.counterparty().report()

    def liquidity(self) -> dict[str, Any]:
        return self._core.liquidity().report()

    def liquidity_buckets(self) -> dict[str, Any]:
        return self._core.liquidity().buckets()

    def mmf(self) -> dict[str, Any]:
        return self._core.liquidity().mmf()

    def optimize(self, method: str = "hrp") -> dict[str, Any]:
        """Riskfolio 优化提案。``is_trade_instruction`` 必须为 False。"""

        return self._core.portfolio().optimize(method)

    def portfolio_risk(self, *, confidence: float = 0.99) -> dict[str, Any]:
        return self._core.portfolio().risk(confidence=confidence)

    def limits(self) -> dict[str, Any]:
        return self._core.limits().evaluate()

    def governance(self) -> dict[str, Any]:
        return self._core.governance().review()

    def validation_pricing(self) -> Any:
        return self._core.validation().pricing()

    def cross_engine(self) -> Any:
        """FinancePy DF vs ORE FlatForward。"""

        return self._core.validation().cross_engine()


def bind(snapshot: Any, engine: Engine | None = None) -> BoundEngine:
    return (engine or Engine()).bind(snapshot)


def resolve_slice(book: BoundEngine, spec: SliceSpec = DEFAULT_SLICE) -> SliceSpec:
    """夹具用固定 security_code；DB 组合自动落到第一只匹配产品。"""

    codes = {p.security_code for p in book.snapshot.positions}
    if spec.security_code in codes:
        return spec
    for position in book.snapshot.positions:
        if book.classify(position) == spec.product_kind:
            return replace(spec, security_code=position.security_code, asset_class=position.asset_class)
    return spec


def _ok(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    return ok


def verify_slice(book: BoundEngine, spec: SliceSpec = DEFAULT_SLICE) -> dict[str, Any]:
    """组装 → 路由 → 零冲击 → 单因子 → 指标 → 情景。

    夹具：DEFAULT_SLICE（BOND5Y）。
    DB：自动选第一只 ``product_kind`` 持仓；权益冲击对固收应≈0。
    """

    spec = resolve_slice(book, spec)
    kinds = [p.kind.value for p in book.products("LOOK_THROUGH")]
    if spec.product_kind not in kinds:
        return {"skipped": True, "kinds": kinds, "passed": True, "reason": f"no {spec.product_kind}"}

    product = next(p for p in book.products("LOOK_THROUGH") if p.instrument.instrument_id == spec.security_code)
    holding = next(p for p in book.snapshot.positions if p.security_code == spec.security_code)
    ref = book.route_price(product)
    classified = book.classify(holding)
    row = next(r for r in book.price().trade_values if r["security_code"] == spec.security_code)
    factor_pnl = next(
        r for r in book.revalue((spec.shock,)).trade_values if r["security_code"] == spec.security_code
    )["pnl"]
    eq_pnl = next(
        r for r in book.revalue((EQUITY_OFF,)).trade_values if r["security_code"] == spec.security_code
    )["pnl"]
    dv01 = book.dv01()
    hike = book.scenario(spec.scenario_id)
    adapter_ok = ref["adapter"] == spec.expected_adapter
    # 活仓路由可能是 ore（OTC）；夹具债券必须是 financepy
    if spec.security_code != "BOND5Y" and spec.product_kind == "BOND":
        adapter_ok = ref["adapter"] in {"financepy", "ore", "riskengine"}

    checks = [
        _ok("classify", classified == spec.product_kind, classified),
        _ok("PRICE adapter", adapter_ok, ref["adapter"]),
        _ok(
            "zero-shock PV == book",
            abs(float(row["base_pv"]) - float(holding.market_value_base)) < 1e-4,
            f"{row['base_pv']} vs {holding.market_value_base}",
        ),
        _ok("factor shock PnL moves", float(factor_pnl) != 0.0 or spec.product_kind == "CASH", str(factor_pnl)),
        _ok("off-factor equity ~0 on FI", abs(float(eq_pnl)) < 1.0 or spec.product_kind not in {"BOND", "CD", "DEPOSIT"}, str(eq_pnl)),
        _ok(
            "DV01 present",
            dv01.get("result") is not None,
            str((dv01.get("result") or {}).get("reval_pnl")),
        ),
        _ok("scenario analytic", hike.get("analytic") == "SCENARIO", str(hike.get("analytic"))),
        _ok("scenario has pnl", "pnl" in hike, str(hike.get("pnl"))),
    ]
    return {
        "security_code": spec.security_code,
        "product_kind": spec.product_kind,
        "adapter": ref["adapter"],
        "base_pv": row["base_pv"],
        "factor_pnl": factor_pnl,
        "equity_off_pnl": eq_pnl,
        "dv01": dv01.get("result"),
        "scenario_pnl": hike.get("pnl"),
        "fund_id": book.snapshot.fund_id,
        "as_of_date": str(book.snapshot.as_of_date),
        "passed": all(checks),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
