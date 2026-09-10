"""原子指標計算器：大類資產層面 Brinson 歸因計算器。

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
SQL_FILE_PATH = Path(__file__).parent / "brinson_asset_class.sql"


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
class BrinsonAssetClassRecord:
    """大類資產 Brinson 歸因數據模型。"""

    fund_id: str
    benchmark_id: str
    start_date: date
    end_date: date
    asset_class: str
    w_p: float
    w_b: float
    r_p: float
    r_b: float
    allocation_effect_pct: Optional[float]
    selection_effect_pct: Optional[float]
    interaction_effect_pct: Optional[float]
    total_excess_pct: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


async def compute_brinson_asset_class(
    fund_id: str,
    benchmark_id: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> List[BrinsonAssetClassRecord]:
    """執行大類資產層面 Brinson 歸因計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param benchmark_id: 基準組合/指數 ID
    :param start_date: 區間起始日 (支持 str 或 date)
    :param end_date: 區間結束日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: List[BrinsonAssetClassRecord]
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
            "benchmark_id": benchmark_id,
            "start_date": parsed_start,
            "end_date": parsed_end,
        },
    )
    rows = result.fetchall()

    if not rows:
        logger.warning(
            "未找到大類資產 Brinson 歸因數據: fund_id=%s, benchmark_id=%s, start_date=%s, end_date=%s",
            fund_id,
            benchmark_id,
            parsed_start,
            parsed_end,
        )
        return []

    def _safe_float(val: Any) -> Optional[float]:
        return float(val) if val is not None else None

    records = []
    for r in rows:
        row_fund_id = str(getattr(r, "fund_id", None) or fund_id)
        row_bm_id = str(getattr(r, "benchmark_id", None) or benchmark_id)
        row_start = getattr(r, "start_date", None)
        row_end = getattr(r, "end_date", None)

        record_start = row_start if isinstance(row_start, date) else parsed_start
        record_end = row_end if isinstance(row_end, date) else parsed_end

        records.append(
            BrinsonAssetClassRecord(
                fund_id=row_fund_id,
                benchmark_id=row_bm_id,
                start_date=record_start,
                end_date=record_end,
                asset_class=str(getattr(r, "asset_class", "")),
                w_p=float(getattr(r, "w_p", 0.0) or 0.0),
                w_b=float(getattr(r, "w_b", 0.0) or 0.0),
                r_p=float(getattr(r, "r_p", 0.0) or 0.0),
                r_b=float(getattr(r, "r_b", 0.0) or 0.0),
                allocation_effect_pct=_safe_float(getattr(r, "allocation_effect_pct", None)),
                selection_effect_pct=_safe_float(getattr(r, "selection_effect_pct", None)),
                interaction_effect_pct=_safe_float(getattr(r, "interaction_effect_pct", None)),
                total_excess_pct=_safe_float(getattr(r, "total_excess_pct", None)),
            )
        )

    return records


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_brinson_asset_class(
    fund_id: str,
    benchmark_id: str,
    start_date: str,
    end_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, List[Dict[str, Any]]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'FOF_01'
    :param benchmark_id: 基準組合/指數 ID，例如 'BM_BALANCED'
    :param start_date: 區間起始日，字串格式如 'YYYY-MM-DD'
    :param end_date: 區間結束日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 List[Dict]；若為 False，返回 Markdown 表格摘要
    :return: 供 Agent 使用的文字描述/表格或結構化數據清單
    """
    try:
        records = await compute_brinson_asset_class(
            fund_id=fund_id,
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not records:
            return (
                f"【查詢結果】未查到基金 [{fund_id}] 對比基準 [{benchmark_id}] "
                f"在區間 {start_date} 至 {end_date} 的大類資產 Brinson 歸因數據。"
            )

        if as_json:
            return [r.to_dict() for r in records]

        # 計算整體合計效應
        tot_alloc = sum(r.allocation_effect_pct or 0.0 for r in records)
        tot_select = sum(r.selection_effect_pct or 0.0 for r in records)
        tot_inter = sum(r.interaction_effect_pct or 0.0 for r in records)
        tot_excess = sum(r.total_excess_pct or 0.0 for r in records)

        def _fmt(val: Optional[float]) -> str:
            return f"{val:+.2f}%" if val is not None else "N/A"

        ref_start = records[0].start_date
        ref_end = records[0].end_date

        lines = [
            f"基金 [{fund_id}] 對比基準 [{benchmark_id}] 在區間 {ref_start} 至 {ref_end} 的大類資產 Brinson 歸因結果：\n",
            "| 大類資產 | 組合權重 (w_p) | 基準權重 (w_b) | 組合收益 (r_p) | 基準收益 (r_b) | 配置效應 (%) | 選擇效應 (%) | 交互效應 (%) | 總超額 (%) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for r in records:
            lines.append(
                f"| {r.asset_class} | {r.w_p:.2f}% | {r.w_b:.2f}% | {r.r_p:.2f}% | {r.r_b:.2f}% | "
                f"{_fmt(r.allocation_effect_pct)} | {_fmt(r.selection_effect_pct)} | "
                f"{_fmt(r.interaction_effect_pct)} | {_fmt(r.total_excess_pct)} |"
            )

        # 增加合計列
        lines.append(
            f"| **合計 (Total)** | **100.00%** | **100.00%** | **-** | **-** | "
            f"**{tot_alloc:+.2f}%** | **{tot_select:+.2f}%** | **{tot_inter:+.2f}%** | **{tot_excess:+.2f}%** |"
        )

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行大類資產 Brinson 歸因計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 對比基準 [{benchmark_id}] 大類資產歸因時發生錯誤: {str(exc)}"