"""Resumable, point-in-time ticker/date-grid evaluation using the existing agent workflow."""

from __future__ import annotations

import math
import json
from datetime import date, datetime, time, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Callable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

try:
    from backtest_store import BacktestRunStore
    from data.point_in_time import point_in_time_context
    from data.portfolio import currency_for_ticker
    from tools.api import (
        _format_ticker_for_yfinance, get_company_news, get_financial_metrics,
        get_insider_trades, get_prices, get_sec_filings, search_line_items,
    )
except ImportError:
    from src.backtest_store import BacktestRunStore
    from src.data.point_in_time import point_in_time_context
    from src.data.portfolio import currency_for_ticker
    from src.tools.api import (
        _format_ticker_for_yfinance, get_company_news, get_financial_metrics,
        get_insider_trades, get_prices, get_sec_filings, search_line_items,
    )


BENCHMARK_MAP_VERSION = "regional-benchmarks-v1"
REGIONAL_BENCHMARKS = {
    ".TW": ("0050.TW", "TWD"),
    ".TWO": ("006208.TW", "TWD"),
    ".HK": ("2800.HK", "HKD"),
    ".T": ("1306.T", "JPY"),
    ".SS": ("510300.SS", "CNY"),
    ".SZ": ("159919.SZ", "CNY"),
    ".L": ("VUSA.L", "GBP"),
    ".PA": ("CW8.PA", "EUR"),
    ".AS": ("CW8.AS", "EUR"),
    ".BR": ("CW8.AS", "EUR"),
}
LINE_ITEM_SNAPSHOT = [
    "revenue", "net_income", "earnings_per_share", "book_value_per_share",
    "free_cash_flow", "operating_income", "total_assets", "total_liabilities",
    "current_assets", "current_liabilities", "cash_and_cash_equivalents",
    "long_term_debt", "outstanding_shares", "capital_expenditure",
    "dividends_and_other_cash_distributions",
]


def _dump(records: list[Any]) -> list[dict[str, Any]]:
    return [record.model_dump() if hasattr(record, "model_dump") else dict(record) for record in records]


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def _benchmark_for(ticker: str) -> tuple[str, str] | None:
    symbol = ticker.upper()
    for suffix, benchmark in REGIONAL_BENCHMARKS.items():
        if symbol.endswith(suffix):
            return benchmark
    if symbol.isalpha() and "." not in symbol:
        return "SPY", "USD"
    return None


def _cutoff_for_session(session_date: str, cutoff_time_utc: str) -> datetime:
    value = cutoff_time_utc.strip().replace("Z", "+00:00")
    if "T" in value:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("cutoff_time_utc must include a UTC offset or Z")
        return datetime.combine(date.fromisoformat(session_date), parsed.timetz()).astimezone(timezone.utc)
    parsed_time = time.fromisoformat(value)
    return datetime.combine(date.fromisoformat(session_date), parsed_time, timezone.utc)


