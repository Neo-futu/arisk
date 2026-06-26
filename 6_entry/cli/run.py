#!/usr/bin/env python
"""Python CLI Runner — 在終端直接觸發風控計算和報告生成。"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, timedelta

import httpx


PROCESSING_API_URL = os.environ.get("PROCESSING_API_URL", "http://localhost:8001")
API_KEY = os.environ.get("PROCESSING_API_KEY", "internal_key_change_me")
HEADERS = {"X-API-Key": API_KEY}


async def cmd_risk(args: argparse.Namespace) -> None:
    """計算並打印風控快照。"""
    as_of = args.date or str(date.today() - timedelta(days=1))
    async with httpx.AsyncClient(base_url=PROCESSING_API_URL, headers=HEADERS) as client:
        resp = await client.get(f"/risk/exposure/{args.fund}", params={"as_of_date": as_of})
        resp.raise_for_status()
        data = resp.json()

    print(f"\n{'='*60}")
    print(f"  風控快照 — {args.fund} · {as_of}")
    print(f"{'='*60}")
    print(f"  總 NAV:        HKD {data['total_nav_hkd']:,.0f}")
    print(f"  WAM:           {data['wam_days']:.1f} 天  (限額: ≤60天)")
    print(f"  WAL:           {data['wal_days']:.1f} 天  (限額: ≤120天)")
    print(f"  每日流動資產:   {data['daily_liquid_pct']:.2f}%  (下限: ≥7.5%)")
    print(f"  每週流動資產:   {data['weekly_liquid_pct']:.2f}%  (下限: ≥15%)")
    print(f"\n  合規狀態:      {'✅ 合規' if data['is_compliant'] else '❌ 違規'}")
    if data.get("breach_flags"):
        print(f"  違規項目:      {', '.join(data['breach_flags'].keys())}")
    print()


async def cmd_positions(args: argparse.Namespace) -> None:
    """打印持倉列表。"""
    as_of = args.date or str(date.today() - timedelta(days=1))
    async with httpx.AsyncClient(base_url=PROCESSING_API_URL, headers=HEADERS) as client:
        resp = await client.get(
            f"/positions/{args.fund}",
            params={"as_of_date": as_of, **({"asset_type": args.type} if args.type else {})},
        )
        resp.raise_for_status()
        data = resp.json()

    print(f"\n持倉列表 — {args.fund} · {as_of}  ({data['count']} 筆)")
    print(f"{'資產ID':<20} {'名稱':<30} {'類型':<12} {'貨幣':<6} {'市值(HKD)':>15} {'佔比':>8}")
    print("-" * 95)
    for p in data["positions"][:args.limit]:
        print(
            f"{p['asset_id']:<20} {(p['asset_name'] or '')[:28]:<30} "
            f"{p['asset_type']:<12} {p['currency']:<6} "
            f"{(p['market_value_hkd'] or 0):>15,.0f} {(p['weight_pct'] or 0):>7.2f}%"
        )
    print()


async def cmd_var(args: argparse.Namespace) -> None:
    """計算 VaR。"""
    as_of = args.date or str(date.today() - timedelta(days=1))
    async with httpx.AsyncClient(base_url=PROCESSING_API_URL, headers=HEADERS) as client:
        resp = await client.get(
            f"/risk/var/{args.fund}",
            params={"as_of_date": as_of, "confidence": args.confidence, "horizon_days": args.horizon},
        )
        resp.raise_for_status()
        data = resp.json()

    print(f"\nVaR — {args.fund} · {as_of}")
    print(f"  方法:      {data['method']}")
    print(f"  置信度:    {data['confidence']*100:.0f}%")
    print(f"  期限:      {data['horizon_days']} 天")
    print(f"  VaR:       HKD {data['var_hkd']:,.0f} ({data['var_pct_nav']:.4f}% NAV)")
    print(f"  CVaR:      HKD {data['cvar_hkd']:,.0f}")
    print(f"  樣本量:    {data['sample_size']} 個交易日\n")


def main():
    parser = argparse.ArgumentParser(description="FSI Risk Platform CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # risk 子命令
    p_risk = sub.add_parser("risk", help="風控快照")
    p_risk.add_argument("fund", help="基金 ID，如 BHMMF")
    p_risk.add_argument("--date", help="日期 YYYY-MM-DD，默認昨日")

    # positions 子命令
    p_pos = sub.add_parser("positions", help="持倉列表")
    p_pos.add_argument("fund", help="基金 ID")
    p_pos.add_argument("--date", help="日期 YYYY-MM-DD")
    p_pos.add_argument("--type", help="資產類型過濾：DEPOSIT/CD/CP/BOND")
    p_pos.add_argument("--limit", type=int, default=50, help="顯示行數")

    # var 子命令
    p_var = sub.add_parser("var", help="VaR 計算")
    p_var.add_argument("fund", help="基金 ID")
    p_var.add_argument("--date", help="日期 YYYY-MM-DD")
    p_var.add_argument("--confidence", type=float, default=0.99)
    p_var.add_argument("--horizon", type=int, default=1, help="持倉期（天）")

    args = parser.parse_args()

    dispatch = {"risk": cmd_risk, "positions": cmd_positions, "var": cmd_var}
    asyncio.run(dispatch[args.command](args))


if __name__ == "__main__":
    main()
