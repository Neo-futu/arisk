初始数据两步已经齐：run_riskengine.py 能分别拉齐 Position 和 MarketData。

步骤	来源	怎么用
1. Position
fixtures
--book mixed|mmf|otc（默认 mixed）
DB 真实组合
--fund-id BHMMF001 --as-of-date 2026-09-01
2. MarketData
DB fsi.mktdata_*
--market-source db（默认）
OpenBB 等第三方
--market-source openbb
可选回退
默认 --no-market-fallback；需要时再 --market-fallback
# 夹具持仓 + 夹具派生行情
python 3_riskengine/scripts/run_riskengine.py --book mixed
# REPO + STRUCTURED（FinancePy / ORE）
python 3_riskengine/scripts/run_riskengine.py --book hybrid
# 独立测试套件
python 3_riskengine/scripts/run_tests.py -q
python 3_riskengine/scripts/run_riskengine.py --check
# DB 持仓 + DB 行情（默认不回退，方便排查）
python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01
# DB 持仓 + OpenBB 行情
python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01 --market-source openbb
输出上：holdings_summary / positions 是持仓；book.market() 是单位行情（非市值），缺口在 missing / [MARKET]。