"""Portfolio optimization APIs (PyPortfolioOpt: efficient frontier / BL / HRP).

Analyze a universe under configurable parameters and return the full result set
(4 return models, 6-metric asset stats, multi-profile optimal portfolios, frontier
diagnosis, frontier curve, correlation) plus downloadable matplotlib PNG charts.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any, Literal

import matplotlib

matplotlib.use("Agg")  # headless PNG rendering
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from fastapi import APIRouter, Depends, HTTPException, Response  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from ...tools.performance import portfolio_optimizer as engine  # noqa: E402
from ..deps import get_db, verify_api_key  # noqa: E402

router = APIRouter(dependencies=[Depends(verify_api_key)])

PROFILES = ["conservative", "balanced", "aggressive", "hrp"]


class OptimizeRequest(BaseModel):
    universe: list[str] = Field(default_factory=lambda: list(engine.DEFAULT_UNIVERSE), max_length=40)
    data_source: Literal["db", "yfinance", "openbb"] = "yfinance"
    lookback_days: int = Field(default=500, ge=120, le=2520)
    start_date: date | None = None
    end_date: date | None = None
    risk_free_rate: float = Field(default=0.04, ge=0, le=0.2)
    weight_bounds: tuple[float, float] = (0.0, 1.0)
    return_model: Literal["historical_mean", "real_cagr", "capm", "black_litterman", "backtest"] = "historical_mean"
    target_return: float | None = None
    custom_weights: dict[str, float] = Field(default_factory=dict)
    benchmark_weights: dict[str, float] = Field(default_factory=dict)
    market_caps: dict[str, float] = Field(default_factory=dict)
    bl_views: dict[str, float] = Field(default_factory=dict)


async def _db_prices(
    db: AsyncSession, tickers: list[str], start: date | None = None, end: date | None = None
) -> pd.DataFrame:
    rows = (
        await db.execute(
            text(
                """
                SELECT price_date, security_code, close_price
                FROM fsi.mktdata_quotes
                WHERE security_code = ANY(:tickers) AND price_type = 'CLOSE'
                  AND (CAST(:start AS date) IS NULL OR price_date >= CAST(:start AS date))
                  AND (CAST(:end AS date) IS NULL OR price_date <= CAST(:end AS date))
                ORDER BY price_date
                """
            ),
            {"tickers": [t.upper() for t in tickers], "start": start, "end": end},
        )
    ).mappings().all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.pivot_table(index="price_date", columns="security_code", values="close_price")


# Price panels only depend on (source, universe, lookback) — cache so repeated
# analyses (RF spin / weight drags) reuse fetched data instead of re-downloading.
_PRICE_CACHE: dict[tuple, Any] = {}
_PRICE_CACHE_MAX = 32


async def _build_manager(req: OptimizeRequest, db: AsyncSession) -> engine.PortfolioManager:
    universe = [t.strip().upper() for t in req.universe if t.strip()]
    if len(universe) < 2:
        raise HTTPException(status_code=422, detail="Universe must contain at least 2 assets")
    pm = engine.PortfolioManager(
        universe,
        risk_free_rate=req.risk_free_rate,
        weight_bounds=(req.weight_bounds[0], req.weight_bounds[1]),
    )
    cache_key = (req.data_source, tuple(sorted(universe)), req.lookback_days, req.start_date, req.end_date)
    cached = _PRICE_CACHE.get(cache_key)
    if cached is not None:
        pm.set_price_panel(cached.reindex(columns=universe).dropna(how="all", axis=1))
    else:
        db_prices = await _db_prices(db, universe, req.start_date, req.end_date) if req.data_source == "db" else None
        try:
            pm.load_prices(req.data_source, lookback_days=req.lookback_days, db_prices=db_prices, start=req.start_date, end=req.end_date)
        except Exception as exc:  # any data-source failure → clean 502, never a 500
            raise HTTPException(status_code=502, detail=f"Data source unavailable: {exc}") from exc
        if len(_PRICE_CACHE) >= _PRICE_CACHE_MAX:
            _PRICE_CACHE.clear()
        _PRICE_CACHE[cache_key] = pm.prices_df
    try:
        pm.set_return_model(req.return_model, market_caps=req.market_caps or None, views=req.bl_views or None)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Return model failed: {exc}") from exc
    return pm


def _analyze(pm: engine.PortfolioManager, req: OptimizeRequest) -> dict[str, Any]:
    return_models = pm.compute_all_return_models(
        market_caps=req.market_caps or None, views=req.bl_views or None
    )
    asset_metrics = pm.calculate_individual_asset_metrics()

    profiles: dict[str, Any] = {}
    for p in PROFILES:
        w, m = pm.build_portfolio_by_profile(p)
        profiles[p] = {"weights": w, "metrics": m}
    if req.target_return is not None:
        w, m = pm.build_portfolio_by_profile("target_return", target_return=req.target_return)
        profiles["target_return"] = {"weights": w, "metrics": m}

    efficiency = None
    if req.custom_weights:
        w, m = pm.evaluate_weights(req.custom_weights)
        profiles["custom"] = {"weights": w, "metrics": m}
        efficiency = pm.check_if_efficient(req.custom_weights)
    if req.benchmark_weights:
        w, m = pm.evaluate_weights(req.benchmark_weights)
        profiles["benchmark"] = {"weights": w, "metrics": m}

    corr = pm.correlation_matrix()
    return {
        "universe": pm.tickers,
        "return_model": req.return_model,
        "return_models": [
            {"asset": idx, **{k: float(v) for k, v in row.items()}}
            for idx, row in return_models.rename(
                columns={
                    "Historical Mean (Arithmetic)": "historical_mean",
                    "Real Historical CAGR (Compound)": "real_cagr",
                    "CAPM Beta Model": "capm",
                    "Black-Litterman Model": "black_litterman",
                    "Historical Backtest (EMA)": "backtest",
                    "Period Total Return": "period_total_return",
                }
            ).iterrows()
        ],
        "asset_metrics": [{"asset": idx, **row.to_dict()} for idx, row in asset_metrics.iterrows()],
        "profiles": profiles,
        "efficiency": efficiency,
        "tangency": pm.tangency_portfolio(),
        "risk_free_rate": req.risk_free_rate,
        "frontier": pm.efficient_frontier_curve(40),
        "asset_points": pm.asset_points(),
        "correlation": {
            "assets": list(corr.columns),
            "matrix": [[round(float(v), 4) for v in corr.loc[a]] for a in corr.columns],
        },
    }


@router.get("/portfolios", summary="平台組合列表（用戶/基準組合選擇）")
async def portfolios(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT port_id, port_name, port_type::text AS port_type, is_active
                FROM fsi.para_portfolio ORDER BY is_active DESC, port_id
                """
            )
        )
    ).mappings().all()
    return {"portfolios": [dict(r) for r in rows]}


