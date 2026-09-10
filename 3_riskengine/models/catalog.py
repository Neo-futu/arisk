"""Named models for products. Vendor math stays in adapters."""

from ..core.contracts import Model, ViewMode
from ..core.resolve import EngineRef

EQUITY_SPOT = Model(name="equity_spot", family="equity")
BOND_DISCOUNT = Model(name="bond_discount_curve", family="fixed_income")
DEPOSIT_ACCRUAL = Model(name="deposit_accrual", family="money_market")
CD_DISCOUNT = Model(name="cd_discount", family="money_market")
CASH_BALANCE = Model(name="cash_balance", family="money_market")
MMF_NAV = Model(name="mmf_nav", family="money_market", parameters={"view": ViewMode.PRODUCT.value})
MMF_LOOK_THROUGH = Model(
    name="mmf_look_through",
    family="money_market",
    parameters={"view": ViewMode.LOOK_THROUGH.value},
)
FX_SPOT = Model(name="fx_spot", family="fx")
FX_FORWARD = Model(name="fx_forward", family="fx")
FX_OPTION = Model(name="fx_option", family="fx")
FUTURE = Model(name="future", family="listed")
EQUITY_OPTION = Model(name="equity_option", family="equity")
IRS = Model(name="irs", family="rates")
SWAP = Model(name="swap", family="rates")
SWAPTION = Model(name="swaption", family="rates")
CDS = Model(name="cds", family="credit")

_BY_RESOLVE_MODEL = {
    "equity_spot": EQUITY_SPOT,
    "bond_discount_curve": BOND_DISCOUNT,
    "ibor_deposit": DEPOSIT_ACCRUAL,
    "deposit_accrual": DEPOSIT_ACCRUAL,
    "bond_zero_or_deposit": CD_DISCOUNT,
    "cd_discount": CD_DISCOUNT,
    "cash_balance": CASH_BALANCE,
    "mmf_nav_yield": MMF_NAV,
    "mmf_nav": MMF_NAV,
    "mmf_look_through": MMF_LOOK_THROUGH,
    "fund_nav": MMF_NAV,
    "fx_spot": FX_SPOT,
    "fx_forward": FX_FORWARD,
    "fx_option": FX_OPTION,
    "future": FUTURE,
    "equity_option": EQUITY_OPTION,
    "irs": IRS,
    "swap": SWAP,
    "swaption": SWAPTION,
    "cds": CDS,
    "greeks": IRS,
}


def model_for_ref(ref: EngineRef | None, name: str | None = None) -> Model:
    key = name or (ref.model if ref is not None else "")
    found = _BY_RESOLVE_MODEL.get(key)
    if found is not None:
        return found
    family = ref.adapter if ref is not None else "riskengine"
    return Model(name=key or "unspecified", family=family)


__all__ = [
    "BOND_DISCOUNT",
    "CASH_BALANCE",
    "CDS",
    "CD_DISCOUNT",
    "DEPOSIT_ACCRUAL",
    "EQUITY_OPTION",
    "EQUITY_SPOT",
    "FUTURE",
    "FX_FORWARD",
    "FX_OPTION",
    "FX_SPOT",
    "IRS",
    "MMF_LOOK_THROUGH",
    "MMF_NAV",
    "SWAP",
    "SWAPTION",
    "model_for_ref",
]
