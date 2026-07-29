"""原子指標計算器：七日年化收益率（貨幣 %）計算器。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_seven_day_annualized_yield.sql"


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
class SevenDayAnnualizedYieldRecord:
    """七日年化收益率數據模型。"""

    fund_id: str
    as_of_date: date
    sample_days: int
    seven_day_annualized_yield_pct: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["as_of_date"] = self.as_of_date.isoformat()
        return data


async def compute_atomic_seven_day_annualized_yield(
    fund_id: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
) -> Optional[SevenDayAnnualizedYieldRecord]:
    """讀取 SQL 檔案並計算原子指標：七日年化收益率（貨幣 %）的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: Optional[SevenDayAnnualizedYieldRecord]
    """
    parsed_date = _parse_date(as_of_date)
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": parsed_date,
        },
    )
    row = result.fetchone()

    if not row or getattr(row, "as_of_date", None) is None:
        logger.warning(
            "未找到七日年化收益率數據: fund_id=%s, as_of_date=%s",
            fund_id,
            parsed_date,
        )
        return None

    row_fund_id = str(getattr(row, "fund_id", None) or fund_id)
    row_date = getattr(row, "as_of_date", None)
    record_date = row_date if isinstance(row_date, date) else parsed_date

    yield_val = getattr(row, "seven_day_annualized_yield_pct", None)

    return SevenDayAnnualizedYieldRecord(
        fund_id=row_fund_id,
        as_of_date=record_date,
        sample_days=int(getattr(row, "sample_days", 0) or 0),
        seven_day_annualized_yield_pct=float(yield_val) if yield_val is not None else None,
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_seven_day_annualized_yield(
    fund_id: str,
    as_of_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'MMF_01'
    :param as_of_date: 計算基準日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_seven_day_annualized_yield(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {as_of_date} 的七日年化收益率數據。"

        if as_json:
            return record.to_dict()

        # 格式化輸出文字摘要
        yield_str = (
            f"{record.seven_day_annualized_yield_pct:.4f}%"
            if record.seven_day_annualized_yield_pct is not None
            else "無資料/不適用"
        )

        sample_status = ""
        if record.sample_days < 7:
            sample_status = f"（警告：數據樣本不足 7 天，僅 {record.sample_days} 天）"

        lines = [
            f"貨幣基金 [{record.fund_id}] 截至 {record.as_of_date} 的七日年化收益率計算結果：",
            f"- 七日年化收益率 (7-Day Annualized Yield)：{yield_str}{sample_status}",
            f"- 有效樣本天數 (Sample Days)：{record.sample_days} 天",
        ]

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行七日年化收益率計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 七日年化收益率時發生錯誤: {str(exc)}"