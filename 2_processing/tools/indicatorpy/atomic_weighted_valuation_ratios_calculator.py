"""原子指標計算器：基金組合加權估值指標 (P/E, P/B, P/S) 計算器。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_weighted_valuation_ratios.sql"


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
class AtomicWeightedValuationRatiosRecord:
    """基金組合加權估值指標數據模型。"""

    fund_id: str
    as_of_date: date
    pe_coverage_pct: float
    pb_coverage_pct: float
    ps_coverage_pct: float
    weighted_pe_arithmetic: Optional[float]
    weighted_pe_harmonic: Optional[float]
    weighted_pb_arithmetic: Optional[float]
    weighted_pb_harmonic: Optional[float]
    weighted_ps_arithmetic: Optional[float]
    weighted_ps_harmonic: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["as_of_date"] = self.as_of_date.isoformat()
        return data


async def compute_atomic_weighted_valuation_ratios(
    fund_id: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicWeightedValuationRatiosRecord]:
    """執行基金組合加權市盈率/市淨率/市銷率計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: Optional[AtomicWeightedValuationRatiosRecord]
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
            "未找到加權估值指標數據: fund_id=%s, as_of_date=%s",
            fund_id,
            parsed_date,
        )
        return None

    def _safe_float(val: Any) -> Optional[float]:
        return float(val) if val is not None else None

    row_fund_id = str(getattr(row, "fund_id", None) or fund_id)
    row_date = getattr(row, "as_of_date", None)
    record_date = row_date if isinstance(row_date, date) else parsed_date

    return AtomicWeightedValuationRatiosRecord(
        fund_id=row_fund_id,
        as_of_date=record_date,
        pe_coverage_pct=float(getattr(row, "pe_coverage_pct", 0.0) or 0.0),
        pb_coverage_pct=float(getattr(row, "pb_coverage_pct", 0.0) or 0.0),
        ps_coverage_pct=float(getattr(row, "ps_coverage_pct", 0.0) or 0.0),
        weighted_pe_arithmetic=_safe_float(getattr(row, "weighted_pe_arithmetic", None)),
        weighted_pe_harmonic=_safe_float(getattr(row, "weighted_pe_harmonic", None)),
        weighted_pb_arithmetic=_safe_float(getattr(row, "weighted_pb_arithmetic", None)),
        weighted_pb_harmonic=_safe_float(getattr(row, "weighted_pb_harmonic", None)),
        weighted_ps_arithmetic=_safe_float(getattr(row, "weighted_ps_arithmetic", None)),
        weighted_ps_harmonic=_safe_float(getattr(row, "weighted_ps_harmonic", None)),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_weighted_valuation_ratios(
    fund_id: str,
    as_of_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'EQUITY_FUND_01'
    :param as_of_date: 計算基準日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_weighted_valuation_ratios(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 在 {as_of_date} 的加權估值指標 (P/E, P/B, P/S) 數據。"

        if as_json:
            return record.to_dict()

        # 格式化數值輔助函數
        def _fmt(val: Optional[float]) -> str:
            return f"{val:.2f}x" if val is not None else "N/A"

        # 檢查覆蓋率警示
        min_coverage = min(record.pe_coverage_pct, record.pb_coverage_pct, record.ps_coverage_pct)
        warning_msg = ""
        if min_coverage < 70.0:
            warning_msg = f"\n⚠️ 注意：部分指標覆蓋率較低（最低 {min_coverage:.1f}%），估值結果可能未完全反映整體持倉。"

        lines = [
            f"基金 [{record.fund_id}] 截至 {record.as_of_date} 的加權估值指標計算結果：\n",
            "| 估值指標 | 調和加權 (Weighted Harmonic) | 算術加權 (Arithmetic) | 持倉覆蓋率 (%) |",
            "| :--- | :--- | :--- | :--- |",
            f"| **市盈率 (P/E)** | {_fmt(record.weighted_pe_harmonic)} | {_fmt(record.weighted_pe_arithmetic)} | {record.pe_coverage_pct:.2f}% |",
            f"| **市淨率 (P/B)** | {_fmt(record.weighted_pb_harmonic)} | {_fmt(record.weighted_pb_arithmetic)} | {record.pb_coverage_pct:.2f}% |",
            f"| **市銷率 (P/S)** | {_fmt(record.weighted_ps_harmonic)} | {_fmt(record.weighted_ps_arithmetic)} | {record.ps_coverage_pct:.2f}% |",
            warning_msg,
        ]

        return "\n".join(lines).strip()

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行加權估值指標計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 加權估值指標時發生錯誤: {str(exc)}"