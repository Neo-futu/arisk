"""Load fund holdings, compute LQA fields, then call RiskEngine LQAP.

Holdings come from balance_* tables. ADTV and asset-class bid-ask come from
mktdata_adtv / sfc_liquidity_bucket_def. Field math lives in
3_riskengine.liquidity.lqa_fields — no backfill from sfc_liquidity_stress.
"""
from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

_lqap = import_module("3_riskengine.liquidity.lqap")
_fields = import_module("3_riskengine.liquidity.lqa_fields")


async def _latest_book_date(db: AsyncSession, fund_id: str, as_of: date) -> date | None:
    return (
        await db.execute(
            text(
                """
                SELECT MAX(d)
                FROM (
                    SELECT MAX(evaluate_date) AS d FROM fsi.balance_bond
                    WHERE port_id = :fund_id AND evaluate_date <= :as_of
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_deposit
                    WHERE port_id = :fund_id AND evaluate_date <= :as_of
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_cash
                    WHERE port_id = :fund_id AND evaluate_date <= :as_of
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_cd
                    WHERE port_id = :fund_id AND evaluate_date <= :as_of
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_repo
                    WHERE port_id = :fund_id AND evaluate_date <= :as_of
                ) t
                """
            ),
            {"fund_id": fund_id, "as_of": as_of},
        )
    ).scalar_one_or_none()


