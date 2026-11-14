"""Standard-library-only contracts shared by the Arena CLI and API."""

import math
from datetime import datetime, timezone

OUTCOMES = {"bearish", "neutral", "bullish"}
# Pilot assets only. Proxies supply research evidence, never settlement prices.
ASSET_POLICIES = {
    "ES": {"ticker": "SPY", "analysts": ["technical_analyst", "sentiment_analyst"],
           "proxy_limitations": "SPY trades equity hours; ES is a frozen futures contract."},
    "GC": {"ticker": "GLD", "analysts": ["technical_analyst", "sentiment_analyst"],
           "proxy_limitations": "GLD is a gold ETF, not the frozen GC delivery month."},
}
SIGNAL_KEYS = {
    "technical_analyst": "technical_analyst_agent",
    "fundamentals_analyst": "fundamentals_agent",
    "sentiment_analyst": "sentiment_agent",
    "valuation_analyst": "valuation_agent",
    "wsb": "wsb_agent",
}


def utc_now():
    return datetime.now(timezone.utc)


def parse_utc(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Missing UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # HA's legacy ISO timestamps omit the UTC suffix.
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def validate_probabilities(value):
    if not isinstance(value, dict) or set(value) != OUTCOMES:
        raise ValueError("probabilities must have exactly bearish/neutral/bullish")
    result = {key: finite_number(value[key], key) for key in sorted(OUTCOMES)}
    if any(v < 0 or v > 1 for v in result.values()) or abs(sum(result.values()) - 1) > 1e-6:
        raise ValueError("probabilities must be in [0,1] and sum to 1")
    return result


def validate_challenge(challenge, now=None):
    if not isinstance(challenge, dict):
        raise ValueError("challenge must be an object")
    if challenge.get("asset") not in ASSET_POLICIES:
        raise ValueError("Asset is outside the ES/GC pilot whitelist")
    if challenge.get("challenge_type") not in {"daily", "btc_session", "flash"}:
        raise ValueError("Unsupported challenge type")
    if challenge.get("status") != "open" or parse_utc(challenge.get("deadline")) <= (now or utc_now()):
        raise ValueError("Challenge is not open before its deadline")
    if parse_utc(challenge.get("resolve_at")) < parse_utc(challenge["deadline"]):
        raise ValueError("Invalid resolution window")
    for field in ("id", "question", "contract_symbol", "resolution_criteria"):
        if not isinstance(challenge.get(field), str) or not challenge[field].strip():
            raise ValueError(f"Missing {field}")
    if challenge.get("open_price_confirmed") is not True or challenge.get("baseline_status") != "confirmed":
        raise ValueError("Opening baseline is not confirmed")
    if finite_number(challenge.get("open_price"), "open_price") <= 0:
        raise ValueError("Invalid opening price")
    if finite_number(challenge.get("dead_zone_pct"), "dead_zone_pct") < 0:
        raise ValueError("Invalid dead-zone threshold")
    # Legacy daily discovery has no per-question schema; these types have the
    # documented ternary predict contract. Explicit schemas must agree with it.
    schema = challenge.get("prediction_schema")
    if schema is None and challenge.get("challenge_type") != "daily":
        raise ValueError("Non-daily challenges require an explicit supported prediction_schema")
    if schema is not None:
        if not isinstance(schema, dict):
            raise ValueError("Unsupported prediction_schema")
        categories = schema.get("outcomes", schema.get("categories", schema.get("directions")))
        encoding = schema.get("input_encoding", schema.get("type"))
        if not isinstance(categories, list) or not all(isinstance(c, str) for c in categories) or set(categories) != OUTCOMES:
            raise ValueError("prediction_schema must explicitly support the three directions")
        if encoding not in {"categorical_probabilities", "categorical", "probabilities"}:
            raise ValueError("Unsupported prediction_schema encoding")
    return ASSET_POLICIES[challenge["asset"]]


def validate_context(context, challenge, now=None):
    if not isinstance(context, dict) or context.get("challenge_id") != challenge["id"]:
        raise ValueError("Missing challenge-bound market context")
    if context.get("prediction_ready") is not True or context.get("prediction_blockers"):
        raise ValueError("Market context is not prediction-ready")
    identity = context.get("contract_identity") or {}
    if identity.get("symbol", identity.get("contract_symbol")) != challenge["contract_symbol"]:
        raise ValueError("Market evidence does not match the frozen contract")
    baseline = context.get("baseline") or {}
    if baseline.get("status") != "confirmed" or baseline.get("price") != challenge["open_price"]:
        raise ValueError("Market context baseline differs from the challenge")
    quote = context.get("quote") or {}
    if quote.get("contract_symbol") != challenge["contract_symbol"] or quote.get("is_delayed") is not False:
        raise ValueError("Quote is delayed or belongs to another contract")
    # as_of is the response time, not necessarily the quote observation time.
    observed = quote.get("as_of") or quote.get("timestamp") or quote.get("observed_at")
    age = ((now or utc_now()) - parse_utc(observed)).total_seconds()
    if age < -60 or age > 900:
        raise ValueError("Market quote is stale or from the future (15-minute maximum age)")
    price = quote.get("price", quote.get("current_price"))
    if finite_number(price, "quote price") <= 0:
        raise ValueError("Missing current quote")
    return context


def analyst_evidence(result, ticker, analysts):
    """Normalize known 0–100 signal confidence without inventing missing signals."""
    if not isinstance(result, dict) or result.get("error"):
        raise ValueError("Analysis failed")
    signals = result.get("analyst_signals") or {}
    evidence = {}
    for analyst in analysts:
        key = SIGNAL_KEYS.get(analyst, analyst if analyst.endswith("_agent") else analyst + "_agent")
        signal = (signals.get(key) or {}).get(ticker)
        if not isinstance(signal, dict) or signal.get("signal") not in OUTCOMES or not isinstance(signal.get("reasoning"), str) or not signal["reasoning"].strip():
            raise ValueError(f"Missing usable signal for {analyst}")
        confidence = finite_number(signal.get("confidence"), "analyst confidence")
        coverage = signal.get("data_coverage") or {}
        observed_neutral_news = (
            analyst == "sentiment_analyst" and signal["signal"] == "neutral"
            and isinstance(coverage.get("news_count"), int) and coverage["news_count"] > 0
        )
        if not 0 <= confidence <= 100 or (confidence == 0 and not observed_neutral_news):
            raise ValueError(f"Invalid or failed signal for {analyst}")
        evidence[analyst] = dict(signal, confidence=confidence / 100)
    return evidence
