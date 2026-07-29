"""原子指標計算器：固收 Campisi 歸因計算器。

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
SQL_FILE_PATH = Path(__file__).parent / "campisi_fixed_income.sql"


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
class CampisiRecord:
    """固收 Campisi 歸因數據模型。"""

    fund_id: str
    start_date: date
    end_date: date
    security_code: str
    security_name: str
    weight_pct: float
    total_return_pct: float
    coupon_effect_pct: float
    treasury_effect_pct: float
    spread_effect_pct: float
    selection_effect_pct: float
    contrib_coupon_pct: float
    contrib_treasury_pct: float
    contrib_spread_pct: float
    contrib_selection_pct: float
    contrib_total_pct: float

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式，日期自動序列化為 ISO 格式字串。"""
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


async def compute_campisi_attribution(
    fund_id: str,
    start_date: Union[str, date],
    end_date: Union[str, date],
    db: AsyncSession,
) -> List[CampisiRecord]:
    """執行固收 Campisi 歸因計算的核心 DB 查詢函數。

    :param fund_id: 基金/組合 ID
    :param start_date: 區間起始日 (支持 str 或 date)
    :param end_date: 區間結束日 (支持 str 或 date)
    :param db: AsyncSession 資料庫連線
    :return: List[CampisiRecord]
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
            "未找到固收 Campisi 歸因數據: fund_id=%s, start_date=%s, end_date=%s",
            fund_id,
            parsed_start,
            parsed_end,
        )
        return []

    def _safe_float(val: Any) -> float:
        return float(val) if val is not None else 0.0

    records = []
    for r in rows:
        row_fund_id = str(getattr(r, "fund_id", None) or fund_id)
        row_start = getattr(r, "start_date", None)
        row_end = getattr(r, "end_date", None)

        record_start = row_start if isinstance(row_start, date) else parsed_start
        record_end = row_end if isinstance(row_end, date) else parsed_end

        records.append(
            CampisiRecord(
                fund_id=row_fund_id,
                start_date=record_start,
                end_date=record_end,
                security_code=str(getattr(r, "security_code", "")),
                security_name=str(getattr(r, "security_name", "")),
                weight_pct=_safe_float(getattr(r, "weight_pct", 0.0)),
                total_return_pct=_safe_float(getattr(r, "total_return_pct", 0.0)),
                coupon_effect_pct=_safe_float(getattr(r, "coupon_effect_pct", 0.0)),
                treasury_effect_pct=_safe_float(getattr(r, "treasury_effect_pct", 0.0)),
                spread_effect_pct=_safe_float(getattr(r, "spread_effect_pct", 0.0)),
                selection_effect_pct=_safe_float(getattr(r, "selection_effect_pct", 0.0)),
                contrib_coupon_pct=_safe_float(getattr(r, "contrib_coupon_pct", 0.0)),
                contrib_treasury_pct=_safe_float(getattr(r, "contrib_treasury_pct", 0.0)),
                contrib_spread_pct=_safe_float(getattr(r, "contrib_spread_pct", 0.0)),
                contrib_selection_pct=_safe_float(getattr(r, "contrib_selection_pct", 0.0)),
                contrib_total_pct=_safe_float(getattr(r, "contrib_total_pct", 0.0)),
            )
        )

    return records


# ==============================================================================
# Agent 工具 (Tool) 對外標準調用入口
# ==============================================================================

async def calculate_campisi_attribution(
    fund_id: str,
    start_date: str,
    end_date: str,
    db: AsyncSession,
    top_n: int = 5,
    as_json: bool = False,
) -> Union[str, List[Dict[str, Any]]]:
    """供 Agent Skill 調用的標準 Tool 介面。

    :param fund_id: 基金/組合 ID，例如 'BOND_FUND_01'
    :param start_date: 區間起始日，字串格式如 'YYYY-MM-DD'
    :param end_date: 區間結束日，字串格式如 'YYYY-MM-DD'
    :param db: AsyncSession 資料庫連線
    :param top_n: 格式化輸出時，顯示總貢獻前 N 大與後 N 大持倉債券，預設 5
    :param as_json: 若為 True，返回完整 List[Dict]；若為 False，返回 Markdown 表格摘要
    :return: 供 Agent 使用的文字描述/表格或結構化數據清單
    """
    try:
        records = await compute_campisi_attribution(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )

        if not records:
            return (
                f"【查詢結果】未查到基金 [{fund_id}] "
                f"在區間 {start_date} 至 {end_date} 的固收 Campisi 歸因數據。"
            )

        if as_json:
            return [r.to_dict() for r in records]

        # 彙總組合層面總效應貢獻
        total_weight = sum(r.weight_pct for r in records)
        tot_coupon_contrib = sum(r.contrib_coupon_pct for r in records)
        tot_treasury_contrib = sum(r.contrib_treasury_pct for r in records)
        tot_spread_contrib = sum(r.contrib_spread_pct for r in records)
        tot_selection_contrib = sum(r.contrib_selection_pct for r in records)
        tot_return_contrib = sum(r.contrib_total_pct for r in records)

        ref_start = records[0].start_date
        ref_end = records[0].end_date

        # 按持倉總貢獻排序
        sorted_records = sorted(records, key=lambda x: x.contrib_total_pct, reverse=True)

        if len(sorted_records) <= top_n * 2:
            display_records = sorted_records
            subset_msg = f"共包含 {len(sorted_records)} 隻債券"
        else:
            display_records = sorted_records[:top_n] + sorted_records[-top_n:]
            subset_msg = f"共 {len(sorted_records)} 隻債券，已篩選總貢獻前 {top_n} 大與後 {top_n} 大標的"

        def _fmt(val: float) -> str:
            return f"{val:+.2f}%"

        lines = [
            f"基金 [{fund_id}] 在區間 {ref_start} 至 {ref_end} 的固收 Campisi 歸因分析結果：\n",
            "### 1. 組合層面歸因總覽",
            f"- **組合總收益率**: {tot_return_contrib:+.2f}%",
            f"  - **票息收益貢獻 (Coupon Contribution)**: {tot_coupon_contrib:+.2f}%",
            f"  - **國債/基準利率變動貢獻 (Treasury Effect)**: {tot_treasury_contrib:+.2f}%",
            f"  - **信用利差變動貢獻 (Spread Effect)**: {tot_spread_contrib:+.2f}%",
            f"  - **個券選擇/擇時貢獻 (Selection Effect)**: {tot_selection_contrib:+.2f}%\n",
            f"### 2. 明細持倉歸因（{subset_msg}）",
            "| 債券代碼 | 債券名稱 | 權重 | 總收益 | 票息貢獻 | 國債貢獻 | 利差貢獻 | 擇券貢獻 | 總貢獻 |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for r in display_records:
            lines.append(
                f"| {r.security_code} | {r.security_name} | {r.weight_pct:.2f}% | {r.total_return_pct:.2f}% | "
                f"{_fmt(r.contrib_coupon_pct)} | {_fmt(r.contrib_treasury_pct)} | "
                f"{_fmt(r.contrib_spread_pct)} | {_fmt(r.contrib_selection_pct)} | {_fmt(r.contrib_total_pct)} |"
            )

        lines.append(
            f"| **組合合計 (Total)** | **-** | **{total_weight:.2f}%** | **-** | "
            f"**{_fmt(tot_coupon_contrib)}** | **{_fmt(tot_treasury_contrib)}** | "
            f"**{_fmt(tot_spread_contrib)}** | **{_fmt(tot_selection_contrib)}** | **{_fmt(tot_return_contrib)}** |"
        )

        return "\n".join(lines)

    except ValueError as err:
        return f"【參數格式錯誤】{str(err)}"
    except Exception as exc:
        logger.exception("執行固收 Campisi 歸因計算工具失敗: %s", exc)
        return f"【系統異常】計算基金 [{fund_id}] Campisi 歸因時發生錯誤: {str(exc)}"