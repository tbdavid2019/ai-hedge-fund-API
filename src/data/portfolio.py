"""Validation and point-in-time normalization for externally supplied portfolios."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any

import yfinance as yf
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class PortfolioPositionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    quantity: float
    average_entry_price: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("must be a three-letter ISO currency code")
        return normalized

    @field_validator("quantity", "average_entry_price")
    @classmethod
    def require_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be a finite number")
        return value


class PortfolioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    cash: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    positions: list[PortfolioPositionInput]

    @field_validator("cash")
    @classmethod
    def require_finite_cash(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be a finite number")
        return value

    @field_validator("as_of")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except (TypeError, ValueError) as exc:
            raise ValueError("must be an ISO date (YYYY-MM-DD)") from exc

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("must be a three-letter ISO currency code")
        return normalized


def _fetch_fx_pair(pair: str, as_of: str) -> float | None:
    start = datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=7)
    end = datetime.strptime(as_of, "%Y-%m-%d")
    if end <= start:
        end = start + timedelta(days=1)
    history = yf.Ticker(pair).history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), auto_adjust=False)
    if history is None or history.empty or "Close" not in history:
        return None
    value = float(history["Close"].dropna().iloc[-1])
    return value if math.isfinite(value) and value > 0 else None


def get_point_in_time_fx_rate(source_currency: str, target_currency: str, as_of: str) -> float | None:
    """Return target units per source unit using a daily Yahoo FX close no later than as_of."""
    source = source_currency.upper()
    target = target_currency.upper()
    if source == target:
        return 1.0
    direct = _fetch_fx_pair(f"{source}{target}=X", as_of)
    if direct:
        return direct
    inverse = _fetch_fx_pair(f"{target}{source}=X", as_of)
    return 1.0 / inverse if inverse else None


def currency_for_ticker(ticker: str) -> str:
    symbol = ticker.upper()
    suffix_currencies = {
        ".TW": "TWD", ".TWO": "TWD", ".HK": "HKD", ".T": "JPY",
        ".SS": "CNY", ".SZ": "CNY", ".L": "GBP", ".PA": "EUR",
        ".AS": "EUR", ".BR": "EUR", ".LS": "EUR", ".OL": "NOK",
    }
    for suffix, currency in suffix_currencies.items():
        if symbol.endswith(suffix):
            return currency
    return "USD"


def mark_portfolio_to_market(
    cash: float, margin_used: float, positions: dict[str, dict[str, Any]],
    prices_in_cash_currency: dict[str, float],
) -> float:
    """Calculate NAV from cash, reserved collateral, and signed marked positions."""
    value = float(cash) + float(margin_used)
    for ticker, holding in positions.items():
        if ticker not in prices_in_cash_currency:
            continue
        quantity = float(holding.get("long", 0)) - float(holding.get("short", 0))
        value += quantity * float(prices_in_cash_currency[ticker])
    return value


def add_quote_currency_rates(
    portfolio: dict[str, Any], tickers: list[str], as_of: str,
    fx_rate_provider=get_point_in_time_fx_rate,
) -> None:
    """Add point-in-time quote-to-cash conversion rates for requested analysis tickers."""
    rates: dict[str, float] = {}
    cash_currency = portfolio["cash_currency"]
    for ticker in tickers:
        quote_currency = currency_for_ticker(ticker)
        try:
            rate = fx_rate_provider(quote_currency, cash_currency, as_of)
        except Exception as exc:
            raise ValueError(f"point-in-time FX lookup failed for {quote_currency}/{cash_currency} on {as_of}") from exc
        if rate is None or not math.isfinite(float(rate)) or float(rate) <= 0:
            raise ValueError(f"no point-in-time FX rate for {quote_currency}/{cash_currency} on {as_of}")
        rates[ticker] = float(rate)
    portfolio["quote_fx_rates"] = rates


def normalize_portfolio_input(
    payload: dict[str, Any],
    *,
    analysis_cutoff: str,
    resolve_ticker,
    fx_rate_provider=get_point_in_time_fx_rate,
    initial_cash: float = 100000.0,
    max_age_days: int | None = 7,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a user portfolio and convert it to the workflow's legacy representation."""
    try:
        parsed = PortfolioInput.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"portfolio.{'.'.join(map(str, error['loc']))}: {error['msg']}"
            for error in exc.errors()
        )
        raise ValueError(details) from exc

    if parsed.as_of > analysis_cutoff[:10]:
        raise ValueError("portfolio.as_of must not be after the analysis cutoff")
    age_days = (datetime.strptime(analysis_cutoff[:10], "%Y-%m-%d").date() - datetime.strptime(parsed.as_of, "%Y-%m-%d").date()).days
    if max_age_days is not None and age_days > max_age_days:
        raise ValueError(f"portfolio.as_of is stale; portfolio snapshots must be no more than {max_age_days} days old")

    normalized: dict[str, Any] = {
        "cash": float(parsed.cash),
        "cash_currency": parsed.currency,
        "positions": {},
        "cost_basis": {},
        "realized_gains": {},
        "as_of": parsed.as_of,
        "fx_rates": {},
        "explicit": True,
    }
    seen: set[str] = set()
    for index, position in enumerate(parsed.positions):
        ticker = resolve_ticker(position.ticker)
        if not ticker:
            raise ValueError(f"portfolio.positions.{index}.ticker could not be resolved")
        if ticker in seen:
            raise ValueError(f"portfolio.positions contains duplicate normalized ticker {ticker}")
        seen.add(ticker)
        try:
            rate = fx_rate_provider(position.currency, parsed.currency, parsed.as_of)
        except Exception as exc:
            raise ValueError(
                f"portfolio.positions.{index}.currency FX lookup failed for "
                f"{position.currency}/{parsed.currency} on {parsed.as_of}"
            ) from exc
        if rate is None or not math.isfinite(float(rate)) or float(rate) <= 0:
            raise ValueError(
                f"portfolio.positions.{index}.currency has no point-in-time FX rate "
                f"from {position.currency} to {parsed.currency} on {parsed.as_of}"
            )
        rate = float(rate)
        normalized["fx_rates"][position.currency] = rate
        quantity = float(position.quantity)
        entry_price = float(position.average_entry_price)
        normalized["positions"][ticker] = {
            "long": max(quantity, 0.0),
            "short": max(-quantity, 0.0),
            "long_cost_basis": entry_price,
            "short_cost_basis": entry_price,
            "currency": position.currency,
        }
        normalized["cost_basis"][ticker] = abs(quantity * entry_price * rate)
        normalized["realized_gains"][ticker] = {"long": 0.0, "short": 0.0}

    # Legacy `initialCash` remains the fallback. An explicit portfolio's cash always wins.
    normalized["cash"] = float(parsed.cash)
    return normalized, {
        "as_of": parsed.as_of,
        "cash": float(parsed.cash),
        "currency": parsed.currency,
        "positions": [position.model_dump() for position in parsed.positions],
        "fx_rates": normalized["fx_rates"],
        "legacy_initial_cash_ignored": initial_cash != parsed.cash,
    }
