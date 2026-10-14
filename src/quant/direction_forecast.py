"""
T+1 to T+3 Short-Term Directional Probability Forecaster
Inspired by sosopop/jev_stock: forecasts short-horizon price direction (up/flat/down)
using structured price action, benchmark relative performance, and SystemOne fast evaluation.
"""

from typing import Dict, Any, List, Optional
import math
import logging

try:
    from tools.jev_client import call_systemone_with_failover
except ImportError:
    from src.tools.jev_client import call_systemone_with_failover

logger = logging.getLogger(__name__)


def forecast_price_direction(
    ticker: str,
    recent_prices: List[Dict[str, Any]],
    benchmark_returns: Optional[List[float]] = None,
    flat_threshold: float = 0.003,
    days: int = 3,
) -> Dict[str, Any]:
    """
    Forecasts short-term price direction for T+1, T+2, T+3:
    - up: return > +0.3%
    - flat: return between -0.3% and +0.3%
    - down: return < -0.3%

    Returns calibrated probability distribution across up, flat, down and overall direction.
    """
    if not recent_prices or len(recent_prices) < 5:
        return {
            "ticker": ticker,
            "signal": "neutral",
            "confidence": 50.0,
            "probabilities": {"bullish": 0.33, "neutral": 0.34, "bearish": 0.33},
            "forecasts": [],
            "reasoning": "Insufficient price history for short-term directional forecast."
        }

    # Extract price trajectory
    closes = [p.get("close") for p in recent_prices if p.get("close") is not None]
    if len(closes) < 3:
        return {
            "ticker": ticker,
            "signal": "neutral",
            "confidence": 50.0,
            "probabilities": {"bullish": 0.33, "neutral": 0.34, "bearish": 0.33},
            "forecasts": [],
            "reasoning": "Missing close prices."
        }

    latest_close = closes[-1]
    prev_close = closes[-2]
    day_return = (latest_close - prev_close) / prev_close if prev_close else 0.0
    five_day_return = (latest_close - closes[-5]) / closes[-5] if len(closes) >= 5 and closes[-5] else day_return

    # Build compact structured market state
    market_snapshot = (
        f"Ticker: {ticker}\n"
        f"Latest Close: {latest_close:.2f}\n"
        f"1-Day Return: {day_return:+.2%}\n"
        f"5-Day Return: {five_day_return:+.2%}\n"
    )
    if benchmark_returns and len(benchmark_returns) > 0:
        market_snapshot += f"Benchmark Recent Return: {benchmark_returns[-1]:+.2%}\n"

    system_prompt = (
        f"You are a short-term quantitative price direction forecaster for {ticker}. "
        f"Evaluate the structured market data over a {days}-day trading horizon. "
        f"Define 'bullish/up' as expected return > +{flat_threshold:.1%}, "
        f"'bearish/down' as expected return < -{flat_threshold:.1%}, "
        f"and 'neutral/flat' as return within +/-{flat_threshold:.1%}."
    )

    try:
        res = call_systemone_with_failover(
            system_prompt=system_prompt,
            user_prompt=market_snapshot,
            model_name="clef-flash",
            timeout=8.0,
            include_bilingual=True
        )

        direction = res.get("signal", "neutral")
        confidence = float(res.get("confidence", 50.0))
        probabilities = res.get("probabilities", {})

        # Build day-by-day forecast cards
        forecasts = []
        for d in range(1, min(days + 1, 4)):
            forecasts.append({
                "trading_day_offset": d,
                "prediction": direction,
                "probabilities": probabilities,
                "confidence": round(confidence / 100.0, 3)
            })

        return {
            "ticker": ticker,
            "signal": direction,
            "confidence": confidence,
            "probabilities": probabilities,
            "forecasts": forecasts,
            "reasoning": res.get("reasoning", "")
        }

    except Exception as e:
        logger.warning(f"[DirectionForecast] SystemOne call failed: {e}. Using momentum baseline.")
        # Quantitative statistical fallback
        if day_return > flat_threshold:
            dir_str = "bullish"
            conf = min(85.0, 50.0 + abs(day_return) * 500)
            probs = {"bullish": 0.60, "neutral": 0.25, "bearish": 0.15}
        elif day_return < -flat_threshold:
            dir_str = "bearish"
            conf = min(85.0, 50.0 + abs(day_return) * 500)
            probs = {"bullish": 0.15, "neutral": 0.25, "bearish": 0.60}
        else:
            dir_str = "neutral"
            conf = 50.0
            probs = {"bullish": 0.30, "neutral": 0.40, "bearish": 0.30}

        return {
            "ticker": ticker,
            "signal": dir_str,
            "confidence": round(conf, 2),
            "probabilities": probs,
            "forecasts": [{"trading_day_offset": 1, "prediction": dir_str, "probabilities": probs, "confidence": conf / 100.0}],
            "reasoning": f"Quantitative momentum fallback: 1-day return is {day_return:+.2%}."
        }
