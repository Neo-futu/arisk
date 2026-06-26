"""匯率換算模組：從 DB / Redis / WindAPI 取匯率，統一換算為 HKD。"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from functools import lru_cache

import redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

REDIS_KEY_FX = "fx:{base}:{quote}:{date}"
FX_TTL_SECONDS = 300  # 5 分鐘緩存


async def get_fx_rate(
    base_ccy: str,
    quote_ccy: str,
    rate_date: date,
    db: AsyncSession,
    cache: redis.Redis | None = None,
) -> Decimal:
    """取指定日期的匯率 base→quote。相同貨幣直接返回 1.0。"""
    if base_ccy == quote_ccy:
        return Decimal("1.0")

    # 1. 嘗試 Redis 緩存
    if cache:
        key = REDIS_KEY_FX.format(base=base_ccy, quote=quote_ccy, date=rate_date)
        cached = cache.get(key)
        if cached:
            return Decimal(cached.decode())

    # 2. 查詢 Postgres
    result = await db.execute(
        text(
            "SELECT rate FROM fsi.fx_rates "
            "WHERE base_ccy = :base AND quote_ccy = :quote AND rate_date = :dt "
            "ORDER BY rate_date DESC LIMIT 1"
        ),
        {"base": base_ccy, "quote": quote_ccy, "dt": rate_date},
    )
    row = result.fetchone()

    if row is None:
        # 嘗試反向匯率
        result_inv = await db.execute(
            text(
                "SELECT rate FROM fsi.fx_rates "
                "WHERE base_ccy = :base AND quote_ccy = :quote AND rate_date <= :dt "
                "ORDER BY rate_date DESC LIMIT 1"
            ),
            {"base": quote_ccy, "quote": base_ccy, "dt": rate_date},
        )
        row_inv = result_inv.fetchone()
        if row_inv is None:
            logger.warning("No FX rate for %s/%s on %s, using 1.0", base_ccy, quote_ccy, rate_date)
            return Decimal("1.0")
        rate = Decimal("1.0") / Decimal(str(row_inv[0]))
    else:
        rate = Decimal(str(row[0]))

    # 3. 寫入緩存
    if cache:
        cache.setex(key, FX_TTL_SECONDS, str(rate))

    return rate


async def convert_to_hkd(
    amount: Decimal,
    from_ccy: str,
    rate_date: date,
    db: AsyncSession,
    cache: redis.Redis | None = None,
) -> Decimal:
    """將金額換算為 HKD。"""
    rate = await get_fx_rate(from_ccy, "HKD", rate_date, db, cache)
    return amount * rate
