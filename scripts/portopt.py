import sys
import os
import subprocess

# ==========================================
# 1. 环境防护：自动检测并进入 openbb-env
# ==========================================
def ensure_openbb_env():
    try:
        from openbb import obb
        import matplotlib
        import pypfopt
        return
    except ImportError:
        pass

    current_dir = os.path.dirname(os.path.abspath(__file__))
    if sys.platform == "win32":
        venv_python = os.path.join(current_dir, "openbb-env", "Scripts", "python.exe")
    else:
        venv_python = os.path.join(current_dir, "openbb-env", "bin", "python")

    if not os.path.exists(venv_python):
        print(f"[ARisk 错误] 未找到虚拟环境解释器: {venv_python}")
        sys.exit(1)

    if os.environ.get("ARISK_ENV_RESTARTED") == "1":
        print("[ARisk 错误] 切换环境后仍缺少依赖，请执行: pip install openbb PyPortfolioOpt matplotlib numpy pandas")
        sys.exit(1)

    print(f"[ARisk 环境] 自动切换至 openbb-env: {venv_python}")
    new_env = os.environ.copy()
    new_env["ARISK_ENV_RESTARTED"] = "1"
    
    result = subprocess.run([venv_python] + sys.argv, env=new_env)
    sys.exit(result.returncode)

ensure_openbb_env()

# ==========================================
# 2. 核心业务逻辑：参数设置、优化引擎与风控度量
# ==========================================
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from openbb import obb
from pypfopt import EfficientFrontier, risk_models, expected_returns, black_litterman, BlackLittermanModel, plotting