def _fetch_fx_series(source_currency: str, target_currency: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    source, target = source_currency.upper(), target_currency.upper()
    if source == target:
        dates = pd.date_range(start_date, end_date, freq="D")
        return [{"date": day.strftime("%Y-%m-%d"), "available_at": f"{day.strftime('%Y-%m-%d')}T00:00:00Z", "rate": 1.0} for day in dates]
    start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    end = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    pair = f"{source}{target}=X"
    inverted = False
    try:
        frame = yf.Ticker(pair).history(start=start, end=end, auto_adjust=False)
        if frame is None or frame.empty:
            raise ValueError("direct FX pair unavailable")
    except Exception:
        pair = f"{target}{source}=X"
        frame = yf.Ticker(pair).history(start=start, end=end, auto_adjust=False)
        inverted = True
    rates = []
    for index, row in frame.iterrows():
        value = float(row["Close"])
        if not math.isfinite(value) or value <= 0:
            continue
        fx_day = index.strftime("%Y-%m-%d")
        fx_close = datetime.combine(date.fromisoformat(fx_day), time(17, 0), ZoneInfo("America/New_York"))
        rates.append({"date": fx_day, "available_at": fx_close.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "rate": 1 / value if inverted else value})
    if not rates:
        raise ValueError(f"No historical FX rates for {source}/{target} over {start_date} to {end_date}")
    return rates


def _rate_at(records: list[dict[str, Any]], cutoff: str | datetime) -> float:
    if isinstance(cutoff, datetime):
        boundary = cutoff
    elif "T" in cutoff:
        boundary = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    else:
        boundary = datetime.combine(date.fromisoformat(cutoff[:10]), time.max, timezone.utc)
    if boundary.tzinfo is None:
        boundary = boundary.replace(tzinfo=timezone.utc)
    eligible = []
    for record in records:
        stamp = datetime.fromisoformat(str(record.get("available_at", f"{record['date']}T23:59:59Z")).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if stamp.astimezone(timezone.utc) <= boundary.astimezone(timezone.utc):
            eligible.append(record)
    if not eligible:
        boundary_text = boundary.astimezone(timezone.utc).isoformat()
        raise ValueError(f"No point-in-time FX rate available by {boundary_text}")
    latest = max(
        eligible,
        key=lambda record: datetime.fromisoformat(
            str(record.get("available_at", f"{record['date']}T23:59:59Z")).replace("Z", "+00:00")
        ).astimezone(timezone.utc),
    )
    return float(latest["rate"])


def _fetch_snapshot_bundle(tickers: list[str], benchmarks: list[str], start: str, end: str, is_crypto: bool) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    snapshots: dict[str, list[dict[str, Any]]] = {}
    coverage: list[str] = []
    fetch_start = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=370)).strftime("%Y-%m-%d")
    all_tickers = list(dict.fromkeys(tickers + benchmarks))
    for ticker in all_tickers:
        prices = get_prices(ticker, fetch_start, end, is_crypto=is_crypto)
        key = f"{ticker}:price" if ticker in tickers else f"benchmark:{ticker}:price"
        snapshots[key] = _dump(prices)
        if ticker in benchmarks and ticker in tickers:
            snapshots[f"benchmark:{ticker}:price"] = _dump(prices)
        coverage.append(f"{key}:{len(prices)}")
        if ticker not in tickers:
            continue
        snapshots[f"{ticker}:financial_metrics"] = _dump(get_financial_metrics(ticker, end, limit=100, is_crypto=is_crypto))
        try:
            snapshots[f"{ticker}:line_items"] = _dump(search_line_items(ticker, LINE_ITEM_SNAPSHOT, end, period="annual", limit=100))
        except Exception:
            snapshots[f"{ticker}:line_items"] = []
        snapshots[f"{ticker}:company_news"] = _dump(get_company_news(ticker, end, start_date=fetch_start, limit=1000, is_crypto=is_crypto))
        snapshots[f"{ticker}:insider_trades"] = _dump(get_insider_trades(ticker, end, start_date=start, limit=1000)) if not is_crypto else []
        try:
            filings, _ = get_sec_filings(ticker)
        except Exception:
            filings = []
        snapshots[f"{ticker}:sec_filing_metadata"] = filings
        try:
            formatted = _format_ticker_for_yfinance(ticker)
            split_series = yf.Ticker(formatted).splits
            if split_series is None:
                raise ValueError("split history is unavailable")
            splits = []
            splits = [
                {"kind": "split", "effective_date": index.strftime("%Y-%m-%d"), "ratio": float(ratio), "source_id": "yfinance_split_history"}
                for index, ratio in split_series.items() if float(ratio) > 0
            ]
            snapshots[f"{ticker}:corporate_actions"] = splits
        except Exception as exc:
            snapshots[f"{ticker}:corporate_actions"] = [{
                "kind": "unavailable", "source_id": "yfinance_split_history",
                "reason": str(exc), "point_in_time_status": "unknown",
            }]
        coverage.extend(f"{ticker}:{kind}:{len(snapshots[f'{ticker}:{kind}'])}" for kind in (
            "financial_metrics", "line_items", "company_news", "insider_trades", "sec_filing_metadata", "corporate_actions"
        ))
    return snapshots, coverage


def _price_lookup(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda item: str(item.get("available_at") or item.get("time") or ""))


