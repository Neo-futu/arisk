"""Deterministic fixtures for RiskEngine tests. Uses in-memory snapshots only."""
from __future__ import annotations

from datetime import date, timedelta
from importlib import import_module

models = import_module("2_processing.tools.risk_testing.models")
PortfolioSnapshot = models.PortfolioSnapshot
Position = models.Position
RiskFactorType = models.RiskFactorType
Shock = models.Shock
ShockMode = models.ShockMode
SCENARIOS = import_module("2_processing.tools.risk_testing.scenarios").SCENARIOS


def sample_snapshot(as_of: date = date(2026, 9, 1), equity_value: float = 300_000.0):
    returns = []
    for index in range(300):
        value = ((index % 17) - 8) * 0.00035
        if index in {90, 180, 270}:
            value = -0.025
        returns.append((as_of - timedelta(days=299 - index), value))
    snapshot = PortfolioSnapshot(
        fund_id="TEST001",
        as_of_date=as_of,
        reporting_currency="HKD",
        net_asset=1_000_000.0,
        positions=[
            Position(
                security_code="BOND5Y",
                security_name="Five Year Bond",
                asset_class="BOND",
                currency="HKD",
                market_value=600_000.0,
                market_value_base=600_000.0,
                duration=4.5,
                convexity=20.0,
                ytm=0.035,
                coupon_rate=0.03,
                maturity_date=as_of + timedelta(days=365 * 5),
                metadata={"issuer": "HKMA", "rating": "AA"},
            ),
            Position(
                security_code="US_EQ",
                security_name="US Equity",
                asset_class="EQUITY",
                currency="USD",
                market_value=equity_value / 7.8,
                market_value_base=equity_value,
                fx_rate=7.8,
                metadata={"sector": "信息技术", "unrealized_pnl": 12_000.0},
            ),
            Position(
                security_code="CASH",
                security_name="Cash",
                asset_class="CASH",
                currency="HKD",
                market_value=100_000.0,
                market_value_base=100_000.0,
            ),
        ],
        nav_returns=returns,
        data_quality={"position_count": 3, "source": "test"},
    )
    # Synthetic index path so Beta / TE exercise without DB.
    snapshot.benchmark_id = "HSI"
    snapshot.benchmark_returns = [value * 0.85 for _, value in returns]
    snapshot.index_levels = [
        (as_of - timedelta(days=299 - index), 1000.0 * (1.0 + 0.0002 * index))
        for index in range(300)
    ]
    return snapshot


def sample_overview_snapshot(as_of: date = date(2026, 9, 1)):
    """组合概况页夹具：多股多债 + 行业/评级，供 overview 业务模块验证。"""

    base = sample_snapshot(as_of=as_of, equity_value=250_000.0)
    extra = [
        Position(
            security_code="CORP3Y",
            security_name="Corp Bond 3Y",
            asset_class="BOND",
            currency="HKD",
            market_value=100_000.0,
            market_value_base=100_000.0,
            duration=2.8,
            ytm=0.042,
            coupon_rate=0.04,
            maturity_date=as_of + timedelta(days=365 * 3),
            metadata={"issuer": "Bank A", "rating": "A", "sector": "金融"},
        ),
        Position(
            security_code="HK_EQ",
            security_name="HK Bank Equity",
            asset_class="EQUITY",
            currency="HKD",
            market_value=50_000.0,
            market_value_base=50_000.0,
            metadata={"sector": "金融", "unrealized_pnl": -2_000.0},
        ),
        Position(
            security_code="CN_EQ",
            security_name="CN Consumer Equity",
            asset_class="EQUITY",
            currency="HKD",
            market_value=40_000.0,
            market_value_base=40_000.0,
            metadata={"sector": "可选消费", "unrealized_pnl": 5_000.0},
        ),
    ]
    positions = list(base.positions) + extra
    # 原现金 100k + 原债 600k + 股 250k = 950k；再加 190k → 1,140k
    snapshot = PortfolioSnapshot(
        fund_id="OVW001",
        as_of_date=as_of,
        reporting_currency="HKD",
        net_asset=1_140_000.0,
        positions=positions,
        nav_returns=list(base.nav_returns),
        data_quality={"position_count": len(positions), "source": "test", "port_type": "MIXED"},
    )
    snapshot.benchmark_id = "HSI"
    snapshot.benchmark_returns = list(getattr(base, "benchmark_returns", []) or [])
    return snapshot


