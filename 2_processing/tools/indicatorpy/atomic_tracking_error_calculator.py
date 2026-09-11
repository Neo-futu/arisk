"""原子指標計算器：基金組合跟蹤誤差 (Tracking Error) 計算器。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_tracking_error.sql"


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
class AtomicTrackingErrorRecord:
    """基金組合跟蹤誤差數據模型。"""

    fund_id: str
    benchmark_code: str
    start_date: date
    end_date: date
    trading_days_count: int
    avg_daily_excess_return_pct: float
    daily_tracking_error_pct: float
    annualized_tracking_error_252_pct: float
    annualized_tracking_error_365_pct: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


async def compute_atomic_tracking_error(
    fund_id: str,
    benchmark_code: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicTrackingErrorRecord]:
    """執行基金組合跟蹤誤差 (Tracking Error) 計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param benchmark_code: 基準指數代碼 (如 'HSI', 'SPX')
    :param start_date: 區間起始日 (支持 str 或 date)
    :param end_date: 區間結束日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: Optional[AtomicTrackingErrorRecord]
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
            "bm_code": benchmark_code,
            "start_date": parsed_start,
            "end_date": parsed_end,
        },
    )
    row = result.fetchone()

    trading_days = int(getattr(row, "trading_days_count", 0) or 0)
    if not row or trading_days == 0:
        logger.warning(
            "未找到跟蹤誤差數據: fund_id=%s, benchmark_code=%s, start_date=%s, end_date=%s",
            fund_id,
            benchmark_code,
            parsed_start,
            parsed_end,
        )
        return None

    row_fund_id = str(getattr(row, "fund_id", None) or fund_id)
    row_bm_code = str(getattr(row, "benchmark_code", None) or benchmark_code)
    row_start = getattr(row, "start_date", None)
    row_end = getattr(row, "end_date", None)

    record_start = row_start if isinstance(row_start, date) else parsed_start
    record_end = row_end if isinstance(row_end, date) else parsed_end

    return AtomicTrackingErrorRecord(
        fund_id=row_fund_id,
        benchmark_code=row_bm_code,
        start_date=record_start,
        end_date=record_end,
        trading_days_count=trading_days,
        avg_daily_excess_return_pct=float(getattr(row, "avg_daily_excess_return_pct", 0.0) or 0.0),
        daily_tracking_error_pct=float(getattr(row, "daily_tracking_error_pct", 0.0) or 0.0),
        annualized_tracking_error_252_pct=float(getattr(row, "annualized_tracking_error_252_pct", 0.0) or 0.0),
        annualized_tracking_error_365_pct=float(getattr(row, "annualized_tracking_error_365_pct", 0.0) or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_tracking_error(
    fund_id: str,
    benchmark_code: str,
    start_date: str,
    end_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'FOF_01'
    :param benchmark_code: 基準指數代碼，例如 'HSI'
    :param start_date: 區間起始日，字串格式如 'YYYY-MM-DD'
    :param end_date: 區間結束日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_tracking_error(
            fund_id=fund_id,
            benchmark_code=benchmark_code,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not record:
            return (
                f"【查詢結果】未查到基金 [{fund_id}] 對比基準 [{benchmark_code}] "
                f"在區間 {start_date} 至 {end_date} 的跟蹤誤差數據。"
            )

        if as_json:
            return record.to_dict()

        # 檢查統計樣本數量警示
        warning_msg = ""
        if record.trading_days_count < 30:
            warning_msg = f"（警告：樣本交易日僅 {record.trading_days_count} 天，統計結果可能不具代表性）"

        # 格式化輸出文字摘要
        lines = [
            f"基金 [{record.fund_id}] 對比基準 [{record.benchmark_code}] 在區間 {record.start_date} 至 {record.end_date} 的跟蹤誤差計算結果{warning_msg}：",
            f"- 有效交易天數 (Trading Days): {record.trading_days_count} 天",
            f"- 平均每日超額收益率 (Avg Daily Excess Return): {record.avg_daily_excess_return_pct:.4f}%",
            f"- 日跟蹤誤差 (Daily Tracking Error): {record.daily_tracking_error_pct:.4f}%",
            f"- 年化跟蹤誤差 (252 日算子): {record.annualized_tracking_error_252_pct:.4f}%",
            f"- 年化跟蹤誤差 (365 日算子): {record.annualized_tracking_error_365_pct:.4f}%",
        ]

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行跟蹤誤差計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 對比基準 [{benchmark_code}] 跟蹤誤差時發生錯誤: {str(exc)}"