import sys
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # 確保在無顯示器環境下順利保存圖片
import matplotlib.pyplot as plt
import riskfolio as rp
from openbb import obb

import warnings
warnings.filterwarnings('ignore', category=UserWarning)

# ==========================================
# 核心業務邏輯：Riskfolio-Lib 組合引擎
# ==========================================
class PortfolioManager:
    """ARisk 組合管理與風控計算引擎 (基於 Riskfolio-Lib 與 OpenBB)"""
    def __init__(self, tickers: list, risk_free_rate: float = 0.04, weight_bounds: tuple = (0.0, 1.0)):
        self.tickers = tickers
        self.risk_free_rate = risk_free_rate
        self.weight_bounds = weight_bounds
        self.prices_df = None
        self.returns_df = None
        self.mu = None  # 年化期望收益率 (Series)
        self.S = None   # 年化協方差矩陣 (DataFrame)

    def fetch_data(self, provider: str = "yfinance") -> pd.DataFrame:
        """從 OpenBB 獲取多資產日頻歷史行情"""
        print(f"[ARisk Data] 正在獲取 {len(self.tickers)} 隻標的行情數據...")
        series_list = []
        for symbol in self.tickers:
            try:
                res = obb.equity.price.historical(symbol=symbol, provider=provider)
                df = res.to_df()
                # 統一列名轉為小寫以相容不同 Provider
                df.columns = [str(c).lower() for c in df.columns]
                
                if 'close' in df.columns:
                    series = df['close'].rename(symbol)
                elif 'adj_close' in df.columns:
                    series = df['adj_close'].rename(symbol)
                else:
                    raise KeyError("數據中未找到 close 或 adj_close 欄位")

                series_list.append(series)
            except Exception as e:
                print(f"[Warning] 獲取 {symbol} 數據失敗: {e}")

        if not series_list:
            raise ValueError("未能獲取任何資產行情數據！")

        self.prices_df = pd.concat(series_list, axis=1).dropna()
        self.returns_df = self.prices_df.pct_change().dropna()
        
        # 預設使用歷史算術平均收益率與樣本協方差矩陣 (年化)
        self.mu = self.returns_df.mean() * 252
        self.S = self.returns_df.cov() * 252
        return self.prices_df

    def compute_all_return_models(self, market_caps: dict = None, views: dict = None) -> pd.DataFrame:
        """
        計算並對比 4 種特定的個股預期收益率模型：
        1. Historical Mean (歷史年化算術平均收益率)
        2. Real Historical CAGR (真實歷史行情實際複合年化收益率)
        3. CAPM Beta Model (CAPM 因子模型 Beta 期望收益率)
        4. Black-Litterman Model (Black-Litterman 貝葉斯均衡預期收益率)
        """
        trading_days = 252

        # 1. 歷史年化算術平均收益率
        hist_mean = self.returns_df.mean() * trading_days

        # 2. 真實歷史行情複合年化收益率 (CAGR)
        total_obs = len(self.returns_df)
        real_cagr = ((1 + self.returns_df).prod()) ** (trading_days / total_obs) - 1

        # 3. CAPM 因子模型 Beta 期望收益率
        market_proxy = self.returns_df.mean(axis=1)  # 等權重市場代理
        var_mkt = market_proxy.var()
        cov_mkt = self.returns_df.apply(lambda col: col.cov(market_proxy))
        beta = cov_mkt / var_mkt if var_mkt > 0 else 1.0
        mkt_ann_ret = market_proxy.mean() * trading_days
        capm_ret = self.risk_free_rate + beta * (mkt_ann_ret - self.risk_free_rate)

        # 4. Black-Litterman 模型預期收益率
        mkt_var_ann = market_proxy.var() * trading_days
        mkt_ret_ann = market_proxy.mean() * trading_days
        delta = (mkt_ret_ann - self.risk_free_rate) / mkt_var_ann if mkt_var_ann > 0 else 2.5

        if market_caps is None:
            w_mkt = np.ones(len(self.tickers)) / len(self.tickers)
        else:
            mcap_s = pd.Series(market_caps).reindex(self.tickers).fillna(0)
            w_mkt = (mcap_s / mcap_s.sum()).values if mcap_s.sum() > 0 else np.ones(len(self.tickers)) / len(self.tickers)

        # 均衡先驗收益率 \Pi = \delta * \Sigma * w_mkt
        pi = delta * np.dot(self.S, w_mkt)
        pi_series = pd.Series(pi, index=self.tickers)

        if views:
            view_assets = [k for k in views.keys() if k in self.tickers]
            if view_assets:
                k_views = len(view_assets)
                P = np.zeros((k_views, len(self.tickers)))
                Q = np.zeros(k_views)
                for idx, asset in enumerate(view_assets):
                    asset_idx = self.tickers.index(asset)
                    P[idx, asset_idx] = 1.0
                    Q[idx] = views[asset]

                tau = 0.05
                tau_S = tau * self.S.values
                omega = np.diag(np.diag(np.dot(np.dot(P, tau_S), P.T)))
                
                inv_tau_S = np.linalg.inv(tau_S)
                inv_omega = np.linalg.inv(omega)
                
                M = np.linalg.inv(inv_tau_S + np.dot(np.dot(P.T, inv_omega), P))
                bl_mu = np.dot(M, (np.dot(inv_tau_S, pi) + np.dot(np.dot(P.T, inv_omega), Q)))
                bl_ret = pd.Series(bl_mu, index=self.tickers)
            else:
                bl_ret = pi_series
        else:
            bl_ret = pi_series

        returns_comparison_df = pd.DataFrame({
            "Historical Mean (Arithmetic)": hist_mean,
            "Real Historical CAGR (Compound)": real_cagr,
            "CAPM Beta Model": capm_ret,
            "Black-Litterman Model": bl_ret
        })
        return returns_comparison_df

    def set_return_model(self, method: str = "historical_mean", market_caps: dict = None, views: dict = None):
        """切換組合優化時使用的預期收益率模型"""
        all_models = self.compute_all_return_models(market_caps=market_caps, views=views)
        
        mapping = {
            "historical_mean": "Historical Mean (Arithmetic)",
            "real_cagr": "Real Historical CAGR (Compound)",
            "capm": "CAPM Beta Model",
            "black_litterman": "Black-Litterman Model"
        }
        if method in mapping:
            self.mu = all_models[mapping[method]]
        else:
            raise ValueError(f"未知的收益率模型方法: {method}")

    def calculate_individual_asset_metrics(self) -> pd.DataFrame:
        """計算個股層面的 4 項核心風控與績效指標"""
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

        return pd.DataFrame(metrics_list).set_index("Asset")

    def calculate_risk_metrics(self, weights: dict) -> dict:
        """計算組合的年化收益率、波動率、夏普比率、最大回撤、VaR 與 CVaR"""
        w = np.array([weights.get(col, 0.0) for col in self.prices_df.columns])
        portfolio_daily_returns = (self.returns_df * w).sum(axis=1)

        exp_ret = float(np.sum(self.mu * w))
        vol = float(np.sqrt(np.dot(w.T, np.dot(self.S, w))))
        sharpe = (exp_ret - self.risk_free_rate) / vol if vol > 0 else 0.0

        cum_returns = (1 + portfolio_daily_returns).cumprod()
        peak = cum_returns.cummax()
        drawdown = (cum_returns - peak) / peak
        max_drawdown = float(drawdown.min())

        var_95 = float(np.percentile(portfolio_daily_returns, 5))
        cvar_95 = float(portfolio_daily_returns[portfolio_daily_returns <= var_95].mean())

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

    def _create_rp_portfolio(self) -> rp.Portfolio:
        """
        內部輔助函式：
        創建並初始化 Riskfolio-Lib Portfolio，
        並嚴格注入資產權重上下限約束。
        """
        # --------------------------------------------------
        # 1. 使用實際成功獲取行情的資產作為唯一資產維度
        # --------------------------------------------------
        assets = list(self.returns_df.columns)
        n_assets = len(assets)

        if n_assets == 0:
            raise ValueError("沒有可用的資產收益率數據，無法建立 Riskfolio Portfolio")

        # --------------------------------------------------
        # 2. 創建 Riskfolio-Lib Portfolio
        # --------------------------------------------------
        port = rp.Portfolio(
            returns=self.returns_df
        )

        # --------------------------------------------------
        # 3. 注入期望收益率與協方差矩陣
        #
        # Riskfolio-Lib optimization(hist=False) 使用
        # portfolio.mu / portfolio.cov
        #
        # self.mu / self.S 為年化數據，
        # 這裡轉回日頻，與 returns_df 的日頻數據保持一致。
        # --------------------------------------------------
        mu_daily = self.mu.reindex(assets) / 252.0
        cov_daily = self.S.reindex(index=assets, columns=assets) / 252.0

        port.mu = mu_daily.to_frame().T
        port.cov = cov_daily

        # --------------------------------------------------
        # 4. 權重上下限
        #
        # 目標：
        #   lower <= w_i <= upper
        #
        # 轉化為 Riskfolio-Lib 線性不等式：
        #
        #   A @ w <= b
        #
        # 上限：
        #   w_i <= upper
        #
        # 下限：
        #   w_i >= lower
        #   等價於
        #   -w_i <= -lower
        # --------------------------------------------------
        lower_bound = float(self.weight_bounds[0])
        upper_bound = float(self.weight_bounds[1])

        if lower_bound > upper_bound:
            raise ValueError(
                f"無效的權重上下限：lower={lower_bound}, upper={upper_bound}"
            )

        if lower_bound < 0:
            raise ValueError(
                f"目前 PortfolioManager 不支持負權重下限：{lower_bound}"
            )

        if upper_bound > 1:
            raise ValueError(
                f"權重上限不能大於 1：{upper_bound}"
            )

        # 上限矩陣
        A_upper = np.eye(n_assets)
        b_upper = np.full(
            (n_assets, 1),
            upper_bound,
            dtype=float
        )

        # 下限矩陣
        A_lower = -np.eye(n_assets)
        b_lower = np.full(
            (n_assets, 1),
            -lower_bound,
            dtype=float
        )

        # --------------------------------------------------
        # 5. 關鍵修正：
        #
        # Riskfolio-Lib 正確屬性名稱是：
        #
        #   port.ainequality
        #   port.binequality
        #
        # 不是：
        #
        #   port.aineq
        #   port.bineq
        #
        # 後兩者不會被 Riskfolio-Lib 優化器當作正式約束。
        # --------------------------------------------------
        port.ainequality = np.vstack([
            A_upper,
            A_lower
        ])

        port.binequality = np.vstack([
            b_upper,
            b_lower
        ])

        # --------------------------------------------------
        # 6. 基本結構自檢
        # --------------------------------------------------
        expected_rows = n_assets * 2

        if port.ainequality.shape != (expected_rows, n_assets):
            raise ValueError(
                "Riskfolio inequality constraint matrix 維度錯誤："
                f"{port.ainequality.shape}, "
                f"expected=({expected_rows}, {n_assets})"
            )

        if port.binequality.shape != (expected_rows, 1):
            raise ValueError(
                "Riskfolio inequality constraint vector 維度錯誤："
                f"{port.binequality.shape}, "
                f"expected=({expected_rows}, 1)"
            )

        return port

    def check_if_efficient(self, weights_dict: dict) -> dict:
        """使用 Riskfolio-Lib 評估非有效前沿組合並計算修復空間"""
        _, current_metrics = self.evaluate_custom_weights(weights_dict)
        cur_ret = current_metrics["Expected Return"]
        cur_vol = current_metrics["Volatility"]

        comparison = {
            "Current Portfolio": current_metrics,
            "Efficient Counterparts": {},
            "Optimization Space": {}
        }

        # 1. 相同收益率下，最小化波動率組合
        try:
            port_ret = self._create_rp_portfolio()
            port_ret.lower_return = cur_ret / 252.0
            w_opt_vol_df = port_ret.optimization(model='Classic', rm='MV', obj='MinRisk', hist=True)
            opt_w_vol = w_opt_vol_df['weights'].to_dict()
            metrics_opt_vol = self.calculate_risk_metrics(opt_w_vol)
            
            comparison["Efficient Counterparts"]["Same Return (Min Vol)"] = metrics_opt_vol
            comparison["Optimization Space"]["Extra Risk (Excess Vol)"] = cur_vol - metrics_opt_vol["Volatility"]
        except Exception:
            comparison["Optimization Space"]["Extra Risk (Excess Vol)"] = None

        # 2. 相同波動率下，最大化收益率組合
        try:
            port_vol = self._create_rp_portfolio()
            port_vol.upper_risk = cur_vol / np.sqrt(252.0)
            w_opt_ret_df = port_vol.optimization(model='Classic', rm='MV', obj='MaxRet', hist=True)
            opt_w_ret = w_opt_ret_df['weights'].to_dict()
            metrics_opt_ret = self.calculate_risk_metrics(opt_w_ret)
            
            comparison["Efficient Counterparts"]["Same Vol (Max Return)"] = metrics_opt_ret
            comparison["Optimization Space"]["Alpha Loss (Shortfall Return)"] = metrics_opt_ret["Expected Return"] - cur_ret
        except Exception:
            comparison["Optimization Space"]["Alpha Loss (Shortfall Return)"] = None

        return comparison

    def build_portfolio_by_profile(self, profile: str = "balanced", target_return: float = None) -> tuple:
        """基於 Riskfolio-Lib 引擎構建不同風險偏好的最優組合"""
        port = self._create_rp_portfolio()

        if profile == "conservative":
            # 保守型：最小化波動率
            w_df = port.optimization(model='Classic', rm='MV', obj='MinRisk', hist=True)
        elif profile == "aggressive":
            # 激進型：最大化效用函數 (Risk Aversion l=1)
            w_df = port.optimization(model='Classic', rm='MV', obj='Utility', l=1.0, hist=True)
        elif profile == "target_return" and target_return is not None:
            # 目標收益率
            port.lower_return = target_return / 252.0
            w_df = port.optimization(model='Classic', rm='MV', obj='MinRisk', hist=True)
        else:
            # 平衡型：最大化夏普比率
            w_df = port.optimization(model='Classic', rm='MV', obj='Sharpe', rf=self.risk_free_rate / 252.0, hist=True)

        cleaned_weights = w_df['weights'].to_dict()
        metrics = self.calculate_risk_metrics(cleaned_weights)
        return cleaned_weights, metrics

