"""As-of market quotes from ``fsi.mktdata_*`` (not position market values)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MARKET_SOURCE_DB = "db"
MARKET_SOURCE_OPENBB = "openbb"
MARKET_SOURCES = (MARKET_SOURCE_DB, MARKET_SOURCE_OPENBB)
# 兼容旧调用：auto ≡ db + fallback=True（新代码请显式传 fallback）
MARKET_SOURCE_AUTO = "auto"

DEFAULT_MARKET_SOURCE = MARKET_SOURCE_DB
DEFAULT_MARKET_FALLBACK = False
DEFAULT_MARKET_FALLBACK_SOURCE = MARKET_SOURCE_OPENBB

STALE_WARN_DAYS = 7


@dataclass
class QuoteRow:
    security_code: str
    price: float
    price_date: date
    source: str
    field: str
    currency: str | None = None


@dataclass
class AsOfMarketPanel:
    """Unit quotes / FX / bond risk for one valuation date — not holdings MV."""

    as_of_date: date
    reporting_currency: str
    prices: dict[str, float] = field(default_factory=dict)
    fx: dict[str, float] = field(default_factory=dict)
    bond_risk: dict[str, dict[str, Any]] = field(default_factory=dict)
    quote_dates: dict[str, date] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    fields: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    stale: list[dict[str, Any]] = field(default_factory=list)
    abnormal: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_tables: list[str] = field(default_factory=list)
    requested_source: str = MARKET_SOURCE_DB
    resolved_source: str = MARKET_SOURCE_DB
    fallback_enabled: bool = False
    fallback_source: str | None = None

    def quality(self) -> dict[str, Any]:
        return {
            "market_data_kind": "quotes",
            "as_of_date": self.as_of_date.isoformat(),
            "requested_source": self.requested_source,
            "resolved_source": self.resolved_source,
            "fallback_enabled": self.fallback_enabled,
            "fallback_source": self.fallback_source,
            "quote_count": len(self.prices),
            "fx_count": len(self.fx),
            "bond_risk_count": len(self.bond_risk),
            "missing": list(self.missing),
            "stale": list(self.stale),
            "abnormal": list(self.abnormal),
            "warnings": list(self.warnings),
            "sources": dict(self.sources),
            "quote_dates": {k: v.isoformat() for k, v in self.quote_dates.items()},
            "source_tables": list(self.source_tables),
        }


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


async def _rows(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    result = await db.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


def _flag_price(
    panel: AsOfMarketPanel,
    code: str,
    price: float,
    price_date: date | None,
    *,
    as_of: date,
    source: str,
    field: str,
) -> None:
    if price_date is None:
        panel.abnormal.append({"security_code": code, "reason": "missing_price_date", "source": source})
        return
    if not (price > 0.0) or price != price:
        panel.abnormal.append(
            {
                "security_code": code,
                "reason": "non_positive_or_nan",
                "price": price,
                "source": source,
                "field": field,
            }
        )
        panel.warnings.append(f"{code}: 行情异常（{field}={price}，来源 {source}）")
        return
    if price > 1e7:
        panel.abnormal.append(
            {
                "security_code": code,
                "reason": "suspiciously_large",
                "price": price,
                "source": source,
                "field": field,
            }
        )
        panel.warnings.append(f"{code}: 行情数值过大（{price}），请核对是否误用市值")
    lag = (as_of - price_date).days
    if lag > STALE_WARN_DAYS:
        panel.stale.append(
            {
                "security_code": code,
                "price_date": price_date.isoformat(),
                "as_of_date": as_of.isoformat(),
                "lag_days": lag,
                "source": source,
            }
        )
        panel.warnings.append(f"{code}: 行情陈旧（{price_date}，落后 as_of {lag} 天）")
    panel.prices[code] = price
    panel.quote_dates[code] = price_date
    panel.sources[code] = source
    panel.fields[code] = field


async def load_db_asof_panel(
    db: AsyncSession,
    *,
    as_of: date,
    security_codes: Iterable[str],
    currencies: Iterable[str],
    reporting_currency: str,
    lookback_days: int = 30,
) -> AsOfMarketPanel:
    """Load latest quotes on/before as_of from canonical ``fsi.mktdata_*`` tables."""

    codes = sorted({str(c) for c in security_codes if c})
    ccys = sorted({str(c) for c in currencies if c and str(c) != reporting_currency})
    panel = AsOfMarketPanel(
        as_of_date=as_of,
        reporting_currency=str(reporting_currency),
        requested_source=MARKET_SOURCE_DB,
        resolved_source=MARKET_SOURCE_DB,
    )
    panel.fx[str(reporting_currency)] = 1.0
    if not codes and not ccys:
        panel.warnings.append("未提供证券代码或外币，跳过行情加载")
        return panel

    start = as_of - timedelta(days=max(int(lookback_days), 1))
    used: set[str] = set()

    if codes:
        quote_rows = await _rows(
            db,
            """
            SELECT DISTINCT ON (security_code)
                   security_code, price_date, close_price, data_source
            FROM fsi.mktdata_quotes
            WHERE security_code = ANY(:codes)
              AND price_type = 'CLOSE'
              AND price_date BETWEEN :start_date AND :as_of
              AND close_price IS NOT NULL
            ORDER BY security_code, price_date DESC
            """,
            {"codes": codes, "start_date": start, "as_of": as_of},
        )
        if quote_rows:
            used.add("fsi.mktdata_quotes")
        for row in quote_rows:
            code = str(row["security_code"])
            _flag_price(
                panel,
                code,
                _num(row.get("close_price")),
                _date(row.get("price_date")),
                as_of=as_of,
                source=str(row.get("data_source") or "fsi.mktdata_quotes"),
                field="CLOSE",
            )

        fund_rows = await _rows(
            db,
            """
            SELECT DISTINCT ON (fund_code)
                   fund_code AS security_code, nav_date AS price_date,
                   COALESCE(acc_unit_nav, unit_nav) AS nav, data_source
            FROM fsi.mktdata_fund_nav
            WHERE fund_code = ANY(:codes)
              AND nav_date BETWEEN :start_date AND :as_of
              AND COALESCE(acc_unit_nav, unit_nav) IS NOT NULL
            ORDER BY fund_code, nav_date DESC
            """,
            {"codes": codes, "start_date": start, "as_of": as_of},
        )
        if fund_rows:
            used.add("fsi.mktdata_fund_nav")
        for row in fund_rows:
            code = str(row["security_code"])
            if code in panel.prices:
                continue
            _flag_price(
                panel,
                code,
                _num(row.get("nav")),
                _date(row.get("price_date")),
                as_of=as_of,
                source=str(row.get("data_source") or "fsi.mktdata_fund_nav"),
                field="NAV",
            )

        bond_rows = await _rows(
            db,
            """
            SELECT DISTINCT ON (internal_id)
                   internal_id AS security_code, price_date,
                   dirty_price, clean_price, ytm, duration, convexity, dv01,
                   accrued_interest, data_source
            FROM fsi.mktdata_bond_risk
            WHERE internal_id = ANY(:codes)
              AND price_date BETWEEN :start_date AND :as_of
            ORDER BY internal_id, price_date DESC
            """,
            {"codes": codes, "start_date": start, "as_of": as_of},
        )
        if bond_rows:
            used.add("fsi.mktdata_bond_risk")
        for row in bond_rows:
            code = str(row["security_code"])
            dirty = _num(row.get("dirty_price"))
            clean = _num(row.get("clean_price"))
            price = dirty if dirty > 0 else clean
            panel.bond_risk[code] = {
                "dirty_price": dirty or None,
                "clean_price": clean or None,
                "ytm": _num(row.get("ytm")) or None,
                "duration": _num(row.get("duration")) or None,
                "convexity": _num(row.get("convexity")) or None,
                "dv01": _num(row.get("dv01")) or None,
                "accrued_interest": _num(row.get("accrued_interest")) or None,
                "price_date": str(row.get("price_date") or ""),
                "source": str(row.get("data_source") or "fsi.mktdata_bond_risk"),
            }
            if code not in panel.prices and price > 0:
                _flag_price(
                    panel,
                    code,
                    price,
                    _date(row.get("price_date")),
                    as_of=as_of,
                    source=str(row.get("data_source") or "fsi.mktdata_bond_risk"),
                    field="DIRTY" if dirty > 0 else "CLEAN",
                )

    if ccys:
        fx_rows = await _rows(
            db,
            """
            SELECT DISTINCT ON (base_ccy, quote_ccy)
                   rate_date, base_ccy, quote_ccy, mid_rate, data_source
            FROM fsi.mktdata_fx_rate
            WHERE rate_type = 'SPOT'
              AND rate_date BETWEEN :start_date AND :as_of
              AND ((base_ccy = ANY(:currencies) AND quote_ccy = :reporting)
                OR (base_ccy = :reporting AND quote_ccy = ANY(:currencies)))
            ORDER BY base_ccy, quote_ccy, rate_date DESC
            """,
            {
                "currencies": ccys,
                "reporting": reporting_currency,
                "start_date": start,
                "as_of": as_of,
            },
        )
        if fx_rows:
            used.add("fsi.mktdata_fx_rate")
        for row in fx_rows:
            base = str(row["base_ccy"])
            quote = str(row["quote_ccy"])
            rate = _num(row.get("mid_rate"))
            if rate <= 0:
                panel.abnormal.append(
                    {
                        "pair": f"{base}/{quote}",
                        "reason": "non_positive_fx",
                        "mid_rate": rate,
                    }
                )
                continue
            if quote == reporting_currency:
                panel.fx[base] = rate
            elif base == reporting_currency:
                panel.fx[quote] = 1.0 / rate
            rate_date = _date(row.get("rate_date"))
            if rate_date and (as_of - rate_date).days > STALE_WARN_DAYS:
                panel.warnings.append(
                    f"FX {base}/{quote}: 汇率陈旧（{rate_date}，落后 {(as_of - rate_date).days} 天）"
                )

    panel.source_tables = sorted(used)
    panel.missing = [c for c in codes if c not in panel.prices]
    for code in panel.missing:
        panel.warnings.append(f"{code}: DB 无可用单位行情（mktdata_quotes/fund_nav/bond_risk）")
    for ccy in ccys:
        if ccy not in panel.fx:
            panel.warnings.append(f"FX {ccy}/{reporting_currency}: DB 无 SPOT 汇率")
    return panel


def panel_from_positions(snapshot: Any, *, label: str = "fixture_derived") -> AsOfMarketPanel:
    """Offline / fixture panel: unit-ish quotes from position market fields — never MV."""

    as_of = snapshot.as_of_date
    reporting = str(getattr(snapshot, "reporting_currency", "HKD") or "HKD")
    panel = AsOfMarketPanel(
        as_of_date=as_of,
        reporting_currency=reporting,
        requested_source=label,
        resolved_source=label,
        source_tables=[],
    )
    panel.fx[reporting] = 1.0
    for position in getattr(snapshot, "positions", ()) or ():
        code = str(position.security_code)
        asset = str(position.asset_class).upper()
        meta = dict(getattr(position, "metadata", None) or {})
        ccy = str(position.currency or reporting)
        fx = _num(getattr(position, "fx_rate", 1.0), 1.0) or 1.0
        if ccy != reporting:
            panel.fx[ccy] = fx

        unit = meta.get("unit_price") or meta.get("last_price") or meta.get("close_price")
        field = "metadata.unit_price"
        if unit is None and asset in {"BOND", "CD"}:
            dirty = meta.get("dirty_price")
            clean = meta.get("clean_price")
            if dirty is not None:
                unit, field = dirty, "metadata.dirty_price"
            elif clean is not None:
                unit, field = clean, "metadata.clean_price"
            else:
                # FI fixtures often omit unit price; use par-style 100 for curve demos
                unit, field = 100.0, "fixture_par_100"
                panel.warnings.append(f"{code}: 夹具无单位价，使用 par=100（非持仓市值）")
        elif unit is None and asset in {"CASH", "DEPOSIT", "UNMAPPED_CASH"}:
            unit, field = 1.0, "cash_par_1"
        elif unit is None and asset in {"EQUITY", "FUND", "ETF"}:
            panel.missing.append(code)
            panel.warnings.append(f"{code}: 夹具缺少单位行情；估值仍用账面 market_value_base")
            continue
        elif unit is None:
            panel.missing.append(code)
            panel.warnings.append(f"{code}: 无单位行情字段，跳过 prices[{code}]（不用市值冒充）")
            continue

        _flag_price(
            panel,
            code,
            _num(unit),
            as_of,
            as_of=as_of,
            source=label,
            field=str(field),
        )
        if asset in {"BOND", "CD", "DEPOSIT"}:
            panel.bond_risk[code] = {
                "ytm": _num(getattr(position, "ytm", 0.0)) or None,
                "duration": _num(getattr(position, "duration", 0.0)) or None,
                "convexity": _num(getattr(position, "convexity", 0.0)) or None,
                "source": "position",
            }
    return panel


def merge_panels(primary: AsOfMarketPanel, secondary: AsOfMarketPanel) -> AsOfMarketPanel:
    """Fill missing primary quotes from a secondary source (only when fallback enabled)."""

    out = AsOfMarketPanel(
        as_of_date=primary.as_of_date,
        reporting_currency=primary.reporting_currency,
        prices=dict(primary.prices),
        fx=dict(primary.fx),
        bond_risk=dict(primary.bond_risk),
        quote_dates=dict(primary.quote_dates),
        sources=dict(primary.sources),
        fields=dict(primary.fields),
        missing=[],
        stale=list(primary.stale),
        abnormal=list(primary.abnormal),
        warnings=list(primary.warnings),
        source_tables=list(dict.fromkeys([*primary.source_tables, *secondary.source_tables])),
        requested_source=primary.requested_source,
        resolved_source=primary.resolved_source,
        fallback_enabled=True,
        fallback_source=secondary.resolved_source,
    )
    filled = 0
    for code, price in secondary.prices.items():
        if code in out.prices:
            continue
        out.prices[code] = price
        out.sources[code] = secondary.sources.get(code, secondary.resolved_source)
        out.fields[code] = secondary.fields.get(code, "CLOSE")
        if code in secondary.quote_dates:
            out.quote_dates[code] = secondary.quote_dates[code]
        filled += 1
    for ccy, rate in secondary.fx.items():
        out.fx.setdefault(ccy, rate)
    for code, risk in secondary.bond_risk.items():
        out.bond_risk.setdefault(code, risk)
    out.warnings.extend(secondary.warnings)
    out.abnormal.extend(secondary.abnormal)
    out.stale.extend(secondary.stale)
    still_missing = [c for c in primary.missing if c not in out.prices]
    out.missing = still_missing
    if filled:
        out.resolved_source = f"{primary.resolved_source}+{secondary.resolved_source}"
        out.warnings.append(f"fallback 补齐 {filled} 个缺失行情（{secondary.resolved_source}）")
    for code in still_missing:
        out.warnings.append(f"{code}: 主源与 fallback 均无可用单位行情")
    return out


def openbb_asof_panel(
    security_codes: Iterable[str],
    *,
    as_of: date,
    reporting_currency: str,
    lookback_days: int = 14,
) -> AsOfMarketPanel:
    """Pull last available equity closes via ``5_integrations`` (OpenBB stays out of RiskEngine)."""

    codes = sorted({str(c) for c in security_codes if c})
    panel = AsOfMarketPanel(
        as_of_date=as_of,
        reporting_currency=reporting_currency,
        requested_source=MARKET_SOURCE_OPENBB,
        resolved_source=MARKET_SOURCE_OPENBB,
        source_tables=["openbb.equity.price.historical"],
    )
    panel.fx[reporting_currency] = 1.0
    if not codes:
        return panel
    try:
        from importlib import import_module

        adapter = import_module("5_integrations.market_data").MarketDataAdapter()
        result = adapter.pull(
            {
                "mode": "asof_quotes",
                "universe": codes,
                "as_of": as_of.isoformat(),
                "lookback_days": lookback_days,
                "provider": "openbb",
            }
        )
    except Exception as exc:  # noqa: BLE001
        panel.warnings.append(f"OpenBB 适配器调用失败: {type(exc).__name__}: {exc}")
        panel.missing = codes
        return panel

    if not result.ok or result.record is None:
        err = (result.error or {}).get("message") or (result.error or {}).get("code") or "unavailable"
        panel.warnings.append(f"OpenBB 不可用: {err}")
        panel.missing = codes
        return panel

    body = dict(getattr(result.record, "payload", None) or {})
    quotes = body.get("quotes") or {}
    quote_dates = body.get("quote_dates") or {}
    for code in codes:
        raw = quotes.get(code)
        if raw is None:
            panel.missing.append(code)
            continue
        qdate = _date(quote_dates.get(code)) or as_of
        _flag_price(
            panel,
            code,
            _num(raw),
            qdate,
            as_of=as_of,
            source=str(body.get("source") or "openbb"),
            field="CLOSE",
        )
    panel.warnings.extend(list(body.get("warnings") or []))
    return panel


async def _load_primary_panel(
    db: AsyncSession | None,
    *,
    source: str,
    as_of: date,
    codes: list[str],
    currencies: list[str],
    reporting: str,
    lookback_days: int,
) -> AsOfMarketPanel:
    if source == MARKET_SOURCE_OPENBB:
        primary = openbb_asof_panel(codes, as_of=as_of, reporting_currency=reporting)
        if db is not None and currencies:
            fx_only = await load_db_asof_panel(
                db,
                as_of=as_of,
                security_codes=[],
                currencies=currencies,
                reporting_currency=reporting,
                lookback_days=lookback_days,
            )
            primary.fx.update(fx_only.fx)
            primary.warnings.extend(fx_only.warnings)
            primary.source_tables = list(dict.fromkeys([*primary.source_tables, *fx_only.source_tables]))
        primary.requested_source = MARKET_SOURCE_OPENBB
        primary.resolved_source = MARKET_SOURCE_OPENBB
        return primary

    if source != MARKET_SOURCE_DB:
        raise ValueError(f"unsupported market source {source!r}; use one of {MARKET_SOURCES}")
    if db is None:
        raise ValueError("market source=db requires an AsyncSession")
    panel = await load_db_asof_panel(
        db,
        as_of=as_of,
        security_codes=codes,
        currencies=currencies,
        reporting_currency=reporting,
        lookback_days=lookback_days,
    )
    panel.requested_source = MARKET_SOURCE_DB
    panel.resolved_source = MARKET_SOURCE_DB
    return panel


def _normalize_source_fallback(
    source: str,
    fallback: bool,
    fallback_source: str | None,
) -> tuple[str, bool, str]:
    """Normalize source + fallback. ``auto`` kept as alias for db+fallback."""

    requested = (source or DEFAULT_MARKET_SOURCE).lower().strip()
    use_fallback = bool(fallback)
    fb_source = (fallback_source or DEFAULT_MARKET_FALLBACK_SOURCE).lower().strip()

    if requested == MARKET_SOURCE_AUTO:
        requested = MARKET_SOURCE_DB
        use_fallback = True
        fb_source = MARKET_SOURCE_OPENBB

    if requested not in MARKET_SOURCES:
        raise ValueError(f"unsupported market source {requested!r}; use one of {MARKET_SOURCES}")
    if fb_source not in MARKET_SOURCES:
        raise ValueError(f"unsupported market fallback source {fb_source!r}; use one of {MARKET_SOURCES}")
    if use_fallback and fb_source == requested:
        raise ValueError(f"fallback_source must differ from source ({requested})")
    return requested, use_fallback, fb_source


async def load_asof_market_panel(
    db: AsyncSession | None,
    snapshot: Any,
    *,
    source: str = DEFAULT_MARKET_SOURCE,
    lookback_days: int = 30,
    fallback: bool = DEFAULT_MARKET_FALLBACK,
    fallback_source: str | None = DEFAULT_MARKET_FALLBACK_SOURCE,
) -> AsOfMarketPanel:
    """Load unit quotes from one primary source; optional explicit fallback.

    Default ``fallback=False`` so missing quotes stay visible for market-data debug.
    """

    as_of = snapshot.as_of_date
    reporting = str(getattr(snapshot, "reporting_currency", "HKD") or "HKD")
    positions = list(getattr(snapshot, "positions", ()) or ())
    codes = [str(p.security_code) for p in positions]
    currencies = [str(p.currency) for p in positions]

    raw = (source or DEFAULT_MARKET_SOURCE).lower().strip()
    if db is None or raw in {"fixture", "offline"}:
        panel = panel_from_positions(snapshot)
        panel.requested_source = raw
        panel.fallback_enabled = False
        return panel

    requested, use_fallback, fb_source = _normalize_source_fallback(raw, fallback, fallback_source)
    primary = await _load_primary_panel(
        db,
        source=requested,
        as_of=as_of,
        codes=codes,
        currencies=currencies,
        reporting=reporting,
        lookback_days=lookback_days,
    )
    primary.requested_source = requested
    primary.fallback_enabled = False
    primary.fallback_source = None

    if not use_fallback:
        if primary.missing:
            primary.warnings.append(
                f"fallback=false：保留 {len(primary.missing)} 个缺失行情，便于排查 "
                f"（可用 --market-fallback / fallback=True 补齐）"
            )
        return primary

    if not primary.missing:
        primary.fallback_enabled = True
        primary.fallback_source = fb_source
        primary.warnings.append(f"fallback=true 但主源无缺口，未调用 {fb_source}")
        return primary

    secondary = await _load_primary_panel(
        db,
        source=fb_source,
        as_of=as_of,
        codes=list(primary.missing),
        currencies=currencies if fb_source == MARKET_SOURCE_DB else [],
        reporting=reporting,
        lookback_days=lookback_days,
    )
    merged = merge_panels(primary, secondary)
    merged.requested_source = requested
    merged.fallback_enabled = True
    merged.fallback_source = fb_source
    return merged


def attach_market_panel(snapshot: Any, panel: AsOfMarketPanel) -> Any:
    """Attach panel onto the existing ARISK snapshot (no second master store)."""

    snapshot.market_panel = panel
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    quality["market"] = panel.quality()
    snapshot.data_quality = quality
    return snapshot
