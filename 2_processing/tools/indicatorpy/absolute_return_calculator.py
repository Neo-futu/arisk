"""絕對收益 (億元) 計算器 — AI Agent Tool 底層模組。

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

SQL_FILE_PATH = Path(__file__).parent / "absolute_return.sql"


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
class AbsoluteReturnRecord:
    """絕對收益計算結果數據模型。"""

    fund_id: str
    start_date: date
    end_date: date
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_dividend_income: float
    total_absolute_return: float
    realized_pnl_yi: float
    unrealized_pnl_yi: float
    dividend_income_yi: float
    absolute_return_yi: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


async def compute_absolute_return(
    fund_id: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AbsoluteReturnRecord]:
    """執行絕對收益 (億元) 計算的底層 DB 查詢函數。

    :param fund_id: 基金/組合 ID (port_id)
    :param start_date: 計算起始日期 (支持 str 或 date)
    :param end_date: 計算截止日期 (支持 str 或 date)
    :param db: SQLAlchemy AsyncSession 數據庫會話
    :return: AbsoluteReturnRecord 或 None
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

    # 若查無數據或全部為 NULL
    if not row or row.fund_id is None:
        logger.warning(
            "未找到相應持倉/盈虧數據: fund_id=%s, range=[%s, %s]",
            fund_id,
            parsed_start_date,
            parsed_end_date,
        )
        return None

    return AbsoluteReturnRecord(
        fund_id=str(row.fund_id),
        start_date=row.start_date,
        end_date=row.end_date,
        total_realized_pnl=float(row.total_realized_pnl or 0.0),
        total_unrealized_pnl=float(row.total_unrealized_pnl or 0.0),
        total_dividend_income=float(row.total_dividend_income or 0.0),
        total_absolute_return=float(row.total_absolute_return or 0.0),
        realized_pnl_yi=float(row.realized_pnl_yi or 0.0),
        unrealized_pnl_yi=float(row.unrealized_pnl_yi or 0.0),
        dividend_income_yi=float(row.dividend_income_yi or 0.0),
        absolute_return_yi=float(row.absolute_return_yi or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_fund_absolute_return(
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
        record = await compute_absolute_return(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {start_date} 至 {end_date} 區間內的盈虧數據。"

        if as_json:
            return record.to_dict()

        return (
            f"基金 [{record.fund_id}] 在 {record.start_date} 至 {record.end_date} 的絕對收益計算結果：\n"
            f"- 總絕對收益：{record.absolute_return_yi:.6f} 億元 ({record.total_absolute_return:,.2f} 元)\n"
            f"- 實現收益：{record.realized_pnl_yi:.6f} 億元 ({record.total_realized_pnl:,.2f} 元)\n"
            f"- 浮動盈虧：{record.unrealized_pnl_yi:.6f} 億元 ({record.total_unrealized_pnl:,.2f} 元)\n"
            f"- 利息分紅：{record.dividend_income_yi:.6f} 億元 ({record.total_dividend_income:,.2f} 元)"
        )

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行絕對收益計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 絕對收益時發生錯誤: {str(exc)}"