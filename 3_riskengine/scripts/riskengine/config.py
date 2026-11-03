"""配置、引入与数据加载（夹具 + 平台 DB 真实组合）。

权威持仓 / 行情仍是 ``fsi.balance_*`` / ``fsi.mktdata_*`` / ``fsi.para_portfolio``。
连库路径与线上一致：``3_riskengine.market.load_portfolio_snapshot``
→ ``2_processing.tools.risk_testing.loader``。
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, AsyncIterator

# ---------------------------------------------------------------------------
# 路径：保证从 scripts/ 或仓库根运行都能 import 3_riskengine / 4_business
# ---------------------------------------------------------------------------

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001 — 无 dotenv 时仍可用环境变量
    pass

from importlib import import_module

# ---------------------------------------------------------------------------
# 平台模块引入（禁止在此 import financepy|ORE|riskfolio）
# ---------------------------------------------------------------------------

_platform = import_module("3_riskengine")
_contracts = import_module("3_riskengine.core.contracts")
_lineage = import_module("3_riskengine.core.lineage")
_classify = import_module("3_riskengine.instruments.classify")
_kpis = import_module("3_riskengine.risk.kpis")
_fixtures = import_module("3_riskengine.tests.fixtures")
_market = import_module("3_riskengine.market")
_catalog = import_module("3_riskengine.scenario.catalog")

PlatformRiskEngine = _platform.RiskEngine
RiskFactorType = _contracts.RiskFactorType
Shock = _contracts.Shock
ShockMode = _contracts.ShockMode
Scenario = _contracts.Scenario
RISKENGINE_NAME = _lineage.RISKENGINE_NAME
RISKENGINE_VERSION = _lineage.RISKENGINE_VERSION
product_kind_of = _classify.product_kind_of
factor_family = _classify.factor_family
kpi_dv01 = _kpis.kpi_dv01
SCENARIOS = _catalog.SCENARIOS
CANONICAL_TABLES = _market.CANONICAL_TABLES
HOLDING_TABLES = _market.HOLDING_TABLES
MARKET_TABLES = _market.MARKET_TABLES
load_portfolio_snapshot = _market.load_portfolio_snapshot

# ---------------------------------------------------------------------------
# 参数默认值
# ---------------------------------------------------------------------------

DEFAULT_LOOKBACK_DAYS = 500
DEFAULT_FIXTURE_BOOK = "mixed"
DEFAULT_AS_OF = date(2026, 9, 1)
DEFAULT_MARKET_SOURCE = "db"  # 主源：db | openbb；默认不回退
DEFAULT_MARKET_FALLBACK = False
DEFAULT_MARKET_FALLBACK_SOURCE = "openbb"
DEFAULT_MARKET_LOOKBACK_DAYS = 30

BOOKS: dict[str, Any] = {
    "mixed": _fixtures.sample_snapshot,
    "mmf": _fixtures.sample_mmf_snapshot,
    "otc": _fixtures.sample_otc_snapshot,
    "hybrid": _fixtures.sample_repo_structured_snapshot,
}


# ---------------------------------------------------------------------------
# 冲击工厂（切片开发时复用）
# ---------------------------------------------------------------------------

def shock_rate(bp: float = 1.0, *, tenor: str | None = None, label: str = "") -> Shock:
    return Shock(
        RiskFactorType.RATE,
        float(bp) * 0.0001,
        ShockMode.ABSOLUTE,
        tenor=tenor,
        label=label or f"rate +{bp:g}bp",
    )


def shock_equity(pct: float = -0.10, *, label: str = "") -> Shock:
    return Shock(
        RiskFactorType.EQUITY,
        float(pct),
        ShockMode.RELATIVE,
        label=label or f"equity {pct:.0%}",
    )


def shock_fx(pct: float = 0.01) -> Shock:
    return Shock(RiskFactorType.FX, float(pct), ShockMode.RELATIVE, label=f"fx {pct:.0%}")


def shock_vol(pct: float = 0.10) -> Shock:
    return Shock(RiskFactorType.VOLATILITY, float(pct), ShockMode.RELATIVE, label=f"vol {pct:.0%}")


def shock_credit(bp: float = 1.0) -> Shock:
    return Shock(
        RiskFactorType.CREDIT_SPREAD,
        float(bp) * 0.0001,
        ShockMode.ABSOLUTE,
        label=f"cs +{bp:g}bp",
    )


EQUITY_OFF = shock_equity(-0.10)


# ---------------------------------------------------------------------------
# 夹具组合
# ---------------------------------------------------------------------------

def load_book(book: str = DEFAULT_FIXTURE_BOOK, as_of: date | None = None, **kwargs: Any) -> Any:
    """内存夹具：mixed / mmf / otc。附带派生单位行情（非市值）。"""

    from importlib import import_module

    asof_mod = import_module("3_riskengine.market.asof")
    factory = BOOKS.get(book)
    if factory is None:
        raise SystemExit(f"unknown fixture book {book!r}; use {sorted(BOOKS)}")
    if as_of is None:
        snapshot = factory(**kwargs) if kwargs else factory()
    else:
        snapshot = factory(as_of, **kwargs) if kwargs else factory(as_of)
    panel = asof_mod.panel_from_positions(snapshot, label=f"fixture:{book}")
    asof_mod.attach_market_panel(snapshot, panel)
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    quality["source"] = quality.get("source") or f"fixture:{book}"
    snapshot.data_quality = quality
    return snapshot


# ---------------------------------------------------------------------------
# 平台 DB（与线上一致）
# ---------------------------------------------------------------------------

def build_database_url(database_url: str | None = None) -> str:
    """与 processing / VaR 脚本同一口径：DATABASE_URL 或 POSTGRES_*。"""

    if database_url:
        return database_url
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    host = os.environ.get("POSTGRES_SERVER") or os.environ.get("POSTGRES_HOST") or "localhost"
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ.get("POSTGRES_DB", "fsi_risk")
    user = os.environ.get("POSTGRES_USER", "fsi_user")
    password = os.environ.get("POSTGRES_PASSWORD", "change_me")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"


def parse_as_of(value: str | date | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


@asynccontextmanager
async def db_session(database_url: str | None = None) -> AsyncIterator[Any]:
    """短生命周期 AsyncSession，脚本用完即关。"""

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    url = build_database_url(database_url)
    engine = create_async_engine(url, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def list_live_portfolios(database_url: str | None = None) -> list[dict[str, Any]]:
    """``fsi.para_portfolio`` 列表，与平台组合选择同源。"""

    from sqlalchemy import text

    async with db_session(database_url) as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT port_id, port_name, port_type::text AS port_type, is_active
                    FROM fsi.para_portfolio
                    ORDER BY is_active DESC, port_id
                    """
                )
            )
        ).mappings().all()
    return [dict(row) for row in rows]