def sample_mmf_snapshot(as_of: date = date(2026, 9, 1)):
    """Look-through MMF book: bond + CD + deposit + cash."""

    return PortfolioSnapshot(
        fund_id="BHMMF001",
        as_of_date=as_of,
        reporting_currency="HKD",
        net_asset=1_000_000.0,
        positions=[
            Position(
                security_code="TBILL90",
                security_name="T-Bill 90D",
                asset_class="BOND",
                currency="HKD",
                market_value=400_000.0,
                market_value_base=400_000.0,
                duration=0.20,
                ytm=0.04,
                coupon_rate=0.0,
                maturity_date=as_of + timedelta(days=90),
                metadata={"issuer": "HKMA", "rating": "AAA"},
            ),
            Position(
                security_code="CD180",
                security_name="Bank CD 180D",
                asset_class="CD",
                currency="HKD",
                market_value=250_000.0,
                market_value_base=250_000.0,
                duration=0.49,
                ytm=0.035,
                coupon_rate=0.035,
                maturity_date=as_of + timedelta(days=180),
                metadata={"issuer": "Bank A", "rating": "A"},
            ),
            Position(
                security_code="DEP30",
                security_name="Call Deposit",
                asset_class="DEPOSIT",
                currency="HKD",
                market_value=250_000.0,
                market_value_base=250_000.0,
                duration=30 / 365,
                ytm=0.03,
                coupon_rate=0.03,
                maturity_date=as_of + timedelta(days=30),
                metadata={"issuer": "Bank B", "rating": "A"},
            ),
            Position(
                security_code="CASH",
                security_name="Cash",
                asset_class="CASH",
                currency="HKD",
                market_value=100_000.0,
                market_value_base=100_000.0,
            ),
        ],
        nav_returns=[],
        data_quality={
            "position_count": 4,
            "source": "test",
            "port_type": "MMF",
            "mmf_wam_limit_days": 60,
            "mmf_wal_limit_days": 120,
        },
    )


def sample_portfolio_opt_meta(n_days: int = 180) -> dict:
    """组合配置与优化夹具：可复现收益面板（含共同市场因子）。"""

    import hashlib

    import numpy as np
    import pandas as pd

    tickers = ["GOOG", "AAPL", "META", "AMZN", "AMD", "WMT", "BAC", "XOM", "JPM", "PFE"]

    def _seed(text: str) -> int:
        return int.from_bytes(hashlib.md5(text.encode()).digest()[:4], "big")

    market = np.random.default_rng(_seed("__MKT__")).normal(0.0004, 0.01, size=n_days)
    cols: dict[str, list[float]] = {}
    for ticker in tickers:
        rng = np.random.default_rng(_seed(ticker))
        drift = rng.uniform(0.0001, 0.0008)
        vol = rng.uniform(0.008, 0.025)
        beta = rng.uniform(0.4, 1.5)
        idio = rng.normal(0.0, vol, size=n_days)
        cols[ticker] = (drift + beta * market + idio).tolist()
    index = pd.bdate_range(end="2026-11-03", periods=n_days)
    returns = pd.DataFrame(cols, index=index)
    return {
        "returns": returns,
        "return_model": "historical_mean",
        "risk_free_rate": 0.042,
        "weight_bounds": (0.0, 0.35),
        "data_source": "synthetic",
        "start_date": "2025-11-03",
        "end_date": "2026-11-03",
        "custom_weights": {t: 0.1 for t in tickers},
        "governed_method": "hrp",
        "bl_views": {"AAPL": 0.12, "AMD": 0.20},
    }


