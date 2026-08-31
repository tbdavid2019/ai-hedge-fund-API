from langchain_core.messages import HumanMessage
from graph.state import AgentState, show_agent_reasoning
from utils.progress import progress
from tools.api import get_prices, prices_to_df
from src.quant.risk import (
    calculate_var_cvar,
    calculate_volatility_metrics,
    calculate_risk_adjusted_position_size,
)
import json
import math
import pandas as pd


##### Risk Management Agent #####
def risk_management_agent(state: AgentState):
    """
    Controls position sizing based on institutional quantitative risk models:
    - 95%/99% VaR (Value at Risk) & CVaR (Expected Shortfall)
    - Realized Volatility Regimes & Volatility Parity Scaling
    - 2% Portfolio Risk Budget Constraints
    """
    portfolio = state["data"]["portfolio"]
    data = state["data"]
    tickers = data["tickers"]

    # Initialize risk analysis for each ticker
    risk_analysis = {}
    current_prices = {}

    # 根據標的物數量動態計算每個標的物的投資上限比例
    num_tickers = len(tickers)
    if num_tickers == 1:
        position_limit_ratio = 1.0  # 100%
    elif num_tickers == 2:
        position_limit_ratio = 0.5  # 50%
    elif num_tickers == 3:
        position_limit_ratio = 0.33  # 33%
    elif num_tickers == 4:
        position_limit_ratio = 0.25  # 25%
    else:
        position_limit_ratio = 0.20  # 20% (5個以上)

    for ticker in tickers:
        progress.update_status("risk_management_agent", ticker, "Analyzing price and volatility data")

        prices = get_prices(
            ticker=ticker,
            start_date=data["start_date"],
            end_date=data["end_date"],
        )

        if not prices:
            progress.update_status("risk_management_agent", ticker, "Failed: No price data found")
            continue

        prices_df = prices_to_df(prices)
        if prices_df.empty or "close" not in prices_df.columns:
            progress.update_status("risk_management_agent", ticker, "Failed: No price data found")
            continue

        close_series = prices_df["close"].dropna()
        if close_series.empty:
            progress.update_status("risk_management_agent", ticker, "Failed: No valid close price found")
            continue

        current_price = float(close_series.iloc[-1])
        if pd.isna(current_price) or current_price <= 0:
            progress.update_status("risk_management_agent", ticker, "Failed: Invalid price found")
            continue

        progress.update_status("risk_management_agent", ticker, "Calculating quantitative risk metrics (VaR/CVaR)")

        current_prices[ticker] = current_price
        current_position_value = float(portfolio.get("cost_basis", {}).get(ticker, 0))
        available_cash = float(portfolio.get("cash", 0))
        total_portfolio_value = available_cash + sum(
            portfolio.get("cost_basis", {}).get(t, 0) for t in portfolio.get("cost_basis", {})
        )

        # 1. 計算量化風險指標 (VaR / CVaR / MDD / Volatility)
        returns = close_series.pct_change().dropna()
        var_cvar_metrics = calculate_var_cvar(returns)
        vol_metrics = calculate_volatility_metrics(prices_df)

        cvar_95 = var_cvar_metrics.get("cvar_95", 0.05)
        ann_vol = var_cvar_metrics.get("volatility_annualized", 0.25)

        # 2. 動態風險預算下單上限 (Risk-Adjusted Position Sizing)
        sizing_result = calculate_risk_adjusted_position_size(
            total_portfolio_value=total_portfolio_value,
            available_cash=available_cash,
            current_price=current_price,
            cvar_95=cvar_95,
            annualized_vol=ann_vol,
            max_risk_budget_ratio=0.02,  # 2% 最大容許虧損
            base_position_limit_ratio=position_limit_ratio,
        )

        recommended_limit = sizing_result["recommended_position_dollars"]
        remaining_position_limit = max(0.0, recommended_limit - current_position_value)
        max_position_size = min(remaining_position_limit, available_cash)

        risk_analysis[ticker] = {
            "remaining_position_limit": float(max_position_size),
            "current_price": float(current_price),
            "recommended_shares": int(max_position_size // current_price) if current_price > 0 else 0,
            "quant_risk": {
                "var_95": var_cvar_metrics.get("var_95"),
                "cvar_95": var_cvar_metrics.get("cvar_95"),
                "var_99": var_cvar_metrics.get("var_99"),
                "cvar_99": var_cvar_metrics.get("cvar_99"),
                "max_drawdown": var_cvar_metrics.get("max_drawdown"),
                "volatility_annualized": ann_vol,
                "volatility_regime": vol_metrics.get("current_regime"),
                "binding_constraint": sizing_result.get("binding_constraint"),
                "vol_scaling_factor": sizing_result.get("vol_scaling_factor"),
            },
            "reasoning": {
                "portfolio_value": float(total_portfolio_value),
                "current_position": float(current_position_value),
                "position_limit": float(recommended_limit),
                "remaining_limit": float(remaining_position_limit),
                "available_cash": float(available_cash),
                "cvar_95_expected_loss_pct": round(cvar_95 * 100, 2),
                "volatility_annualized_pct": round(ann_vol * 100, 2),
                "risk_regime": vol_metrics.get("current_regime"),
                "risk_constraint": sizing_result.get("binding_constraint"),
            },
        }

        progress.update_status("risk_management_agent", ticker, "Done")

    message = HumanMessage(
        content=json.dumps(risk_analysis),
        name="risk_management_agent",
    )

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(risk_analysis, "Risk Management Agent")

    # Add the signal to the analyst_signals list
    state["data"]["analyst_signals"]["risk_management_agent"] = risk_analysis

    return {
        "messages": state["messages"] + [message],
        "data": data,
    }
