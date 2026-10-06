这个页面，功能过一遍，审阅。

20260929
http://localhost:5173/investment-risk/overview 点击菜单进入该页面 怎么刷新按钮会动，刷新完成后布局又上调，刷新的时候的 载入中请放到刷新按钮右边或者其他位置，这样载入数据时，不影响页面布局

http://localhost:5173/investment-risk/indicators#risk-exposure 基本信息后面请加个 持仓明细，添加完整所有持仓表格和分类别资产的持仓明细
是细化到个券层面的，整体持仓和分类别资产的持仓明细。
分类别资产的持仓明细，的各个类别请固定下来，债券，。。。。，，，等，最后是衍生品及其他。没有相应类别的持仓显示0就可以。
分类别个券持仓明细
债券共 5 笔 · 42.774%
债券子类别汇总 的 债券子类别汇总请去掉。CN0002001234	26國債01 这个子类别应该是国债啊，债券类别和子类别是通过哪个数据字典，哪个数据表从db中获取确定的。DBANFN25034.CMU 这个看着原来也是信用债吧。

answer:函数不在单独文件名里叫 compute_risk_indicator_timeseries.py，而是定义在：

arisk/2_processing/tools/performance/investment_analysis_timeseries.py
里的函数 compute_risk_indicator_timeseries（大约第 65 行）。

调用链（从前端到计算）
前端
  fsiApi.getRiskIndicatorTimeseries(fundId, start, end)
  → GET /api/v1/fsi/investment/risk-indicators-timeseries/{fund_id}
        │
        ▼
① backend（只做代理，不算数）
  arisk/backend/app/api/routes/fsi/investment.py
  → ProcessingClient GET /investment/risk-indicators-timeseries/{fund_id}
        │
        ▼
② processing API 路由
  arisk/2_processing/api/routers/investment.py
  → _ir.compute_risk_indicator_timeseries(...)
        │
        │  _ir = import_module("4_business.investment_risk.service")
        ▼
③ 业务层门面（转发别名）
  arisk/4_business/investment_risk/service.py
  → compute_risk_indicator_timeseries = _analysis.compute_risk_indicator_timeseries
        │
        │  _analysis = import_module("2_processing.tools.performance.investment_analysis")
        ▼
④ 兼容入口（再导出）
  arisk/2_processing/tools/performance/investment_analysis.py
  → from .investanalsis import compute_risk_indicator_timeseries
        │
        ▼
⑤ 聚合 facade
  arisk/2_processing/tools/performance/investanalsis.py
  → from .investment_analysis_timeseries import compute_risk_indicator_timeseries
        │
        ▼
⑥ 真正计算（这里）
  arisk/2_processing/tools/performance/investment_analysis_timeseries.py
  → async def compute_risk_indicator_timeseries(...)
       · 读 NAV：_nav_history / _resolve_nav_period（common）
       · 日收益：_nav_daily_returns（优先 day_return）
       · 算滚动波动、回撤、滚动 VaR
       · 返回 points[]
各文件角色
文件	作用
backend/.../investment.py
BFF 鉴权 + 转发到 Processing
2_processing/api/routers/investment.py
HTTP 入口，校验日期，调业务层
4_business/.../service.py
用例门面；页面契约函数多是 _analysis.xxx 别名
investment_analysis.py / investanalsis.py
再导出，避免到处改 import
investment_analysis_timeseries.py
滚动波动率时序真正实现
investment_analysis_common.py
_nav_history、_nav_daily_returns 等共享工具
所以：service.py / investment.py 都不写算法，只做路由和转发；算法在 investment_analysis_timeseries.py。在 Cursor 里用全局搜索 def compute_risk_indicator_timeseries 就能直接跳到该函数。