def sample_factor_behavior_meta(as_of: date = date(2026, 11, 2)) -> dict:
    """基本面因子与行为夹具：单股权重 100% → HHI=10000；对齐页面样例结构。"""

    start = as_of - timedelta(days=180)
    # 区间价格下行 → 负 Momentum；日波动适中 → LowVol≈0.96
    quotes = []
    for index in range(40):
        day = start + timedelta(days=index * 3)
        # 平稳略降：期末/期初 -9.72% 量级
        price = 400.0 * (1.0 - 0.0025 * index)
        quotes.append(
            {
                "security_code": "0700.HK",
                "price_date": day.isoformat(),
                "close_price": price,
                "volume": 80_000_000.0,
            }
        )
    return {
        "fund_id": "BHMMF001",
        "period_start": start.isoformat(),
        "period_end": as_of.isoformat(),
        "holdings": [
            {
                "security_code": "0700.HK",
                "security_name": "騰訊控股",
                "sector": "Information Technology",
                "quantity": 1_000_000.0,
                "market_value": 380_000_000.0,
            }
        ],
        "quotes": quotes,
        "turnover_pct": 0.0,
        "value_weight_pct": 0.0,
        "growth_weight_pct": 100.0,
        "large_weight_pct": 100.0,
        "small_weight_pct": 0.0,
    }


def sample_factor_risk_meta(as_of: date = date(2026, 9, 1)) -> dict:
    """因子风险页夹具：对齐 NAV / 基准收益对，供 Beta·TE 与页面 KPI。"""

    # 构造弱相关主动收益 → Beta 接近 0、TE 显著
    fund: list[float] = []
    bench: list[float] = []
    for index in range(60):
        b = ((index % 11) - 5) * 0.001
        # 货币基金样：接近 0 的平稳收益，对权益基准呈近零 Beta、高 TE
        f = 0.00005 * ((index % 3) - 1)
        fund.append(f)
        bench.append(b)
    return {
        "benchmark_id": "HSI",
        "period_start": (as_of - timedelta(days=180)).isoformat(),
        "period_end": as_of.isoformat(),
        "fund_returns": fund,
        "benchmark_returns": bench,
        "benchmark": {
            "benchmark_id": "HSI",
            "quote_count": len(bench),
            "fund_return_days": len(fund),
            "paired_days": len(fund),
            "index_start": (as_of - timedelta(days=180)).isoformat(),
            "index_end": as_of.isoformat(),
        },
    }


def sample_product_stress_meta(as_of: date = date(2026, 6, 25)) -> dict:
    """产品压力测试夹具：存款 / 信用债 / 逆回购 / 长端存款，对齐 LQAP 画面结构。"""

    holdings = [
        {
            "security_code": "DEP_ON",
            "security_name": "Overnight Deposit",
            "asset_category": "DEPOSIT",
            "market_value": 239_315_000.0,
            "is_overnight": True,
            "remaining_days": 0,
            "duration": 0.0,
            "sector": "Deposit",
        },
        {
            "security_code": "CORP_A",
            "security_name": "IG Corp Note A",
            "asset_category": "BOND_CORP",
            "market_value": 150_000_000.0,
            "duration": 3.2,
            "sector": "Corporate",
        },
        {
            "security_code": "CORP_B",
            "security_name": "IG Corp Note B",
            "asset_category": "BOND_CORP",
            "market_value": 121_000_000.0,
            "duration": 4.1,
            "sector": "Corporate",
        },
        {
            "security_code": "REV_REPO_1",
            "security_name": "Reverse Repo 3D",
            "asset_category": "REV_REPO",
            "market_value": 100_000_000.0,
            # SEVERE day_factor=1.4 → 3.0*1.4=4.2 → 落入 3.1-5 days
            "remaining_days": 3.0,
            "duration": 0.01,
            "sector": "Reverse Repo",
        },
        {
            "security_code": "DEP_TERM",
            "security_name": "Term Deposit 90D",
            "asset_category": "DEPOSIT",
            "market_value": 250_000_000.0,
            "is_overnight": False,
            # SEVERE → 90*1.4=126 → >25 days
            "remaining_days": 90,
            "duration": 0.25,
            "sector": "Deposit",
        },
        {
            "security_code": "TBILL",
            "security_name": "T-Bill",
            "asset_category": "BOND_GOVT",
            "market_value": 570_000.0,
            "duration": 0.2,
            "sector": "Government",
        },
    ]
    # 市值合计 860,885,000（与页面样例一致）
    return {
        "fund_id": "BHMMF001",
        "as_of_date": as_of,
        "data_as_of": as_of.isoformat(),
        "currency": "USD",
        "holdings": holdings,
        "adtv_by_code": {},
        "bid_ask_bps_by_asset": {
            "BOND_CORP": 3.0,
            "BOND_GOVT": 1.0,
            "CD": 2.0,
            "DEPOSIT": 0.0,
            "REV_REPO": 0.0,
        },
        "fi_horizon_ladder": [
            (10.0, 1.0),
            (50.0, 3.0),
            (150.0, 10.0),
            (None, 40.0),
        ],
    }


