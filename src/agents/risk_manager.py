from langchain_core.messages import HumanMessage
from graph.state import AgentState, show_agent_reasoning
from utils.progress import progress
from tools.api import get_prices, prices_to_df
import json


##### Risk Management Agent #####
def risk_management_agent(state: AgentState):
    """Controls position sizing based on real-world risk factors for multiple tickers."""
    portfolio = state["data"]["portfolio"]
    data = state["data"]
    tickers = data["tickers"]

    # Initialize risk analysis for each ticker
    risk_analysis = {}
    current_prices = {}  # Store prices here to avoid redundant API calls
    
    # 根據標的物數量動態計算每個標的物的投資上限比例
    # 1個標的 = 100%, 2個 = 50%, 3個 = 33%, 4個 = 25%, 5+個 = 20%
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
        progress.update_status("risk_management_agent", ticker, "Analyzing price data")

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

        progress.update_status("risk_management_agent", ticker, "Calculating position limits")

        # Calculate portfolio value
        current_prices[ticker] = current_price  # Store the current price

        # Calculate current position value for this ticker
        current_position_value = portfolio.get("cost_basis", {}).get(ticker, 0)

        # Calculate total portfolio value using stored prices
        total_portfolio_value = portfolio.get("cash", 0) + sum(portfolio.get("cost_basis", {}).get(t, 0) for t in portfolio.get("cost_basis", {}))

        # 根據標的物數量動態計算投資上限
        # Dynamic position limit based on number of tickers
        position_limit = total_portfolio_value * position_limit_ratio

        # For existing positions, subtract current position value from limit
        remaining_position_limit = position_limit - current_position_value

        # Ensure we don't exceed available cash
        max_position_size = min(remaining_position_limit, portfolio.get("cash", 0))

        risk_analysis[ticker] = {
            "remaining_position_limit": float(max_position_size),
            "current_price": float(current_price),
            "reasoning": {
                "portfolio_value": float(total_portfolio_value),
                "current_position": float(current_position_value),
                "position_limit": float(position_limit),
                "remaining_limit": float(remaining_position_limit),
                "available_cash": float(portfolio.get("cash", 0)),
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