class PortfolioManager:
    """ARisk 组合管理与风控计算引擎"""
    def __init__(self, tickers: list, risk_free_rate: float = 0.04, weight_bounds: tuple = (0.0, 1.0)):
        self.tickers = tickers
        self.risk_free_rate = risk_free_rate
        self.weight_bounds = weight_bounds
        self.prices_df = None
        self.returns_df = None
        self.mu = None
        self.S = None

    def fetch_data(self, provider: str = "yfinance") -> pd.DataFrame:
        """从 OpenBB 获取多资产日频历史行情"""
        print(f"[ARisk Data] 正在获取 {len(self.tickers)} 只标的行情数据...")
        series_list = []
        for symbol in self.tickers:
            try:
                res = obb.equity.price.historical(symbol=symbol, provider=provider)
                df = res.to_df()
                series = df['close'].rename(symbol)
                series_list.append(series)
            except Exception as e:
                print(f"[Warning] 获取 {symbol} 数据失败: {e}")

        if not series_list:
            raise ValueError("未能获取任何资产行情数据！")

        self.prices_df = pd.concat(series_list, axis=1).dropna()
        self.returns_df = self.prices_df.pct_change().dropna()
        
        # 默认使用历史算术平均收益率与样本协方差矩阵
        self.mu = expected_returns.mean_historical_return(self.prices_df, compounding=False)
        self.S = risk_models.sample_cov(self.prices_df)
        return self.prices_df

    def compute_all_return_models(self, market_caps: dict = None, views: dict = None) -> pd.DataFrame:
        """
        计算并对比 4 种特定的个股预期收益率模型：
        1. Historical Mean (历史年化算术平均收益率)
        2. Real Historical CAGR (真实历史行情实际复合年化收益率)
        3. CAPM Beta Model (CAPM 因子模型 Beta 期望收益率)
        4. Black-Litterman (Black-Litterman 贝叶斯均衡预期收益率)
        """
        # 1. 历史年化算术平均收益率
        hist_mean = expected_returns.mean_historical_return(self.prices_df, compounding=False)

        # 2. 真实历史行情复合年化收益率 (CAGR)
        real_cagr = expected_returns.mean_historical_return(self.prices_df, compounding=True)

        # 3. CAPM 因子模型 Beta 期望收益率
        try:
            capm_ret = expected_returns.capm_return(self.prices_df, risk_free_rate=self.risk_free_rate)
        except Exception:
            market_proxy = self.prices_df.mean(axis=1)
            capm_ret = expected_returns.capm_return(
                self.prices_df, 
                market_prices=market_proxy, 
                risk_free_rate=self.risk_free_rate
            )

        # 4. Black-Litterman 模型预期收益率
        market_prices = self.prices_df.mean(axis=1)
        delta = black_litterman.market_implied_risk_aversion(market_prices, risk_free_rate=self.risk_free_rate)
        
        if market_caps is None:
            # 若未提供市值，默认设定等权重市值代理
            mcap_series = pd.Series(1.0 / len(self.tickers), index=self.tickers)
        else:
            mcap_series = pd.Series(market_caps)

        prior_returns = black_litterman.market_implied_prior_returns(mcap_series, delta, self.S)

        if views:
            bl = BlackLittermanModel(self.S, pi=prior_returns, absolute_views=views)
            bl_ret = bl.bl_returns()
        else:
            bl_ret = prior_returns

        returns_comparison_df = pd.DataFrame({
            "Historical Mean (Arithmetic)": hist_mean,
            "Real Historical CAGR (Compound)": real_cagr,
            "CAPM Beta Model": capm_ret,
            "Black-Litterman Model": bl_ret
        })
        return returns_comparison_df

    def set_return_model(self, method: str = "historical_mean", market_caps: dict = None, views: dict = None):
        """
        切换组合优化时使用的预期收益率模型
        可选方法: 'historical_mean', 'real_cagr', 'capm', 'black_litterman'
        """
        all_models = self.compute_all_return_models(market_caps=market_caps, views=views)
        
        if method == "historical_mean":
            self.mu = all_models["Historical Mean (Arithmetic)"]
        elif method == "real_cagr":
            self.mu = all_models["Real Historical CAGR (Compound)"]
        elif method == "capm":
            self.mu = all_models["CAPM Beta Model"]
        elif method == "black_litterman":
            self.mu = all_models["Black-Litterman Model"]
        else:
            raise ValueError(f"未知的收益率模型方法: {method}")

    def calculate_individual_asset_metrics(self) -> pd.DataFrame:
        """计算个股层面的 4 项核心风控与绩效指标"""
        metrics_list = []
        trading_days = 252

        for col in self.prices_df.columns:
            daily_ret = self.returns_df[col]

            ann_ret = daily_ret.mean() * trading_days
            ann_vol = daily_ret.std() * np.sqrt(trading_days)
            sharpe = (ann_ret - self.risk_free_rate) / ann_vol if ann_vol > 0 else 0.0

            cum_ret = (1 + daily_ret).cumprod()
            peak = cum_ret.cummax()
            drawdown = (cum_ret - peak) / peak
            max_dd = drawdown.min()

            metrics_list.append({
                "Asset": col,
                "Expected Return": ann_ret,
                "Volatility": ann_vol,
                "Sharpe Ratio": sharpe,
                "Max Drawdown": max_dd
            })

        df_metrics = pd.DataFrame(metrics_list).set_index("Asset")
        return df_metrics

    def calculate_risk_metrics(self, weights: dict) -> dict:
        """计算组合的年化收益率、波动率、夏普比率、最大回撤、VaR 与 CVaR"""
        w = np.array([weights.get(col, 0.0) for col in self.prices_df.columns])
        portfolio_daily_returns = (self.returns_df * w).sum(axis=1)

        exp_ret = np.sum(self.mu * w)
        vol = np.sqrt(np.dot(w.T, np.dot(self.S, w)))
        sharpe = (exp_ret - self.risk_free_rate) / vol if vol > 0 else 0

        cum_returns = (1 + portfolio_daily_returns).cumprod()
        peak = cum_returns.cummax()
        drawdown = (cum_returns - peak) / peak
        max_drawdown = drawdown.min()

        var_95 = np.percentile(portfolio_daily_returns, 5)
        cvar_95 = portfolio_daily_returns[portfolio_daily_returns <= var_95].mean()

        return {
            "Expected Return": exp_ret,
            "Volatility": vol,
            "Sharpe Ratio": sharpe,
            "Max Drawdown": max_drawdown,
            "Historical VaR (95%)": var_95,
            "Historical CVaR (95%)": cvar_95
        }

    def evaluate_custom_weights(self, weights_dict: dict) -> tuple:
        full_weights = {col: weights_dict.get(col, 0.0) for col in self.prices_df.columns}
        total_w = sum(full_weights.values())
        if total_w > 0:
            normalized_weights = {k: v / total_w for k, v in full_weights.items()}
        else:
            normalized_weights = full_weights

        metrics = self.calculate_risk_metrics(normalized_weights)
        return normalized_weights, metrics

    def check_if_efficient(self, weights_dict: dict) -> dict:
        norm_weights, current_metrics = self.evaluate_custom_weights(weights_dict)
        cur_ret = current_metrics["Expected Return"]
        cur_vol = current_metrics["Volatility"]

        comparison = {
            "Current Portfolio": current_metrics,
            "Efficient Counterparts": {},
            "Optimization Space": {}
        }

        try:
            ef_ret = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)
            ef_ret.efficient_return(target_return=cur_ret)
            opt_w_vol = ef_ret.clean_weights()
            metrics_opt_vol = self.calculate_risk_metrics(opt_w_vol)
            
            comparison["Efficient Counterparts"]["Same Return (Min Vol)"] = metrics_opt_vol
            comparison["Optimization Space"]["Extra Risk (Excess Vol)"] = cur_vol - metrics_opt_vol["Volatility"]
        except Exception:
            comparison["Optimization Space"]["Extra Risk (Excess Vol)"] = None

        try:
            ef_risk = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)
            ef_risk.efficient_risk(target_volatility=cur_vol)
            opt_w_ret = ef_risk.clean_weights()
            metrics_opt_ret = self.calculate_risk_metrics(opt_w_ret)
            
            comparison["Efficient Counterparts"]["Same Vol (Max Return)"] = metrics_opt_ret
            comparison["Optimization Space"]["Alpha Loss (Shortfall Return)"] = metrics_opt_ret["Expected Return"] - cur_ret
        except Exception:
            comparison["Optimization Space"]["Alpha Loss (Shortfall Return)"] = None

        return comparison

    def build_portfolio_by_profile(self, profile: str = "balanced", target_return: float = None) -> tuple:
        ef = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)

        if profile == "conservative":
            ef.min_volatility()
        elif profile == "aggressive":
            ef.max_quadratic_utility(risk_aversion=1)
        elif profile == "target_return" and target_return is not None:
            ef.efficient_return(target_return=target_return)
        else:
            ef.max_sharpe(risk_free_rate=self.risk_free_rate)

        cleaned_weights = ef.clean_weights()
        metrics = self.calculate_risk_metrics(cleaned_weights)
        return cleaned_weights, metrics

