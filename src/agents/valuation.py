from langchain_core.messages import HumanMessage
from graph.state import AgentState, show_agent_reasoning
from utils.progress import progress
import json

from tools.api import get_financial_metrics, get_market_cap, search_line_items, get_prices, prices_to_df
from src.quant.valuation import (
    calculate_dcf_sensitivity,
    calculate_altman_z_score,
    calculate_piotroski_f_score,
)


##### Valuation Agent #####
def valuation_agent(state: AgentState):
    """
    Performs institutional quantitative valuation analysis:
    1. DCF 5x5 Sensitivity Analysis Matrix (WACC vs Terminal Growth)
    2. Buffett Owner Earnings Intrinsic Valuation
    3. Altman Z-Score Bankruptcy / Financial Distress Risk
    4. Piotroski F-Score (0-9) Fundamental Improvement Metric
    """
    data = state["data"]
    end_date = data["end_date"]
    start_date = data["start_date"]
    tickers = data["tickers"]

    valuation_analysis = {}

    for ticker in tickers:
        progress.update_status("valuation_agent", ticker, "Fetching financial metrics and statements")

        financial_metrics = get_financial_metrics(
            ticker=ticker,
            end_date=end_date,
            period="ttm",
        )

        if not financial_metrics:
            progress.update_status("valuation_agent", ticker, "Failed: No financial metrics found")
            continue

        metrics = financial_metrics[0]
        prev_metrics = financial_metrics[1] if len(financial_metrics) > 1 else None

        progress.update_status("valuation_agent", ticker, "Gathering detailed financial statement items")
        financial_line_items = search_line_items(
            ticker=ticker,
            line_items=[
                "free_cash_flow",
                "net_income",
                "depreciation_and_amortization",
                "capital_expenditure",
                "working_capital",
                "total_assets",
                "total_liabilities",
                "retained_earnings",
                "operating_income",
                "total_revenue",
            ],
            end_date=end_date,
            period="ttm",
            limit=2,
        )

        current_item = financial_line_items[0] if financial_line_items else None
        prev_item = financial_line_items[1] if len(financial_line_items) > 1 else None

        # 獲取當前股價與市值
        market_cap = get_market_cap(ticker=ticker, end_date=end_date) or 1.0
        prices = get_prices(ticker=ticker, start_date=start_date, end_date=end_date)
        prices_df = prices_to_df(prices) if prices else None
        current_price = float(prices_df["close"].dropna().iloc[-1]) if (prices_df is not None and not prices_df.empty and "close" in prices_df.columns) else 100.0

        progress.update_status("valuation_agent", ticker, "Computing Owner Earnings & DCF Sensitivity Matrix")

        # 1. 計算營運資金變動與 Owner Earnings (巴菲特法)
        working_capital_change = 0.0
        if current_item and prev_item:
            curr_wc = getattr(current_item, "working_capital", None)
            prev_wc = getattr(prev_item, "working_capital", None)
            if curr_wc is not None and prev_wc is not None:
                working_capital_change = curr_wc - prev_wc

        net_income = getattr(current_item, "net_income", None) or getattr(metrics, "net_income", 0.0) or 0.0
        deprec = getattr(current_item, "depreciation_and_amortization", None) or 0.0
        capex = getattr(current_item, "capital_expenditure", None) or 0.0
        fcf = getattr(current_item, "free_cash_flow", None) or getattr(metrics, "free_cash_flow", 0.0) or (net_income + deprec - capex)

        owner_earnings_value = calculate_owner_earnings_value(
            net_income=net_income,
            depreciation=deprec,
            capex=capex,
            working_capital_change=working_capital_change,
            growth_rate=getattr(metrics, "earnings_growth", 0.05) or 0.05,
            required_return=0.15,
            margin_of_safety=0.25,
        )

        # 2. DCF 5x5 敏感度矩陣
        earnings_growth = getattr(metrics, "earnings_growth", 0.08) or 0.08
        safe_growth = max(-0.20, min(0.30, float(earnings_growth)))
        
        dcf_result = calculate_dcf_sensitivity(
            free_cash_flow=float(fcf),
            current_price=float(current_price),
            market_cap=float(market_cap),
            base_wacc=0.10,
            base_terminal_growth=0.025,
            forecast_growth=safe_growth,
        )

        progress.update_status("valuation_agent", ticker, "Computing Altman Z-Score & Piotroski F-Score")

        # 3. Altman Z-Score
        z_score_result = calculate_altman_z_score(
            working_capital=getattr(current_item, "working_capital", None),
            total_assets=getattr(current_item, "total_assets", None) or getattr(metrics, "total_assets", None),
            retained_earnings=getattr(current_item, "retained_earnings", None),
            ebit=getattr(current_item, "operating_income", None) or getattr(metrics, "operating_income", None),
            market_cap=market_cap,
            total_liabilities=getattr(current_item, "total_liabilities", None) or getattr(metrics, "total_liabilities", None),
            total_revenue=getattr(current_item, "total_revenue", None) or getattr(metrics, "total_revenue", None),
        )

        # 4. Piotroski F-Score
        current_metric_dict = {
            "net_income": net_income,
            "return_on_assets": getattr(metrics, "return_on_assets", 0.0),
            "operating_cash_flow": getattr(metrics, "operating_cash_flow", 0.0) or fcf,
            "current_ratio": getattr(metrics, "current_ratio", 1.0),
            "gross_margin": getattr(metrics, "gross_margin", 0.0),
            "debt_to_equity": getattr(metrics, "debt_to_equity", 0.0),
        }
        prev_metric_dict = {
            "current_ratio": getattr(prev_metrics, "current_ratio", 1.0) if prev_metrics else 1.0,
            "gross_margin": getattr(prev_metrics, "gross_margin", 0.0) if prev_metrics else 0.0,
            "debt_to_equity": getattr(prev_metrics, "debt_to_equity", 0.0) if prev_metrics else 0.0,
        } if prev_metrics else None

        f_score_result = calculate_piotroski_f_score(current_metric_dict, prev_metric_dict)

        # 綜合多空信號與信心度計算
        dcf_gap = (dcf_result.get("fair_value_median", current_price) - current_price) / current_price if current_price > 0 else 0.0
        owner_gap = (owner_earnings_value - market_cap) / market_cap if market_cap > 0 else 0.0
        composite_gap = (dcf_gap + owner_gap) / 2.0 if owner_earnings_value > 0 else dcf_gap

        if composite_gap > 0.15:
            signal = "bullish"
        elif composite_gap < -0.15:
            signal = "bearish"
        else:
            signal = "neutral"

        # 若 Z-Score 處於破產困境區，強行降級信號保護本金
        if z_score_result.get("risk_level") == "High":
            if signal == "bullish":
                signal = "neutral"
            elif signal == "neutral":
                signal = "bearish"

        confidence = round(min(100.0, max(20.0, abs(composite_gap) * 100.0)), 2)

        valuation_analysis[ticker] = {
            "signal": signal,
            "confidence": confidence,
            "quant_valuation": {
                "dcf_fair_value_median": dcf_result.get("fair_value_median"),
                "dcf_fair_value_range": dcf_result.get("fair_value_range"),
                "margin_of_safety_pct": dcf_result.get("margin_of_safety_pct"),
                "dcf_valuation_status": dcf_result.get("valuation_status"),
                "altman_z_score": z_score_result.get("z_score"),
                "altman_zone": z_score_result.get("zone"),
                "altman_risk_level": z_score_result.get("risk_level"),
                "piotroski_f_score": f_score_result.get("f_score"),
                "piotroski_assessment": f_score_result.get("assessment"),
            },
            "reasoning": {
                "dcf_analysis": {
                    "signal": "bullish" if dcf_gap > 0.15 else "bearish" if dcf_gap < -0.15 else "neutral",
                    "details": f"DCF Median Fair Value: ${dcf_result.get('fair_value_median', 0):,.2f} vs Current Price: ${current_price:,.2f} (Margin of Safety: {dcf_result.get('margin_of_safety_pct', 0)}%)",
                },
                "owner_earnings_analysis": {
                    "signal": "bullish" if owner_gap > 0.15 else "bearish" if owner_gap < -0.15 else "neutral",
                    "details": f"Owner Earnings Intrinsic Value: ${owner_earnings_value:,.2f} vs Market Cap: ${market_cap:,.2f}",
                },
                "financial_health_audit": {
                    "altman_z_score": f"{z_score_result.get('z_score')} ({z_score_result.get('zone')})",
                    "piotroski_f_score": f"{f_score_result.get('f_score')}/9 ({f_score_result.get('assessment')})",
                },
            },
        }

        progress.update_status("valuation_agent", ticker, "Done")

    message = HumanMessage(
        content=json.dumps(valuation_analysis),
        name="valuation_agent",
    )

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(valuation_analysis, "Valuation Analysis Agent")

    state["data"]["analyst_signals"]["valuation_agent"] = valuation_analysis

    return {
        "messages": [message],
        "data": data,
    }


def calculate_owner_earnings_value(
    net_income: float,
    depreciation: float,
    capex: float,
    working_capital_change: float,
    growth_rate: float = 0.05,
    required_return: float = 0.15,
    margin_of_safety: float = 0.25,
    num_years: int = 5,
) -> float:
    """Calculates intrinsic value using Buffett's Owner Earnings method."""
    if not all([isinstance(x, (int, float)) for x in [net_income, depreciation, capex, working_capital_change]]):
        return 0.0

    owner_earnings = net_income + depreciation - capex - working_capital_change
    if owner_earnings <= 0:
        return 0.0

    growth_rate = growth_rate if growth_rate is not None else 0.05
    future_values = []
    for year in range(1, num_years + 1):
        future_value = owner_earnings * (1 + growth_rate) ** year
        discounted_value = future_value / (1 + required_return) ** year
        future_values.append(discounted_value)

    terminal_growth = min(growth_rate, 0.03)
    terminal_value = (future_values[-1] * (1 + terminal_growth)) / (required_return - terminal_growth)
    terminal_value_discounted = terminal_value / (1 + required_return) ** num_years

    intrinsic_value = sum(future_values) + terminal_value_discounted
    return intrinsic_value * (1 - margin_of_safety)