def sample_rates_credit_meta(as_of: date = date(2026, 9, 1)) -> dict:
    """利率信用 Tab 夹具：对齐 indicators 页面样例 KPI（7 只债 · IG 100%）。

    ΣMV=136_640_000；Σ(MV×D)=246_480_000 → 加权久期≈1.804、DV01=24_648、CS01=19_718.4。
    """

    bonds = [
        {
            "security_code": "3141.HK",
            "security_name": "ABF HK Bond Index ETF",
            "issuer_name": "ABF Hong Kong Bond Index Fund",
            "issuer_rating": "AAA",
            "debt_rating": "AAA",
            "internal_rating": "AAA",
            "rating_agency": "SP",
            "rating": "AAA",
            "maturity_date": (as_of + timedelta(days=900)).isoformat(),
            "duration": 2.10,
            "ytm": 0.032,
            "market_value": 49_980_000.0,
        },
        {
            "security_code": "VCIT.US",
            "security_name": "Vanguard Interm-Term Corp Bond ETF",
            "issuer_name": "Vanguard",
            "issuer_rating": "AA+",
            "debt_rating": "AA+",
            "internal_rating": "AA+",
            "rating_agency": "SP",
            "rating": "AA+",
            "maturity_date": (as_of + timedelta(days=1500)).isoformat(),
            "duration": 2.40,
            "ytm": 0.041,
            "market_value": 28_560_000.0,
        },
        {
            "security_code": "BIL.US",
            "security_name": "iShares 1-3 Month Treasury Bond ETF",
            "issuer_name": "iShares (BlackRock)",
            "issuer_rating": "AAA",
            "debt_rating": "AAA",
            "internal_rating": "AAA",
            "rating_agency": "SP",
            "rating": "AAA",
            "maturity_date": (as_of + timedelta(days=25)).isoformat(),
            "duration": 0.08,
            "ytm": 0.045,
            "market_value": 19_250_000.0,
        },
        {
            "security_code": "LQD.US",
            "security_name": "iShares iBoxx $ Inv Grade Corp Bond ETF",
            "issuer_name": "iShares (BlackRock)",
            "issuer_rating": "AA+",
            "debt_rating": "AA+",
            "internal_rating": "AA+",
            "rating_agency": "SP",
            "rating": "AA+",
            "maturity_date": (as_of + timedelta(days=2000)).isoformat(),
            "duration": 2.80,
            "ytm": 0.043,
            "market_value": 13_850_000.0,
        },
        {
            "security_code": "US912828FT00",
            "security_name": "US Treasury 2Y 2026-06-30",
            "issuer_name": "US Treasury",
            "issuer_rating": "AAA",
            "debt_rating": "AAA",
            "internal_rating": "AAA",
            "rating_agency": "SP",
            "rating": "AAA",
            "maturity_date": date(2026, 6, 30).isoformat(),
            "duration": 1.70,
            "ytm": 0.038,
            "market_value": 10_000_000.0,
        },
        {
            "security_code": "SGOV.US",
            "security_name": "iShares 0-3 Month Treasury Bond ETF",
            "issuer_name": "iShares (BlackRock)",
            "issuer_rating": "AAA",
            "debt_rating": "AAA",
            "internal_rating": "AAA",
            "rating_agency": "SP",
            "rating": "AAA",
            "maturity_date": (as_of + timedelta(days=60)).isoformat(),
            "duration": 0.12,
            "ytm": 0.044,
            "market_value": 10_000_000.0,
        },
        {
            "security_code": "US037833BL17",
            "security_name": "Apple Inc 3.625% 2042-05-10",
            "issuer_name": "Apple Inc",
            "issuer_rating": "AA+",
            "debt_rating": "AA+",
            "internal_rating": "AA+",
            "rating_agency": "SP",
            "rating": "AA+",
            "maturity_date": date(2042, 5, 10).isoformat(),
            "duration": 5.37216,
            "ytm": 0.036,
            "market_value": 5_000_000.0,
        },
    ]
    # 校准 Apple 久期使 Σ(MV×D)=246_480_000 → DV01=24_648
    known = sum(
        b["market_value"] * b["duration"] for b in bonds if b["security_code"] != "US037833BL17"
    )
    bonds[-1]["duration"] = (246_480_000.0 - known) / 5_000_000.0

    agency_rows: list[dict] = []
    multi = {
        "3141.HK": {
            "CSCI": ("AAA", "AAA"),
            "LIANHE": ("AA+", "AA+"),
            "SP": ("AAA", "AAA"),
            "MOODY": ("Aaa", "Aaa"),
            "FITCH": ("AAA", "AAA"),
        },
        "VCIT.US": {
            "CSCI": ("AA+", "AA+"),
            "LIANHE": ("AA", "AA"),
            "SP": ("AA+", "AA+"),
            "MOODY": ("Aa1", "Aa1"),
            "FITCH": ("AA+", "AA+"),
        },
        "BIL.US": {
            "CSCI": ("AAA", "AAA"),
            "LIANHE": ("AA+", "AA+"),
            "SP": ("AAA", "AAA"),
            "MOODY": ("Aaa", "Aaa"),
            "FITCH": ("AAA", "AAA"),
        },
        "LQD.US": {
            "CSCI": ("AA+", "AA+"),
            "LIANHE": ("AA", "AA"),
            "SP": ("AA+", "AA+"),
            "MOODY": ("Aa1", "Aa1"),
            "FITCH": ("AA+", "AA+"),
        },
        "US912828FT00": {
            "CSCI": ("AAA", "AAA"),
            "LIANHE": ("AA+", "AA+"),
            "SP": ("AAA", "AAA"),
            "MOODY": ("Aaa", "Aaa"),
            "FITCH": ("AAA", "AAA"),
        },
        "SGOV.US": {
            "CSCI": ("AAA", "AAA"),
            "LIANHE": ("AA+", "AA+"),
            "SP": ("AAA", "AAA"),
            "MOODY": ("Aaa", "Aaa"),
            "FITCH": ("AAA", "AAA"),
        },
        "US037833BL17": {
            "CSCI": ("AA+", "AA+"),
            "LIANHE": ("AA", "AA"),
            "SP": ("AA+", "AA+"),
            "MOODY": ("Aa1", "Aa1"),
            "FITCH": ("AA+", "AA+"),
        },
    }
    for code, agencies in multi.items():
        for agency, (issuer, debt) in agencies.items():
            agency_rows.append(
                {
                    "security_code": code,
                    "rating_agency": agency,
                    "issuer_rating": issuer,
                    "debt_rating": debt,
                }
            )

    return {
        "net_asset": 2_744_176_706.83,  # 136_640_000 / 0.0498
        "bonds": bonds,
        "agency_rows": agency_rows,
    }