# ==========================================
# Riskfolio-Lib 專用功能驗證模組
# ==========================================
def verify_riskfolio_lib(pm: PortfolioManager):
    """驗證 Riskfolio-Lib 核心組件運作狀態"""
    print("\n=================== Riskfolio-Lib 核心功能專項驗證 ===================")

    port = pm._create_rp_portfolio()

    # --------------------------------------------------
    # 0. 驗證線性權重約束是否真正注入
    # --------------------------------------------------
    print(
        f"[驗證 0] 權重約束矩陣建立成功 "
        f"(A={port.ainequality.shape}, B={port.binequality.shape})"
    )

    # --------------------------------------------------
    # 1. Mean-Variance Sharpe 優化
    # --------------------------------------------------
    w_mv = port.optimization(
        model='Classic',
        rm='MV',
        obj='Sharpe',
        rf=pm.risk_free_rate / 252.0,
        hist=False
    )

    if w_mv is None or 'weights' not in w_mv.columns:
        raise ValueError("Riskfolio-Lib Sharpe 優化未返回有效 weights")

    weights_mv = w_mv['weights']

    sum_mv = float(weights_mv.sum())

    print(
        f"[驗證 1] Mean-Variance 最優夏普優化成功 "
        f"(權重總和 = {sum_mv:.4f})"
    )

    # --------------------------------------------------
    # 2. Min-CVaR
    # --------------------------------------------------
    w_cvar = port.optimization(
        model='Classic',
        rm='CVaR',
        obj='MinRisk',
        hist=True
    )

    if w_cvar is None or 'weights' not in w_cvar.columns:
        raise ValueError("Riskfolio-Lib CVaR 優化未返回有效 weights")

    weights_cvar = w_cvar['weights']

    sum_cvar = float(weights_cvar.sum())

    print(
        f"[驗證 2] Min-CVaR (尾部風險) 優化成功 "
        f"(權重總和 = {sum_cvar:.4f})"
    )

    # --------------------------------------------------
    # 3. 驗證權重邊界
    # --------------------------------------------------
    max_w = float(weights_mv.max())
    min_w = float(weights_mv.min())

    upper_bound = float(pm.weight_bounds[1])
    lower_bound = float(pm.weight_bounds[0])

    print(
        f"[驗證 3] 實際權重範圍："
        f"Min={min_w:.6f}, Max={max_w:.6f}"
    )

    assert abs(sum_mv - 1.0) <= 1e-5, (
        f"Sharpe 優化後權重總和異常: {sum_mv}"
    )

    assert abs(sum_cvar - 1.0) <= 1e-5, (
        f"CVaR 優化後權重總和異常: {sum_cvar}"
    )

    assert max_w <= upper_bound + 1e-5, (
        f"超出權重上限: max={max_w}, upper={upper_bound}"
    )

    assert min_w >= lower_bound - 1e-5, (
        f"低於權重下限: min={min_w}, lower={lower_bound}"
    )

    print(
        f"[驗證 3] 權重盒約束 Validation Passed! "
        f"(Min: {min_w:.2%}, Max: {max_w:.2%}, "
        f"Bounds: [{lower_bound:.2%}, {upper_bound:.2%}])"
    )

