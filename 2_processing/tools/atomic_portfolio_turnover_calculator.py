"""原子指標計算器：基金組合年換手率 (Annualized Portfolio Turnover Rate) 計算器 (Atomic Portfolio Turnover Calculator)。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_turnover.sql"


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
class AtomicPortfolioTurnoverRecord:
    """基金組合年換手率數據模型。"""

    fund_id: str
    start_date: date
    end_date: date
    days_in_period: int
    avg_net_asset_value_hkd: float
    total_purchases_hkd: float
    total_sales_hkd: float
    turnover_base_amount_hkd: float
    period_turnover_rate_pct: float
    annualized_turnover_rate_pct: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


async def compute_atomic_portfolio_turnover(
    fund_id: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicPortfolioTurnoverRecord]:
    """執行基金組合年換手率計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param start_date: 計算區間起始日
    :param end_date: 計算區間結束日
    :param db: AsyncSession 資料庫連線
    :return: Optional[AtomicPortfolioTurnoverRecord]
    """
    parsed_start_date = _parse_date(start_date)
    parsed_end_date = _parse_date(end_date)
    
    if parsed_start_date > parsed_end_date:
        raise ValueError("起始日期不能晚於結束日期。")

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

    if not row or row.fund_id is None or float(row.avg_net_asset_value_hkd or 0.0) == 0:
        logger.warning(
            "未找到雙邊換手率計算所需數據或平均淨值為 0: fund_id=%s, start_date=%s, end_date=%s",
            fund_id,
            parsed_start_date,
            parsed_end_date,
        )
        return None

    return AtomicPortfolioTurnoverRecord(
        fund_id=str(row.fund_id),
        start_date=row.start_date if isinstance(row.start_date, date) else parsed_start_date,
        end_date=row.end_date if isinstance(row.end_date, date) else parsed_end_date,
        days_in_period=int(row.days_in_period or 0),
        avg_net_asset_value_hkd=float(row.avg_net_asset_value_hkd or 0.0),
        total_purchases_hkd=float(row.total_purchases_hkd or 0.0),
        total_sales_hkd=float(row.total_sales_hkd or 0.0),
        turnover_base_amount_hkd=float(row.turnover_base_amount_hkd or 0.0),
        period_turnover_rate_pct=float(row.period_turnover_rate_pct or 0.0),
        annualized_turnover_rate_pct=float(row.annualized_turnover_rate_pct or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_portfolio_turnover(
    fund_id: str,
    start_date: str,
    end_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param start_date: 計算區間起始日，字串格式如 'YYYY-MM-DD'
    :param end_date: 計算區間結束日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_portfolio_turnover(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 在區間 {start_date} 至 {end_date} 的年換手率數據 (可能是期間無交易或缺乏淨值數據)。"

        if as_json:
            return record.to_dict()

        # 格式化輸出文字摘要
        lines = [
            f"基金 [{record.fund_id}] 期間 {record.start_date} 至 {record.end_date} ({record.days_in_period}天) 的組合換手率計算結果：",
            f"- 區間平均總淨值 (Avg NAV)：HKD {record.avg_net_asset_value_hkd:,.2f}",
            f"- 總買入金額 (Total Purchases)：HKD {record.total_purchases_hkd:,.2f}",
            f"- 總賣出金額 (Total Sales)：HKD {record.total_sales_hkd:,.2f}",
            f"- 換手基礎金額 (Turnover Base Amount, 取較小值)：HKD {record.turnover_base_amount_hkd:,.2f}",
            f"- 區間換手率 (Period Rate)：{record.period_turnover_rate_pct:.2f}%",
            f"- 年化換手率 (Annualized Rate)：{record.annualized_turnover_rate_pct:.2f}%",
        ]

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行組合年換手率計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 換手率時發生錯誤: {str(exc)}"