def sample_basic_info_meta() -> dict:
    """整体风险敞口 · 基本信息页 meta（para_portfolio + 投管人员）。"""

    return {
        "port_name": "博晖港币货币基金",
        "port_name_en": "Bohui HKD MMF",
        "port_type": "MMF",
        "is_mmf": True,
        "base_currency": "HKD",
        "inception_date": "2020-03-15",
        "is_active": True,
        "mmf_wam_limit_days": 60,
        "mmf_wal_limit_days": 120,
        "asset_mgr_id": "AM_BOHUI",
        "trustee_id": "TRUSTEE_01",
        "custodian_id": "CUST_01",
        "managers": [
            {
                "person_id": "P001",
                "person_name": "张经理",
                "person_name_en": "Zhang",
                "role": "FUND_MANAGER",
                "is_lead": True,
                "begin_date": "2020-03-15",
                "end_date": None,
                "email": "zhang@example.com",
                "sfc_licence_no": "SFC-001",
                "is_current": True,
            },
            {
                "person_id": "P002",
                "person_name": "李风控",
                "person_name_en": "Li",
                "role": "RISK_OFFICER",
                "is_lead": False,
                "begin_date": "2021-01-01",
                "end_date": None,
                "email": "li@example.com",
                "sfc_licence_no": "SFC-002",
                "is_current": True,
            },
            {
                "person_id": "P003",
                "person_name": "王前经理",
                "role": "FUND_MANAGER",
                "is_lead": False,
                "begin_date": "2018-01-01",
                "end_date": "2020-03-14",
                "is_current": False,
            },
        ],
    }