def render_portfolio_dashboard(pm: PortfolioManager, profiles_results: dict, custom_results: dict = None):
    print("[ARisk Visual] 正在生成组合分析图表集...")

    fig, ax = plt.subplots(figsize=(10, 8))
    plotting.plot_covariance(pm.S, ax=ax, show_tickers=True)
    ax.set_title("Asset Covariance Heatmap", fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig("covariance_heatmap.png", dpi=300)
    plt.close()

    fig, ax = plt.subplots(figsize=(10, 6))
    ef_curve = EfficientFrontier(pm.mu, pm.S, weight_bounds=pm.weight_bounds)
    plotting.plot_efficient_frontier(ef_curve, ax=ax, show_assets=True)

    colors = {"conservative": "blue", "balanced": "red", "aggressive": "green"}
    markers = {"conservative": "s", "balanced": "*", "aggressive": "^"}

    for name, data in profiles_results.items():
        m = data["metrics"]
        ax.scatter(
            m["Volatility"], 
            m["Expected Return"], 
            marker=markers.get(name, "o"), 
            color=colors.get(name, "black"), 
            s=180, 
            label=f"{name.capitalize()} Portfolio",
            zorder=5
        )

    if custom_results:
        for name, data in custom_results.items():
            m = data["metrics"]
            ax.scatter(
                m["Volatility"], 
                m["Expected Return"], 
                marker="X", 
                color="purple", 
                s=200, 
                label=f"{name} (Custom)",
                zorder=6
            )
            ax.annotate(
                f"  {name}\n  (Sharpe: {m['Sharpe Ratio']:.2f})",
                (m["Volatility"], m["Expected Return"]),
                fontsize=9
            )

    ax.set_title("Efficient Frontier & Portfolio Comparisons", fontsize=14, fontweight='bold')
    ax.set_xlabel("Annualized Volatility (Risk)")
    ax.set_ylabel("Annualized Expected Return")
    ax.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig("efficient_frontier_portfolios.png", dpi=300)
    plt.close()

    combined_weights = {k: v["weights"] for k, v in profiles_results.items()}
    if custom_results:
        for k, v in custom_results.items():
            combined_weights[k] = v["weights"]

    weights_df = pd.DataFrame(combined_weights)
    weights_df = weights_df.loc[(weights_df != 0).any(axis=1)]

    weights_df.plot(kind="bar", figsize=(12, 6), width=0.8)
    plt.title("Asset Allocation Comparison Across Portfolios", fontsize=14, fontweight='bold')
    plt.xlabel("Assets")
    plt.ylabel("Weight Allocation")
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend(title="Portfolio Name")
    plt.tight_layout()
    plt.savefig("asset_allocation_comparison.png", dpi=300)
    plt.close()

    print("[ARisk Visual] 图表生成完毕，已保存为 png 文件：")
    print("  - covariance_heatmap.png")
    print("  - efficient_frontier_portfolios.png")
    print("  - asset_allocation_comparison.png")

def main():
    # ==========================================
    # 模块 A：自定义参数设置
    # ==========================================
    symbols = [
        "GOOG", "AAPL", "META", "BABA", "AMZN", 
        "GE", "AMD", "WMT", "BAC", "GM", 
        "T", "UAA", "XOM", "BBY", "MA", 
        "PFE", "JPM", "SBUX"
    ]
    RISK_FREE_RATE = 0.04          # 无风险利率
    WEIGHT_BOUNDS = (0.0, 0.25)     # 单标的持仓权重约束 (0% - 25%)

    # ==========================================
    # 模块 B：初始化与行情提取
    # ==========================================
    pm = PortfolioManager(tickers=symbols, risk_free_rate=RISK_FREE_RATE, weight_bounds=WEIGHT_BOUNDS)
    pm.fetch_data(provider="yfinance")

    # ==========================================
    # 模块 B2：4 种特定预期收益率模型计算与导出
    # ==========================================
    # 可选配置 Black-Litterman 模型的观点 (Views)
    sample_views = {
        "AAPL": 0.15,
        "GOOG": 0.12,
        "AMD": 0.20
    }

    print("\n=================== ARisk 个股预期收益率模型对比 (4 种方法) ===================")
    returns_comparison = pm.compute_all_return_models(views=sample_views)
    formatted_returns = returns_comparison.map(lambda x: f"{x*100:.2f}%")
    print(formatted_returns)
    returns_comparison.to_csv("individual_assets_return_models.csv")
    print("[ARisk Data] 4 种个股收益率模型结果已导出至: individual_assets_return_models.csv")

    # 设置特定模型用于后续组合优化（示例采用 Black-Litterman 收益率）
    pm.set_return_model(method="black_litterman", views=sample_views)

    print("\n=================== ARisk 个股独立风险与绩效指标 ===================")
    asset_metrics = pm.calculate_individual_asset_metrics()
    formatted_asset_metrics = asset_metrics.copy()
    formatted_asset_metrics["Expected Return"] = formatted_asset_metrics["Expected Return"].map(lambda x: f"{x*100:.2f}%")
    formatted_asset_metrics["Volatility"] = formatted_asset_metrics["Volatility"].map(lambda x: f"{x*100:.2f}%")
    formatted_asset_metrics["Sharpe Ratio"] = formatted_asset_metrics["Sharpe Ratio"].map(lambda x: f"{x:.2f}")
    formatted_asset_metrics["Max Drawdown"] = formatted_asset_metrics["Max Drawdown"].map(lambda x: f"{x*100:.2f}%")
    print(formatted_asset_metrics)
    asset_metrics.to_csv("individual_assets_metrics.csv")
    print("[ARisk Data] 个股独立风险与绩效指标已导出至: individual_assets_metrics.csv")

    # ==========================================
    # 模块 C：基于不同风控偏好构建理论最优组合
    # ==========================================
    profiles = ["conservative", "balanced", "aggressive"]
    results = {}

    print("\n=================== ARisk 理论最优组合分析报告 ===================")
    for p in profiles:
        weights, metrics = pm.build_portfolio_by_profile(profile=p)
        results[p] = {"weights": weights, "metrics": metrics}

        print(f"\n【{p.upper()} 投资组合】")
        print(f"  年化预期收益率: {metrics['Expected Return']*100:.2f}%")
        print(f"  年化波动率    : {metrics['Volatility']*100:.2f}%")
        print(f"  夏普比率      : {metrics['Sharpe Ratio']:.2f}")

    # ==========================================
    # 模块 D：评估自定义 / 非有效前沿组合
    # ==========================================
    print("\n=================== ARisk 自定义/非有效前沿组合诊断 ===================")
    
    user_custom_weights = {
        "GOOG": 0.10, "AAPL": 0.10, "META": 0.10, "BABA": 0.10, "AMZN": 0.10,
        "GE": 0.10, "AMD": 0.10, "WMT": 0.10, "BAC": 0.10, "GM": 0.10
    }

    norm_custom_w, custom_metrics = pm.evaluate_custom_weights(user_custom_weights)
    print("\n【用户自定义组合 - 风控与绩效指标】")
    print(f"  年化预期收益率: {custom_metrics['Expected Return']*100:.2f}%")
    print(f"  年化波动率    : {custom_metrics['Volatility']*100:.2f}%")
    print(f"  夏普比率      : {custom_metrics['Sharpe Ratio']:.2f}")
    print(f"  历史最大回撤  : {custom_metrics['Max Drawdown']*100:.2f}%")
    print(f"  日度 VaR (95%): {custom_metrics['Historical VaR (95%)']*100:.2f}%")
    print(f"  日度 CVaR(95%): {custom_metrics['Historical CVaR (95%)']*100:.2f}%")

    efficiency_report = pm.check_if_efficient(user_custom_weights)
    space = efficiency_report["Optimization Space"]
    print("\n【有效前沿优化空间诊断】")
    if space.get("Alpha Loss (Shortfall Return)") is not None:
        print(f"  Alpha 收益损失 : {space['Alpha Loss (Shortfall Return)']*100:.2f}% (在相同波动率下，理论最高收益可提升该数值)")
    if space.get("Extra Risk (Excess Vol)") is not None:
        print(f"  无用风险溢价   : {space['Extra Risk (Excess Vol)']*100:.2f}% (在实现相同收益下，理论最小波动率可降低该数值)")

    custom_results = {
        "User Custom": {"weights": norm_custom_w, "metrics": custom_metrics}
    }

    summary_df = pd.DataFrame({k: v["weights"] for k, v in {**results, **custom_results}.items()})
    summary_df.to_csv("portfolio_profiles_weights.csv")
    print("\n[ARisk Portfolio] 各组合权重已导出至: portfolio_profiles_weights.csv")

    # ==========================================
    # 模块 E：渲染并显示可视化仪表盘
    # ==========================================
    render_portfolio_dashboard(pm, results, custom_results=custom_results)

if __name__ == "__main__":
    main()