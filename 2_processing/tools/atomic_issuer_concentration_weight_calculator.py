"""原子指標計算器：發行人集中度 (%) (Atomic Issuer Concentration Weight Calculator)。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_issuer_concentration_weight.sql"


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
class IssuerConcentrationWeightRecord:
    """發行人集中度佔比數據模型。"""

    fund_id: str
    as_of_date: date
    issuer_id: str
    issuer_name: str
    issuer_mv_hkd: float
    total_nav: float
    concentration_pct: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["as_of_date"] = self.as_of_date.isoformat()
        return data


async def compute_atomic_issuer_concentration_weight(
    fund_id: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
) -> List[IssuerConcentrationWeightRecord]:
    """讀取 SQL 檔案並執行發行人集中度 (%) 計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: List[IssuerConcentrationWeightRecord]
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
            "未找到發行人集中度數據: fund_id=%s, as_of_date=%s",
            fund_id,
            parsed_date,
        )
        return []

    records: List[IssuerConcentrationWeightRecord] = []
    for r in rows:
        if r.fund_id is None:
            continue
        records.append(
            IssuerConcentrationWeightRecord(
                fund_id=str(r.fund_id),
                as_of_date=r.as_of_date if isinstance(r.as_of_date, date) else parsed_date,
                issuer_id=str(r.issuer_id or "UNKNOWN_ISSUER"),
                issuer_name=str(r.issuer_name or "未命名發行人"),
                issuer_mv_hkd=float(r.issuer_mv_hkd or 0.0),
                total_nav=float(r.total_nav or 0.0),
                concentration_pct=float(r.concentration_pct)
                if r.concentration_pct is not None
                else None,
            )
        )

    return records


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_issuer_concentration_weight(
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
        records = await compute_atomic_issuer_concentration_weight(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
        )

        if not records:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {as_of_date} 的發行人集中度數據。"

        if as_json:
            return [r.to_dict() for r in records]

        # 格式化輸出文字摘要與表格
        total_nav = records[0].total_nav if records else 0.0
        lines = [
            f"基金 [{fund_id}] 截至 {as_of_date} 的發行人集中度 (%) 計算結果：",
            f"總淨值 (Total NAV): HKD {total_nav:,.2f}\n",
            "| 發行人 ID | 發行人名稱 | 發行人市值 (HKD) | 佔總淨值比 (%) |",
            "|---|---|---|---|",
        ]

        for r in records:
            conc_str = f"{r.concentration_pct:.4f}%" if r.concentration_pct is not None else "N/A"
            lines.append(f"| {r.issuer_id} | {r.issuer_name} | HKD {r.issuer_mv_hkd:,.2f} | {conc_str} |")

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行發行人集中度計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 發行人集中度時發生錯誤: {str(exc)}"

        