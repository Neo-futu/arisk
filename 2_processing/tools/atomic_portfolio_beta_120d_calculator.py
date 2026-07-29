"""原子指標計算器：基金組合 Beta (近 120 個交易日) (Atomic Portfolio Beta 120d Calculator)。

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
SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_beta_120d.sql"


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
class AtomicPortfolioBeta120dRecord:
    """近 120 個交易日基金組合 Beta 數據模型。"""

    fund_id: str
    benchmark_code: str
    window_start_date: date
    window_end_date: date
    trading_days_count: int
    avg_portfolio_return_pct: float
    avg_benchmark_return_pct: float
    var_benchmark: float
    cov_portfolio_benchmark: float
    beta_120d: float
    beta_regr_slope_120d: float
    r_squared_120d: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期欄位自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["window_start_date"] = self.window_start_date.isoformat()
        data["window_end_date"] = self.window_end_date.isoformat()
        return data


async def compute_atomic_portfolio_beta_120d(
    fund_id: str,
    benchmark_code: str,
    as_of_date: Union[str, date],
    db: AsyncSession,
) -> Optional[AtomicPortfolioBeta120dRecord]:
    """執行近 120 個交易日基金組合 Beta 計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param benchmark_code: 基準代碼
    :param as_of_date: 計算基準日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: Optional[AtomicPortfolioBeta120dRecord]
    """
    parsed_date = _parse_date(as_of_date)
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "bm_code": benchmark_code,
            "as_of_date": parsed_date,
        },
    )
    row = result.fetchone()

    if not row or row.fund_id is None or int(row.trading_days_count or 0) == 0:
        logger.warning(
            "未找到足夠的 120d Beta 計算數據: fund_id=%s, benchmark_code=%s, as_of_date=%s",
            fund_id,
            benchmark_code,
            parsed_date,
        )
        return None

    return AtomicPortfolioBeta120dRecord(
        fund_id=str(row.fund_id),
        benchmark_code=str(row.benchmark_code or benchmark_code),
        window_start_date=row.window_start_date
        if isinstance(row.window_start_date, date)
        else _parse_date(str(row.window_start_date)),
        window_end_date=row.window_end_date
        if isinstance(row.window_end_date, date)
        else parsed_date,
        trading_days_count=int(row.trading_days_count or 0),
        avg_portfolio_return_pct=float(row.avg_portfolio_return_pct or 0.0),
        avg_benchmark_return_pct=float(row.avg_benchmark_return_pct or 0.0),
        var_benchmark=float(row.var_benchmark or 0.0),
        cov_portfolio_benchmark=float(row.cov_portfolio_benchmark or 0.0),
        beta_120d=float(row.beta_120d or 0.0),
        beta_regr_slope_120d=float(row.beta_regr_slope_120d or 0.0),
        r_squared_120d=float(row.r_squared_120d or 0.0),
    )


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_atomic_portfolio_beta_120d(
    fund_id: str,
    benchmark_code: str,
    as_of_date: str,
    db: AsyncSession,
    as_json: bool = False,
) -> Union[str, Dict[str, Any]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'PORT_01'
    :param benchmark_code: 基準代碼，例如 'MSCI_WORLD'
    :param as_of_date: 計算基準日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param as_json: 若為 True，返回 Dict；若為 False，返回格式化文字摘要
    :return: 供 Agent 使用的文字描述或結構化數據
    """
    try:
        record = await compute_atomic_portfolio_beta_120d(
            fund_id=fund_id,
            benchmark_code=benchmark_code,
            as_of_date=as_of_date,
            db=db,
        )

        if not record:
            return f"【查詢結果】未查到基金 [{fund_id}] 對比基準 [{benchmark_code}] 在 {as_of_date} 的近 120 個交易日 Beta 數據（可能交易日數量不足）。"

        if as_json:
            return record.to_dict()

        # 格式化輸出文字摘要
        lines = [
            f"基金 [{record.fund_id}] 對比基準 [{record.benchmark_code}] 截至 {record.window_end_date} 的近 120 日 Beta 計算結果：",
            f"- 計算區間：{record.window_start_date} 至 {record.window_end_date} (共 {record.trading_days_count} 個有效交易日)",
            f"- 120日 Beta 值：{record.beta_120d:.4f}",
            f"- 迴歸斜率 Beta (Slope)：{record.beta_regr_slope_120d:.4f}",
            f"- 決定係數 ($R^2$)：{record.r_squared_120d:.4f}",
            f"- 組合平均日收益率：{record.avg_portfolio_return_pct:.4f}%",
            f"- 基準平均日收益率：{record.avg_benchmark_return_pct:.4f}%",
        ]

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行 120 日 Portfolio Beta 計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] 近 120 日 Beta 時發生錯誤: {str(exc)}"