"""原子指標計算器：淨交易佔淨值比例 (Net Trade Amount to Average NAV Ratio) 計算器。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_stock_net_trade_to_nav_ratio.sql"


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
    raise TypeError(f"不支援的日期類型: {type(value)}")


@dataclass
class AtomicStockNetTradeToNavRatioRecord:
    """單個股票淨交易佔淨值比例數據模型。"""

    fund_id: str
    security_code: str
    start_date: date
    end_date: date
    avg_net_asset_value_hkd: float
    total_buy_amount_hkd: float
    total_sell_amount_hkd: float
    net_trade_amount_hkd: float
    net_trade_to_nav_ratio_pct: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


async def compute_atomic_stock_net_trade_to_nav_ratio(
    fund_id: str,
    security_code: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicStockNetTradeToNavRatioRecord]:
    """執行單個股票淨交易佔淨值比例計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param security_code: 證券代碼 (如 '700.HK', 'AAPL')
    :param start_date: 區間起始日 (支持 str 或 date)
    :param end_date: 區間結束日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: Optional[AtomicStockNetTradeToNavRatioRecord]
    """
    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)

    if parsed_start > parsed_end:
        raise ValueError(f"起始日期 ({parsed_start}) 不能晚於結束日期 ({parsed_end})")

    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "security_code": security_code,
            "start_date": parsed_start,
            "end_date": parsed_end,
        },
    )
    row = result.fetchone()

    if not row or getattr(row, "avg_net_asset_value_hkd", None) is None:
        logger.warning(
            "未找到淨交易佔淨值比例數據: fund_id=%s, security_code=%s, start_date=%s, end_date=%s",
            fund_id,
            security_code,
            parsed_start,
            parsed_end,
        )
        return None

    avg_nav = float(getattr(row, "avg_net_asset_value_hkd", 0.0) or 0.0)
    if avg_nav == 0.0:
        logger.warning(
            "區間平均淨值為 0，無法計算交易佔比: fund_id=%s, start_date=%s, end_date=%s",
            fund_id,
            parsed_start,
            parsed_end,
        )
        return None

    row_fund_id = str(getattr(row, "fund_id", None) or fund_id)
    row_sec_code = str(getattr(row, "security_code", None) or security_code)
    row_start = getattr(row, "start_date", None)
    row_end = getattr(row, "end_date", None)

    record_start = row_start if isinstance(row_start, date) else parsed_start
    record_end = row_end if isinstance(row_end, date) else parsed_end

    return AtomicStockNetTradeToNavRatioRecord(
        fund_id=row_fund_id,
        security_code=row_sec_code,
        start_date=record_start,
        end_date=record_end,
        avg_net_asset_value_hkd=avg_nav,
        total_buy_amount_hkd=float(getattr(row, "total_buy_amount_hkd", 0.0) or 0.0),
        total_sell_amount_hkd=float(getattr(row, "total_sell_amount_hkd", 0.0) or 0.0),
        net_trade_amount_hkd=float(getattr(row, "net_trade_amount_hkd", 0.0) or 0.0),
        net_trade_to_nav_ratio_pct=float(getattr(row, "net_trade_to_nav_ratio_pct", 0.0) or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_stock_net_trade_to_nav_ratio(
    fund_id: str,
    security_code: str,
    start_date: str,
    end_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'MAIN_FUND_01'
    :param security_code: 證券代碼，例如 '700.HK'
    :param start_date: 區間起始日，字串格式如 'YYYY-MM-DD'
    :param end_date: 區間結束日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_stock_net_trade_to_nav_ratio(
            fund_id=fund_id,
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not record:
            return (
                f"【查詢結果】未查到基金 [{fund_id}] 個股 [{security_code}] "
                f"在區間 {start_date} 至 {end_date} 的淨交易與 NAV 數據。"
            )

        if as_json:
            return record.to_dict()

        # 格式化輸出文字摘要
        lines = [
            f"基金 [{record.fund_id}] 個股 [{record.security_code}] 在區間 {record.start_date} 至 {record.end_date} 的淨交易佔 NAV 比例計算結果：",
            f"- 區間平均淨值 (Average NAV): HKD {record.avg_net_asset_value_hkd:,.2f}",
            f"- 區間累計買入金額 (Total Buy Amount): HKD {record.total_buy_amount_hkd:,.2f}",
            f"- 區間累計賣出金額 (Total Sell Amount): HKD {record.total_sell_amount_hkd:,.2f}",
            f"- 區間淨交易金額 (Net Trade Amount): HKD {record.net_trade_amount_hkd:,.2f}",
            f"- 淨交易佔平均淨值比例 (Net Trade to NAV Ratio): {record.net_trade_to_nav_ratio_pct:.4f}%",
        ]

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行淨交易佔淨值比例計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 個股 [{security_code}] 淨交易佔比時發生錯誤: {str(exc)}"