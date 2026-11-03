"""投资风险 · 业绩归因 Tab 业务模块打包。

页面对应 ``/investment-risk/indicators`` → 业绩归因域，业务能力（非 UI）：

1. **Brinson 摘要** — 组合/基准/超额收益，配置·选券·交互效应
2. **各类资产收益贡献** — 资产类别净损益与贡献%
3. **个股损益前/后十大** — 按净损益排序
4. **个券收益贡献** — C_i = W_i × R_i（单期 / 平均 / 日链 Carino）
5. **Brinson 模型** — BHB / BF，单期或多期 GRAP
6. **Campisi 模型** — 债券收入 / 国债 / 利差 / 择券
7. **个股 Beta 贡献** — 前十大权重 × Beta

模型实现相对独立：``brinson`` / ``campisi`` / ``contribution`` 为本包纯函数，
不读报表层、不 import 2_processing。持仓帧经 ``meta`` 或 snapshot 派生注入。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from ...core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ...instruments.classify import EQUITY_LIKE, FIXED_INCOME
from .brinson import brinson
from .campisi import campisi
from .contribution import contribution

BUSINESS_MODULES = (
    "summary",
    "asset_contribution",
    "security_pnl",
    "contribution_model",
    "brinson_model",
    "campisi_model",
    "equity_beta",
)

# 页面资产类展示码
_ASSET_LABEL = {
    "BOND": "BOND_CORP",
    "CD": "CD",
    "DEPOSIT": "DEPOSIT",
    "EQUITY": "STOCK",
    "ETF": "FUND_ETF",
    "CASH": "CASH",
    "REPO": "REPO",
    "MMF": "FUND_MMF",
}


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value) * 100.0


def _meta(product_or_pos: Any) -> dict[str, Any]:
    return dict(getattr(product_or_pos, "metadata", None) or {})


def _asset_of(position: Any) -> str:
    klass = str(getattr(position, "asset_class", None) or "OTHER").upper()
    return _ASSET_LABEL.get(klass, klass)


def _industry_of(position: Any) -> str:
    meta = _meta(position)
    return str(meta.get("sector") or meta.get("industry") or "未分类")


def _nav_return(snapshot: Any) -> float:
    returns = list(getattr(snapshot, "nav_returns", None) or ())
    if not returns:
        return 0.0
    growth = 1.0
    for _, ret in returns:
        growth *= 1.0 + float(ret)
    return growth - 1.0


def _bench_return(snapshot: Any, info: Mapping[str, Any]) -> float:
    if info.get("benchmark_return") is not None:
        return float(info["benchmark_return"])
    series = list(getattr(snapshot, "benchmark_returns", None) or info.get("benchmark_returns") or ())
    if not series:
        return 0.0
    # 若与 NAV 等长，用全样本复利；否则用均值×N 近似
    growth = 1.0
    for ret in series:
        growth *= 1.0 + float(ret)
    return growth - 1.0


def _synthetic_period_rows(
    snapshot: Any,
    *,
    as_of: date,
    side: str = "portfolio",
) -> list[dict[str, Any]]:
    """无外部帧时：用当前持仓权重 + 代理收益构造单期归因输入。"""

    nav = float(snapshot.net_asset or 0.0) or 1.0
    rows: list[dict[str, Any]] = []
    for position in getattr(snapshot, "positions", ()) or ():
        mv = abs(float(getattr(position, "market_value_base", 0.0) or 0.0))
        weight = mv / nav
        meta = _meta(position)
        # 代理区间收益：优先 metadata.period_return，否则用 ytm/日收益近似 0
        ret = meta.get("period_return")
        if ret is None and side == "portfolio":
            pnl = meta.get("unrealized_pnl")
            if pnl is not None and mv:
                ret = float(pnl) / mv
        if ret is None:
            ret = float(getattr(position, "ytm", 0.0) or 0.0) * 0.25  # 粗代理一季
        rows.append(
            {
                "date": as_of,
                "symbol": str(getattr(position, "security_code", "") or ""),
                "security_name": str(getattr(position, "security_name", "") or ""),
                "weight": weight,
                "asset": _asset_of(position),
                "industry": _industry_of(position),
                "return_period": float(ret or 0.0),
                # Campisi
                "total_return": float(ret or 0.0),
                "income": float(getattr(position, "coupon_rate", 0.0) or meta.get("income") or 0.0) * 0.25,
                "duration": float(getattr(position, "duration", 0.0) or 0.0),
                "treasury_change": float(meta.get("treasury_change") or 0.0),
                "spread_change": float(meta.get("spread_change") or 0.0),
                "convexity": float(getattr(position, "convexity", 0.0) or 0.0),
            }
        )
    return rows


def _equal_weight_benchmark(portfolio_rows: Sequence[Mapping[str, Any]], as_of: date) -> list[dict[str, Any]]:
    """无指数成分时：按组合资产类别等权对照。"""

    assets = sorted({str(row.get("asset") or "OTHER") for row in portfolio_rows})
    if not assets:
        return []
    w = 1.0 / len(assets)
    # 各类基准收益取组合同类平均
    rets: dict[str, list[float]] = defaultdict(list)
    for row in portfolio_rows:
        rets[str(row.get("asset") or "OTHER")].append(float(row.get("return_period") or 0.0))
    return [
        {
            "date": as_of,
            "symbol": f"BENCH_{asset}",
            "security_name": f"Equal-weight {asset}",
            "weight": w,
            "asset": asset,
            "industry": asset,
            "return_period": (sum(rets[asset]) / len(rets[asset])) if rets[asset] else 0.0,
        }
        for asset in assets
    ]


def module_summary(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    brinson_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """六卡摘要：组合/基准/超额 + 配置/选券/交互。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    raw = dict(brinson_result or {})
    fund_r = float(raw.get("portfolio_return") if raw.get("portfolio_return") is not None else _nav_return(snapshot))
    bench_r = float(raw.get("benchmark_return") if raw.get("benchmark_return") is not None else _bench_return(snapshot, info))
    allocation = float(raw.get("allocation") or 0.0)
    selection = float(raw.get("selection") or 0.0)
    interaction = float(raw.get("interaction") or 0.0)
    active = float(raw.get("active_return") if raw.get("active_return") is not None else fund_r - bench_r)
    return {
        "module": "summary",
        "benchmark_id": info.get("benchmark_id") or getattr(snapshot, "benchmark_id", None),
        "fund_return_pct": _pct(fund_r),
        "benchmark_return_pct": _pct(bench_r),
        "active_return_pct": _pct(active),
        "allocation_effect_pct": _pct(allocation),
        "selection_effect_pct": _pct(selection),
        "interaction_effect_pct": _pct(interaction),
        "method": raw.get("method") or "BHB",
        "formula": {
            "BHB": "alloc=(w_p-w_b)*r_b ; sel=w_b*(r_p-r_b) ; inter=(w_p-w_b)*(r_p-r_b)",
            "BF": "alloc=(w_p-w_b)*(r_b-R_b) ; sel=w_p*(r_p-r_b)",
        },
    }


