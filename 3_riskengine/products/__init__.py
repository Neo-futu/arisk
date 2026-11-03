"""Product layer. Unified Product contract; per-family risk models differ."""

from ..core.contracts import Product, ProductKind, ViewMode
from .assemble import product_from_holding, products_from_snapshot
from .cash import Cash
from .credit import CreditDefaultSwap
from .equity import Equity
from .fixed_income import Bond, CertificateOfDeposit, Deposit, Repo
from .fx import FxForward, FxOption, FxSpot
from .futures import Future
from .money_market.fund import MoneyMarketFund
from .options import EquityOption
from .rates import InterestRateSwap, Swaption
from .structured import StructuredNote

__all__ = [
    "Bond",
    "Cash",
    "CertificateOfDeposit",
    "CreditDefaultSwap",
    "Deposit",
    "Equity",
    "EquityOption",
    "Future",
    "FxForward",
    "FxOption",
    "FxSpot",
    "InterestRateSwap",
    "MoneyMarketFund",
    "Product",
    "ProductKind",
    "Repo",
    "StructuredNote",
    "Swaption",
    "ViewMode",
    "product_from_holding",
    "products_from_snapshot",
]