def sample_otc_snapshot(as_of: date = date(2026, 9, 1)):
    """FX / listed / rates / credit book for ORE product tests."""

    maturity_1y = as_of + timedelta(days=365)
    maturity_5y = as_of + timedelta(days=365 * 5)
    return PortfolioSnapshot(
        fund_id="OTC001",
        as_of_date=as_of,
        reporting_currency="HKD",
        net_asset=300_000.0,
        positions=[
            Position(
                security_code="FXSPOT",
                security_name="USD Spot",
                asset_class="FX",
                currency="USD",
                market_value=12_820.51,
                market_value_base=100_000.0,
                fx_rate=7.8,
                metadata={"pair": "USDHKD", "spot": 7.8, "counterparty": "BANKFX"},
            ),
            Position(
                security_code="FXFWD",
                security_name="EURUSD Forward 1Y",
                asset_class="FX_FORWARD",
                currency="USD",
                market_value=100_000.0,
                market_value_base=100_000.0,
                fx_rate=7.8,
                duration=1.0,
                maturity_date=maturity_1y,
                metadata={
                    "pair": "EURUSD",
                    "spot": 1.08,
                    "strike": 1.08,
                    "notional": 100_000.0,
                    "counterparty": "BANKFX",
                },
            ),
            Position(
                security_code="FXOPT",
                security_name="EURUSD Call 6M",
                asset_class="FX_OPTION",
                currency="USD",
                market_value=5_000.0,
                market_value_base=5_000.0,
                duration=0.5,
                maturity_date=as_of + timedelta(days=182),
                metadata={
                    "pair": "EURUSD",
                    "spot": 1.08,
                    "strike": 1.08,
                    "volatility": 0.10,
                    "option_type": "Call",
                    "exercise": "European",
                    "notional": 100_000.0,
                    "domestic_rate": 0.045,
                    "foreign_rate": 0.03,
                    "counterparty": "BANKFX",
                },
            ),
            Position(
                security_code="EQFUT",
                security_name="Equity Future",
                asset_class="FUTURE",
                currency="USD",
                market_value=50_000.0,
                market_value_base=50_000.0,
                duration=0.25,
                maturity_date=as_of + timedelta(days=90),
                metadata={"spot": 100.0, "underlying": "EQUITY", "notional": 50_000.0},
            ),
            Position(
                security_code="EQOPT",
                security_name="Equity Call",
                asset_class="OPTION",
                currency="USD",
                market_value=8_000.0,
                market_value_base=8_000.0,
                duration=0.5,
                maturity_date=as_of + timedelta(days=182),
                metadata={
                    "spot": 100.0,
                    "strike": 100.0,
                    "volatility": 0.20,
                    "option_type": "Call",
                    "exercise": "European",
                    "notional": 100.0,
                },
            ),
            Position(
                security_code="IRS5Y",
                security_name="USD IRS 5Y",
                asset_class="IRS",
                currency="USD",
                market_value=2_000.0,
                market_value_base=2_000.0,
                duration=4.5,
                ytm=0.03,
                maturity_date=maturity_5y,
                metadata={"notional": 1_000_000.0, "strike": 0.03, "pay_fixed": True, "tenor_years": 5.0, "counterparty": "BANKIR"},
            ),
            Position(
                security_code="SWPT",
                security_name="1y5y Payer Swaption",
                asset_class="SWAPTION",
                currency="USD",
                market_value=15_000.0,
                market_value_base=15_000.0,
                duration=5.0,
                maturity_date=maturity_5y,
                metadata={
                    "notional": 1_000_000.0,
                    "strike": 0.03,
                    "volatility": 0.20,
                    "pay_fixed": True,
                    "tenor_years": 5.0,
                    "option_tenor_years": 1.0,
                    "counterparty": "BANKIR",
                },
            ),
            Position(
                security_code="CDS5Y",
                security_name="5Y CDS",
                asset_class="CDS",
                currency="USD",
                market_value=20_000.0,
                market_value_base=20_000.0,
                duration=5.0,
                maturity_date=maturity_5y,
                metadata={
                    "notional": 1_000_000.0,
                    "strike": 0.01,
                    "hazard_rate": 0.01,
                    "recovery_rate": 0.40,
                    "protection_seller": False,
                    "tenor_years": 5.0,
                    "counterparty": "BANKCD",
                },
            ),
        ],
        nav_returns=[],
        data_quality={"position_count": 8, "source": "test", "port_type": "OTC"},
    )


