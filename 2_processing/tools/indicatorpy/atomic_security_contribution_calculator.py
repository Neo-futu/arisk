"""原子指標計算器：個股/個券每日收益累計與區間貢獻計算器 (Atomic Security Contribution Calculator)。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_security_contribution.sql"


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
class AtomicSecurityContributionRecord:
    """個股/個券區間貢獻數據模型。"""

    fund_id: str
    start_date: date
    end_date: date
    security_code: str
    security_name: str
    avg_weight_pct: float
    simple_sum_contrib_pct: float
    cumulative_contrib_pct: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


async def compute_atomic_security_contribution(
    fund_id: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> List[AtomicSecurityContributionRecord]:
    """執行個股/個券每日收益累計與區間貢獻計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param start_date: 區間起始日 (支持 str 或 date)
    :param end_date: 區間結束日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: List[AtomicSecurityContributionRecord]
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
            "start_date": parsed_start,
            "end_date": parsed_end,
        },
    )
    rows = result.fetchall()

    if not rows:
        logger.warning(
            "未找到個券貢獻度計算數據: fund_id=%s, start_date=%s, end_date=%s",
            fund_id,
            parsed_start,
            parsed_end,
        )
        return []

    records = []
    for r in rows:
        row_fund_id = str(getattr(r, "fund_id", None) or fund_id)
        row_start = getattr(r, "start_date", None)
        row_end = getattr(r, "end_date", None)

        record_start = row_start if isinstance(row_start, date) else parsed_start
        record_end = row_end if isinstance(row_end, date) else parsed_end

        records.append(
            AtomicSecurityContributionRecord(
                fund_id=row_fund_id,
                start_date=record_start,
                end_date=record_end,
                security_code=str(getattr(r, "security_code", "")),
                security_name=str(getattr(r, "security_name", "")),
                avg_weight_pct=float(getattr(r, "avg_weight_pct", 0.0) or 0.0),
                simple_sum_contrib_pct=float(getattr(r, "simple_sum_contrib_pct", 0.0) or 0.0),
                cumulative_contrib_pct=float(getattr(r, "cumulative_contrib_pct", 0.0) or 0.0),
            )
        )

    return records


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_security_contribution(
    fund_id: str,
    start_date: str,
    end_date: str,
    db: AsyncSession,
    top_n: Optional[int] = None,
    as_json: bool = False,
) -> Union[str, List[Dict[str, Any]]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'EQUITY_01'
    :param start_date: 區間起始日，字串格式如 'YYYY-MM-DD'
    :param end_date: 區間結束日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param top_n: 選填，限制僅顯示累計貢獻最高的 前 N 個證券
    :param as_json: 若為 True，返回 List[Dict]；若為 False，返回 Markdown 表格摘要
    :return: 供 Agent 使用的文字描述/表格或結構化數據清單
    """
    try:
        records = await compute_atomic_security_contribution(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not records:
            return f"【查詢結果】未查到基金 [{fund_id}] 在區間 {start_date} 至 {end_date} 的個券貢獻度數據。"

        # 按複利累計貢獻度降序排序
        records.sort(key=lambda x: x.cumulative_contrib_pct, reverse=True)

        display_records = records[:top_n] if top_n and top_n > 0 else records

        if as_json:
            return [record.to_dict() for record in display_records]

        # 格式化輸出 Markdown 表格摘要
        s_date = records[0].start_date
        e_date = records[0].end_date

        title_suffix = f" (前 {top_n} 項)" if top_n and top_n < len(records) else ""
        lines = [
            f"基金 [{fund_id}] 在區間 {s_date} 至 {e_date} 的個券貢獻度計算結果{title_suffix}：\n",
            "| 證券代碼 | 證券名稱 | 平均權重 (%) | 簡單累計貢獻 (%) | 複利累計貢獻 (%) |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]

        for rec in display_records:
            lines.append(
                f"| {rec.security_code} | {rec.security_name} | {rec.avg_weight_pct:.2f}% | "
                f"{rec.simple_sum_contrib_pct:.4f}% | {rec.cumulative_contrib_pct:.4f}% |"
            )

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行個券區間貢獻度計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 個券貢獻度時發生錯誤: {str(exc)}"