# ==========================================
# 可視化儀表盤渲染
# ==========================================
def render_portfolio_dashboard(pm: PortfolioManager, profiles_results: dict, custom_results: dict = None):
    print("\n[ARisk Visual] 正在生成組合分析圖表集...")

    # 1. 協方差矩陣熱力圖
    fig, ax = plt.subplots(figsize=(10, 8))
    cax = ax.matshow(pm.S, cmap='coolwarm')
    fig.colorbar(cax)
    ax.set_xticks(range(len(pm.tickers)))
    ax.set_yticks(range(len(pm.tickers)))
    ax.set_xticklabels(pm.tickers, rotation=90)
    ax.set_yticklabels(pm.tickers)
    ax.set_title("Asset Covariance Heatmap (Riskfolio-Lib)", fontsize=14, fontweight='bold', pad=20)
    plt.tight_layout()
    plt.savefig("covariance_heatmap.png", dpi=300)
    plt.close()

    # 2. 有效前沿曲線繪製
    port = pm._create_rp_portfolio()
    frontier = port.efficient_frontier(model='Classic', rm='MV', points=50, hist=True)

    frontier_vols = []
    frontier_rets = []
    for col in frontier.columns:
        w_vec = frontier[col].values
        r = float(np.dot(w_vec, pm.mu))
        v = float(np.sqrt(np.dot(w_vec.T, np.dot(pm.S, w_vec))))
        frontier_rets.append(r)
        frontier_vols.append(v)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(frontier_vols, frontier_rets, linestyle='--', color='navy', label='Efficient Frontier (Riskfolio-Lib)', linewidth=2)

    # 標註個股點
    asset_vols = np.sqrt(np.diag(pm.S))
    asset_rets = pm.mu
    ax.scatter(asset_vols, asset_rets, color='gray', alpha=0.5, label='Individual Assets')

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

    # 3. 資產配置比率柱狀圖
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

    print("[ARisk Visual] 圖表生成完畢，已保存為 png 文件：")
    print("  - covariance_heatmap.png")
    print("  - efficient_frontier_portfolios.png")
    print("  - asset_allocation_comparison.png")

