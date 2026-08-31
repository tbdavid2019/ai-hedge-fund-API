import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional


def calculate_dcf_sensitivity(
    free_cash_flow: float,
    current_price: float,
    shares_outstanding: Optional[float] = None,
    market_cap: Optional[float] = None,
    base_wacc: float = 0.10,
    base_terminal_growth: float = 0.025,
    forecast_growth: float = 0.08,
    forecast_years: int = 5
) -> Dict[str, Any]:
    """
    計算 5x5 DCF 敏感度分析矩陣 (WACC 折現率 vs. 永續增長率 Terminal Growth)。
    
    Args:
        free_cash_flow: 最近一期自由現金流 (FCF, USD)
        current_price: 當前股價
        shares_outstanding: 流通股數
        market_cap: 總市值 (若 shares_outstanding 為空則由此推算)
        base_wacc: 基準加權平均資金成本 (預設 10%)
        base_terminal_growth: 基準永續增長率 (預設 2.5%)
        forecast_growth: 前 5 年預估 FCF 年增率 (預設 8%)
        forecast_years: 預測年數 (預設 5 年)
        
    Returns:
        包含 5x5 矩陣、中位數內在價值、安全邊際 (Margin of Safety) 之字典
    """
    if free_cash_flow <= 0 or current_price <= 0:
        return {
            "status": "invalid_fcf_or_price",
            "message": "Free cash flow or current price must be positive for DCF.",
            "fair_value_median": current_price,
            "margin_of_safety": 0.0
        }
        
    if not shares_outstanding or shares_outstanding <= 0:
        if market_cap and market_cap > 0 and current_price > 0:
            shares_outstanding = market_cap / current_price
        else:
            shares_outstanding = 1.0  # 避免除以零
            
    wacc_range = [base_wacc - 0.02, base_wacc - 0.01, base_wacc, base_wacc + 0.01, base_wacc + 0.02]
    growth_range = [
        base_terminal_growth - 0.01,
        base_terminal_growth - 0.005,
        base_terminal_growth,
        base_terminal_growth + 0.005,
        base_terminal_growth + 0.01
    ]
    
    matrix = []
    fair_values = []
    
    for w in wacc_range:
        row = {"wacc": f"{w*100:.1f}%"}
        for g in growth_range:
            g_key = f"g_{g*100:.1f}%"
            if w <= g:
                row[g_key] = None
                continue
                
            # 1. 預測期 FCF 現值 (PV of Forecast Period)
            pv_forecast = 0.0
            for t in range(1, forecast_years + 1):
                fcf_t = free_cash_flow * ((1 + forecast_growth) ** t)
                pv_forecast += fcf_t / ((1 + w) ** t)
                
            # 2. 終值現值 (PV of Terminal Value - Gordon Growth Model)
            terminal_fcf = free_cash_flow * ((1 + forecast_growth) ** forecast_years) * (1 + g)
            terminal_value = terminal_fcf / (w - g)
            pv_terminal = terminal_value / ((1 + w) ** forecast_years)
            
            enterprise_value = pv_forecast + pv_terminal
            per_share_val = enterprise_value / shares_outstanding
            per_share_val = max(0.0, per_share_val)
            
            row[g_key] = round(per_share_val, 2)
            fair_values.append(per_share_val)
            
        matrix.append(row)
        
    valid_values = [v for v in fair_values if v is not None and v > 0]
    if valid_values:
        median_fair_value = float(np.median(valid_values))
        min_fair_value = float(np.min(valid_values))
        max_fair_value = float(np.max(valid_values))
        margin_of_safety = float((median_fair_value - current_price) / median_fair_value) if median_fair_value > 0 else 0.0
    else:
        median_fair_value = current_price
        min_fair_value = current_price
        max_fair_value = current_price
        margin_of_safety = 0.0
        
    valuation_status = (
        "Severely Undervalued" if margin_of_safety >= 0.30 else
        "Modestly Undervalued" if margin_of_safety >= 0.10 else
        "Fairly Valued" if margin_of_safety >= -0.10 else
        "Modestly Overvalued" if margin_of_safety >= -0.30 else
        "Severely Overvalued"
    )
    
    return {
        "status": "calculated",
        "current_price": round(current_price, 2),
        "fair_value_median": round(median_fair_value, 2),
        "fair_value_range": [round(min_fair_value, 2), round(max_fair_value, 2)],
        "margin_of_safety_pct": round(margin_of_safety * 100, 2),
        "valuation_status": valuation_status,
        "sensitivity_matrix": matrix
    }


