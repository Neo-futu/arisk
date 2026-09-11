"""原子指標計算器：貨幣基金組合加權平均剩餘存續期 (WAL) 及 Duration 計算器。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_wal.sql"


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
class AtomicPortfolioWalRecord:
    """貨幣基金組合加權平均剩餘存續期數據模型。"""

    fund_id: str
    as_of_date: date
    total_portfolio_nav: float
    total_mmf_mv: float
    mmf_weight_pct: float
    wal_days_mmf_only: float
    wal_years_mmf_only: float
    weighted_duration_years: float
    wal_days_total_nav: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["as_of_date"] = self.as_of_date.isoformat()
        return data


async def compute_atomic_portfolio_wal(
    fund_id: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicPortfolioWalRecord]:
    """執行貨幣基金組合加權平均剩餘存續期 (WAL) 及 Duration 計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: Optional[AtomicPortfolioWalRecord]
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

    if not row or row.fund_id is None or float(row.total_portfolio_nav or 0.0) == 0:
        logger.warning(
            "未找到貨幣基金組合加權平均剩餘存續期 (WAL) 計算數據: fund_id=%s, as_of_date=%s",
            fund_id,
            parsed_date,
        )
        return None

    return AtomicPortfolioWalRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date if isinstance(row.as_of_date, date) else parsed_date,
        total_portfolio_nav=float(row.total_portfolio_nav or 0.0),
        total_mmf_mv=float(row.total_mmf_mv or 0.0),
        mmf_weight_pct=float(row.mmf_weight_pct or 0.0),
        wal_days_mmf_only=float(row.wal_days_mmf_only or 0.0),
        wal_years_mmf_only=float(row.wal_years_mmf_only or 0.0),
        weighted_duration_years=float(row.weighted_duration_years or 0.0),
        wal_days_total_nav=float(row.wal_days_total_nav or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_portfolio_wal(
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
        record = await compute_atomic_portfolio_wal(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {as_of_date} 的加權平均剩餘存續期 (WAL) 數據。"

        if as_json:
            return record.to_dict()

        # 格式化輸出文字摘要
        lines = [
            f"貨幣基金 [{record.fund_id}] 截至 {record.as_of_date} 的 WAL 與 Duration 計算結果：",
            f"- 組合總淨值 (Total NAV)：HKD {record.total_portfolio_nav:,.2f}",
            f"- 貨幣工具總市值 (Total MMF MV)：HKD {record.total_mmf_mv:,.2f}",
            f"- 貨幣工具資產佔比 (MMF Weight)：{record.mmf_weight_pct:.2f}%",
            f"- 剩餘存續期_貨幣部位 (WAL - MMF Only)：{record.wal_days_mmf_only:.2f} 天 ({record.wal_years_mmf_only:.4f} 年)",
            f"- 剩餘存續期_全組合淨值 (WAL - Total NAV)：{record.wal_days_total_nav:.2f} 天",
            f"- 加權存續期 (Weighted Duration)：{record.weighted_duration_years:.4f} 年",
        ]

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行組合 WAL 計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] WAL 時發生錯誤: {str(exc)}"