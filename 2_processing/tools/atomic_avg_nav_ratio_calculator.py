"""日均佔資產淨值 (%) 計算器 (Atomic Avg NAV Ratio Calculator)。

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

SQL_FILE_PATH = Path(__file__).parent / "atomic_avg_nav_ratio.sql"


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
class AtomicAvgNavRatioRecord:
    """日均佔資產淨值比例數據模型。"""

    fund_id: str
    start_date: date
    end_date: date
    security_code: str
    security_name: str
    holding_days: int
    total_trading_days: int
    avg_nav_ratio_holding_period_pct: float
    avg_nav_ratio_full_period_pct: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


async def compute_atomic_avg_nav_ratio(
    fund_id: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> List[AtomicAvgNavRatioRecord]:
    """執行日均佔資產淨值 (%) 算術平均值計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID (port_id)
    :param start_date: 計算區間起始日 (支持 str 或 date)
    :param end_date: 計算區間截止日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: List[AtomicAvgNavRatioRecord]
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
    rows = result.fetchall()

    if not rows:
        logger.warning(
            "未找到日均佔淨值比數據: fund_id=%s, range=[%s, %s]",
            fund_id,
            parsed_start_date,
            parsed_end_date,
        )
        return []

    records: List[AtomicAvgNavRatioRecord] = []
    for r in rows:
        if r.fund_id is None:
            continue
        records.append(
            AtomicAvgNavRatioRecord(
                fund_id=str(r.fund_id),
                start_date=r.start_date if isinstance(r.start_date, date) else parsed_start_date,
                end_date=r.end_date if isinstance(r.end_date, date) else parsed_end_date,
                security_code=str(r.security_code or ""),
                security_name=str(r.security_name or "未知證券"),
                holding_days=int(r.holding_days or 0),
                total_trading_days=int(r.total_trading_days or 0),
                avg_nav_ratio_holding_period_pct=float(r.avg_nav_ratio_holding_period_pct or 0.0),
                avg_nav_ratio_full_period_pct=float(r.avg_nav_ratio_full_period_pct or 0.0),
            )
        )

    return records


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_avg_nav_ratio(
    fund_id: str,
    start_date: str,
    end_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, List[Dict[str, Any]]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param start_date: 計算區間起始日，字串格式如 'YYYY-MM-DD'
    :param end_date: 計算區間截止日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict 列表；若為 False，返回格式化文字/表格摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        records = await compute_atomic_avg_nav_ratio(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not records:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {start_date} 至 {end_date} 區間內的日均佔資產淨值數據。"

        if as_json:
            return [r.to_dict() for r in records]

        # 格式化輸出文字摘要與表格
        lines = [
            f"基金 [{fund_id}] 在 {start_date} 至 {end_date} 區間的日均佔資產淨值 (%) 計算結果：\n",
            "| 證券代碼 | 證券名稱 | 持有天數/總交易日 | 持有期日均 NAV 占比 (%) | 全期日均 NAV 占比 (%) |",
            "|---|---|---|---|---|",
        ]

        for r in records:
            days_str = f"{r.holding_days}/{r.total_trading_days}"
            lines.append(
                f"| {r.security_code} | {r.security_name} | {days_str} | "
                f"{r.avg_nav_ratio_holding_period_pct:.4f}% | {r.avg_nav_ratio_full_period_pct:.4f}% |"
            )

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行日均佔資產淨值計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 日均佔資產淨值時發生錯誤: {str(exc)}"