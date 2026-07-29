"""原子指標計算器：基金總槓桿率 (Total Portfolio Leverage Ratio) (Atomic Portfolio Leverage Calculator)。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_leverage.sql"


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
class AtomicPortfolioLeverageRecord:
    """基金總槓桿率數據模型。"""

    fund_id: str
    as_of_date: date
    total_nav_hkd: float
    total_gross_assets_hkd: float
    physical_asset_mv_hkd: float
    derivative_gross_notional_hkd: float
    total_gross_exposure_hkd: float
    gross_asset_leverage_pct: float
    gross_exposure_leverage_pct: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["as_of_date"] = self.as_of_date.isoformat()
        return data


async def compute_atomic_portfolio_leverage(
    fund_id: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicPortfolioLeverageRecord]:
    """執行基金總槓桿率計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: Optional[AtomicPortfolioLeverageRecord]
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

    if not row or row.fund_id is None or float(row.total_nav_hkd or 0.0) == 0:
        logger.warning(
            "未找到基金總槓桿率數據: fund_id=%s, as_of_date=%s",
            fund_id,
            parsed_date,
        )
        return None

    return AtomicPortfolioLeverageRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date if isinstance(row.as_of_date, date) else parsed_date,
        total_nav_hkd=float(row.total_nav_hkd or 0.0),
        total_gross_assets_hkd=float(row.total_gross_assets_hkd or 0.0),
        physical_asset_mv_hkd=float(row.physical_asset_mv_hkd or 0.0),
        derivative_gross_notional_hkd=float(row.derivative_gross_notional_hkd or 0.0),
        total_gross_exposure_hkd=float(row.total_gross_exposure_hkd or 0.0),
        gross_asset_leverage_pct=float(row.gross_asset_leverage_pct or 0.0),
        gross_exposure_leverage_pct=float(row.gross_exposure_leverage_pct or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_portfolio_leverage(
    fund_id: str,
    as_of_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param as_of_date: 計算基準日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_portfolio_leverage(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {as_of_date} 的總槓桿率數據。"

        if as_json:
            return record.to_dict()

        # 格式化輸出文字摘要
        lines = [
            f"基金 [{record.fund_id}] 截至 {record.as_of_date} 的總槓桿率計算結果：",
            f"- 組合總淨值 (Total NAV)：HKD {record.total_nav_hkd:,.2f}",
            f"- 實物資產市值 (Physical Asset MV)：HKD {record.physical_asset_mv_hkd:,.2f}",
            f"- 衍生品總名義本金 (Derivative Gross Notional)：HKD {record.derivative_gross_notional_hkd:,.2f}",
            f"- 總總額敞口 (Total Gross Exposure)：HKD {record.total_gross_exposure_hkd:,.2f}",
            f"- 資產總槓桿率 (Gross Asset Leverage)：{record.gross_asset_leverage_pct:.2f}%",
            f"- 總敞口槓桿率 (Gross Exposure Leverage)：{record.gross_exposure_leverage_pct:.2f}%",
        ]

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行基金總槓桿率計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 總槓桿率時發生錯誤: {str(exc)}"