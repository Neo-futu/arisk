"""Unit tests for SQL asset header parsing / categorization (no DB)."""
from importlib import import_module

sql_assets = import_module("2_processing.api.routers.sql_assets")


def test_parse_header_title_and_description() -> None:
    text = (
        "-- atomic_portfolio_wam.sql\n"
        "-- 貨幣基金組合加權平均剩餘期限 (WAM)\n"
        "-- 說明：\n"
        "-- 1. 優先讀取官方聚合指標\n"
        "\n"
        "SELECT 1;\n"
    )
    title, description = sql_assets._parse_header(text)
    assert title == "貨幣基金組合加權平均剩餘期限 (WAM)"
    assert "說明" in description and "官方聚合指標" in description


def test_parse_header_single_comment_falls_back_to_it() -> None:
    title, description = sql_assets._parse_header("-- only_one.sql\nSELECT 1;\n")
    assert title == "only_one.sql"
    assert description == ""


def test_parse_header_no_comments() -> None:
    title, description = sql_assets._parse_header("SELECT 1;\n")
    assert title is None
    assert description == ""


def test_parse_header_stops_at_blank_after_comments() -> None:
    text = "-- file.sql\n-- Title\n-- desc line\n\n-- not part of header\nSELECT 1;"
    title, description = sql_assets._parse_header(text)
    assert title == "Title"
    assert description == "desc line"


def test_category_indicators_by_prefix() -> None:
    assert sql_assets._category("indicators", "atomic_portfolio_wam.sql") == "原子指標"
    assert sql_assets._category("indicators", "brinson_asset_class.sql") == "業績歸因"
    assert sql_assets._category("indicators", "campisi_fixed_income.sql") == "業績歸因"
    assert sql_assets._category("indicators", "position_exposure.sql") == "暴露分析"
    assert sql_assets._category("indicators", "absolute_return.sql") == "收益計算"


def test_category_mmf_group() -> None:
    assert sql_assets._category("mmf", "01_nav_deviation.sql") == "貨幣基金報表"


def test_category_other_fallback() -> None:
    assert sql_assets._category("indicators", "misc_query.sql") == "其他"
