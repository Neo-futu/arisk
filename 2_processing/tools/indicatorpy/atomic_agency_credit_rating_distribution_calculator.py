"""基金組合按評級機構分劃信用評級分布占比計算器。

Atomic Agency Credit Rating Distribution Calculator.
本模組提供供上層 Agent Skills / Tool Router 調用的標準數據查詢與計算介面。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_agency_credit_rating_distribution.sql"


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
class AgencyRatingItem:
    """單個評級機構下特定信用評級分布明細。"""

    rating_agency: str
    rating_agency_name: str
    credit_rating: str
    rating_market_value_hkd: float
    nav_weight_pct: float
    total_bond_weight_pct: float
    agency_share_pct: float
    agency_sort_order: int
    rating_sort_order: int

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式。"""
        return asdict(self)


@dataclass
class AtomicAgencyCreditRatingDistributionRecord:
    """評級機構信用評級分布完整計算結果。"""

    fund_id: str
    as_of_date: date
    ratings: List[AgencyRatingItem]

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        return {
            "fund_id": self.fund_id,
            "as_of_date": self.as_of_date.isoformat(),
            "ratings": [item.to_dict() for item in self.ratings],
        }


async def compute_atomic_agency_credit_rating_distribution(
    fund_id: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicAgencyCreditRatingDistributionRecord]:
    """執行基金組合按評級機構分劃信用評級分布占比計算的核心 DB 查詢。

    :param fund_id: 基金/組合 ID (port_id)
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: SQLAlchemy AsyncSession 數據庫會話
    :return: AtomicAgencyCreditRatingDistributionRecord 或 None
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
    rows = result.fetchall()

    if not rows:
        logger.warning(
            "未找到相應持倉或評級數據: fund_id=%s, as_of_date=%s",
            fund_id,
            parsed_date,
        )
        return None

    items = [
        AgencyRatingItem(
            rating_agency=str(row.rating_agency or ""),
            rating_agency_name=str(row.rating_agency_name or ""),
            credit_rating=str(row.credit_rating or "NR"),
            rating_market_value_hkd=float(row.rating_market_value_hkd or 0.0),
            nav_weight_pct=float(row.nav_weight_pct or 0.0),
            total_bond_weight_pct=float(row.total_bond_weight_pct or 0.0),
            agency_share_pct=float(row.agency_share_pct or 0.0),
            agency_sort_order=int(row.agency_sort_order or 999),
            rating_sort_order=int(row.rating_sort_order or 999),
        )
        for row in rows
    ]

    return AtomicAgencyCreditRatingDistributionRecord(
        fund_id=fund_id,
        as_of_date=parsed_date,
        ratings=items,
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_agency_credit_rating_distribution(
    fund_id: str,
    as_of_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param as_of_date: 計算基準日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 數據庫會話
    :param as_json: 若為 True，返回 Dict；若為 False，返回 Markdown 表格與文字摘要
    :return: 供 Agent 使用的文字描述/表格或結構化數據
    """
    try:
        record = await compute_atomic_agency_credit_rating_distribution(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
        )

        if not record or not record.ratings:
            return f"【查詢結果】未查到基金 [{fund_id}] 在基準日 {as_of_date} 的評級機構信用評級數據。"

        if as_json:
            return record.to_dict()

        # 生成 Markdown 表格供 LLM 展示
        table_lines = [
            f"基金 [{record.fund_id}] 在基準日 {record.as_of_date} 的按評級機構劃分信用評級分布：\n",
            "| 評級機構 | 評級機構名稱 | 信用評級 | 市值 (HKD) | 占 NAV 比例 (%) | 占債券總重 (%) | 機構內占比 (%) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for item in record.ratings:
            table_lines.append(
                f"| {item.rating_agency} | {item.rating_agency_name} | {item.credit_rating} "
                f"| {item.rating_market_value_hkd:,.2f} | {item.nav_weight_pct:.2f}% "
                f"| {item.total_bond_weight_pct:.2f}% | {item.agency_share_pct:.2f}% |"
            )

        return "\n".join(table_lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行評級機構信用評級分布計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 評級機構信用評級分布時發生錯誤: {str(exc)}"