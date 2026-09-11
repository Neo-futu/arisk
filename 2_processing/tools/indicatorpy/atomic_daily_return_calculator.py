"""原子指標計算器：日收益率 (%) (Atomic Daily Return Calculator)。

本模組提供供上層 Agent Skills / Tool Router 調用的標準數據查詢與計算介面。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 指向同目錄下的獨立 SQL 檔案
SQL_FILE_PATH = Path(__file__).parent / "atomic_daily_return.sql"


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
class DailyReturnRecord:
    """日收益率數據模型。"""

    fund_id: str
    as_of_date: date
    total_nav: float
    prev_nav: Optional[float]
    daily_return_pct: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["as_of_date"] = self.as_of_date.isoformat()
        return data


async def compute_atomic_daily_return(
    fund_id: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
    lookback_days: int = 252,
) -> List[DailyReturnRecord]:
    """讀取 SQL 檔案並執行日收益率 (%) 計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :param lookback_days: 回溯天數 (預設 252)
    :return: List[DailyReturnRecord]
    """
    parsed_date = _parse_date(as_of_date)
    start_date = parsed_date - timedelta(days=int(lookback_days * 1.5))
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "start_date": start_date,
            "end_date": parsed_date,
        },
    )
    rows = result.fetchall()

    if not rows:
        logger.warning(
            "未找到日收益率數據: fund_id=%s, as_of_date=%s",
            fund_id,
            parsed_date,
        )
        return []

    records: List[DailyReturnRecord] = []
    for r in rows:
        if r.fund_id is None:
            continue
        records.append(
            DailyReturnRecord(
                fund_id=str(r.fund_id),
                as_of_date=r.as_of_date if isinstance(r.as_of_date, date) else parsed_date,
                total_nav=float(r.total_nav or 0.0),
                prev_nav=float(r.prev_nav) if r.prev_nav is not None else None,
                daily_return_pct=float(r.daily_return_pct)
                if r.daily_return_pct is not None
                else None,
            )
        )

    return records


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_daily_return(
    fund_id: str,
    as_of_date: str,
    db: AsyncSession,
    lookback_days: int = 252,
    as_json: bool = False,
) -> Union[str, List[Dict[str, Any]]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param as_of_date: 計算基準日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param lookback_days: 回溯天數，預設為 252
    :param as_json: 若為 True，返回 Dict 列表；若為 False，返回格式化文字/表格摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        records = await compute_atomic_daily_return(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
            lookback_days=lookback_days,
        )

        if not records:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {as_of_date} (回溯 {lookback_days} 天) 的日收益率數據。"

        if as_json:
            return [r.to_dict() for r in records]

        # 格式化輸出最新數筆紀錄表格與文字摘要
        display_records = records[-10:] if len(records) > 10 else records
        latest = records[-1]
        latest_ret = (
            f"{latest.daily_return_pct:.4f}%"
            if latest.daily_return_pct is not None
            else "N/A"
        )

        lines = [
            f"基金 [{fund_id}] 截至 {latest.as_of_date} 的日收益率計算結果：",
            f"- 最新日收益率：{latest_ret}",
            f"- 歷史數據筆數：{len(records)} 筆\n",
            "| 日期 | 當日單位淨值 (NAV) | 前日單位淨值 (NAV) | 日收益率 (%) |",
            "|---|---|---|---|",
        ]

        for r in display_records:
            prev_str = f"{r.prev_nav:.4f}" if r.prev_nav is not None else "N/A"
            ret_str = f"{r.daily_return_pct:.4f}%" if r.daily_return_pct is not None else "N/A"
            lines.append(f"| {r.as_of_date} | {r.total_nav:.4f} | {prev_str} | {ret_str} |")

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行日收益率計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 日收益率時發生錯誤: {str(exc)}"