async def _load_holdings(db: AsyncSession, fund_id: str, book_date: date) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT security_code, security_name, asset_category, market_value,
                   duration, remaining_days, sector, is_overnight
            FROM (
                SELECT security_code,
                       COALESCE(security_name, security_code) AS security_name,
                       asset_subtype::text AS asset_category,
                       COALESCE(market_value_base, market_value, 0) AS market_value,
                       duration,
                       remaining_days,
                       sector,
                       FALSE AS is_overnight
                FROM fsi.balance_bond
                WHERE port_id = :fund_id AND evaluate_date = :book_date

                UNION ALL
                SELECT security_code,
                       COALESCE(security_name, security_code),
                       'CD',
                       COALESCE(market_value_base, market_value, principal, 0),
                       duration,
                       remaining_days,
                       NULL,
                       FALSE
                FROM fsi.balance_cd
                WHERE port_id = :fund_id AND evaluate_date = :book_date

                UNION ALL
                SELECT deposit_id,
                       COALESCE(deposit_name, deposit_id),
                       'DEPOSIT',
                       COALESCE(total_value_base, total_value, principal, 0),
                       NULL,
                       remaining_days,
                       NULL,
                       COALESCE(is_overnight, FALSE)
                FROM fsi.balance_deposit
                WHERE port_id = :fund_id AND evaluate_date = :book_date

                UNION ALL
                SELECT cash_account_id,
                       COALESCE(account_name, cash_account_id),
                       'CASH',
                       COALESCE(amount_base_ccy, amount, 0),
                       NULL,
                       0,
                       NULL,
                       TRUE
                FROM fsi.balance_cash
                WHERE port_id = :fund_id AND evaluate_date = :book_date

                UNION ALL
                SELECT repo_id,
                       COALESCE(pledged_security_name, repo_id),
                       CASE WHEN UPPER(repo_type) IN ('REV', 'REV_REPO', 'REVERSE')
                            THEN 'REV_REPO' ELSE 'REPO' END,
                       COALESCE(total_value, principal, 0),
                       NULL,
                       remaining_days,
                       NULL,
                       FALSE
                FROM fsi.balance_repo
                WHERE port_id = :fund_id AND evaluate_date = :book_date
            ) h
            WHERE market_value <> 0
            """
        ),
        {"fund_id": fund_id, "book_date": book_date},
    )
    return [dict(row) for row in result.mappings().all()]


async def _load_adtv_map(
    db: AsyncSession,
    codes: list[str],
    as_of: date,
) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    result = await db.execute(
        text(
            """
            SELECT DISTINCT ON (security_code)
                   security_code, adtv_30d, sample_days, adtv_date
            FROM fsi.mktdata_adtv
            WHERE security_code IN :codes
              AND adtv_date <= :as_of
            ORDER BY security_code, adtv_date DESC
            """
        ).bindparams(bindparam("codes", expanding=True)),
        {"codes": codes, "as_of": as_of},
    )
    return {str(row["security_code"]): dict(row) for row in result.mappings().all()}


async def _load_bid_ask_bps(db: AsyncSession) -> dict[str, float]:
    result = await db.execute(
        text(
            """
            SELECT asset_category, bid_ask_cost_bps
            FROM fsi.sfc_liquidity_bucket_def
            WHERE scenario = 'NORMAL'
            """
        )
    )
    return {str(row["asset_category"]): float(row["bid_ask_cost_bps"] or 0) for row in result.mappings().all()}


async def _load_fi_horizon_ladder(
    db: AsyncSession,
    *,
    ladder_id: str = "DEFAULT",
) -> list[tuple[float | None, float]]:
    """Load 方案 A bands from fsi.lqa_fi_horizon_ladder; empty → caller uses code default."""
    try:
        result = await db.execute(
            text(
                """
                SELECT max_bid_ask_bps, horizon_days
                FROM fsi.lqa_fi_horizon_ladder
                WHERE ladder_id = :ladder_id
                  AND is_active = TRUE
                ORDER BY band_seq
                """
            ),
            {"ladder_id": ladder_id},
        )
    except Exception:
        return []
    rows: list[tuple[float | None, float]] = []
    for row in result.mappings().all():
        max_bps = row["max_bid_ask_bps"]
        rows.append((None if max_bps is None else float(max_bps), float(row["horizon_days"])))
    return rows


async def _persist_computed_lqa(
    db: AsyncSession,
    as_of: date,
    positions: list[dict[str, Any]],
) -> None:
    """Write computed LQA snapshot for audit; not a backfill from stress results."""
    await db.execute(
        text(
            """
            DELETE FROM fsi.mktdata_lqa
            WHERE as_of_date = :as_of
              AND security_code IN :codes
              AND data_source = 'COMPUTED'
            """
        ).bindparams(bindparam("codes", expanding=True)),
        {"as_of": as_of, "codes": [str(p["security_code"]) for p in positions]},
    )
    for row in positions:
        await db.execute(
            text(
                """
                INSERT INTO fsi.mktdata_lqa (
                    as_of_date, security_code, asset_category, duration_years,
                    price_volatility, expected_daily_volume, bid_ask_spread, spread_bps,
                    sector_score, liquidity_sector, hk_sfc_port_lqdty_class, liq_horizon_days,
                    unif_mkt_imp_cost,
                    empirical_trade_count, empirical_evaluation_date, empirical_min_trade_volume,
                    empirical_source_date, empirical_days_since_last_trade, empirical_avg_trade_volume,
                    empirical_max_trade_volume, empirical_lookback_period, empirical_total_trade_volume,
                    data_source
                ) VALUES (
                    :as_of, :security_code, :asset_category, :duration,
                    :price_volatility, :expected_daily_volume, :bid_ask_spread, :spread_bps,
                    :sector_score, :liquidity_sector, :hk_sfc_port_lqdty_class, :liq_horizon_days,
                    :unif_mkt_imp_cost,
                    :empirical_trade_count, :empirical_evaluation_date, :empirical_min_trade_volume,
                    :empirical_source_date, :empirical_days_since_last_trade, :empirical_avg_trade_volume,
                    :empirical_max_trade_volume, :empirical_lookback_period, :empirical_total_trade_volume,
                    'COMPUTED'
                )
                ON CONFLICT (as_of_date, security_code) DO UPDATE SET
                    asset_category = EXCLUDED.asset_category,
                    duration_years = EXCLUDED.duration_years,
                    price_volatility = EXCLUDED.price_volatility,
                    expected_daily_volume = EXCLUDED.expected_daily_volume,
                    bid_ask_spread = EXCLUDED.bid_ask_spread,
                    spread_bps = EXCLUDED.spread_bps,
                    sector_score = EXCLUDED.sector_score,
                    liquidity_sector = EXCLUDED.liquidity_sector,
                    hk_sfc_port_lqdty_class = EXCLUDED.hk_sfc_port_lqdty_class,
                    liq_horizon_days = EXCLUDED.liq_horizon_days,
                    unif_mkt_imp_cost = EXCLUDED.unif_mkt_imp_cost,
                    empirical_trade_count = EXCLUDED.empirical_trade_count,
                    empirical_evaluation_date = EXCLUDED.empirical_evaluation_date,
                    empirical_min_trade_volume = EXCLUDED.empirical_min_trade_volume,
                    empirical_source_date = EXCLUDED.empirical_source_date,
                    empirical_days_since_last_trade = EXCLUDED.empirical_days_since_last_trade,
                    empirical_avg_trade_volume = EXCLUDED.empirical_avg_trade_volume,
                    empirical_max_trade_volume = EXCLUDED.empirical_max_trade_volume,
                    empirical_lookback_period = EXCLUDED.empirical_lookback_period,
                    empirical_total_trade_volume = EXCLUDED.empirical_total_trade_volume,
                    data_source = 'COMPUTED',
                    loaded_at = NOW()
                """
            ),
            {
                "as_of": as_of,
                "security_code": row["security_code"],
                "asset_category": row.get("asset_category"),
                "duration": row.get("duration"),
                "price_volatility": row.get("price_volatility"),
                "expected_daily_volume": row.get("expected_daily_volume"),
                "bid_ask_spread": row.get("bid_ask_spread"),
                "spread_bps": row.get("spread_bps"),
                "sector_score": row.get("sector_score"),
                "liquidity_sector": row.get("liquidity_sector"),
                "hk_sfc_port_lqdty_class": row.get("hk_sfc_port_lqdty_class"),
                "liq_horizon_days": row.get("liq_horizon_days"),
                "unif_mkt_imp_cost": row.get("unif_mkt_imp_cost"),
                "empirical_trade_count": row.get("empirical_trade_count"),
                "empirical_evaluation_date": row.get("empirical_evaluation_date"),
                "empirical_min_trade_volume": row.get("empirical_min_trade_volume"),
                "empirical_source_date": row.get("empirical_source_date"),
                "empirical_days_since_last_trade": row.get("empirical_days_since_last_trade"),
                "empirical_avg_trade_volume": row.get("empirical_avg_trade_volume"),
                "empirical_max_trade_volume": row.get("empirical_max_trade_volume"),
                "empirical_lookback_period": row.get("empirical_lookback_period"),
                "empirical_total_trade_volume": row.get("empirical_total_trade_volume"),
            },
        )
    await db.commit()


async def compute_lqa_portfolio_analytics(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    *,
    scenario: str = "SEVERE",
    redemption_pct: float = 100.0,
    cost_multiple: float = 0.5,
    include_current_day: bool = True,
) -> dict[str, Any]:
    book_date = await _latest_book_date(db, fund_id, as_of_date)
    holdings = await _load_holdings(db, fund_id, book_date) if book_date else []
    codes = [str(row["security_code"]) for row in holdings]
    adtv_map = await _load_adtv_map(db, codes, as_of_date)
    spreads = await _load_bid_ask_bps(db)
    fi_ladder = await _load_fi_horizon_ladder(db)
    positions = _fields.enrich_book(
        holdings,
        adtv_by_code=adtv_map,
        bid_ask_bps_by_asset=spreads,
        as_of_date=book_date,
        fi_horizon_ladder=fi_ladder or None,
    )
    if positions and book_date is not None:
        await _persist_computed_lqa(db, book_date, positions)

    analytics = _lqap.analyze(
        positions,
        scenario_code=scenario,
        redemption_pct=redemption_pct,
        cost_multiple=cost_multiple,
        include_current_day=include_current_day,
    )
    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date.isoformat(),
        "data_as_of": book_date.isoformat() if book_date is not None else None,
        "currency": "USD",
        "message": None if positions else "所选日期之前没有组合持仓，无法生成 LQAP。",
        "lqa_proxy_positions": len(positions),
        "lqa_missing_positions": 0,
        "lqa_input": "balance_* + mktdata_adtv + sfc_liquidity_bucket_def",
        **analytics,
    }
