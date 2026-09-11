"""原子指標計算器：某行業佔股票市值比 (%) (Atomic Industry Stock Weight Calculator)。

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

# 指向同目錄下的獨立 SQL 檔案
SQL_FILE_PATH = Path(__file__).parent / "atomic_industry_stock_weight.sql"


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
class IndustryStockWeightRecord:
    """行業股票市值佔比數據模型。"""

    fund_id: str
    as_of_date: date
    industry_name: str
    industry_stock_mv_hkd: float
    total_stock_mv: float
    industry_stock_weight_pct: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["as_of_date"] = self.as_of_date.isoformat()
        return data


async def compute_atomic_industry_stock_weight(
    fund_id: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
) -> List[IndustryStockWeightRecord]:
    """讀取 SQL 檔案並執行某行業佔股票市值比 (%) 計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: List[IndustryStockWeightRecord]
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
            "未找到行業股票市值佔比數據: fund_id=%s, as_of_date=%s",
            fund_id,
            parsed_date,
        )
        return []

    records: List[IndustryStockWeightRecord] = []
    for r in rows:
        if r.fund_id is None:
            continue
        records.append(
            IndustryStockWeightRecord(
                fund_id=str(r.fund_id),
                as_of_date=r.as_of_date if isinstance(r.as_of_date, date) else parsed_date,
                industry_name=str(r.industry_name or "未分類行業"),
                industry_stock_mv_hkd=float(r.industry_stock_mv_hkd or 0.0),
                total_stock_mv=float(r.total_stock_mv or 0.0),
                industry_stock_weight_pct=float(r.industry_stock_weight_pct)
                if r.industry_stock_weight_pct is not None
                else None,
            )
        )

    return records


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_industry_stock_weight(
    fund_id: str,
    as_of_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, List[Dict[str, Any]]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param as_of_date: 計算基準日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict 列表；若為 False，返回格式化文字/表格摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        records = await compute_atomic_industry_stock_weight(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
        )

        if not records:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {as_of_date} 的行業股票市值佔比數據。"

        if as_json:
            return [r.to_dict() for r in records]

        # 格式化輸出文字摘要與表格
        total_stock_mv = records[0].total_stock_mv if records else 0.0
        lines = [
            f"基金 [{fund_id}] 截至 {as_of_date} 的行業股票市值佔比 (%) 計算結果：",
            f"股票總市值 (Total Stock MV): HKD {total_stock_mv:,.2f}\n",
            "| 行業名稱 | 行業股票市值 (HKD) | 佔股票市值比 (%) |",
            "|---|---|---|",
        ]

        for r in records:
            weight_str = f"{r.industry_stock_weight_pct:.4f}%" if r.industry_stock_weight_pct is not None else "N/A"
            lines.append(f"| {r.industry_name} | HKD {r.industry_stock_mv_hkd:,.2f} | {weight_str} |")

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行行業股票市值佔比計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 行業股票市值佔比時發生錯誤: {str(exc)}"