@router.get("/holdings/{port_id}", summary="組合證券級持倉→優化資產池與權重")
async def holdings(port_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    port_id = port_id.strip().upper()
    # Union of security-level holdings across asset-class balance tables.
    rows = (
        await db.execute(
            text(
                """
                WITH latest AS (
                    SELECT security_code, security_name, weight_pct, market_value FROM fsi.balance_bond
                    WHERE port_id = :pid AND evaluate_date = (SELECT MAX(evaluate_date) FROM fsi.balance_bond WHERE port_id = :pid)
                    UNION ALL
                    SELECT security_code, security_name, weight_pct, market_value FROM fsi.balance_stock
                    WHERE port_id = :pid AND evaluate_date = (SELECT MAX(evaluate_date) FROM fsi.balance_stock WHERE port_id = :pid)
                    UNION ALL
                    SELECT security_code, security_name, weight_pct, market_value FROM fsi.balance_cd
                    WHERE port_id = :pid AND evaluate_date = (SELECT MAX(evaluate_date) FROM fsi.balance_cd WHERE port_id = :pid)
                    UNION ALL
                    SELECT deposit_id AS security_code, deposit_name AS security_name, weight_pct,
                           total_value AS market_value FROM fsi.balance_deposit
                    WHERE port_id = :pid AND evaluate_date = (SELECT MAX(evaluate_date) FROM fsi.balance_deposit WHERE port_id = :pid)
                )
                SELECT security_code,
                       MAX(security_name) AS security_name,
                       SUM(COALESCE(market_value, 0)) AS market_value,
                       SUM(COALESCE(weight_pct, 0)) AS weight_pct
                FROM latest GROUP BY security_code ORDER BY market_value DESC
                """
            ),
            {"pid": port_id},
        )
    ).mappings().all()

    # Fall back to valuation-sheet subjects if no security-level holdings exist.
    if not rows:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT subject_code AS security_code, subject_name AS security_name,
                           market_value, weight_pct
                    FROM fsi.balance_valuation_sheet
                    WHERE port_id = :pid AND evaluate_date = (SELECT MAX(evaluate_date) FROM fsi.balance_valuation_sheet WHERE port_id = :pid)
                    ORDER BY market_value DESC
                    """
                ),
                {"pid": port_id},
            )
        ).mappings().all()

    total_mv = sum(float(r["market_value"] or 0) for r in rows) or 1.0
    universe: list[str] = []
    weights: dict[str, float] = {}
    names: dict[str, str] = {}
    for r in rows:
        code = str(r["security_code"])
        universe.append(code)
        # Prefer explicit weight_pct; else derive from market value share.
        wp = float(r["weight_pct"] or 0)
        weights[code] = (wp / 100.0) if wp > 0 else float(r["market_value"] or 0) / total_mv
        names[code] = r["security_name"] or code
    return {"port_id": port_id, "universe": universe, "weights": weights, "names": names}


@router.get("/risk-free-options", summary="無風險利率預設（含指標庫實時值）")
async def risk_free_options(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    async def _latest(indicator_id: str) -> float | None:
        v = (
            await db.execute(
                text(
                    """
                    SELECT value FROM fsi.mktdata_indicator_series
                    WHERE indicator_id = :id ORDER BY obs_date DESC LIMIT 1
                    """
                ),
                {"id": indicator_id},
            )
        ).scalar()
        return round(float(v) / 100.0, 4) if v is not None else None

    def _live_yield(symbol: str) -> float | None:
        """Fetch a Treasury-yield index (e.g. ^TNX 10Y, ^IRX 13wk) via yfinance."""
        try:
            import yfinance as yf

            hist = yf.Ticker(symbol).history(period="5d")
            if hist.empty:
                return None
            v = float(hist["Close"].dropna().iloc[-1])
            # ^TNX/^IRX quote the yield in percent (~4.2); some feeds use x10 (~42).
            rate = v / 1000.0 if v > 20 else v / 100.0
            return round(rate, 4)
        except Exception:
            return None

    us_10y_live = _live_yield("^TNX")
    us_fed_live = _live_yield("^IRX")  # 13-week T-bill, short-rate/Fed proxy
    us_fed_ind = await _latest("US_FEDRATE")
    hk_hibor = await _latest("HK_HIBOR3M")
    cn_lpr = await _latest("CN_LPR1Y")

    def _opt(key: str, label: str, live: float | None, fallback: float) -> dict[str, Any]:
        val = live if live is not None else fallback
        return {"key": key, "label": label, "value": val, "source": "live" if live is not None else "fallback"}

    options = [
        _opt("us_10y", "US 10Y Treasury", us_10y_live, 0.042),
        _opt("us_fed", "US Short Rate / Fed", us_fed_live, us_fed_ind if us_fed_ind is not None else 0.0538),
        _opt("hk_hibor", "HK 3M HIBOR", hk_hibor, 0.043),
        _opt("cn_lpr", "CN 1Y LPR", cn_lpr, 0.0345),
        _opt("zero", "Risk-Neutral", None, 0.0),
    ]
    return {"options": options}


@router.post("/evaluate", summary="用戶權重快速評估（滑桿實時反饋）")
async def evaluate(req: OptimizeRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    pm = await _build_manager(req, db)
    weights, metrics = pm.evaluate_weights(req.custom_weights or {c: 1.0 for c in pm.tickers})
    return {
        "weights": weights,
        "metrics": metrics,
        "point": {"volatility": metrics["volatility"], "expected_return": metrics["expected_return"]},
    }


@router.get("/universe", summary="默認資產池與可選標的")
async def universe(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    db_rows = (
        await db.execute(
            text("SELECT DISTINCT security_code FROM fsi.mktdata_quotes ORDER BY security_code LIMIT 100")
        )
    ).scalars().all()
    return {"default": list(engine.DEFAULT_UNIVERSE), "db_tickers": [str(t) for t in db_rows]}


@router.post("/analyze", summary="組合優化與風控分析")
async def analyze(req: OptimizeRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    pm = await _build_manager(req, db)
    return _analyze(pm, req)


@router.post("/chart/{name}", summary="生成高清 PNG 圖表")
async def chart(name: str, req: OptimizeRequest, db: AsyncSession = Depends(get_db)) -> Response:
    if name not in ("covariance_heatmap", "efficient_frontier", "asset_allocation"):
        raise HTTPException(status_code=404, detail="Unknown chart")
    pm = await _build_manager(req, db)
    result = _analyze(pm, req)
    png = _render_chart(name, pm, result)
    return Response(content=png, media_type="image/png", headers={
        "Content-Disposition": f'attachment; filename="{name}.png"'
    })


def _render_chart(name: str, pm: engine.PortfolioManager, result: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    if name == "covariance_heatmap":
        corr = pm.correlation_matrix()
        fig, ax = plt.subplots(figsize=(9, 7))
        im = ax.imshow(corr.to_numpy(), cmap="RdYlGn_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(corr.columns))); ax.set_xticklabels(corr.columns, rotation=90, fontsize=8)
        ax.set_yticks(range(len(corr.columns))); ax.set_yticklabels(corr.columns, fontsize=8)
        fig.colorbar(im, ax=ax)
        ax.set_title("Asset Correlation Heatmap", fontweight="bold")
    elif name == "efficient_frontier":
        fig, ax = plt.subplots(figsize=(10, 6))
        fr = result["frontier"]
        if fr:
            ax.plot([p["volatility"] for p in fr], [p["expected_return"] for p in fr], "b--", label="Efficient Frontier")
        for a in result["asset_points"]:
            ax.scatter(a["volatility"], a["expected_return"], color="gray", s=30)
            ax.annotate(a["asset"], (a["volatility"], a["expected_return"]), fontsize=7)
        markers = {"conservative": ("s", "blue"), "balanced": ("*", "red"), "aggressive": ("^", "green"),
                   "hrp": ("D", "orange"), "custom": ("X", "purple"), "benchmark": ("P", "black"), "target_return": ("v", "brown")}
        for pname, data in result["profiles"].items():
            m = data["metrics"]; mk, col = markers.get(pname, ("o", "gray"))
            ax.scatter(m["volatility"], m["expected_return"], marker=mk, color=col, s=180, label=pname.capitalize(), zorder=5)
        ax.set_xlabel("Annualized Volatility"); ax.set_ylabel("Annualized Expected Return")
        ax.set_title("Efficient Frontier & Portfolios", fontweight="bold"); ax.legend(loc="best", fontsize=8)
    else:  # asset_allocation
        weights = {k: v["weights"] for k, v in result["profiles"].items()}
        df = pd.DataFrame(weights)
        df = df.loc[(df != 0).any(axis=1)]
        fig, ax = plt.subplots(figsize=(12, 6))
        df.plot(kind="bar", ax=ax, width=0.8)
        ax.set_title("Asset Allocation Comparison", fontweight="bold")
        ax.set_ylabel("Weight"); ax.grid(axis="y", linestyle="--", alpha=0.6)
        plt.xticks(rotation=45, fontsize=8)
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=200)
    plt.close(fig)
    return buf.getvalue()
