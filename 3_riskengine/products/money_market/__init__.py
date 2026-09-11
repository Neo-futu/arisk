"""Money-market / MMF products. Same Product contract as Equity and Bond."""

from .fund import MoneyMarketFund, is_money_market_book

__all__ = ["MoneyMarketFund", "is_money_market_book"]
