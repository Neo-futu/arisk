"""投资风险 · 整体风险敞口 / 基本信息业务模块（``/investment-risk/indicators#risk-exposure``）。

资管风控口径（非 UI 控件）：

1. **组合** — 组合代码、名称、产品线、基金大类、是否货基
2. **币种** — 报表基准币种与数据日
3. **成立日** — 成立 / 关闭 / 运作状态
4. **WAM / WAL** — 货基加权平均期限与剩余期限（实际值 + 限额 + SFC 状态）
5. **投资管理人员** — 基金经理 / 风控 / 合规等任职（角色、首席、任期）

权威主数据：``fsi.para_portfolio`` + ``fsi.para_portfolio_manager`` + ``fsi.para_person``；
WAM/WAL 由持仓穿透计算（与 ``liquidity.mmf.sfc_metrics`` 同口径）。
引擎在 ``bind(snapshot)`` 上给出可对账、可单测的同一套业务数字；人员名单经 ``meta`` 注入
（与 HTTP ``compute_portfolio_basic_info`` 对账）。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ..limits.sfc import SFC_WAL_LIMIT_DAYS, SFC_WAM_LIMIT_DAYS

BUSINESS_MODULES = (
    "portfolio",
    "currency",
    "inception",
    "wam_wal",
    "managers",
)

# 与 2_processing investment_analysis_basic_info._CATEGORY_MAP 对齐
_CATEGORY_MAP: dict[str, str] = {
    "MMF": "MONEY_MARKET",
    "BOND": "BOND",
    "EQUITY": "EQUITY",
    "ETF": "EQUITY",
    "INDEX": "EQUITY",
    "BALANCED": "MIXED",
    "HEDGE": "MIXED",
    "PRIVATE": "MIXED",
    "PENSION": "MIXED",
    "MANDATE": "MIXED",
    "SMA": "MIXED",
    "MIXED": "MIXED",
    "OTHER": "OTHER",
}

PERSON_ROLES = frozenset(
    {
        "FUND_MANAGER",
        "DEPUTY_MANAGER",
        "RISK_OFFICER",
        "COMPLIANCE_OFFICER",
        "PORTFOLIO_ANALYST",
        "TRADER",
        "ADMIN",
    }
)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if text else None


def _bool(value: Any, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def resolve_fund_category(
    *,
    port_type: str | None,
    is_mmf: bool,
    explicit: str | None = None,
) -> str:
    if explicit:
        return str(explicit).upper()
    if is_mmf:
        return "MONEY_MARKET"
    return _CATEGORY_MAP.get(str(port_type or "").upper(), "OTHER")


def module_portfolio(bound: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """组合身份：代码、名称、产品线、基金大类。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    mmf = _mmf_pack(bound, meta=info)
    is_mmf = bool(info.get("is_mmf") if info.get("is_mmf") is not None else mmf["is_mmf"])
    port_type = str(
        info.get("port_type")
        or info.get("portfolio_type")
        or quality.get("port_type")
        or ("MMF" if is_mmf else "MIXED")
    ).upper()
    fund_category = resolve_fund_category(
        port_type=port_type,
        is_mmf=is_mmf,
        explicit=info.get("fund_category"),
    )
    return {
        "module": "portfolio",
        "port_id": str(info.get("port_id") or info.get("fund_id") or snapshot.fund_id),
        "fund_id": str(info.get("fund_id") or snapshot.fund_id),
        "port_name": str(info.get("port_name") or snapshot.fund_id),
        "port_name_en": info.get("port_name_en"),
        "port_type": port_type,
        "fund_category": fund_category,
        "is_mmf": is_mmf,
        "is_active": _bool(info.get("is_active"), True),
        "asset_mgr_id": info.get("asset_mgr_id"),
        "trustee_id": info.get("trustee_id"),
        "custodian_id": info.get("custodian_id"),
        "position_count": len(getattr(snapshot, "positions", ()) or ()),
        "source": "fsi.para_portfolio（经 meta / data_quality 注入）",
    }


