"""
PEAD (Post-Earnings-Announcement Drift) Quantitative Alpha Model
Forms systematic conviction based on earnings surprise:
- Bullish drift after an EPS BEAT
- Bearish drift after an EPS MISS
Strictly Point-in-Time: only announcements on or before `as_of_date` qualify.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import math


def calculate_pead_signal(
    ticker: str,
    earnings_history: List[Dict[str, Any]],
    as_of_date: str,
    signal_window_days: int = 45,
    min_surprise_threshold: float = 0.02,  # 2% surprise threshold
) -> Dict[str, Any]:
    """
    Evaluates Post-Earnings Announcement Drift (PEAD):
    - earnings_history: list of dicts with keys:
        'date' or 'filing_date' (YYYY-MM-DD),
        'eps_actual' (float),
        'eps_estimate' (float, optional),
        'surprise_pct' (float, optional),
        'surprise_direction' ('BEAT' | 'MISS' | 'IN_LINE', optional)
    - as_of_date: point-in-time cutoff date (YYYY-MM-DD)
    - signal_window_days: maximum age of announcement to generate drift conviction
    """
    if not earnings_history:
        return {
            "ticker": ticker,
            "signal": "neutral",
            "conviction": 0.0,
            "confidence": 50.0,
            "reasoning": "No historical earnings reports available for PEAD evaluation."
        }

    try:
        as_of_dt = datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    except Exception:
        as_of_dt = datetime.now()

    # Point-in-time filtering: announcements strictly <= as_of_date
    past_earnings = []
    for report in earnings_history:
        report_date_str = report.get("filing_date") or report.get("date") or report.get("report_date")
        if not report_date_str:
            continue
        try:
            report_dt = datetime.strptime(str(report_date_str)[:10], "%Y-%m-%d")
            if report_dt <= as_of_dt:
                past_earnings.append((report_dt, report))
        except Exception:
            continue

    if not past_earnings:
        return {
            "ticker": ticker,
            "signal": "neutral",
            "conviction": 0.0,
            "confidence": 50.0,
            "reasoning": f"No earnings announcements found on or before {as_of_date}."
        }

    # Sort descending to find most recent announcement
    past_earnings.sort(key=lambda x: x[0], reverse=True)
    latest_dt, latest_report = past_earnings[0]
    days_elapsed = (as_of_dt - latest_dt).days

    if days_elapsed > signal_window_days:
        return {
            "ticker": ticker,
            "signal": "neutral",
            "conviction": 0.0,
            "confidence": 50.0,
            "days_elapsed": days_elapsed,
            "reasoning": f"Latest earnings announcement was {days_elapsed} days ago, outside the {signal_window_days}-day PEAD drift window."
        }

    # Evaluate earnings surprise (preserve exact zero values)
    eps_actual = latest_report.get("eps_actual") if latest_report.get("eps_actual") is not None else latest_report.get("actual")
    eps_estimate = latest_report.get("eps_estimate") if latest_report.get("eps_estimate") is not None else latest_report.get("estimate")
    surprise_pct = latest_report.get("surprise_pct")

    if surprise_pct is None and eps_actual is not None and eps_estimate is not None:
        if abs(eps_estimate) > 1e-4:
            surprise_pct = (eps_actual - eps_estimate) / abs(eps_estimate)
        else:
            surprise_pct = 1.0 if eps_actual > 0 else (-1.0 if eps_actual < 0 else 0.0)

    # Time-decay factor: drift conviction is highest immediately after announcement and decays linearly
    decay_factor = max(0.1, 1.0 - (days_elapsed / signal_window_days))

    if surprise_pct is not None:
        if surprise_pct >= min_surprise_threshold:
            signal = "bullish"
            magnitude = min(1.0, abs(surprise_pct) * 5.0)
            conviction = round(magnitude * decay_factor, 3)
            confidence = round(50.0 + conviction * 40.0, 2)
            reasoning = (
                f"EPS BEAT: Earnings surprised by {surprise_pct:+.1%} {days_elapsed} days ago. "
                f"Positive PEAD drift expected (conviction: {conviction:+.2f})."
            )
        elif surprise_pct <= -min_surprise_threshold:
            signal = "bearish"
            magnitude = min(1.0, abs(surprise_pct) * 5.0)
            conviction = round(-magnitude * decay_factor, 3)
            confidence = round(50.0 + abs(conviction) * 40.0, 2)
            reasoning = (
                f"EPS MISS: Earnings missed by {surprise_pct:+.1%} {days_elapsed} days ago. "
                f"Negative PEAD drift expected (conviction: {conviction:+.2f})."
            )
        else:
            signal = "neutral"
            conviction = 0.0
            confidence = 50.0
            reasoning = f"Earnings met expectations within +/-{min_surprise_threshold:.1%}; no significant PEAD drift."
    else:
        # Fallback to surprise_direction tag
        direction_tag = str(latest_report.get("surprise_direction", "")).upper()
        if "BEAT" in direction_tag:
            signal = "bullish"
            conviction = round(0.5 * decay_factor, 3)
            confidence = 65.0
            reasoning = f"EPS BEAT announced {days_elapsed} days ago; positive PEAD drift expected."
        elif "MISS" in direction_tag:
            signal = "bearish"
            conviction = round(-0.5 * decay_factor, 3)
            confidence = 65.0
            reasoning = f"EPS MISS announced {days_elapsed} days ago; negative PEAD drift expected."
        else:
            signal = "neutral"
            conviction = 0.0
            confidence = 50.0
            reasoning = f"Earnings announcement {days_elapsed} days ago had no clear surprise direction."

    return {
        "ticker": ticker,
        "signal": signal,
        "conviction": conviction,
        "confidence": confidence,
        "days_elapsed": days_elapsed,
        "surprise_pct": round(surprise_pct, 4) if surprise_pct is not None else None,
        "reasoning": reasoning
    }