def _historical_share_basis(records: list[dict[str, Any]], split_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Undo provider's all-history split scaling so each bar uses its effective share basis."""
    if any(event.get("kind") == "unavailable" for event in split_events):
        raise ValueError("split history is unavailable; strict point-in-time price bars cannot be verified")
    output = []
    parsed_events = []
    for event in split_events:
        try:
            parsed_events.append((str(event["effective_date"])[:10], float(event["ratio"])))
        except (KeyError, TypeError, ValueError):
            continue
    for original in records:
        record = dict(original)
        bar_day = str(record.get("time", ""))[:10]
        factor = math.prod(ratio for effective_date, ratio in parsed_events if effective_date > bar_day and ratio > 0)
        if factor != 1.0:
            for field in ("open", "high", "low", "close"):
                if record.get(field) is not None:
                    record[field] = float(record[field]) * factor
            if record.get("volume") is not None:
                record["volume"] = int(record["volume"] / factor)
        output.append(record)
    return output


def _apply_effective_splits(portfolio: dict[str, Any], snapshots: dict[str, list[dict[str, Any]]], after_date: str, through_date: str):
    for ticker, holding in portfolio["positions"].items():
        for event in snapshots.get(f"{ticker}:corporate_actions", []):
            effective = str(event.get("effective_date", ""))[:10]
            if event.get("kind") != "split" or not (after_date < effective <= through_date):
                continue
            ratio = float(event.get("ratio", 0))
            if ratio <= 0:
                continue
            holding["long"] *= ratio
            holding["short"] *= ratio
            holding["long_cost_basis"] /= ratio
            holding["short_cost_basis"] /= ratio
            for order in portfolio.get("pending_orders", []):
                if order.get("ticker") == ticker and str(order.get("fill_date", "")) >= effective:
                    order["quantity"] = int(order["quantity"] * ratio)


def _last_price(records: list[dict[str, Any]], cutoff: datetime) -> tuple[float, str, str] | None:
    eligible = []
    for record in records:
        available_at = record.get("available_at")
        if not available_at:
            continue
        stamp = datetime.fromisoformat(str(available_at).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if stamp.astimezone(timezone.utc) <= cutoff:
            eligible.append((stamp, float(record["close"]), str(record.get("time"))[:10]))
    if not eligible:
        return None
    stamp, price, day = max(eligible, key=lambda value: value[0])
    return price, day, stamp.isoformat().replace("+00:00", "Z")


def _next_price(records: list[dict[str, Any]], cutoff: datetime) -> tuple[float, str, str] | None:
    eligible = []
    for record in records:
        available_at = record.get("available_at")
        if not available_at:
            continue
        stamp = datetime.fromisoformat(str(available_at).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if stamp.astimezone(timezone.utc) > cutoff:
            eligible.append((stamp, float(record["close"]), str(record.get("time"))[:10]))
    if not eligible:
        return None
    stamp, price, day = min(eligible, key=lambda value: value[0])
    return price, day, stamp.isoformat().replace("+00:00", "Z")


def _portfolio_value(portfolio: dict[str, Any], prices: dict[str, float]) -> float:
    # Cash excludes reserved collateral; add it back, then mark all open short
    # liabilities at current market value. Sale proceeds already sit in cash.
    value = float(portfolio["cash"]) + float(portfolio.get("margin_used", 0))
    for ticker, holding in portfolio["positions"].items():
        price = prices[ticker]
        value += float(holding["long"]) * price
        value -= float(holding["short"]) * price
    return value


def _execute_order(portfolio: dict[str, Any], ticker: str, action: str, quantity: float, price: float, fee_rate: float, slippage_rate: float, margin_ratio: float) -> dict[str, Any]:
    quantity = max(0, int(quantity))
    if quantity == 0 or action not in {"buy", "sell", "short", "cover"}:
        return {"filled_quantity": 0, "fee": 0.0, "fill_price": price, "reason": "no executable order"}
    position = portfolio["positions"][ticker]
    execution_price = price * (1 + slippage_rate if action in {"buy", "cover"} else 1 - slippage_rate)
    if action == "buy":
        quantity = min(quantity, int(portfolio["cash"] / (execution_price * (1 + fee_rate))))
        fee = quantity * execution_price * fee_rate
        if quantity:
            old = position["long"]
            position["long_cost_basis"] = (old * position["long_cost_basis"] + quantity * execution_price) / (old + quantity)
            position["long"] += quantity
            portfolio["cash"] -= quantity * execution_price + fee
    elif action == "sell":
        quantity = min(quantity, int(position["long"]))
        fee = quantity * execution_price * fee_rate
        position["long"] -= quantity
        portfolio["cash"] += quantity * execution_price - fee
        if position["long"] == 0:
            position["long_cost_basis"] = 0.0
    elif action == "short":
        max_qty = int(portfolio["cash"] / (execution_price * (margin_ratio + fee_rate))) if margin_ratio > 0 else 0
        quantity = min(quantity, max_qty)
        fee = quantity * execution_price * fee_rate
        margin = quantity * execution_price * margin_ratio
        old = position["short"]
        if quantity:
            position["short_cost_basis"] = (old * position["short_cost_basis"] + quantity * execution_price) / (old + quantity)
            position["short"] += quantity
            position["short_margin_used"] += margin
            portfolio["margin_used"] += margin
            portfolio["cash"] += quantity * execution_price - margin - fee
    else:
        quantity = min(quantity, int(position["short"]))
        fee = quantity * execution_price * fee_rate
        if quantity:
            portion = quantity / position["short"]
            released = portion * position["short_margin_used"]
            position["short"] -= quantity
            position["short_margin_used"] -= released
            portfolio["margin_used"] -= released
            portfolio["cash"] += released - quantity * execution_price - fee
            if position["short"] == 0:
                position["short_cost_basis"] = 0.0
                position["short_margin_used"] = 0.0
    return {"filled_quantity": quantity, "fee": fee, "fill_price": execution_price, "reason": None if quantity else "insufficient cash or position"}


def _fill_due_orders(portfolio: dict[str, Any], cutoff: datetime, fee_rate: float, slippage_rate: float, margin_ratio: float) -> tuple[list[dict[str, Any]], float]:
    due, pending = [], []
    for order in portfolio.get("pending_orders", []):
        stamp = datetime.fromisoformat(order["available_at"].replace("Z", "+00:00"))
        (due if stamp <= cutoff else pending).append(order)
    portfolio["pending_orders"] = pending
    fills = []
    total_fees = 0.0
    for order in due:
        fill = _execute_order(portfolio, order["ticker"], order["action"], order["quantity"], order["price"], fee_rate, slippage_rate, margin_ratio)
        fill.update({"ticker": order["ticker"], "fill_date": order["fill_date"], "available_at": order["available_at"]})
        fills.append(fill)
        total_fees += float(fill.get("fee", 0))
    return fills, total_fees


def run_backtest_grid(
    *, run_id: str, tickers: list[str], start_date: str, end_date: str,
    cutoff_time_utc: str, agent: Callable, initial_cash: float = 100000.0,
    starting_portfolio: dict[str, Any] | None = None, model_name: str = "openai/gpt-oss-20b",
    model_provider: str = "Groq", selected_analysts: list[str] | None = None,
    is_crypto: bool = False, daily_rebalance_policy: str = "daily",
    transaction_fee_rate: float = 0.001, slippage_rate: float = 0.0005,
    margin_ratio: float = 0.5, database_path: str | None = None,
) -> dict[str, Any]:
    """Run a resumable synchronized UTC decision grid and persist all run inputs/results."""
    tickers = list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))
    if not tickers:
        raise ValueError("tickers must contain at least one symbol")
    start = date.fromisoformat(start_date[:10]).isoformat()
    end = date.fromisoformat(end_date[:10]).isoformat()
    if start >= end:
        raise ValueError("start_date must be before end_date")
    if starting_portfolio is not None and starting_portfolio.get("as_of") != start:
        raise ValueError("starting_portfolio.as_of must match the evaluation start date")
    if daily_rebalance_policy not in {"daily", "none"}:
        raise ValueError("daily_rebalance_policy must be 'daily' or 'none'")
    if not (0 <= transaction_fee_rate < 1 and 0 <= slippage_rate < 1 and 0 < margin_ratio <= 1):
        raise ValueError("invalid transaction fee, slippage, or margin assumptions")

    base_currency = str((starting_portfolio or {}).get("cash_currency", "USD")).upper()
    starting = starting_portfolio or {
        "cash": float(initial_cash), "cash_currency": base_currency, "positions": {}, "cost_basis": {}, "realized_gains": {},
    }
    model_config = {
        "model_name": model_name, "model_provider": model_provider,
        "selected_analysts": selected_analysts or [], "is_crypto": is_crypto,
    }
    benchmark_by_ticker = {ticker: _benchmark_for(ticker) for ticker in tickers}
    benchmark_tickers = list(dict.fromkeys(item[0] for item in benchmark_by_ticker.values() if item))
    source_versions = {"yfinance": _package_version("yfinance"), "pandas": pd.__version__, "point_in_time_schema": "1"}
    manifest = {
        "run_id": run_id, "tickers": tickers, "start_date": start, "end_date": end,
        "cutoff_time_utc": cutoff_time_utc, "daily_rebalance_policy": daily_rebalance_policy,
        "starting_portfolio": starting, "model": model_config,
        "benchmark_map_version": BENCHMARK_MAP_VERSION, "benchmark_by_ticker": benchmark_by_ticker,
        "transaction_fee_rate": transaction_fee_rate, "slippage_rate": slippage_rate,
        "margin_ratio": margin_ratio, "point_in_time_mode": "strict",
        "source_versions": source_versions,
    }
    store = BacktestRunStore(database_path)
    run_info = store.create_or_resume(run_id, manifest)
    saved_run = store.get_run(run_id)
    if saved_run and saved_run["status"] == "completed" and saved_run["result"]:
        return saved_run["result"]

    snapshots = store.load_snapshots(run_id)
    snapshot_coverage: list[str] = []
    if not snapshots:
        snapshots, snapshot_coverage = _fetch_snapshot_bundle(tickers, benchmark_tickers, start, end, is_crypto)
        for currency in {currency_for_ticker(ticker) for ticker in tickers + benchmark_tickers}:
            key = f"fx:{currency}:{base_currency}"
            snapshots[key] = _fetch_fx_series(currency, base_currency, start, end)
        provider_version = ";".join(f"{key}={value}" for key, value in source_versions.items())
        store.save_snapshots(run_id, snapshots, provider_version)
    else:
        snapshot_coverage = [f"{key}:{len(records)}" for key, records in snapshots.items()]

    # Materialized inputs are immutable before any LLM decision session begins.
    price_snapshots = {
        ticker: _historical_share_basis(
            _price_lookup(snapshots.get(f"{ticker}:price", [])),
            snapshots.get(f"{ticker}:corporate_actions", []),
        )
        for ticker in tickers
    }
    benchmark_prices = {ticker: _price_lookup(snapshots.get(f"benchmark:{ticker}:price", [])) for ticker in benchmark_tickers}
    for ticker in tickers:
        if not price_snapshots[ticker]:
            raise ValueError(f"No price snapshot available for {ticker}")

    holdings = {}
    for ticker in tickers:
        raw = (starting.get("positions") or {}).get(ticker, {})
        long_qty = float(raw.get("long", 0))
        short_qty = float(raw.get("short", 0))
        holdings[ticker] = {
            "long": long_qty, "short": short_qty,
            "long_cost_basis": float(raw.get("long_cost_basis", 0)) * float(starting.get("fx_rates", {}).get(raw.get("currency", currency_for_ticker(ticker)), 1.0)),
            "short_cost_basis": float(raw.get("short_cost_basis", 0)) * float(starting.get("fx_rates", {}).get(raw.get("currency", currency_for_ticker(ticker)), 1.0)),
            "short_margin_used": float(raw.get("short_margin_used", 0)),
            "currency": raw.get("currency", currency_for_ticker(ticker)),
        }
    portfolio = {
        "cash": float(starting.get("cash", initial_cash)), "cash_currency": base_currency,
        "positions": holdings, "margin_used": float(starting.get("margin_used", 0)),
        "cost_basis": {}, "realized_gains": {}, "fx_rates": starting.get("fx_rates", {}),
        "quote_fx_rates": {}, "explicit": True, "pending_orders": [], "last_effective_date": start,
    }
    for ticker in tickers:
        portfolio["realized_gains"][ticker] = {"long": 0.0, "short": 0.0}

    fx_snapshots = {currency: snapshots[f"fx:{currency}:{base_currency}"] for currency in {currency_for_ticker(t) for t in tickers + benchmark_tickers}}
    start_cutoff = _cutoff_for_session(start, cutoff_time_utc)
    start_prices: dict[str, float] = {}
    start_values: dict[str, float] = {}
    for ticker in tickers:
        quote = _last_price(price_snapshots[ticker], start_cutoff)
        if not quote:
            raise ValueError(f"No starting valuation price for {ticker} at {start}")
        fx = _rate_at(fx_snapshots[currency_for_ticker(ticker)], start_cutoff)
        start_prices[ticker] = quote[0] * fx
        holding = holdings[ticker]
        start_values[ticker] = abs((holding["long"] - holding["short"]) * start_prices[ticker])
    initial_value = float(portfolio["cash"]) + sum(
        (holding["long"] * start_prices[ticker]) + holding["short"] * (holding["short_cost_basis"] - start_prices[ticker])
        for ticker, holding in holdings.items()
    )
    if initial_value <= 0:
        raise ValueError("starting portfolio net asset value must be positive")

    benchmark_weights: dict[str, float] = {}
    invested = sum(start_values.values())
    for ticker, mapped in benchmark_by_ticker.items():
        if not mapped:
            continue
        benchmark = mapped[0]
        weight = start_values[ticker] / invested if invested > 0 else 1.0 / len(tickers)
        benchmark_weights[benchmark] = benchmark_weights.get(benchmark, 0.0) + weight
    benchmark_start_prices: dict[str, float] = {}
    benchmark_unavailable = []
    for benchmark in benchmark_weights:
        records = benchmark_prices.get(benchmark, [])
        quote = _last_price(records, start_cutoff)
        if not quote:
            benchmark_unavailable.append(f"missing start price for {benchmark}")
            continue
        currency = next((currency for mapping in benchmark_by_ticker.values() if mapping and mapping[0] == benchmark for currency in [mapping[1]]), "USD")
        fx = _rate_at(fx_snapshots[currency], start_cutoff)
        benchmark_start_prices[benchmark] = quote[0] * fx
    if len(benchmark_start_prices) != len(benchmark_weights):
        benchmark_unavailable.append("one or more regional benchmark series are unavailable")
    if any(mapping is None for mapping in benchmark_by_ticker.values()):
        benchmark_unavailable.append("no regional benchmark is mapped for one or more requested tickers")
    if not benchmark_weights:
        benchmark_unavailable.append("no regional benchmark is mapped")

    completed = store.completed_sessions(run_id)
    portfolio = store.load_last_portfolio(run_id, portfolio)
    holdings = portfolio["positions"]
    valuation_dates = pd.bdate_range(start, end).strftime("%Y-%m-%d").tolist()
    sessions = [day for day in valuation_dates if day < end]
    final_cutoff = _cutoff_for_session(end, cutoff_time_utc)
    if daily_rebalance_policy == "none":
        sessions = sessions[:1]
    for session_day in sessions:
        if session_day in completed:
            continue
        cutoff = _cutoff_for_session(session_day, cutoff_time_utc)
        _apply_effective_splits(portfolio, snapshots, portfolio.get("last_effective_date", start), session_day)
        portfolio["last_effective_date"] = session_day
        before = json_safe(portfolio)
        prior_fills, prior_fees = _fill_due_orders(portfolio, cutoff, transaction_fee_rate, slippage_rate, margin_ratio)
        current_prices: dict[str, float] = {}
        for ticker in tickers:
            quote = _last_price(price_snapshots[ticker], cutoff)
            if not quote:
                continue
            rate = _rate_at(fx_snapshots[currency_for_ticker(ticker)], cutoff)
            current_prices[ticker] = quote[0] * rate
        if len(current_prices) != len(tickers):
            store.commit_session(
                run_id, session_day, decisions={}, portfolio_before=before,
                portfolio_after=json_safe(portfolio), prices=current_prices,
                metrics={"fills": {f"prior:{index}:{fill['ticker']}": fill for index, fill in enumerate(prior_fills)},
                         "fees": prior_fees, "cutoff": cutoff.isoformat().replace("+00:00", "Z"),
                         "skipped_reason": "incomplete synchronized price grid"},
            )
            completed.add(session_day)
            continue
        for ticker in tickers:
            portfolio["cost_basis"][ticker] = abs((holdings[ticker]["long"] - holdings[ticker]["short"]) * current_prices[ticker])
            portfolio["quote_fx_rates"][ticker] = _rate_at(fx_snapshots[currency_for_ticker(ticker)], cutoff)
        lookback = (datetime.strptime(session_day, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
        pit_cutoff = cutoff.isoformat().replace("+00:00", "Z")
        with point_in_time_context(cutoff, strict=True, coverage={}, snapshots=snapshots):
            output = agent(
                tickers=tickers, start_date=lookback, end_date=session_day,
                portfolio=portfolio, model_name=model_name, model_provider=model_provider,
                selected_analysts=selected_analysts or [], point_in_time=True,
                point_in_time_cutoff=pit_cutoff, point_in_time_snapshots=snapshots,
            )
        decisions = output.get("decisions", {})
        pretrade_value = _portfolio_value(portfolio, current_prices)
        session_fills = {f"prior:{index}:{fill['ticker']}": fill for index, fill in enumerate(prior_fills)}
        total_fees = prior_fees
        for ticker in tickers:
            next_quote = _next_price(price_snapshots[ticker], cutoff)
            decision = decisions.get(ticker, {})
            if not next_quote or datetime.fromisoformat(next_quote[2].replace("Z", "+00:00")) > final_cutoff:
                session_fills[ticker] = {"filled_quantity": 0, "reason": "no tradable observation before end date"}
                continue
            raw_price, fill_day, fill_available_at = next_quote
            fx = _rate_at(fx_snapshots[currency_for_ticker(ticker)], fill_available_at)
            action = str(decision.get("action", "hold")).lower()
            quantity = max(0, int(float(decision.get("quantity", 0) or 0)))
            if action in {"buy", "sell", "short", "cover"} and quantity:
                portfolio.setdefault("pending_orders", []).append({
                    "ticker": ticker, "action": action, "quantity": quantity,
                    "price": raw_price * fx, "fill_date": fill_day,
                    "available_at": fill_available_at,
                })
                session_fills[ticker] = {"scheduled_quantity": quantity, "fill_date": fill_day, "available_at": fill_available_at}
            else:
                session_fills[ticker] = {"filled_quantity": 0, "reason": "no executable order"}
        portfolio["cost_basis"] = {}
        after = json_safe(portfolio)
        store.commit_session(
            run_id, session_day, decisions=decisions, portfolio_before=before,
            portfolio_after=after, prices=current_prices,
            metrics={"fills": session_fills, "fees": total_fees, "cutoff": pit_cutoff,
                     "pretrade_value": pretrade_value,
                     "point_in_time": output.get("point_in_time", {})},
            analyst_signals=output.get("analyst_signals", {}),
        )
        completed.add(session_day)

    # Apply corporate actions and orders only when their effective/observable time is
    # within the evaluation interval. The end date creates no new signal or order.
    _apply_effective_splits(portfolio, snapshots, portfolio.get("last_effective_date", start), end)
    _, final_fees = _fill_due_orders(portfolio, final_cutoff, transaction_fee_rate, slippage_rate, margin_ratio)
    final_prices: dict[str, float] = {}
    for ticker in tickers:
        quote = _last_price(price_snapshots[ticker], final_cutoff)
        if not quote:
            raise ValueError(f"No final valuation price for {ticker} by {end}")
        final_prices[ticker] = quote[0] * _rate_at(fx_snapshots[currency_for_ticker(ticker)], final_cutoff)
    final_value = _portfolio_value(portfolio, final_prices)
    values_by_day = {start: initial_value}
    for row in _session_rows(store, run_id):
        metrics = json.loads(row["metrics_json"])
        if metrics.get("pretrade_value") is not None:
            values_by_day[row["session_date"]] = float(metrics["pretrade_value"])
    values_by_day[end] = final_value
    daily_values = sorted(values_by_day.items())
    returns = pd.Series([value for _, value in daily_values]).pct_change().dropna()
    drawdown = (pd.Series([value for _, value in daily_values]) / pd.Series([value for _, value in daily_values]).cummax() - 1).min() if daily_values else 0.0
    sharpe = float(np.sqrt(252) * returns.mean() / returns.std()) if len(returns) > 1 and returns.std() > 0 else None
    downside = returns[returns < 0]
    sortino = float(np.sqrt(252) * returns.mean() / downside.std()) if len(downside) > 1 and downside.std() > 0 else None
    strategy_return = (final_value / initial_value - 1) * 100
    benchmark_return = None
    if not benchmark_unavailable and benchmark_start_prices:
        weighted = 0.0
        for benchmark, weight in benchmark_weights.items():
            final_quote = _last_price(benchmark_prices[benchmark], final_cutoff)
            if not final_quote:
                benchmark_unavailable.append(f"missing final price for {benchmark}")
                break
            currency = next((mapping[1] for mapping in benchmark_by_ticker.values() if mapping and mapping[0] == benchmark), "USD")
            rate = _rate_at(fx_snapshots[currency], final_cutoff)
            weighted += weight * ((final_quote[0] * rate) / benchmark_start_prices[benchmark] - 1)
        if not benchmark_unavailable:
            benchmark_return = weighted * 100

    result = {
        "run_id": run_id,
        "fingerprint": run_info["fingerprint"],
        "configuration": manifest,
        "status": "completed",
        "start_value": initial_value,
        "end_value": final_value,
        "portfolio_return_pct": strategy_return,
        "benchmark": {
            "map_version": BENCHMARK_MAP_VERSION,
            "weights": benchmark_weights,
            "return_pct": benchmark_return,
            "relative_return_pct": strategy_return - benchmark_return if benchmark_return is not None else None,
            "unavailable_reason": "; ".join(benchmark_unavailable) if benchmark_unavailable else None,
        },
        "risk_metrics": {"sharpe_ratio": sharpe, "sortino_ratio": sortino, "max_drawdown_pct": float(drawdown * 100)},
        "execution_costs": {"transaction_fee_rate": transaction_fee_rate, "slippage_rate": slippage_rate, "total_fees": final_fees + sum(
            float(json.loads(row["metrics_json"]).get("fees", 0)) for row in _session_rows(store, run_id)
        )},
        "coverage": {"snapshots": snapshot_coverage, "point_in_time": _snapshot_coverage(snapshots, tickers), "strict_point_in_time": True,
                     "excluded_unknown_financial_availability": True,
                     "historical_universe": "current_registry_survivorship_biased",
                     "dividend_cash_flows": "not_modeled"},
        "completed_sessions": sorted(store.completed_sessions(run_id)),
        "completed_ticker_date_cells": len(store.get_cells(run_id)),
        "portfolio": json_safe(portfolio),
    }
    store.set_result(run_id, result)
    return result


def _session_rows(store: BacktestRunStore, run_id: str) -> list[dict[str, Any]]:
    with store._connect() as db:
        rows = db.execute("SELECT session_date,metrics_json FROM sessions WHERE run_id=? ORDER BY session_date", (run_id,)).fetchall()
    return [{"session_date": row["session_date"], "metrics_json": row["metrics_json"]} for row in rows]


def _snapshot_coverage(snapshots: dict[str, list[dict[str, Any]]], tickers: list[str]) -> dict[str, Any]:
    result = {}
    kinds = ("price", "financial_metrics", "line_items", "insider_trades", "company_news", "sec_filing_metadata")
    for ticker in tickers:
        for kind in kinds:
            records = snapshots.get(f"{ticker}:{kind}", [])
            source_ids = sorted({str(record.get("source_id") or "unknown") for record in records})
            verified = sum(bool(record.get("available_at")) and record.get("point_in_time_status") == "verified" for record in records)
            unknown = len(records) - verified
            result[f"{ticker}:{kind}"] = {
                "source_ids": source_ids, "records": len(records),
                "verified_availability": verified, "unknown_availability": unknown,
                "strict_exclusions": {"unknown_availability": unknown} if unknown else {},
            }
    return result


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