def module_currency(bound: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """基准币种与最近估值数据日。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    data_date = _iso(info.get("data_date")) or snapshot.as_of_date.isoformat()
    return {
        "module": "currency",
        "base_currency": str(
            info.get("base_currency") or snapshot.reporting_currency or "HKD"
        ).upper(),
        "reporting_currency": str(snapshot.reporting_currency or "").upper() or None,
        "data_date": data_date,
        "as_of_date": snapshot.as_of_date.isoformat(),
        "source": "para_portfolio.base_currency / snapshot.reporting_currency",
    }


def module_inception(bound: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """成立日、关闭日与运作状态。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    inception = _iso(info.get("inception_date"))
    close = _iso(info.get("close_date"))
    is_active = _bool(info.get("is_active"), True)
    return {
        "module": "inception",
        "inception_date": inception,
        "close_date": close,
        "is_active": is_active,
        "status": "CLOSED" if is_active is False else "ACTIVE",
        "as_of_date": snapshot.as_of_date.isoformat(),
        "tenure_days": _tenure_days(inception, snapshot.as_of_date),
        "source": "fsi.para_portfolio.inception_date / close_date / is_active",
    }


def _tenure_days(inception: str | None, as_of: date) -> int | None:
    if not inception:
        return None
    try:
        start = date.fromisoformat(inception[:10])
    except ValueError:
        return None
    return max((as_of - start).days, 0)


def _mmf_pack(bound: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    info = dict(meta or {})
    quality = dict(getattr(bound.snapshot, "data_quality", None) or {})
    try:
        from ..liquidity.mmf import sfc_metrics

        pack = dict(sfc_metrics(bound))
    except Exception:
        pack = {
            "is_mmf": False,
            "wam_days": None,
            "wal_days": None,
            "wam_limit": SFC_WAM_LIMIT_DAYS,
            "wal_limit": SFC_WAL_LIMIT_DAYS,
            "status": "ok",
        }
    # meta / quality 可覆盖限额与预计算值（与驾驶舱 HTTP 行对账）
    if info.get("wam_days") is not None:
        pack["wam_days"] = float(info["wam_days"])
    if info.get("wal_days") is not None:
        pack["wal_days"] = float(info["wal_days"])
    wam_limit = info.get("mmf_wam_limit_days") or info.get("wam_limit_days") or quality.get(
        "mmf_wam_limit_days"
    )
    wal_limit = info.get("mmf_wal_limit_days") or info.get("wal_limit_days") or quality.get(
        "mmf_wal_limit_days"
    )
    if wam_limit is not None:
        pack["wam_limit"] = float(wam_limit)
    if wal_limit is not None:
        pack["wal_limit"] = float(wal_limit)
    if info.get("is_mmf") is not None:
        pack["is_mmf"] = bool(info["is_mmf"])
    return pack


def module_wam_wal(bound: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """货基 WAM / WAL：实际值、限额、占用率、SFC 合规状态。

    非货基仍返回结构（is_mmf=False，实际值为空），便于页面统一渲染。
    """

    pack = _mmf_pack(bound, meta=meta)
    is_mmf = bool(pack.get("is_mmf"))
    wam = pack.get("wam_days")
    wal = pack.get("wal_days")
    wam_limit = float(pack.get("wam_limit") or SFC_WAM_LIMIT_DAYS)
    wal_limit = float(pack.get("wal_limit") or SFC_WAL_LIMIT_DAYS)

    def _util(value: Any, limit: float) -> float | None:
        if value is None or limit <= 0:
            return None
        return float(value) / limit

    return {
        "module": "wam_wal",
        "is_mmf": is_mmf,
        "wam_days": None if wam is None else float(wam),
        "wal_days": None if wal is None else float(wal),
        "mmf_wam_limit_days": wam_limit if is_mmf else None,
        "mmf_wal_limit_days": wal_limit if is_mmf else None,
        "wam_utilization": _util(wam, wam_limit) if is_mmf else None,
        "wal_utilization": _util(wal, wal_limit) if is_mmf else None,
        "status": pack.get("status") if is_mmf else "ok",
        "shadow_deviation_bp": pack.get("shadow_deviation_bp"),
        "formula": "WAM = Σ(w_i × days_to_reset_i)；WAL = Σ(w_i × days_to_final_maturity_i)",
        "source": "3_riskengine.liquidity.mmf.sfc_metrics / para_portfolio 限额",
        "applicable": is_mmf,
    }


def _normalize_manager(row: Mapping[str, Any]) -> dict[str, Any]:
    role = str(row.get("role") or "FUND_MANAGER").upper()
    end_date = _iso(row.get("end_date"))
    is_current = row.get("is_current")
    if is_current is None:
        is_current = end_date is None
    return {
        "person_id": str(row.get("person_id") or row.get("id") or ""),
        "person_name": str(row.get("person_name") or row.get("name") or ""),
        "person_name_en": row.get("person_name_en"),
        "role": role if role in PERSON_ROLES else role,
        "is_lead": bool(row.get("is_lead")),
        "begin_date": _iso(row.get("begin_date")),
        "end_date": end_date,
        "email": row.get("email"),
        "sfc_licence_no": row.get("sfc_licence_no"),
        "is_current": bool(is_current),
    }


def module_managers(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    managers: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """投资管理人员任职表（与平台登录账号分离）。"""

    info = dict(meta or {})
    raw = list(managers or info.get("managers") or ())
    rows = [_normalize_manager(row) for row in raw if row]
    rows.sort(
        key=lambda item: (
            0 if item["is_current"] else 1,
            0 if item["is_lead"] else 1,
            item["begin_date"] or "",
        ),
        reverse=False,
    )
    current = [row for row in rows if row["is_current"]]
    leads = [row for row in current if row["is_lead"]]
    return {
        "module": "managers",
        "rows": rows,
        "count": len(rows),
        "current_count": len(current),
        "lead_names": [row["person_name"] for row in leads],
        "source": "fsi.para_portfolio_manager × fsi.para_person（经 meta 注入）",
        "note": "业务投资管理人员 ≠ 平台登录账号",
    }


def http_shaped(
    portfolio: Mapping[str, Any],
    currency: Mapping[str, Any],
    inception: Mapping[str, Any],
    wam_wal: Mapping[str, Any],
    managers: Mapping[str, Any],
    *,
    fund_id: str,
    as_of_date: str,
) -> dict[str, Any]:
    """与 HTTP ``PortfolioBasicInfo`` / ``compute_portfolio_basic_info`` 同形，便于对账。"""

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "data_date": currency.get("data_date"),
        "portfolio": {
            "port_id": portfolio.get("port_id"),
            "port_name": portfolio.get("port_name"),
            "port_name_en": portfolio.get("port_name_en"),
            "port_type": portfolio.get("port_type"),
            "fund_category": portfolio.get("fund_category"),
            "base_currency": currency.get("base_currency"),
            "inception_date": inception.get("inception_date"),
            "close_date": inception.get("close_date"),
            "is_active": inception.get("is_active"),
            "is_mmf": portfolio.get("is_mmf"),
            "mmf_wam_limit_days": wam_wal.get("mmf_wam_limit_days"),
            "mmf_wal_limit_days": wam_wal.get("mmf_wal_limit_days"),
            "asset_mgr_id": portfolio.get("asset_mgr_id"),
            "trustee_id": portfolio.get("trustee_id"),
            "custodian_id": portfolio.get("custodian_id"),
        },
        "managers": list(managers.get("rows") or ()),
        # 引擎扩展：页面基本信息卡未直接展示实际 WAM/WAL，但对账与货基风控需要
        "wam_wal": {
            "wam_days": wam_wal.get("wam_days"),
            "wal_days": wam_wal.get("wal_days"),
            "status": wam_wal.get("status"),
            "wam_utilization": wam_wal.get("wam_utilization"),
            "wal_utilization": wam_wal.get("wal_utilization"),
        },
    }


def fundamentals(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    managers: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """整体风险敞口页 · 基本信息五大业务模块打包。"""

    portfolio = module_portfolio(bound, meta=meta)
    currency = module_currency(bound, meta=meta)
    inception = module_inception(bound, meta=meta)
    wam_wal = module_wam_wal(bound, meta=meta)
    mgr = module_managers(bound, meta=meta, managers=managers)
    fund_id = str(portfolio["fund_id"])
    as_of = bound.snapshot.as_of_date.isoformat()
    shaped = http_shaped(
        portfolio, currency, inception, wam_wal, mgr, fund_id=fund_id, as_of_date=as_of
    )
    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/investment-risk/indicators#risk-exposure",
        "fund_id": fund_id,
        "as_of_date": as_of,
        "business_modules": list(BUSINESS_MODULES),
        "modules": {
            "portfolio": portfolio,
            "currency": currency,
            "inception": inception,
            "wam_wal": wam_wal,
            "managers": mgr,
        },
        # HTTP basic-info 同形
        "data_date": shaped["data_date"],
        "portfolio": shaped["portfolio"],
        "managers": shaped["managers"],
        "wam_wal": shaped["wam_wal"],
        "adapters": bound.engine.adapters_status(),
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing {name}")
    portfolio = modules.get("portfolio") or {}
    if not portfolio.get("port_id") and not portfolio.get("fund_id"):
        errors.append("portfolio.port_id")
    if not portfolio.get("fund_category"):
        errors.append("portfolio.fund_category")
    currency = modules.get("currency") or {}
    if not currency.get("base_currency"):
        errors.append("currency.base_currency")
    inception = modules.get("inception") or {}
    if inception.get("is_active") is None:
        errors.append("inception.is_active")
    wam_wal = modules.get("wam_wal") or {}
    if "is_mmf" not in wam_wal:
        errors.append("wam_wal.is_mmf")
    if wam_wal.get("is_mmf") and wam_wal.get("wam_days") is None and wam_wal.get("wal_days") is None:
        # 货基应至少能算出一侧；若穿透失败记 warning 级错误
        errors.append("wam_wal.wam_or_wal")
    managers = modules.get("managers") or {}
    if "rows" not in managers:
        errors.append("managers.rows")
    http_portfolio = pack.get("portfolio") or {}
    if not http_portfolio.get("fund_category") and not http_portfolio.get("port_id"):
        errors.append("http.portfolio")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
