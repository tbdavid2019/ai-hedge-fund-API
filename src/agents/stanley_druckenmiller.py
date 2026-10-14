from graph.state import AgentState, show_agent_reasoning
from tools.api import get_financial_metrics, get_market_cap, search_line_items, get_price_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
import json
from typing_extensions import Literal
from utils.progress import progress
from utils.llm import call_llm


class StanleyDruckenmillerSignal(BaseModel):
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float
    reasoning: str


def stanley_druckenmiller_agent(state: AgentState):
    """
    Analyzes stocks using Stanley Druckenmiller's macroeconomic, growth inflection,
    and asymmetric risk/reward investing principles.
    """
    data = state["data"]
    end_date = data["end_date"]
    tickers = data["tickers"]

    analysis_data = {}
    druckenmiller_analysis = {}

    for ticker in tickers:
        progress.update_status("stanley_druckenmiller_agent", ticker, "Fetching financial trajectory")
        metrics = get_financial_metrics(ticker, end_date, period="quarterly", limit=6)
        if not metrics:
            metrics = get_financial_metrics(ticker, end_date, period="annual", limit=5)

        progress.update_status("stanley_druckenmiller_agent", ticker, "Gathering fundamental line items")
        financial_line_items = search_line_items(
            ticker,
            [
                "revenue",
                "operating_margin",
                "net_income",
                "free_cash_flow",
                "debt_to_equity",
                "total_liabilities",
                "outstanding_shares"
            ],
            end_date,
            period="quarterly",
            limit=6
        )
        if not financial_line_items:
            financial_line_items = search_line_items(
                ticker,
                [
                    "revenue",
                    "operating_margin",
                    "net_income",
                    "free_cash_flow",
                    "debt_to_equity",
                    "total_liabilities",
                    "outstanding_shares"
                ],
                end_date,
                period="annual",
                limit=5
            )

        progress.update_status("stanley_druckenmiller_agent", ticker, "Getting market cap and price trend")
        market_cap = get_market_cap(ticker, end_date)

        # 1. Analyze fundamental inflections (rate-of-change, acceleration vs deceleration)
        inflection_analysis = analyze_inflections(metrics, financial_line_items)

        # 2. Analyze leverage and downside risk (prevent account blowups)
        risk_analysis = analyze_leverage_risk(financial_line_items)

        analysis_data[ticker] = {
            "inflection_analysis": inflection_analysis,
            "risk_analysis": risk_analysis,
            "market_cap": market_cap,
        }

        progress.update_status("stanley_druckenmiller_agent", ticker, "Generating Druckenmiller conviction")
        druckenmiller_output = generate_druckenmiller_output(
            ticker=ticker,
            analysis_data=analysis_data[ticker],
            model_name=state["metadata"]["model_name"],
            model_provider=state["metadata"]["model_provider"],
        )

        druckenmiller_analysis[ticker] = {
            "signal": druckenmiller_output.signal,
            "confidence": druckenmiller_output.confidence,
            "reasoning": druckenmiller_output.reasoning,
        }

        progress.update_status("stanley_druckenmiller_agent", ticker, "Done")

    message = HumanMessage(content=json.dumps(druckenmiller_analysis), name="stanley_druckenmiller_agent")

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(druckenmiller_analysis, "Stanley Druckenmiller Agent")

    state["data"]["analyst_signals"]["stanley_druckenmiller_agent"] = druckenmiller_analysis

    return {"messages": [message], "data": state["data"]}


def analyze_inflections(metrics: list, line_items: list) -> dict[str, any]:
    """
    Evaluates revenue, margin, and cash flow inflections (acceleration vs deceleration).
    """
    details = []
    acceleration_score = 0

    if not metrics and not line_items:
        return {"status": "insufficient_data", "details": ["Insufficient historical data to detect inflections."]}

    # Check metrics trend
    if metrics and len(metrics) >= 2:
        rev_growth_latest = getattr(metrics[0], "revenue_growth", None)
        rev_growth_prev = getattr(metrics[1], "revenue_growth", None)
        if rev_growth_latest is not None and rev_growth_prev is not None:
            if rev_growth_latest > rev_growth_prev:
                acceleration_score += 2
                details.append(f"Revenue growth accelerating from {rev_growth_prev:.1%} to {rev_growth_latest:.1%}.")
            else:
                acceleration_score -= 2
                details.append(f"Revenue growth decelerating from {rev_growth_prev:.1%} to {rev_growth_latest:.1%}.")

        op_margin_latest = getattr(metrics[0], "operating_margin", None)
        op_margin_prev = getattr(metrics[1], "operating_margin", None)
        if op_margin_latest is not None and op_margin_prev is not None:
            if op_margin_latest > op_margin_prev:
                acceleration_score += 1
                details.append(f"Operating margin expanding from {op_margin_prev:.1%} to {op_margin_latest:.1%}.")
            else:
                acceleration_score -= 1
                details.append(f"Operating margin contracting from {op_margin_prev:.1%} to {op_margin_latest:.1%}.")

    return {
        "acceleration_score": acceleration_score,
        "details": details,
        "trajectory": "accelerating" if acceleration_score > 0 else ("decelerating" if acceleration_score < 0 else "neutral")
    }


