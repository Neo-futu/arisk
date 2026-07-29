"""年化波動率 (%) 計算器 (Atomic Annualized Volatility Calculator)。

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

SQL_FILE_PATH = Path(__file__).parent / "atomic_annualized_volatility.sql"


@lru_cache(maxsize=1)
def _load_sql_query(file_path: Path = SQL_FILE_PATH) -> str:
    """載入 SQL 查詢語句，並使用快取避免重複讀取磁碟。"""
    if not file_path.exists():
        raise FileNotFoundError(f"SQL 檔案不存在: {file_path}")
    return file_path.read_text(encoding="utf-8")


def _parse_date(value: Union[str, date]) -> date:
    """相容解析 Agent 傳入的日期參數 (支持 str 与 date)。"""
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
class AtomicAnnualizedVolatilityRecord:
    """年化波動率計算結果數據模型。"""

    fund_id: str
    start_date: date
    end_date: date
    trading_days: int
    daily_volatility_pct: float
    annualized_volatility_252_pct: float
    annualized_volatility_365_pct: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


async def compute_atomic_annualized_volatility(
    fund_id: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicAnnualizedVolatilityRecord]:
    """執行年化波動率 (%) 計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID (port_id)
    :param start_date: 計算起始日期 (支持 str 或 date)
    :param end_date: 計算截止日期 (支持 str 或 date)
    :param db: SQLAlchemy AsyncSession 數據庫會話
    :return: AtomicAnnualizedVolatilityRecord 或 None
    """
    parsed_start_date = _parse_date(start_date)
    parsed_end_date = _parse_date(end_date)

    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "start_date": parsed_start_date,
            "end_date": parsed_end_date,
        },
    )
    row = result.fetchone()

    if not row or row.fund_id is None:
        logger.warning(
            "未找到相應波動率數據: fund_id=%s, range=[%s, %s]",
            fund_id,
            parsed_start_date,
            parsed_end_date,
        )
        return None

    return AtomicAnnualizedVolatilityRecord(
        fund_id=str(row.fund_id),
        start_date=row.start_date,
        end_date=row.end_date,
        trading_days=int(row.trading_days or 0),
        daily_volatility_pct=float(row.daily_volatility_pct or 0.0),
        annualized_volatility_252_pct=float(row.annualized_volatility_252_pct or 0.0),
        annualized_volatility_365_pct=float(row.annualized_volatility_365_pct or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_annualized_volatility(
    fund_id: str,
    start_date: str,
    end_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param start_date: 計算起始日期，字串格式如 'YYYY-MM-DD'
    :param end_date: 計算截止日期，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 數據庫會話
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_annualized_volatility(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {start_date} 至 {end_date} 區間內的年化波動率數據。"

        if as_json:
            return record.to_dict()

        return (
            f"基金 [{record.fund_id}] 在 {record.start_date} 至 {record.end_date} 區間的年化波動率計算結果：\n"
            f"- 交易日數量：{record.trading_days} 天\n"
            f"- 日收益率波動率：{record.daily_volatility_pct:.4f}%\n"
            f"- 年化波動率 (基于 252 交易日)：{record.annualized_volatility_252_pct:.4f}%\n"
            f"- 年化波動率 (基于 365 自然日)：{record.annualized_volatility_365_pct:.4f}%"
        )

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行年化波動率計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 年化波動率時發生錯誤: {str(exc)}"