def module_asset_contribution(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """各类资产收益贡献（净损益 + 贡献%）。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    if info.get("asset_contribution"):
        rows = [dict(row) for row in info["asset_contribution"]]
        return {"module": "asset_contribution", "rows": rows, "count": len(rows), "source": "meta"}

    nav = float(snapshot.net_asset or 0.0) or 1.0
    buckets: dict[str, float] = defaultdict(float)
    for position in getattr(snapshot, "positions", ()) or ():
        meta_p = _meta(position)
        pnl = float(meta_p.get("unrealized_pnl") or meta_p.get("net_pnl") or 0.0)
        # 无损益时用权重×代理收益×NAV
        if abs(pnl) < 1e-12:
            mv = abs(float(getattr(position, "market_value_base", 0.0) or 0.0))
            ret = float(meta_p.get("period_return") or getattr(position, "ytm", 0.0) or 0.0) * 0.25
            pnl = mv * ret
        buckets[_asset_of(position)] += pnl
    rows = [
        {
            "asset_class": asset,
            "net_pnl": pnl,
            "contribution_pct": pnl / nav * 100.0,
        }
        for asset, pnl in sorted(buckets.items(), key=lambda item: abs(item[1]), reverse=True)
    ]
    return {"module": "asset_contribution", "rows": rows, "count": len(rows), "source": "snapshot"}


def module_security_pnl(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """个股损益前十大 / 后十大。"""

    info = dict(meta or {})
    if info.get("pnl_rows"):
        rows = [dict(row) for row in info["pnl_rows"]]
    else:
        rows = []
        for position in getattr(bound.snapshot, "positions", ()) or ():
            meta_p = _meta(position)
            mv = abs(float(getattr(position, "market_value_base", 0.0) or 0.0))
            pnl = meta_p.get("unrealized_pnl")
            if pnl is None:
                pnl = meta_p.get("net_pnl")
            if pnl is None:
                ret = float(meta_p.get("period_return") or 0.0)
                pnl = mv * ret
            rows.append(
                {
                    "security_code": str(getattr(position, "security_code", "") or ""),
                    "security_name": str(getattr(position, "security_name", "") or ""),
                    "sector": _industry_of(position),
                    "asset_class": _asset_of(position),
                    "net_pnl": float(pnl or 0.0),
                }
            )
    winners = sorted(rows, key=lambda row: float(row.get("net_pnl") or 0.0), reverse=True)[:top_n]
    losers = sorted(rows, key=lambda row: float(row.get("net_pnl") or 0.0))[:top_n]
    return {
        "module": "security_pnl",
        "top_winners": winners,
        "top_losers": losers,
        "count": len(rows),
        "top_n": top_n,
    }


def module_contribution_model(
    portfolio_rows: Sequence[Mapping[str, Any]],
    *,
    mode: str = "daily",
    link_method: str = "carino",
    group_by: str = "symbol",
    portfolio_return: float | None = None,
) -> dict[str, Any]:
    raw = contribution(
        [dict(row) for row in portfolio_rows],
        mode=mode if mode in {"single", "average", "daily"} else "daily",  # type: ignore[arg-type]
        link_method=link_method if link_method in {"carino", "menchero", "sum"} else "carino",  # type: ignore[arg-type]
        group_by=group_by,
        portfolio_return=portfolio_return,
    )
    return {
        "module": "contribution_model",
        "formula": "C_i = W_i × R_i；日链 Carino：C_i = (1/κ) Σ_t κ_t W_{t-1} R_t",
        **raw,
        "views": {
            f"{mode}|{link_method}|{group_by}": raw,
        },
    }


def module_brinson_model(
    portfolio_rows: Sequence[Mapping[str, Any]],
    benchmark_rows: Sequence[Mapping[str, Any]],
    *,
    method: str = "BHB",
    multi_period: bool = True,
    multi_period_method: str = "grap",
    group_by: str = "asset",
) -> dict[str, Any]:
    raw = brinson(
        [dict(row) for row in portfolio_rows],
        [dict(row) for row in benchmark_rows],
        method=method,
        multi_period=multi_period,
        multi_period_method=multi_period_method,
        group_by=group_by,
    )
    key = f"{method}|{'grap' if multi_period else 'single'}|{group_by}"
    return {
        "module": "brinson_model",
        "period_count": len(raw.get("periods") or []),
        "views": {key: raw},
        **raw,
    }


def module_campisi_model(
    bond_rows: Sequence[Mapping[str, Any]],
    *,
    benchmark: bool = True,
    multi_period: bool = True,
    group_by: str = "industry",
    convexity: bool = False,
) -> dict[str, Any]:
    raw = campisi(
        [dict(row) for row in bond_rows],
        benchmark=benchmark,
        convexity=convexity,
        multi_period=multi_period,
        group_by=group_by,
    )
    key = f"{'bench' if benchmark else 'absolute'}|{'multi' if multi_period else 'single'}|{group_by}"
    return {
        "module": "campisi_model",
        "period_count": len(raw.get("periods") or []),
        "views": {key: raw},
        **raw,
    }


def module_equity_beta(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """个股 Beta 贡献（前十大权重）。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    constituents = list(info.get("beta_constituents") or ())
    portfolio_beta = info.get("equity_beta")
    if portfolio_beta is None:
        from ...risk import kpis as _kpis

        bench = list(getattr(snapshot, "benchmark_returns", None) or info.get("benchmark_returns") or ())
        portfolio_beta = _kpis.kpi_beta(snapshot, benchmark_returns=bench or None)["result"].get("beta")

    if not constituents:
        nav = float(snapshot.net_asset or 0.0) or 1.0
        equities = [
            p
            for p in (getattr(snapshot, "positions", ()) or ())
            if str(getattr(p, "asset_class", "") or "") in EQUITY_LIKE
        ]
        equities.sort(key=lambda p: abs(float(getattr(p, "market_value_base", 0.0) or 0.0)), reverse=True)
        for position in equities[:top_n]:
            mv = abs(float(getattr(position, "market_value_base", 0.0) or 0.0))
            meta_p = _meta(position)
            constituents.append(
                {
                    "security_code": str(getattr(position, "security_code", "") or ""),
                    "security_name": str(getattr(position, "security_name", "") or ""),
                    "weight_pct": mv / nav * 100.0,
                    "beta": float(meta_p.get("beta") if meta_p.get("beta") is not None else (portfolio_beta or 0.0)),
                    "sample_size": int(meta_p.get("beta_sample_size") or 0),
                }
            )

    return {
        "module": "equity_beta",
        "value": None if portfolio_beta is None else float(portfolio_beta),
        "benchmark_id": info.get("benchmark_id") or getattr(snapshot, "benchmark_id", None),
        "constituents": constituents[:top_n],
        "count": len(constituents[:top_n]),
        "note": "前十大权重个股 Beta；组合 Beta 为 NAV 对基准回归",
    }


def fundamentals(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    brinson_method: str = "BHB",
    brinson_multi: bool = True,
    brinson_group: str = "asset",
    campisi_benchmark: bool = True,
    campisi_multi: bool = True,
    campisi_group: str = "industry",
    contrib_mode: str = "daily",
    contrib_link: str = "carino",
    contrib_group: str = "symbol",
    top_n: int = 10,
) -> dict[str, Any]:
    """业绩归因 Tab 七大业务模块打包。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    as_of = snapshot.as_of_date
    if info.get("as_of_date"):
        raw = info["as_of_date"]
        as_of = raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])

    portfolio_rows = [dict(row) for row in (info.get("portfolio_rows") or ())]
    benchmark_rows = [dict(row) for row in (info.get("benchmark_rows") or ())]
    if not portfolio_rows:
        portfolio_rows = _synthetic_period_rows(snapshot, as_of=as_of, side="portfolio")
    if not benchmark_rows:
        # 若有多期帧未提供，用等权资产类对照；页面说明「无指数成分时」走此口径
        benchmark_rows = _equal_weight_benchmark(portfolio_rows, as_of)

    # 确保 date 为 date 对象
    for row in portfolio_rows + benchmark_rows:
        day = row.get("date")
        if isinstance(day, str):
            row["date"] = date.fromisoformat(day[:10])

    brinson_pack = module_brinson_model(
        portfolio_rows,
        benchmark_rows,
        method=brinson_method,
        multi_period=brinson_multi,
        multi_period_method="grap",
        group_by=brinson_group,
    )
    summary = module_summary(bound, meta=info, brinson_result=brinson_pack)
    assets = module_asset_contribution(bound, meta=info)
    security = module_security_pnl(bound, meta=info, top_n=top_n)

    fund_r = (summary.get("fund_return_pct") or 0.0) / 100.0
    contrib = module_contribution_model(
        portfolio_rows,
        mode=contrib_mode,
        link_method=contrib_link,
        group_by=contrib_group,
        portfolio_return=fund_r,
    )

    bond_rows = [
        row
        for row in portfolio_rows
        if str(row.get("asset") or "").upper() in {"BOND", "BOND_CORP", "CD", "DEPOSIT"}
        or str(row.get("asset") or "") in FIXED_INCOME
    ]
    if not bond_rows:
        # 从 snapshot 再筛一层 FI
        bond_rows = [
            row
            for row in _synthetic_period_rows(snapshot, as_of=as_of)
            if str(row.get("asset") or "") in {"BOND_CORP", "BOND", "CD", "DEPOSIT"}
        ]
    campisi_pack = module_campisi_model(
        bond_rows,
        benchmark=campisi_benchmark,
        multi_period=campisi_multi,
        group_by=campisi_group,
    )
    beta = module_equity_beta(bound, meta=info, top_n=top_n)

    period_start = info.get("period_start")
    period_end = info.get("period_end")
    if not period_start and portfolio_rows:
        dates = [row["date"] for row in portfolio_rows if isinstance(row.get("date"), date)]
        if dates:
            period_start = min(dates).isoformat()
            period_end = max(dates).isoformat()
    if not period_end:
        period_end = as_of.isoformat()
    if not period_start:
        period_start = (as_of - timedelta(days=90)).isoformat()

    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/investment-risk/indicators",
        "tab": "attribution",
        "fund_id": str(snapshot.fund_id),
        "period_start": str(period_start)[:10],
        "period_end": str(period_end)[:10],
        "benchmark_id": summary.get("benchmark_id"),
        "business_modules": list(BUSINESS_MODULES),
        "modules": {
            "summary": summary,
            "asset_contribution": assets,
            "security_pnl": security,
            "contribution_model": contrib,
            "brinson_model": brinson_pack,
            "campisi_model": campisi_pack,
            "equity_beta": beta,
        },
        # HTTP 同形（compute_performance_attribution + models）
        "summary": {
            "fund_return_pct": summary["fund_return_pct"],
            "benchmark_return_pct": summary["benchmark_return_pct"],
            "active_return_pct": summary["active_return_pct"],
            "allocation_effect_pct": summary["allocation_effect_pct"],
            "selection_effect_pct": summary["selection_effect_pct"],
            "interaction_effect_pct": summary["interaction_effect_pct"],
        },
        "asset_contribution": assets["rows"],
        "top_winners": security["top_winners"],
        "top_losers": security["top_losers"],
        "brinson_model": {"period_count": brinson_pack["period_count"], "views": brinson_pack["views"]},
        "campisi_model": {"period_count": campisi_pack["period_count"], "views": campisi_pack["views"]},
        "contribution_model": {"views": contrib["views"], **{k: contrib[k] for k in ("mode", "link_method", "group_by", "portfolio_return", "contribution_total", "residual", "groups") if k in contrib}},
        "equity_beta": {
            "value": beta["value"],
            "benchmark_id": beta["benchmark_id"],
            "constituents": beta["constituents"],
        },
        "adapters": bound.engine.adapters_status(),
        "note": "模型在请求内实时计算，不读取报表层缓存",
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing {name}")
    summary = modules.get("summary") or {}
    for key in (
        "fund_return_pct",
        "benchmark_return_pct",
        "active_return_pct",
        "allocation_effect_pct",
        "selection_effect_pct",
        "interaction_effect_pct",
    ):
        if key not in summary:
            errors.append(f"summary.{key}")
    if not (modules.get("asset_contribution") or {}).get("rows") and (modules.get("asset_contribution") or {}).get("count") != 0:
        # 允许空组合，但必须有 rows 键
        if "rows" not in (modules.get("asset_contribution") or {}):
            errors.append("asset_contribution.rows")
    sec = modules.get("security_pnl") or {}
    if "top_winners" not in sec or "top_losers" not in sec:
        errors.append("security_pnl.winners_losers")
    if not (modules.get("brinson_model") or {}).get("views"):
        errors.append("brinson_model.views")
    if not (modules.get("campisi_model") or {}).get("views"):
        errors.append("campisi_model.views")
    if not (modules.get("contribution_model") or {}).get("views"):
        errors.append("contribution_model.views")
    if "value" not in (modules.get("equity_beta") or {}):
        errors.append("equity_beta.value")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
