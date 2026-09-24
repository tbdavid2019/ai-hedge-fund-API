"""Shared point-in-time metadata and strict cutoff filtering for dated inputs."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable
from functools import wraps
from inspect import signature
from zoneinfo import ZoneInfo


_PIT_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("pit_context", default=None)

_EXCHANGE_ZONES = {
    ".TW": ("Asia/Taipei", time(13, 30)),
    ".TWO": ("Asia/Taipei", time(13, 30)),
    ".HK": ("Asia/Hong_Kong", time(16, 0)),
    ".T": ("Asia/Tokyo", time(15, 30)),
    ".SS": ("Asia/Shanghai", time(15, 0)),
    ".SZ": ("Asia/Shanghai", time(15, 0)),
    ".L": ("Europe/London", time(16, 30)),
    ".PA": ("Europe/Paris", time(17, 30)),
    ".AS": ("Europe/Amsterdam", time(17, 30)),
    ".BR": ("Europe/Brussels", time(17, 30)),
}


def normalize_utc(value: str | datetime) -> datetime:
    """Parse an ISO timestamp and normalize it to an aware UTC datetime."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def date_cutoff_utc(day: str | date, ticker: str | None = None) -> datetime:
    """Resolve date-only cutoffs to the exchange local close; default to UTC close."""
    parsed_day = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    zone_name = "America/New_York" if ticker else "UTC"
    close_time = time(16, 0) if ticker else time(23, 59, 59)
    upper_ticker = (ticker or "").upper()
    for suffix, zone in _EXCHANGE_ZONES.items():
        if upper_ticker.endswith(suffix):
            zone_name, close_time = zone
            break
    # A date-only cutoff includes the exchange's closing print. Multi-market grid runs
    # pass no ticker and therefore share the UTC end-of-day cutoff.
    local = datetime.combine(parsed_day, close_time, ZoneInfo(zone_name))
    return local.astimezone(timezone.utc)


@contextmanager
def point_in_time_context(
    cutoff: str | datetime,
    *,
    strict: bool = True,
    coverage: dict[str, Any] | None = None,
    snapshots: dict[str, list[dict[str, Any]]] | None = None,
):
    token = _PIT_CONTEXT.set({
        "cutoff": normalize_utc(cutoff),
        "strict": strict,
        "coverage": coverage if coverage is not None else {},
        "snapshots": snapshots or {},
    })
    try:
        yield
    finally:
        _PIT_CONTEXT.reset(token)


def current_point_in_time_context() -> dict[str, Any] | None:
    return _PIT_CONTEXT.get()