def analyze_leverage_risk(line_items: list) -> dict[str, any]:
    """
    Checks leverage and hidden blowup risks: deteriorating fundamentals + excessive debt.
    """
    details = []
    is_high_risk = False

    if line_items:
        # Check debt-to-equity or liabilities
        for item in line_items:
            dte = getattr(item, "debt_to_equity", None)
            if dte and dte > 3.0:
                is_high_risk = True
                details.append(f"Elevated debt-to-equity ratio of {dte:.2f}.")
                break

    return {
        "is_high_risk": is_high_risk,
        "details": details or ["Leverage profile within manageable limits."]
    }


def generate_druckenmiller_output(
    ticker: str,
    analysis_data: dict[str, any],
    model_name: str,
    model_provider: str,
) -> StanleyDruckenmillerSignal:
    """
    Generates investment decisions in the authentic style of Stanley Druckenmiller.
    """
    template = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are Stanley Druckenmiller, evaluating an equity investment opportunity.
You don't care what a business looked like three years ago — you care what the trajectory
looks like RIGHT NOW versus what the market already believes.
It's not whether you're right or wrong; it's how much money you make when you're right and how much
you lose when you're wrong. You only swing aggressively when the setup is asymmetric.

Work through your core read:
1. The Inflection: Scan the recent quarters against the older ones. Is revenue growth accelerating
   or decelerating? Are margins inflecting up or rolling over? Direction and rate-of-change (second derivative)
   matter far more than static accounting levels.
2. Earnings & Cash Flow Momentum: Is momentum building or fading across the most recent periods specifically?
3. What's Priced In: A rich valuation on accelerating numbers can still be a screaming buy; a cheap multiple
   on deteriorating fundamentals is a deadly value trap. Ask what the multiple says the market expects,
   and whether the fundamental inflection disagrees.
4. Asymmetric Risk/Reward: Go big only when the inflection and price line up. If the setup is merely average,
   the correct position is none (neutral).
5. Downside Protection: Deteriorating fundamentals plus heavy leverage is how accounts blow up.
   That combination is a strict short or a pass, never a hold.

Signal rules:
- bullish: Clear acceleration in recent trajectory that the market hasn't fully appreciated.
- bearish: Clear fundamental deterioration, margin rollover, or deteriorating numbers with leverage.
- neutral: No discernible inflection, or the trend and valuation are in complete alignment.

Confidence scale (0-100):
- 90-100: Unmistakable inflection with massive asymmetric setup.
- 70-89: Solid trend change / accelerating inflection.
- 40-69: Mixed or early signs.
- 10-39: No edge or murky signal."""
        ),
        (
            "human",
            """Based on the following inflection and fundamental data, create an investment signal as Stanley Druckenmiller would.

Analysis Data for {ticker}:
{analysis_data}

Return the trading signal in the following JSON format:
{{
  "signal": "bullish/bearish/neutral",
  "confidence": float (0-100),
  "reasoning": "string"
}}
"""
        )
    ])

    prompt = template.invoke({
        "analysis_data": json.dumps(analysis_data, indent=2),
        "ticker": ticker
    })

    def create_default_druckenmiller_signal():
        return StanleyDruckenmillerSignal(
            signal="neutral",
            confidence=0.0,
            reasoning="Default baseline: insufficient data for conclusive inflection assessment."
        )

    return call_llm(
        prompt=prompt,
        model_name=model_name,
        model_provider=model_provider,
        pydantic_model=StanleyDruckenmillerSignal,
        agent_name="stanley_druckenmiller_agent",
        default_factory=create_default_druckenmiller_signal,
    )