def sample_repo_structured_snapshot(as_of: date = date(2026, 9, 1)):
    """REPO (FinancePy) + STRUCTURED (ORE) book for adapter coverage tests."""

    return PortfolioSnapshot(
        fund_id="HYBRID001",
        as_of_date=as_of,
        reporting_currency="HKD",
        net_asset=250_000.0,
        positions=[
            Position(
                security_code="REPO7D",
                security_name="7D Repo",
                asset_class="REPO",
                currency="HKD",
                market_value=150_000.0,
                market_value_base=150_000.0,
                duration=7 / 365,
                ytm=0.028,
                coupon_rate=0.028,
                maturity_date=as_of + timedelta(days=7),
                metadata={"repo_rate": 0.028, "haircut": 0.02, "issuer": "BankRepo"},
            ),
            Position(
                security_code="STRUCT1",
                security_name="Equity-Linked Note",
                asset_class="STRUCTURED",
                currency="HKD",
                market_value=100_000.0,
                market_value_base=100_000.0,
                duration=2.0,
                maturity_date=as_of + timedelta(days=365 * 2),
                metadata={
                    "notional": 100_000.0,
                    "script_id": "ELN_AUTOCALL_V1",
                    "equity_beta": 0.8,
                    "rate_duration": 1.5,
                    "vol_vega": 0.3,
                    "spread_cs01": 0.4,
                    "volatility": 0.22,
                    "counterparty": "BANKST",
                },
            ),
        ],
        nav_returns=[],
        data_quality={"position_count": 2, "source": "test", "port_type": "HYBRID"},
    )
