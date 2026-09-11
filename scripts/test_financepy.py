import sys
import financepy.utils.global_types as gt
import financepy.utils as utils

# 1. 自動解析 FinancePy 列舉型別
def resolve_enum(candidates):
    for name in candidates:
        if hasattr(gt, name):
            return getattr(gt, name)
    for attr in dir(gt):
        if not attr.startswith("_"):
            for name in candidates:
                if name.lower() in attr.lower():
                    return getattr(gt, attr)
    for sub_name in dir(utils):
        sub_mod = getattr(utils, sub_name)
        for name in candidates:
            if hasattr(sub_mod, name):
                return getattr(sub_mod, name)
    available = [x for x in dir(gt) if not x.startswith("_")]
    raise ImportError(f"無法找到列舉 {candidates}。global_types 可用屬性: {available}")

OptionTypes = resolve_enum(["FinOptionTypes", "OptionTypes"])
FrequencyTypes = resolve_enum(["FinFrequencyTypes", "FrequencyTypes", "Frequency"])
DayCountTypes = resolve_enum(["FinDayCountTypes", "DayCountTypes", "DayCount"])

from financepy.utils.date import Date

# 使用最新 FlatDiscountCurve 類別
try:
    from financepy.market.curves.discount_curve_flat import FlatDiscountCurve
except ImportError:
    from financepy.market.curves.discount_curve_flat import DiscountCurveFlat as FlatDiscountCurve

from financepy.products.equity.equity_vanilla_option import EquityVanillaOption
from financepy.products.bonds.bond import Bond
from financepy.models.black_scholes import BlackScholes

def test_financepy_environment():
    print("===== FinancePy 1.1.2 核心模組功能驗證 =====")

    # 1. 驗證 Date 與 FlatDiscountCurve
    valuation_date = Date(10, 9, 2026)
    risk_free_rate = 0.045
    discount_curve = FlatDiscountCurve(valuation_date, risk_free_rate)
    
    target_date = Date(10, 9, 2027)
    df = discount_curve.df(target_date)
    print(f"[1] 市場數據 (Market) : 評估日期 = {valuation_date}, 1年期折現因子 DF = {df:.6f}")

    # 2. 驗證 股票期權定價 (Black-Scholes)
    spot_price = 100.0
    strike_price = 100.0
    dividend_yield = 0.015
    volatility = 0.20

    # 將股利殖利率包裝為 FlatDiscountCurve 物件傳入
    dividend_curve = FlatDiscountCurve(valuation_date, dividend_yield)
    option = EquityVanillaOption(target_date, strike_price, OptionTypes.EUROPEAN_CALL)
    bs_model = BlackScholes(volatility)

    call_price = option.value(valuation_date, spot_price, discount_curve, dividend_curve, bs_model)
    delta = option.delta(valuation_date, spot_price, discount_curve, dividend_curve, bs_model)
    print(f"[2] 權益期權 (Equity) : European Call Price = ${call_price:.4f}, Delta = {delta:.4f}")

    # 3. 驗證 固定利率債券定價
    issue_date = Date(10, 9, 2024)
    maturity_date = Date(10, 9, 2029)
    coupon = 0.05
    freq = FrequencyTypes.SEMI_ANNUAL
    day_count = DayCountTypes.ACT_ACT_ICMA

    bond = Bond(issue_date, maturity_date, coupon, freq, day_count)
    clean_price = bond.clean_price_from_discount_curve(valuation_date, discount_curve)
    dirty_price = bond.dirty_price_from_discount_curve(valuation_date, discount_curve)
    ytm = bond.yield_to_maturity(valuation_date, clean_price)

    print(f"[3] 固收產品 (Bond)   : Clean Price = ${clean_price:.4f}, Dirty Price = ${dirty_price:.4f}, YTM = {ytm:.4%}")

    print("==========================================")
    print("驗證結果: FinancePy 核心模組運作正常。")

if __name__ == "__main__":
    test_financepy_environment()


