import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
import math


def calculate_var_cvar(
    returns: pd.Series | np.ndarray,
    confidence_levels: List[float] = [0.95, 0.99]
) -> Dict[str, Any]:
    """
    計算標的資產之歷史法與參數法 VaR (Value at Risk) 及 CVaR (Conditional VaR / Expected Shortfall)。
    
    Args:
        returns: 收益率序列 (例如每日 pct_change)
        confidence_levels: 信賴水準清單，預設 [0.95, 0.99]
        
    Returns:
        包含各信賴水準下 VaR、CVaR 與年化波動率之字典
    """
    if isinstance(returns, np.ndarray):
        clean_returns = pd.Series(returns).dropna()
    else:
        clean_returns = returns.dropna()
        
    if len(clean_returns) < 10:
        return {
            "var_95": 0.05,
            "cvar_95": 0.08,
            "var_99": 0.08,
            "cvar_99": 0.12,
            "volatility_annualized": 0.30,
            "max_drawdown": 0.15,
            "sample_size": len(clean_returns),
            "status": "fallback_insufficient_data"
        }
        
    mean_ret = float(clean_returns.mean())
    std_ret = float(clean_returns.std(ddof=1))
    ann_vol = float(std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
    
    # 計算最大回撤 (Max Drawdown)
    cum_returns = (1 + clean_returns).cumprod()
    peak = cum_returns.cummax()
    drawdown = (cum_returns - peak) / peak
    max_drawdown = float(abs(drawdown.min())) if not drawdown.empty else 0.0
    
    result = {
        "mean_daily_return": round(mean_ret, 6),
        "volatility_daily": round(std_ret, 6),
        "volatility_annualized": round(ann_vol, 4),
        "max_drawdown": round(max_drawdown, 4),
        "sample_size": len(clean_returns),
        "status": "calculated"
    }
    
    for cl in confidence_levels:
        pct_label = int(cl * 100)
        # 1. 歷史法 (Historical Simulation)
        hist_cutoff = np.percentile(clean_returns, (1 - cl) * 100)
        var_hist = abs(float(hist_cutoff))
        
        tail_losses = clean_returns[clean_returns <= hist_cutoff]
        if not tail_losses.empty:
            cvar_hist = abs(float(tail_losses.mean()))
        else:
            cvar_hist = var_hist * 1.25
            
        # 2. 參數法 (Parametric Gaussian VaR)
        # Z-scores: 95% -> 1.64485, 99% -> 2.32635
        z_score = 1.64485 if cl == 0.95 else (2.32635 if cl == 0.99 else 1.95996)
        var_param = max(0.0, float(-(mean_ret - z_score * std_ret)))
        # Gaussian CVaR approx: mean + std * phi(z) / (1 - cl)
        pdf_z = np.exp(-0.5 * (z_score ** 2)) / np.sqrt(2 * np.pi)
        cvar_param = max(var_param, float(-(mean_ret - std_ret * (pdf_z / (1 - cl)))))
        
        result[f"var_{pct_label}_hist"] = round(var_hist, 4)
        result[f"cvar_{pct_label}_hist"] = round(cvar_hist, 4)
        result[f"var_{pct_label}_param"] = round(var_param, 4)
        result[f"cvar_{pct_label}_param"] = round(cvar_param, 4)
        
        # 預設綜合回傳歷史法為主（更能捕捉厚尾肥尾風險）
        result[f"var_{pct_label}"] = round(var_hist, 4)
        result[f"cvar_{pct_label}"] = round(cvar_hist, 4)
        
    return result


def calculate_volatility_metrics(prices_df: pd.DataFrame) -> Dict[str, Any]:
    """
    計算不同時間週期的歷史實現波動度 (Realized Volatility) 與波動度區間 (Cones)。
    """
    if prices_df is None or prices_df.empty or "close" not in prices_df.columns:
        return {"current_regime": "Normal", "vol_20d": 0.25, "vol_60d": 0.25}
        
    close = prices_df["close"].dropna()
    if len(close) < 15:
        return {"current_regime": "Normal", "vol_20d": 0.25, "vol_60d": 0.25}
        
    returns = close.pct_change().dropna()
    
    vol_20d = float(returns.tail(20).std() * np.sqrt(252)) if len(returns) >= 10 else 0.25
    vol_60d = float(returns.tail(60).std() * np.sqrt(252)) if len(returns) >= 30 else vol_20d
    vol_120d = float(returns.tail(120).std() * np.sqrt(252)) if len(returns) >= 60 else vol_60d
    
    # 判斷當前波動度體制 (Regime)
    if vol_20d > vol_60d * 1.3:
        regime = "High Volatility (Expanding)"
    elif vol_20d < vol_60d * 0.7:
        regime = "Low Volatility (Compressing / Squeeze)"
    else:
        regime = "Normal Volatility"
        
    return {
        "vol_20d_ann": round(vol_20d, 4),
        "vol_60d_ann": round(vol_60d, 4),
        "vol_120d_ann": round(vol_120d, 4),
        "current_regime": regime
    }


def calculate_risk_adjusted_position_size(
    total_portfolio_value: float,
    available_cash: float,
    current_price: float,
    cvar_95: float,
    annualized_vol: float,
    max_risk_budget_ratio: float = 0.02,
    base_position_limit_ratio: float = 0.25
) -> Dict[str, Any]:
    """
    動態風險部位估算：結合 CVaR 極端風險預算與波動率逆權重 (Volatility Parity)。
    
    Args:
        total_portfolio_value: 投資組合總淨值
        available_cash: 可用現金
        current_price: 當前股價
        cvar_95: 95% 信賴水準下的預期條件虧損 (Expected Shortfall)
        annualized_vol: 年化波動率
        max_risk_budget_ratio: 單筆交易所允許的最大組合淨值損失比例 (預設 2%)
        base_position_limit_ratio: 基礎部位上限比例 (由多標的數量決定)
        
    Returns:
        包含建議下單上限、安全股數與量化風控論據
    """
    if total_portfolio_value <= 0 or current_price <= 0:
        return {
            "max_position_dollars": 0.0,
            "max_shares": 0,
            "sizing_method": "error_invalid_inputs"
        }
        
    # 1. 名義等權分配上限 (Nominal Base Limit)
    nominal_limit = total_portfolio_value * base_position_limit_ratio
    
    # 2. CVaR 極端風險預算上限 (Risk Budget Limit)
    # 允許最大損失金額 = 組合淨值 * 2%
    max_tolerable_loss_dollars = total_portfolio_value * max_risk_budget_ratio
    safe_cvar = max(0.02, cvar_95)  # 至少 2% 的單日風險底線
    cvar_position_limit = max_tolerable_loss_dollars / safe_cvar
    
    # 3. 波動度逆權重調節因子 (Volatility Penalty)
    # 基準年化波動度設為 25% (S&P 500 約 15-20%)，高波動標的予以壓縮
    benchmark_vol = 0.25
    vol_scaling = min(1.5, max(0.4, benchmark_vol / max(0.10, annualized_vol)))
    vol_adjusted_limit = nominal_limit * vol_scaling
    
    # 綜合取最小值（保守穩健防禦）
    recommended_position_dollars = min(
        nominal_limit,
        cvar_position_limit,
        vol_adjusted_limit,
        available_cash
    )
    
    recommended_position_dollars = max(0.0, recommended_position_dollars)
    max_shares = int(recommended_position_dollars // current_price) if current_price > 0 else 0
    
    return {
        "recommended_position_dollars": round(recommended_position_dollars, 2),
        "recommended_shares": max_shares,
        "nominal_limit": round(nominal_limit, 2),
        "cvar_risk_budget_limit": round(cvar_position_limit, 2),
        "vol_adjusted_limit": round(vol_adjusted_limit, 2),
        "vol_scaling_factor": round(vol_scaling, 3),
        "max_tolerable_loss_dollars": round(max_tolerable_loss_dollars, 2),
        "binding_constraint": (
            "Available Cash" if recommended_position_dollars == available_cash else
            "CVaR Risk Budget" if recommended_position_dollars == cvar_position_limit else
            "Volatility Penalty" if recommended_position_dollars == vol_adjusted_limit else
            "Nominal Concentration Limit"
        )
    }