# ==========================================
# 主程序入口
# ==========================================
def main():
    symbols = [
        "GOOG", "AAPL", "META", "BABA", "AMZN", 
        "GE", "AMD", "WMT", "BAC", "GM", 
        "T", "UAA", "XOM", "BBY", "MA", 
        "PFE", "JPM", "SBUX"
    ]
    RISK_FREE_RATE = 0.04
    WEIGHT_BOUNDS = (0.0, 0.25)

    pm = PortfolioManager(tickers=symbols, risk_free_rate=RISK_FREE_RATE, weight_bounds=WEIGHT_BOUNDS)
    pm.fetch_data(provider="yfinance")

    # 執行 Riskfolio-Lib 專有功能驗證
    verify_riskfolio_lib(pm)

    sample_views = {
        "AAPL": 0.15,
        "GOOG": 0.12,
        "AMD": 0.20
    }

    print("\n=================== ARisk 個股預期收益率模型對比 (4 種方法) ===================")
    returns_comparison = pm.compute_all_return_models(views=sample_views)
    
    # 兼容不同版本 Pandas 的 map/applymap 方法
    if hasattr(returns_comparison, "map"):
        formatted_returns = returns_comparison.map(lambda x: f"{x*100:.2f}%")
    else:
        formatted_returns = returns_comparison.applymap(lambda x: f"{x*100:.2f}%")
        
    print(formatted_returns)
    returns_comparison.to_csv("individual_assets_return_models.csv")
    print("[ARisk Data] 4 種個股收益率模型結果已導出至: individual_assets_return_models.csv")

    pm.set_return_model(method="black_litterman", views=sample_views)

    print("\n=================== ARisk 個股獨立風險與績效指標 ===================")
    asset_metrics = pm.calculate_individual_asset_metrics()
    formatted_asset_metrics = asset_metrics.copy()
    formatted_asset_metrics["Expected Return"] = formatted_asset_metrics["Expected Return"].map(lambda x: f"{x*100:.2f}%")
    formatted_asset_metrics["Volatility"] = formatted_asset_metrics["Volatility"].map(lambda x: f"{x*100:.2f}%")
    formatted_asset_metrics["Sharpe Ratio"] = formatted_asset_metrics["Sharpe Ratio"].map(lambda x: f"{x:.2f}")
    formatted_asset_metrics["Max Drawdown"] = formatted_asset_metrics["Max Drawdown"].map(lambda x: f"{x*100:.2f}%")
    print(formatted_asset_metrics)
    asset_metrics.to_csv("individual_assets_metrics.csv")
    print("[ARisk Data] 個股獨立風險與績效指標已導出至: individual_assets_metrics.csv")

    profiles = ["conservative", "balanced", "aggressive"]
    results = {}

    print("\n=================== ARisk 理論最優組合分析報告 (Riskfolio Engine) ===================")
    for p in profiles:
        weights, metrics = pm.build_portfolio_by_profile(profile=p)
        results[p] = {"weights": weights, "metrics": metrics}

        print(f"\n【{p.upper()} 投資組合】")
        print(f"  年化預期收益率: {metrics['Expected Return']*100:.2f}%")
        print(f"  年化波動率    : {metrics['Volatility']*100:.2f}%")
        print(f"  夏普比率      : {metrics['Sharpe Ratio']:.2f}")

    print("\n=================== ARisk 自訂/非有效前沿組合診斷 ===================")
    user_custom_weights = {
        "GOOG": 0.10, "AAPL": 0.10, "META": 0.10, "BABA": 0.10, "AMZN": 0.10,
        "GE": 0.10, "AMD": 0.10, "WMT": 0.10, "BAC": 0.10, "GM": 0.10
    }

    norm_custom_w, custom_metrics = pm.evaluate_custom_weights(user_custom_weights)
    print("\n【用戶自訂組合 - 風控與績效指標】")
    print(f"  年化預期收益率: {custom_metrics['Expected Return']*100:.2f}%")
    print(f"  年化波動率    : {custom_metrics['Volatility']*100:.2f}%")
    print(f"  夏普比率      : {custom_metrics['Sharpe Ratio']:.2f}")
    print(f"  歷史最大回撤  : {custom_metrics['Max Drawdown']*100:.2f}%")
    print(f"  日度 VaR (95%): {custom_metrics['Historical VaR (95%)']*100:.2f}%")
    print(f"  日度 CVaR(95%): {custom_metrics['Historical CVaR (95%)']*100:.2f}%")

    efficiency_report = pm.check_if_efficient(user_custom_weights)
    space = efficiency_report["Optimization Space"]
    print("\n【有效前沿優化空間診斷】")
    if space.get("Alpha Loss (Shortfall Return)") is not None:
        print(f"  Alpha 收益損失 : {space['Alpha Loss (Shortfall Return)']*100:.2f}% (在相同波動率下，理論最高收益可提升該數值)")
    if space.get("Extra Risk (Excess Vol)") is not None:
        print(f"  無用風險溢價   : {space['Extra Risk (Excess Vol)']*100:.2f}% (在實現相同收益下，理論最小波動率可降低該數值)")

    custom_results = {
        "User Custom": {"weights": norm_custom_w, "metrics": custom_metrics}
    }

    summary_df = pd.DataFrame({k: v["weights"] for k, v in {**results, **custom_results}.items()})
    summary_df.to_csv("portfolio_profiles_weights.csv")
    print("\n[ARisk Portfolio] 各組合權重已導出至: portfolio_profiles_weights.csv")

    render_portfolio_dashboard(pm, results, custom_results=custom_results)

if __name__ == "__main__":
    main()