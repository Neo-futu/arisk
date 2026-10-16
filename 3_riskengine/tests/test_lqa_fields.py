from importlib import import_module


def test_enrich_cash_and_bond_from_holdings() -> None:
    fields = import_module("3_riskengine.liquidity.lqa_fields")
    rows = fields.enrich_book(
        [
            {
                "security_code": "CASH1",
                "security_name": "Cash",
                "asset_category": "CASH",
                "market_value": 100.0,
                "remaining_days": 0,
                "is_overnight": True,
            },
            {
                "security_code": "BOND1",
                "security_name": "Corp",
                "asset_category": "BOND_CORP",
                "market_value": 1000.0,
                "duration": 2.0,
                "sector": "Technology",
            },
        ],
        adtv_by_code={"BOND1": {"adtv_30d": 200.0, "sample_days": 30, "adtv_date": "2026-06-25"}},
        bid_ask_bps_by_asset={"CASH": 0.0, "BOND_CORP": 3.0},
        as_of_date="2026-06-25",
    )
    cash, bond = rows
    assert cash["liq_horizon_days"] == 0
    assert cash["hk_sfc_port_lqdty_class"] == "1 day or less"
    assert cash["lqa_source"] == "COMPUTED"
    assert cash["horizon_model"] == "contractual"
    # Bond may still carry ADTV as informational EDV, but horizon is bid-ask based.
    assert bond["expected_daily_volume"] == 200.0
    assert bond["bid_ask_spread"] == 0.0003
    assert bond["liq_horizon_days"] == 1.0  # 3 bps ≤10 → 1 day (方案 A；非 ADTV 参与率)
    assert bond["horizon_model"] == "bid_ask"
    assert bond["liquidity_sector"] == "Technology"
    assert bond["price_volatility"] == 0.02


def test_fi_bid_ask_ladder_scheme_a() -> None:
    fields = import_module("3_riskengine.liquidity.lqa_fields")
    assert fields._fi_horizon_from_bid_ask_bps(10) == 1.0
    assert fields._fi_horizon_from_bid_ask_bps(10.01) == 3.0
    assert fields._fi_horizon_from_bid_ask_bps(50) == 3.0
    assert fields._fi_horizon_from_bid_ask_bps(50.01) == 10.0
    assert fields._fi_horizon_from_bid_ask_bps(150) == 10.0
    assert fields._fi_horizon_from_bid_ask_bps(150.01) == 40.0
    assert fields._fi_horizon_from_bid_ask_bps(None) is None
    # DB 可配置阶梯：收紧上沿后映射变化
    tight = fields.normalize_fi_horizon_ladder([(5.0, 0.5), (None, 20.0)])
    assert fields._fi_horizon_from_bid_ask_bps(3.0, tight) == 0.5
    assert fields._fi_horizon_from_bid_ask_bps(6.0, tight) == 20.0


def test_equity_uses_participation_not_bid_ask_for_horizon() -> None:
    fields = import_module("3_riskengine.liquidity.lqa_fields")
    rows = fields.enrich_book(
        [
            {
                "security_code": "EQ1",
                "security_name": "Stock",
                "asset_category": "EQUITY",
                "market_value": 1000.0,
            },
        ],
        adtv_by_code={"EQ1": {"adtv_30d": 200.0, "sample_days": 30}},
        bid_ask_bps_by_asset={"EQUITY": 50.0},
        as_of_date="2026-06-25",
    )
    eq = rows[0]
    assert eq["horizon_model"] == "participation"
    assert eq["liq_horizon_days"] == 50.0  # 1000 / (200 * 0.1)
