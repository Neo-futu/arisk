import ORE as ql

# 1. 設定評估日期
evaluation_date = ql.Date(10, 9, 2026)
ql.Settings.instance().evaluationDate = evaluation_date

# 2. 定義美式外匯期貨期權參數 (以 EUR/USD 期貨期權為例)
future_price = 1.0800      # 標的期貨合約價格
strike_price = 1.0800      # 履約價
risk_free_rate = 0.045     # 折現無風險利率 (4.5%)
volatility = 0.10          # 隱含波動率 (10%)
maturity_date = ql.Date(10, 3, 2027)  # 到期日 (6個月)

# 3. 建立美式行權與 Payoff
payoff = ql.PlainVanillaPayoff(ql.Option.Call, strike_price)
# 美式期權：可在評估日與到期日之間的任意交易日行權
exercise = ql.AmericanExercise(evaluation_date, maturity_date)
american_option = ql.VanillaOption(payoff, exercise)

# 4. 構建 Black-76 過程 (專門用於期貨期權)
day_count = ql.Actual365Fixed()
calendar = ql.NullCalendar()

future_handle = ql.QuoteHandle(ql.SimpleQuote(future_price))
rate_handle = ql.YieldTermStructureHandle(
    ql.FlatForward(evaluation_date, risk_free_rate, day_count)
)
vol_handle = ql.BlackVolTermStructureHandle(
    ql.BlackConstantVol(evaluation_date, calendar, volatility, day_count)
)

# BlackProcess 實現了 Black-76 模型的動力學方程式
bs_process = ql.BlackProcess(future_handle, rate_handle, vol_handle)

# 5. 配置數值定價引擎 (使用 Cox-Ross-Rubinstein 二項式樹，設為 200 步)
time_steps = 200
engine = ql.BinomialVanillaEngine(bs_process, "crr", time_steps)
american_option.setPricingEngine(engine)

# 6. 計算價格與希臘字母
npv = american_option.NPV()
delta = american_option.delta()
gamma = american_option.gamma()

print("===== 美式外匯期貨期權 (Black-76 / Binomial Tree) 驗證 =====")
print(f"評估日期     : {evaluation_date}")
print(f"期貨標的價格 : {future_price:.4f}")
print(f"履約價       : {strike_price:.4f}")
print(f"期權價格 NPV : {npv:.6f}")
print(f"Delta        : {delta:.6f}")
print(f"Gamma        : {gamma:.6f}")