def filter_point_in_time(
    records: Iterable[dict[str, Any]],
    *,
    cutoff: str | datetime | None = None,
    strict: bool | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter records to known availability and return auditable source coverage."""
    context = current_point_in_time_context() or {}
    active_cutoff = normalize_utc(cutoff) if cutoff else context.get("cutoff")
    active_strict = context.get("strict", False) if strict is None else strict
    included: list[dict[str, Any]] = []
    exclusions: dict[str, int] = {}
    sources: set[str] = set()
    verified = 0
    unknown = 0

    for original in records:
        record = dict(original)
        source = str(record.get("source_id") or "unknown")
        raw_status = record.get("point_in_time_status")
        status = str(raw_status or "unknown")
        available_at = record.get("available_at")
        if source != "unknown":
            sources.add(source)
        if available_at:
            try:
                available = normalize_utc(str(available_at))
                record["available_at"] = available.isoformat().replace("+00:00", "Z")
                if raw_status in (None, "", "verified"):
                    status = "verified"
            except (TypeError, ValueError):
                status = "unknown"
        if status != "verified" or not available_at:
            unknown += 1
            if active_strict:
                exclusions["unknown_availability"] = exclusions.get("unknown_availability", 0) + 1
                continue
        elif active_cutoff and normalize_utc(str(available_at)) > active_cutoff:
            exclusions["after_cutoff"] = exclusions.get("after_cutoff", 0) + 1
            continue
        else:
            verified += 1
        included.append(record)

    return included, {
        "cutoff": active_cutoff.isoformat().replace("+00:00", "Z") if active_cutoff else None,
        "strict": bool(active_strict),
        "source_ids": sorted(sources),
        "included": len(included),
        "verified": verified,
        "unknown_availability": unknown,
        "exclusions": exclusions,
        "historical_universe": "current_registry_survivorship_biased",
    }


def daily_bar_availability_utc(business_date: str, ticker: str) -> str:
    parsed_day = date.fromisoformat(str(business_date)[:10])
    upper_ticker = ticker.upper()
    is_crypto = "-USD" in upper_ticker or "/USD" in upper_ticker
    zone_name = "UTC" if is_crypto else "America/New_York"
    close_time = time(23, 59, 59) if is_crypto else time(16, 0)
    for suffix, zone in _EXCHANGE_ZONES.items():
        if upper_ticker.endswith(suffix):
            zone_name, close_time = zone
            break
    local_close = datetime.combine(parsed_day, close_time, ZoneInfo(zone_name))
    # The end-of-day daily bar is observable only after the exchange close.
    return local_close.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def filter_model_records(values: list[Any], ticker: str, data_kind: str) -> tuple[list[Any], dict[str, Any]]:
    """Apply the active cutoff to model records and accumulate source coverage."""
    context = current_point_in_time_context()
    if not context:
        return values, {"strict": False, "included": len(values), "exclusions": {}}
    records: list[dict[str, Any]] = []
    fallback_sources = {
        "financial_metrics": "yfinance_financial_statements",
        "line_items": "financial_data_provider",
        "insider_trades": "alpha_vantage_insider_transactions",
        "company_news": "news_provider",
    }
    for value in values:
        record = value.model_dump() if hasattr(value, "model_dump") else dict(value)
        if record.get("source_id") in (None, "", "unknown"):
            record["source_id"] = fallback_sources.get(data_kind, "unknown")
        if not record.get("business_date"):
            record["business_date"] = (
                record.get("report_period")
                or record.get("filing_date")
                or record.get("date")
                or record.get("time")
            )
        if data_kind == "price" and not record.get("available_at") and record.get("source_id") in {
            "yfinance_daily_ohlc", "stockdata_eod", "alpha_vantage_daily_ohlc", "coincap_daily_ohlc"
        }:
            record.update({
                "business_date": record.get("time"),
                "available_at": daily_bar_availability_utc(record.get("time", ""), ticker),
                "source_id": record.get("source_id") or "yfinance_daily_ohlc",
                "point_in_time_status": "verified",
            })
        records.append(record)
    filtered, coverage = filter_point_in_time(records)
    coverage["data_kind"] = data_kind
    coverage["ticker"] = ticker
    coverage["as_of"] = context["cutoff"].isoformat().replace("+00:00", "Z")
    context["coverage"][f"{ticker}:{data_kind}"] = coverage

    model_type = type(values[0]) if values else None
    # Preserve already-parsed objects when possible; reconstruct only records enriched by the filter.
    output = []
    for record in filtered:
        try:
            output.append(model_type(**record) if model_type else record)
        except (TypeError, ValueError):
            output.append(record)
    return output, coverage


def point_in_time_filter(data_kind: str, model_type: type | None = None) -> Callable:
    """Decorate list-returning data adapters with active strict PIT filtering."""
    def decorate(function: Callable) -> Callable:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any):
            context = current_point_in_time_context()
            ticker = kwargs.get("ticker")
            if ticker is None and args:
                ticker = args[0]
            snapshot_key = f"{ticker}:{data_kind}"
            if context and snapshot_key in context.get("snapshots", {}):
                result = [model_type(**record) if model_type else record for record in context["snapshots"][snapshot_key]]
                bound = signature(function).bind_partial(*args, **kwargs)
                parameters = bound.arguments
                start = parameters.get("start_date")
                end = parameters.get("end_date") or parameters.get("endDate")
                if end:
                    date_field = {"price": "time", "financial_metrics": "report_period", "line_items": "report_period", "insider_trades": "filing_date", "company_news": "date"}.get(data_kind)
                    if date_field:
                        result = [item for item in result if getattr(item, date_field, None) and str(getattr(item, date_field))[:10] <= str(end)[:10]]
                        if start:
                            result = [item for item in result if str(getattr(item, date_field))[:10] >= str(start)[:10]]
                limit = parameters.get("limit")
                if limit and data_kind != "price":
                    result = result[:int(limit)]
                if data_kind == "price":
                    cutoff_day = context["cutoff"].date().isoformat()
                    split_records = context["snapshots"].get(f"{ticker}:corporate_actions", [])
                    split_events = []
                    for event in split_records:
                        if event.get("kind") != "split":
                            continue
                        split_day = str(event.get("effective_date", ""))[:10]
                        try:
                            ratio = float(event.get("ratio", 0))
                        except (TypeError, ValueError):
                            continue
                        if split_day > cutoff_day and ratio > 0:
                            split_events.append((split_day, ratio))
                    for index, price in enumerate(result):
                        factor = 1.0
                        volume_factor = 1.0
                        for split_day, ratio in split_events:
                            if str(price.time) < split_day:
                                factor *= ratio
                                volume_factor /= ratio
                        if factor != 1.0:
                            result[index] = price.model_copy(update={
                                "open": price.open * factor,
                                "close": price.close * factor,
                                "high": price.high * factor,
                                "low": price.low * factor,
                                "volume": int(price.volume * volume_factor),
                            })
            else:
                result = function(*args, **kwargs)
            if not isinstance(result, list):
                return result
            filtered, _ = filter_model_records(result, str(ticker or ""), data_kind)
            return filtered
        return wrapped
    return decorate
