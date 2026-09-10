"""Model families. Identities live in contracts.Model; catalog names the defaults."""

from ..core.contracts import Model
from .catalog import (
    BOND_DISCOUNT,
    CASH_BALANCE,
    CD_DISCOUNT,
    DEPOSIT_ACCRUAL,
    EQUITY_SPOT,
    MMF_LOOK_THROUGH,
    MMF_NAV,
    model_for_ref,
)

__all__ = [
    "BOND_DISCOUNT",
    "CASH_BALANCE",
    "CD_DISCOUNT",
    "DEPOSIT_ACCRUAL",
    "EQUITY_SPOT",
    "MMF_LOOK_THROUGH",
    "MMF_NAV",
    "Model",
    "model_for_ref",
]
