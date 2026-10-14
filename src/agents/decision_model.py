import json
import logging
from langchain_core.messages import HumanMessage
from graph.state import AgentState, show_agent_reasoning
from tools.api import get_prices, get_financial_metrics
from utils.progress import progress
from src.quant.direction_forecast import forecast_price_direction
from src.quant.pead import calculate_pead_signal

logger = logging.getLogger(__name__)


def decision_model_agent(state: AgentState):
    """
    Independent Quantitative Algorithmic Decision Model Agent.
    Powered by TypeSafe JEV / Clef-Flash SystemOne fast structured evaluation,
    T+1~T+3 directional probability forecasting, and PEAD earnings drift signals.

    High Availability Guarantee:
    If all external LLM/Jev endpoints fail, it automatically degrades to a
    quantitative momentum and statistical distribution model without breaking the hedge fund.
    """
    data = state["data"]
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    tickers = data.get("tickers", [])

    decision_analysis = {}

    for ticker in tickers:
        progress.update_status("decision_model_agent", ticker, "Fetching market price series")

        try:
            # 1. Fetch historical prices
            prices = get_prices(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
            )

            # 2. Run T+1 to T+3 directional forecast (with automatic SystemOne multi-tier failover & momentum baseline)
            progress.update_status("decision_model_agent", ticker, "Computing short-term directional probabilities")
            price_dicts = []
            if prices:
                for p in prices:
                    if isinstance(p, dict):
                        price_dicts.append(p)
                    elif hasattr(p, "model_dump"):
                        price_dicts.append(p.model_dump())
                    elif hasattr(p, "dict"):
                        price_dicts.append(p.dict())
                    elif hasattr(p, "close"):
                        price_dicts.append({"close": getattr(p, "close")})

            forecast_res = forecast_price_direction(
                ticker=ticker,
                recent_prices=price_dicts,
                days=3
            )

            signal = forecast_res.get("signal", "neutral")
            confidence = float(forecast_res.get("confidence", 50.0))
            probabilities = forecast_res.get("probabilities", {"bullish": 0.33, "neutral": 0.34, "bearish": 0.33})
            forecast_cards = forecast_res.get("forecasts", [])
            base_reasoning = forecast_res.get("reasoning", "")

            # 3. Incorporate PEAD if available
            progress.update_status("decision_model_agent", ticker, "Evaluating earnings drift (PEAD)")
            pead_notes = ""
            try:
                metrics = get_financial_metrics(ticker=ticker, end_date=end_date, period="quarterly", limit=4)
                if metrics:
                    earnings_history = [
                        m.model_dump() if hasattr(m, "model_dump") else (m.dict() if hasattr(m, "dict") else {})
                        for m in metrics
                    ]
                    pead_res = calculate_pead_signal(ticker=ticker, earnings_history=earnings_history, as_of_date=end_date)
                    if pead_res.get("signal") != "neutral":
                        pead_notes = f" | PEAD Surprise Conviction: {pead_res.get('conviction', 0.0):+.2f} ({pead_res.get('reasoning', '')[:100]})"
            except Exception as pead_err:
                logger.debug(f"[decision_model] PEAD check skipped: {pead_err}")

            prob_str = f"Probabilities: Bullish {probabilities.get('bullish', 0.33):.1%}, Neutral {probabilities.get('neutral', 0.34):.1%}, Bearish {probabilities.get('bearish', 0.33):.1%}"
            final_reasoning = f"{base_reasoning}\n[{prob_str}]{pead_notes}".strip()

            decision_analysis[ticker] = {
                "signal": signal,
                "confidence": round(confidence, 2),
                "probabilities": probabilities,
                "forecasts": forecast_cards,
                "reasoning": final_reasoning,
            }
            progress.update_status("decision_model_agent", ticker, "Done")

        except Exception as exc:
            # High-availability guarantee: Never crash the workflow if decision model fails
            logger.warning(f"[decision_model_agent] Non-blocking error for {ticker}: {exc}. Applying neutral fallback.")
            decision_analysis[ticker] = {
                "signal": "neutral",
                "confidence": 50.0,
                "probabilities": {"bullish": 0.33, "neutral": 0.34, "bearish": 0.33},
                "forecasts": [],
                "reasoning": f"Algorithmic decision model active in safe-mode fallback: {exc}",
            }
            progress.update_status("decision_model_agent", ticker, "Fallback complete")

    message = HumanMessage(
        content=json.dumps(decision_analysis),
        name="decision_model_agent"
    )

    if state.get("metadata", {}).get("show_reasoning"):
        show_agent_reasoning(decision_analysis, "JEV Decision Model Agent")

    state["data"]["analyst_signals"]["decision_model_agent"] = decision_analysis
    state["data"]["analyst_signals"]["decision_model"] = decision_analysis

    return {"messages": [message], "data": state["data"]}
