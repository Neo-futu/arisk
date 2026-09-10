"""MMF WAM/WAL versus SFC limits. SQL is input only."""
from __future__ import annotations

from typing import Any, Mapping

from ..core.contracts import ProductKind, ViewMode
from ..limits.sfc import SFC_WAL_LIMIT_DAYS, SFC_WAM_LIMIT_DAYS, report as sfc_report
from ..products.assemble import products_from_snapshot
from ..products.money_market.fund import MoneyMarketFund, is_money_market_book


def _deviation_bp(snapshot: Any) -> float | None:
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    raw = quality.get("shadow_deviation_bp")
    if raw is None:
        raw = quality.get("shadow_nav_deviation_bp")
    if raw is None:
        return None
    return float(raw)


def _mmf_product(bound: Any) -> MoneyMarketFund | None:
    products = products_from_snapshot(bound.snapshot, view=ViewMode.PRODUCT)
    if products and products[0].kind is ProductKind.MMF and isinstance(products[0], MoneyMarketFund):
        return products[0]
    lines = products_from_snapshot(bound.snapshot, view=ViewMode.LOOK_THROUGH)
    if is_money_market_book(lines):
        header = products[0] if products else None
        if isinstance(header, MoneyMarketFund):
            return header
    return None


def sfc_metrics(bound: Any) -> dict[str, Any]:
    snapshot = bound.snapshot
    fund = _mmf_product(bound)
    is_mmf = fund is not None
    as_of = snapshot.as_of_date
    wam = float(fund.wam_days(as_of)) if fund is not None else None
    wal = float(fund.wal_days(as_of)) if fund is not None else None
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    wam_limit = float(quality.get("mmf_wam_limit_days") or SFC_WAM_LIMIT_DAYS)
    wal_limit = float(quality.get("mmf_wal_limit_days") or SFC_WAL_LIMIT_DAYS)
    pack = sfc_report(
        is_mmf=is_mmf,
        wam_days=wam,
        wal_days=wal,
        wam_limit=wam_limit,
        wal_limit=wal_limit,
        deviation_bp=_deviation_bp(snapshot),
    )
    pack["analytic"] = "MMF_SFC"
    pack["fund_id"] = str(getattr(snapshot, "fund_id", "") or "")
    pack["ore_app"] = False
    if fund is not None:
        pack["holding_count"] = len(fund.holdings)
        pack["nav"] = float(fund.nav or snapshot.net_asset or 0.0)
    return pack


def reconcile(engine_report: Mapping[str, Any], cockpit: Mapping[str, Any]) -> dict[str, Any]:
    """Same 口径: engine status vs cockpit-supplied WAM/WAL/deviation."""

    from ..limits.sfc import compliance_status

    cockpit_status = compliance_status(
        bool(cockpit.get("is_mmf", engine_report.get("is_mmf"))),
        cockpit.get("wam_days", engine_report.get("wam_days")),
        cockpit.get("wal_days", engine_report.get("wal_days")),
        cockpit.get("wam_limit", engine_report.get("wam_limit")),
        cockpit.get("wal_limit", engine_report.get("wal_limit")),
        cockpit.get("shadow_deviation_bp", engine_report.get("shadow_deviation_bp")),
    )
    engine_status = str(engine_report.get("status") or "")
    return {
        "aligned": cockpit_status == engine_status,
        "engine_status": engine_status,
        "cockpit_status": cockpit_status,
        "source": "3_riskengine.limits.sfc",
    }