def calculate_altman_z_score(
    working_capital: Optional[float],
    total_assets: Optional[float],
    retained_earnings: Optional[float],
    ebit: Optional[float],
    market_cap: Optional[float],
    total_liabilities: Optional[float],
    total_revenue: Optional[float]
) -> Dict[str, Any]:
    """
    計算 Altman Z-Score 破產風險預警模型。
    Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 0.999*X5
    
    X1 = Working Capital / Total Assets
    X2 = Retained Earnings / Total Assets
    X3 = EBIT / Total Assets
    X4 = Market Cap / Total Liabilities
    X5 = Total Revenue / Total Assets
    """
    if not total_assets or total_assets <= 0:
        return {"z_score": None, "zone": "Unknown (Insufficient Asset Data)", "risk_level": "Unknown"}
        
    wc = working_capital if working_capital is not None else 0.0
    re = retained_earnings if retained_earnings is not None else 0.0
    eb = ebit if ebit is not None else 0.0
    mc = market_cap if market_cap is not None else 0.0
    tl = total_liabilities if (total_liabilities is not None and total_liabilities > 0) else (total_assets * 0.5)
    rev = total_revenue if total_revenue is not None else 0.0
    
    x1 = wc / total_assets
    x2 = re / total_assets
    x3 = eb / total_assets
    x4 = mc / tl
    x5 = rev / total_assets
    
    z_score = float(1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 0.999 * x5)
    
    if z_score >= 2.99:
        zone = "Safe Zone (財務健全，低破產風險)"
        risk_level = "Low"
    elif z_score >= 1.81:
        zone = "Grey Zone (灰色區間，需關注財務槓桿)"
        risk_level = "Moderate"
    else:
        zone = "Distress Zone (破產高風險警戒區)"
        risk_level = "High"
        
    return {
        "z_score": round(z_score, 2),
        "zone": zone,
        "risk_level": risk_level,
        "components": {
            "x1_working_capital_to_assets": round(x1, 4),
            "x2_retained_earnings_to_assets": round(x2, 4),
            "x3_ebit_to_assets": round(x3, 4),
            "x4_market_equity_to_liabilities": round(x4, 4),
            "x5_asset_turnover": round(x5, 4)
        }
    }


def calculate_piotroski_f_score(
    current_metrics: Dict[str, Any],
    previous_metrics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    計算 Piotroski F-Score (0~9 分)，評估企業財務體質是否正在改善。
    
    9大信號標準：
    1. Net Income > 0 (獲利性)
    2. ROA > 0 (獲利性)
    3. Operating Cash Flow (CFO) > 0 (獲利性)
    4. CFO > Net Income (盈餘品質 - 無應計項目灌水)
    5. 長期負債佔總資產比重下降 (槓桿降低)
    6. 流動比率增加 (流動性改善)
    7. 流通股數未增加 (無股權稀釋)
    8. 毛利率較前一年提升 (營運效率)
    9. 資產周轉率較前一年提升 (資產使用效率)
    """
    score = 0
    breakdown = {}
    
    net_income = current_metrics.get("net_income") or 0.0
    roa = current_metrics.get("return_on_assets") or 0.0
    cfo = current_metrics.get("operating_cash_flow") or 0.0
    
    # 1. 淨利潤為正
    f1 = 1 if net_income > 0 else 0
    score += f1
    breakdown["positive_net_income"] = bool(f1)
    
    # 2. 資產報酬率 ROA 為正
    f2 = 1 if roa > 0 else 0
    score += f2
    breakdown["positive_roa"] = bool(f2)
    
    # 3. 營業現金流為正
    f3 = 1 if cfo > 0 else 0
    score += f3
    breakdown["positive_operating_cf"] = bool(f3)
    
    # 4. 營業現金流大於淨利潤 (高盈餘品質)
    f4 = 1 if cfo > net_income else 0
    score += f4
    breakdown["cf_greater_than_net_income"] = bool(f4)
    
    # 若有前一期數據進行跨期比較
    if previous_metrics:
        prev_lt_debt = previous_metrics.get("long_term_debt", 0.0) or 0.0
        curr_lt_debt = current_metrics.get("long_term_debt", 0.0) or 0.0
        f5 = 1 if curr_lt_debt <= prev_lt_debt else 0
        score += f5
        breakdown["lower_leverage"] = bool(f5)
        
        curr_cr = current_metrics.get("current_ratio", 1.0) or 1.0
        prev_cr = previous_metrics.get("current_ratio", 1.0) or 1.0
        f6 = 1 if curr_cr >= prev_cr else 0
        score += f6
        breakdown["higher_liquidity"] = bool(f6)
        
        curr_shares = current_metrics.get("shares_outstanding", 1.0) or 1.0
        prev_shares = previous_metrics.get("shares_outstanding", 1.0) or 1.0
        f7 = 1 if curr_shares <= prev_shares * 1.01 else 0  # 容許 1% 誤差
        score += f7
        breakdown["no_share_dilution"] = bool(f7)
        
        curr_gm = current_metrics.get("gross_margin", 0.0) or 0.0
        prev_gm = previous_metrics.get("gross_margin", 0.0) or 0.0
        f8 = 1 if curr_gm >= prev_gm else 0
        score += f8
        breakdown["higher_gross_margin"] = bool(f8)
        
        curr_ato = current_metrics.get("asset_turnover", 0.0) or 0.0
        prev_ato = previous_metrics.get("asset_turnover", 0.0) or 0.0
        f9 = 1 if curr_ato >= prev_ato else 0
        score += f9
        breakdown["higher_asset_turnover"] = bool(f9)
    else:
        # 單期保守預設估計
        score += 3  # 給予基準分
        breakdown["comparison_mode"] = "single_period_estimated"
        
    assessment = (
        "Strong Fundamental Quality (8-9/9: 頂級財務實力)" if score >= 8 else
        "Moderate Quality (5-7/9: 財務穩健)" if score >= 5 else
        "Weak Quality (0-4/9: 財務體質欠佳)"
    )
    
    return {
        "f_score": score,
        "max_score": 9,
        "assessment": assessment,
        "breakdown": breakdown
    }