async def load_live_snapshot(
    fund_id: str,
    as_of: date | str | None = None,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    database_url: str | None = None,
    market_source: str = DEFAULT_MARKET_SOURCE,
    market_lookback_days: int = DEFAULT_MARKET_LOOKBACK_DAYS,
    market_fallback: bool = DEFAULT_MARKET_FALLBACK,
    market_fallback_source: str = DEFAULT_MARKET_FALLBACK_SOURCE,
) -> Any:
    """从平台表加载真实组合快照（持仓 + ``fsi.mktdata_*`` 单位行情 + NAV 历史）。"""

    as_of_date = parse_as_of(as_of)
    async with db_session(database_url) as db:
        snapshot = await load_portfolio_snapshot(
            fund_id,
            as_of_date,
            db,
            lookback_days,
            market_source=market_source,
            market_lookback_days=market_lookback_days,
            market_fallback=market_fallback,
            market_fallback_source=market_fallback_source,
        )
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    quality["source"] = quality.get("source") or "fsi.balance_*"
    quality["loader"] = "3_riskengine.market.load_portfolio_snapshot"
    quality["loaded_at"] = datetime.now().isoformat(timespec="seconds")
    snapshot.data_quality = quality
    return snapshot


async def load_snapshot(
    *,
    book: str | None = None,
    fund_id: str | None = None,
    as_of: date | str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    database_url: str | None = None,
    market_source: str = DEFAULT_MARKET_SOURCE,
    market_lookback_days: int = DEFAULT_MARKET_LOOKBACK_DAYS,
    market_fallback: bool = DEFAULT_MARKET_FALLBACK,
    market_fallback_source: str = DEFAULT_MARKET_FALLBACK_SOURCE,
) -> Any:
    """统一入口：有 ``fund_id`` 走 DB，否则走夹具 ``book``。"""

    if fund_id:
        return await load_live_snapshot(
            fund_id,
            as_of,
            lookback_days=lookback_days,
            database_url=database_url,
            market_source=market_source,
            market_lookback_days=market_lookback_days,
            market_fallback=market_fallback,
            market_fallback_source=market_fallback_source,
        )
    return load_book(book or DEFAULT_FIXTURE_BOOK, parse_as_of(as_of) if as_of else None)


def load_snapshot_sync(**kwargs: Any) -> Any:
    """同步包装，供 CLI / platform_workflow 调用。"""

    import asyncio

    if kwargs.get("fund_id"):
        return asyncio.run(load_snapshot(**kwargs))
    book = kwargs.get("book") or DEFAULT_FIXTURE_BOOK
    as_of = kwargs.get("as_of")
    return load_book(book, parse_as_of(as_of) if as_of else None)
