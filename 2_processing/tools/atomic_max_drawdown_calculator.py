"""原子指標計算器：最大回撤 (%) (Atomic Max Drawdown Calculator)。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_max_drawdown.sql"


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
class AtomicMaxDrawdownRecord:
    """最大回撤數據模型。"""

    fund_id: str
    start_date: date
    end_date: date
    max_drawdown_pct: float
    trough_date: Optional[date]
    trough_nav: float
    peak_nav: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期欄位自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        if self.trough_date:
            data["trough_date"] = self.trough_date.isoformat()
        return data


async def compute_atomic_max_drawdown(
    fund_id: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicMaxDrawdownRecord]:
    """執行最大回撤 (%) 計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param start_date: 區間起始日 (支持 str 或 date)
    :param end_date: 區間截止日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: Optional[AtomicMaxDrawdownRecord]
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
            "未找到最大回撤數據: fund_id=%s, range=[%s, %s]",
            fund_id,
            parsed_start_date,
            parsed_end_date,
        )
        return None

    trough_dt = row.trough_date
    if trough_dt and not isinstance(trough_dt, date):
        trough_dt = _parse_date(str(trough_dt))

    return AtomicMaxDrawdownRecord(
        fund_id=str(row.fund_id),
        start_date=row.start_date if isinstance(row.start_date, date) else parsed_start_date,
        end_date=row.end_date if isinstance(row.end_date, date) else parsed_end_date,
        max_drawdown_pct=float(row.max_drawdown_pct or 0.0),
        trough_date=trough_dt,
        trough_nav=float(row.trough_nav or 0.0),
        peak_nav=float(row.peak_nav or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_max_drawdown(
    fund_id: str,
    start_date: str,
    end_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param start_date: 計算區間起始日，字串格式如 'YYYY-MM-DD'
    :param end_date: 計算區間截止日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_max_drawdown(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {start_date} 至 {end_date} 區間內的最大回撤數據。"

        if as_json:
            return record.to_dict()

        # 格式化輸出文字摘要
        trough_str = record.trough_date.isoformat() if record.trough_date else "N/A"
        lines = [
            f"基金 [{fund_id}] 在 {record.start_date} 至 {record.end_date} 區間的最大回撤計算結果：",
            f"- 最大回撤率 (Max Drawdown)：{record.max_drawdown_pct:.4f}%",
            f"- 峰值淨值 (Peak NAV)：{record.peak_nav:,.4f}",
            f"- 谷底淨值 (Trough NAV)：{record.trough_nav:,.4f}",
            f"- 谷底發生日期：{trough_str}",
        ]

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行最大回撤計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 最大回撤時發生錯誤: {str(exc)}"