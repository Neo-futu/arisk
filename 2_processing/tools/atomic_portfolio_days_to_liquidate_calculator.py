"""原子指標計算器：組合變現天數 (Days to Liquidate Portfolio) (Atomic Portfolio Days To Liquidate Calculator)。

本模組提供供上層 Agent Skills / Tool Router 調用的標準數據查詢與計算介面。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 指向同目錄下的獨立 SQL 檔案
SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_days_to_liquidate.sql"


@lru_cache(maxsize=1)
def _load_sql_query(file_path: Path = SQL_FILE_PATH) -> str:
    """載入 SQL 查詢語句，並使用快取避免重複讀取磁碟。"""
    if not file_path.exists():
        raise FileNotFoundError(f"SQL 檔案不存在: {file_path}")
    return file_path.read_text(encoding="utf-8")


def _parse_date(value: Union[str, date]) -> date:
    """相容解析 Agent 傳入的日期參數 (支持 str 與 date)。"""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        clean_str = value.strip().replace("/", "-")
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(clean_str, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"無法解析日期格式: '{value}'，請提供 YYYY-MM-DD 格式。")
    raise TypeError(f"不支持的日期類型: {type(value)}")


@dataclass
class AtomicPortfolioDaysToLiquidateRecord:
    """組合變現天數數據模型。"""

    fund_id: str
    as_of_date: date
    total_nav_hkd: float
    total_position_market_value_hkd: float
    adv_participation_rate_parameter: float
    max_days_to_liquidate: float
    weighted_avg_days_to_liquidate: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["as_of_date"] = self.as_of_date.isoformat()
        return data


async def compute_atomic_portfolio_days_to_liquidate(
    fund_id: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
    adv_participation_rate: float = 0.20,
) -> Optional[AtomicPortfolioDaysToLiquidateRecord]:
    """執行組合變現天數計算的核心 DB 查詢函數。

    :param fund_id: 基金代號
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :param adv_participation_rate: 假定佔市場日均成交量之最高比例（預設 20% 即 0.20）
    :return: Optional[AtomicPortfolioDaysToLiquidateRecord]
    """
    parsed_date = _parse_date(as_of_date)
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": parsed_date,
            "adv_participation_rate": adv_participation_rate,
        },
    )
    row = result.fetchone()

    if not row or row.fund_id is None or float(row.total_nav_hkd or 0.0) == 0:
        logger.warning(
            "未找到組合變現天數數據: fund_id=%s, as_of_date=%s",
            fund_id,
            parsed_date,
        )
        return None

    return AtomicPortfolioDaysToLiquidateRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date if isinstance(row.as_of_date, date) else parsed_date,
        total_nav_hkd=float(row.total_nav_hkd or 0.0),
        total_position_market_value_hkd=float(row.total_position_market_value_hkd or 0.0),
        adv_participation_rate_parameter=float(
            row.adv_participation_rate_parameter or adv_participation_rate
        ),
        max_days_to_liquidate=float(row.max_days_to_liquidate or 0.0),
        weighted_avg_days_to_liquidate=float(row.weighted_avg_days_to_liquidate or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_portfolio_days_to_liquidate(
    fund_id: str,
    as_of_date: str,
    db: AsyncSession,
    adv_participation_rate: float = 0.20,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param as_of_date: 計算基準日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param adv_participation_rate: 參與率上限（預設 0.20）
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_portfolio_days_to_liquidate(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
            adv_participation_rate=adv_participation_rate,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {as_of_date} 的組合變現天數數據。"

        if as_json:
            return record.to_dict()

        # 格式化輸出文字摘要
        lines = [
            f"基金 [{record.fund_id}] 截至 {record.as_of_date} 的組合變現天數計算結果 (參與率上限: {record.adv_participation_rate_parameter * 100:.1f}%)：",
            f"- 總淨值 (Total NAV)：HKD {record.total_nav_hkd:,.2f}",
            f"- 總持倉市值 (Total Position MV)：HKD {record.total_position_market_value_hkd:,.2f}",
            f"- 加權平均變現天數 (Weighted Avg Days)：{record.weighted_avg_days_to_liquidate:.2f} 天",
            f"- 最大單一資產變現天數 (Max Days)：{record.max_days_to_liquidate:.2f} 天",
        ]

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行組合變現天數計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 變現天數時發生錯誤: {str(exc)}"