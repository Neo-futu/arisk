"""
openbb_fetcher.py — 生產級 OpenBB 行情抓取器（高可用設計）
=====================================
設計要點：
  1. 多 provider 鏈式 fallback：按憑據自動啟用，按優先級依次嘗試
     · yfinance（免費，無需 key，港股/ETF/美股）
     · fmp（Financial Modeling Prep，付費，覆蓋更廣）
     · polygon（付費，美股/ETF 高質量）
     · tiingo（付費，美股/ETF）
     只裝了憑據的 provider 才會進入鏈；首個成功即返回，剩餘 provider 不再調用
  2. 重試機制：網絡波動自動重試 N 次（指數退避 1s/2s/4s）
  3. 並發抓取：多證券用線程池並發（默認 8 路），降低批量耗時
  4. 健康檢查：fetcher 啟動時探測每個 provider 可用性，記錄到 source_health
  5. 結果標準化：統一輸出 {security_code, alias, provider, rows: [{date,close,volume,turnover}]}
  6. 覆蓋缺口報告：抓取結束返回 succeeded/failed/no_data 三類清單，供上層 EXCEL/PROXY 兜底

依賴：openbb（pip install openbb）；憑據通過環境變量或 obb.user.credentials 配置
    環境變量：FMP_API_KEY / POLYGON_API_KEY / TIINGO_TOKEN（任選，無則跳過該 provider）
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── provider 優先級與憑據映射 ───────────────────────────────
# (openbb_provider_name, env_var_name, credentials_attr_name)
PROVIDER_CHAIN = [
    ("yfinance", None, None),                # 免費 provider，總是可用
    ("fmp", "FMP_API_KEY", "fmp_api_key"),
    ("polygon", "POLYGON_API_KEY", "polygon_api_key"),
    ("tiingo", "TIINGO_TOKEN", "tiingo_token"),
]


@dataclass
class FetchResult:
    """單證券抓取結果。"""
    security_code: str
    alias: str
    provider: str | None = None        # 實際成功的 provider；None=全部失敗
    rows: list[dict] = field(default_factory=list)
    status: str = "no_data"             # ok / no_data / error
    error: str | None = None
    attempts: list[str] = field(default_factory=list)  # 嘗試過的 provider 鏈


def _get_active_providers() -> list[str]:
    """返回當前可用的 provider 鏈（按優先級，僅含已配置憑據的）。"""
    active = []
    try:
        from openbb import obb
        creds = obb.user.credentials
        for name, env_var, attr in PROVIDER_CHAIN:
            if name == "yfinance":
                active.append(name)  # 免費 provider 總是啟用
                continue
            # 優先環境變量，其次 obb 憑據對象
            val = os.getenv(env_var) if env_var else None
            if not val and attr and hasattr(creds, attr):
                val = getattr(creds, attr, None)
            if val:
                active.append(name)
        return active
    except Exception as e:
        logger.warning(f"OpenBB 憑據探測失敗，僅啟用 yfinance: {e}")
        return ["yfinance"]


def _fetch_one_openbb(symbol: str, provider: str, start: date, end: date) -> list[dict]:
    """用指定 provider 抓單個證券，返回標準化行列表。"""
    from openbb import obb
    r = obb.equity.price.historical(
        symbol=symbol, provider=provider,
        start_date=start.isoformat(), end_date=(end + timedelta(days=1)).isoformat(),
    )
    df = r.to_df()
    if df is None or df.empty:
        return []
    rows = []
    for idx, row in df.iterrows():
        qd = idx.date() if hasattr(idx, "date") else idx
        close = row.get("close")
        vol = row.get("volume") or 0
        if close is None:
            continue
        try:
            close_f = float(close)
            vol_f = float(vol) if vol else 0.0
        except (TypeError, ValueError):
            continue
        rows.append({"date": qd, "close": close_f, "volume": vol_f, "turnover": close_f * vol_f})
    return rows


def _with_retry(fn, *, max_retries: int = 3, base_delay: float = 1.0, label: str = ""):
    """指數退避重試包裝。"""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(f"{label} 第{attempt+1}次失敗，{delay}s 後重試: {str(e)[:60]}")
                time.sleep(delay)
    raise last_exc


def fetch_one(security_code: str, alias: str, start: date, end: date,
              providers: list[str] | None = None) -> FetchResult:
    """抓單證券，按 provider 鏈 fallback。"""
    chain = providers or _get_active_providers()
    res = FetchResult(security_code=security_code, alias=alias)
    for p in chain:
        res.attempts.append(p)
        try:
            rows = _with_retry(
                lambda p=p: _fetch_one_openbb(alias, p, start, end),
                label=f"{security_code}@{p}",
            )
            if rows:
                res.provider = p
                res.rows = rows
                res.status = "ok"
                return res
            # 該 provider 無數據，繼續下一個 provider
        except Exception as e:
            res.error = f"{p}: {type(e).__name__} {str(e)[:80]}"
            logger.debug(f"{security_code} provider={p} 失敗: {res.error}")
            continue
    res.status = "no_data" if not res.error else "error"
    return res


def fetch_batch(alias_map: dict[str, str], start: date, end: date,
                max_workers: int = 8, providers: list[str] | None = None) -> list[FetchResult]:
    """並發抓取多證券。alias_map: {security_code: alias}。"""
    chain = providers or _get_active_providers()
    logger.info(f"OpenBB provider 鏈: {chain}（共 {len(alias_map)} 證券，{max_workers} 路並發）")
    results: list[FetchResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fetch_one, sc, al, start, end, chain): sc
            for sc, al in alias_map.items()
        }
        for fut in as_completed(futures):
            sc = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                results.append(FetchResult(security_code=sc, alias=sc,
                                           status="error", error=str(e)[:120]))
    return results


def health_check(providers: list[str] | None = None) -> dict[str, dict]:
    """探測每個 provider 是否可用（用流動性極高的基準證券驗證）。"""
    chain = providers or _get_active_providers()
    # 各 provider 的基準測試證券（流動性極高，便於驗證通道）
    benchmarks = {"yfinance": "0700.HK", "fmp": "AAPL", "polygon": "AAPL", "tiingo": "AAPL"}
    today = date.today()
    start = today - timedelta(days=10)
    health: dict[str, dict] = {}
    for p in chain:
        sym = benchmarks.get(p, "AAPL")
        try:
            rows = _fetch_one_openbb(sym, p, start, today)
            health[p] = {"ok": True, "sample": len(rows), "benchmark": sym}
        except Exception as e:
            health[p] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:60]}",
                         "benchmark": sym}
    return health


def coverage_report(results: list[FetchResult]) -> dict[str, list]:
    """匯總覆蓋情況，供 EXCEL/PROXY 兜底參考。"""
    succeeded = [r for r in results if r.status == "ok"]
    no_data = [r for r in results if r.status == "no_data"]
    errored = [r for r in results if r.status == "error"]
    return {
        "succeeded": [{"code": r.security_code, "alias": r.alias, "provider": r.provider,
                       "rows": len(r.rows)} for r in succeeded],
        "no_data": [{"code": r.security_code, "alias": r.alias, "attempts": r.attempts}
                    for r in no_data],
        "errored": [{"code": r.security_code, "alias": r.alias, "error": r.error}
                    for r in errored],
        "summary": {
            "total": len(results),
            "ok": len(succeeded),
            "no_data": len(no_data),
            "error": len(errored),
        },
    }


if __name__ == "__main__":
    # 自檢：provider 健康狀況 + 抓取示例
    import sys
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
    print("=== OpenBB Provider 健康檢查 ===")
    h = health_check()
    for p, info in h.items():
        print(f"  {p}: {'OK' if info['ok'] else 'FAIL'} {info}")
    print()
    print("=== 抓取測試（0700.HK 近 45 天）===")
    today = date.today()
    r = fetch_one("0700.HK", "0700.HK", today - timedelta(days=45), today)
    print(f"  status={r.status}, provider={r.provider}, rows={len(r.rows)}, attempts={r.attempts}")
    if r.rows:
        print(f"  首日: {r.rows[0]}")
        print(f"  末日: {r.rows[-1]}")
        avg_turnover = sum(x["turnover"] for x in r.rows) / len(r.rows)
        print(f"  ADTV(算術平均日成交額): {avg_turnover:,.0f}")
