from datetime import datetime, timezone
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from src.backtest_store import BacktestRunStore
from src.data.models import Price
from src.data.point_in_time import date_cutoff_utc, filter_model_records, filter_point_in_time, point_in_time_context
from src.data.portfolio import add_quote_currency_rates, normalize_portfolio_input
from src.tools import sec_edgar
from src.backtest_evaluation import _execute_order, _next_price, _rate_at


def test_exchange_and_shared_cutoffs_are_normalized_to_utc():
    assert date_cutoff_utc("2026-01-05", "2330.TW").isoformat() == "2026-01-05T05:30:00+00:00"
    assert date_cutoff_utc("2026-01-05").isoformat() == "2026-01-05T23:59:59+00:00"
    late_tw_record, _ = filter_point_in_time(
        [{"source_id": "fixture", "available_at": "2026-01-05T05:31:00Z", "point_in_time_status": "verified"}],
        cutoff=date_cutoff_utc("2026-01-05", "2330.TW"), strict=True,
    )
    assert late_tw_record == []


def test_strict_filter_excludes_unknown_and_after_cutoff_records():
    records = [
        {"source_id": "test", "available_at": "2026-01-05T15:00:00Z", "point_in_time_status": "verified"},
        {"source_id": "test", "available_at": "2026-01-05T17:00:00Z", "point_in_time_status": "verified"},
        {"source_id": "test", "available_at": None, "point_in_time_status": "unknown"},
    ]
    included, report = filter_point_in_time(records, cutoff="2026-01-05T16:00:00Z", strict=True)
    assert len(included) == 1
    assert report["exclusions"] == {"after_cutoff": 1, "unknown_availability": 1}


def test_explicit_unknown_status_is_not_upgraded_by_a_timestamp():
    included, report = filter_point_in_time(
        [{"source_id": "provider", "available_at": "2026-01-05T15:00:00Z", "point_in_time_status": "unknown"}],
        cutoff="2026-01-05T16:00:00Z", strict=True,
    )
    assert included == []
    assert report["exclusions"] == {"unknown_availability": 1}


def test_daily_prices_get_verified_exchange_close_metadata():
    bars = [Price(open=10, high=11, low=9, close=10, volume=100, time="2026-01-05", source_id="yfinance_daily_ohlc")]
    with point_in_time_context("2026-01-05T05:30:00Z", strict=True):
        included, report = filter_model_records(bars, "2330.TW", "price")
    assert included[0].available_at == "2026-01-05T05:30:00Z"
    assert report["verified"] == 1


def test_portfolio_normalization_handles_short_empty_and_legacy_cash():
    payload = {
        "as_of": "2026-01-05", "cash": 2500, "currency": "USD",
        "positions": [{"ticker": "aapl", "quantity": -3, "average_entry_price": 100, "currency": "USD"}],
    }
    normalized, snapshot = normalize_portfolio_input(
        payload, analysis_cutoff="2026-01-05", resolve_ticker=str.upper,
        fx_rate_provider=lambda source, target, day: 1.0, initial_cash=10000,
    )
    assert normalized["cash"] == 2500
    assert normalized["positions"]["AAPL"]["short"] == 3
    assert snapshot["legacy_initial_cash_ignored"] is True
    payload["positions"][0]["quantity"] = 3
    long_position, _ = normalize_portfolio_input(
        payload, analysis_cutoff="2026-01-05", resolve_ticker=str.upper,
        fx_rate_provider=lambda source, target, day: 1.0,
    )
    assert long_position["positions"]["AAPL"]["long"] == 3
    assert long_position["positions"]["AAPL"]["short"] == 0
    payload["positions"][0]["quantity"] = -3
    empty, _ = normalize_portfolio_input(
        {**payload, "positions": []}, analysis_cutoff="2026-01-05", resolve_ticker=str.upper,
        fx_rate_provider=lambda source, target, day: 1.0,
    )
    assert empty["positions"] == {}


def test_portfolio_rejects_stale_snapshots_and_missing_fx():
    payload = {"as_of": "2026-01-01", "cash": 1, "currency": "USD", "positions": []}
    with pytest.raises(ValueError, match="stale"):
        normalize_portfolio_input(payload, analysis_cutoff="2026-01-10", resolve_ticker=str.upper)
    payload["as_of"] = "2026-01-05"
    payload["positions"] = [{"ticker": "2330.TW", "quantity": 1, "average_entry_price": 100, "currency": "TWD"}]
    with pytest.raises(ValueError, match="no point-in-time FX"):
        normalize_portfolio_input(payload, analysis_cutoff="2026-01-05", resolve_ticker=str.upper,
                                  fx_rate_provider=lambda source, target, day: None)
    payload["as_of"] = "not-a-date"
    with pytest.raises(ValueError, match="ISO date"):
        normalize_portfolio_input(payload, analysis_cutoff="2026-01-05", resolve_ticker=str.upper,
                                  fx_rate_provider=lambda source, target, day: 1.0)


def test_analysis_cutoff_fx_is_added_for_holdings_outside_requested_tickers():
    portfolio, _ = normalize_portfolio_input(
        {"as_of": "2026-01-05", "cash": 1000, "currency": "USD", "positions": [
            {"ticker": "2330.TW", "quantity": 5, "average_entry_price": 100, "currency": "TWD"}
        ]},
        analysis_cutoff="2026-01-09", resolve_ticker=str.upper,
        fx_rate_provider=lambda source, target, day: 1.0,
    )
    lookups = []
    def fx(source, target, day):
        lookups.append((source, target, day))
        return 0.03
    add_quote_currency_rates(portfolio, ["AAPL", "2330.TW"], "2026-01-09", fx_rate_provider=fx)
    assert ("TWD", "USD", "2026-01-09") in lookups
    assert portfolio["quote_fx_rates"]["2330.TW"] == 0.03


def test_sec_filing_keeps_report_period_separate_from_availability(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "pytest app contact test@example.invalid")
    monkeypatch.setattr(sec_edgar, "_ticker_to_cik", lambda: {"ABC": "0000000001"})
    responses = [
        {"filings": {"recent": {"accessionNumber": ["x"], "filingDate": ["2026-01-06"],
          "acceptanceDateTime": ["2026-01-06T15:00:00.000Z"], "reportDate": ["2025-12-31"],
          "form": ["10-Q"], "primaryDocument": ["q.htm"]}}}
    ]
    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload
    monkeypatch.setattr(sec_edgar.requests, "get", lambda *args, **kwargs: Response(responses.pop(0)))
    sec_edgar._cached_sec_filing_availability.cache_clear()
    filing = sec_edgar.get_sec_filing_availability("ABC")[0]
    assert filing["report_period"] == "2025-12-31"
    assert filing["available_at"] == "2026-01-06T15:03:00Z"
    assert filing["source_id"] == "sec_edgar_submissions"
    sec_edgar._cached_sec_filing_availability.cache_clear()


def test_run_store_fingerprint_snapshots_and_atomic_cells(tmp_path):
    store = BacktestRunStore(str(tmp_path / "runs.sqlite3"))
    manifest = {"ticker": "AAPL", "fee": 0.001}
    assert store.create_or_resume("run-1", manifest)["resumed"] is False
    assert store.create_or_resume("run-1", manifest)["resumed"] is True
    with pytest.raises(ValueError, match="fingerprint"):
        store.create_or_resume("run-1", {"ticker": "AAPL", "fee": 0.002})
    store.save_snapshots("run-1", {"AAPL:price": [{"close": 10}]}, "fixture-v1")
    with pytest.raises(ValueError, match="immutable"):
        store.save_snapshots("run-1", {"AAPL:price": [{"close": 11}]}, "fixture-v2")
    assert store.commit_session("run-1", "2026-01-05", decisions={"AAPL": {"action": "hold"}},
                                portfolio_before={"cash": 100}, portfolio_after={"cash": 100}, prices={"AAPL": 10},
                                metrics={"fills": {}}, analyst_signals={"analyst": {"AAPL": {"signal": "neutral"}}})
    assert store.commit_session("run-1", "2026-01-05", decisions={}, portfolio_before={}, portfolio_after={}, prices={}, metrics={}) is False
    assert store.completed_sessions("run-1") == {"2026-01-05"}
    assert store.get_cells("run-1")[0]["analyst_signals"]["analyst"]["signal"] == "neutral"


def test_next_fill_respects_availability_and_rates_use_latest_eligible():
    prices = [
        {"time": "2026-01-05", "close": 10, "available_at": "2026-01-05T20:00:00Z"},
        {"time": "2026-01-06", "close": 11, "available_at": "2026-01-06T20:00:00Z"},
    ]
    assert _next_price(prices, datetime(2026, 1, 5, 19, tzinfo=timezone.utc))[1] == "2026-01-05"
    assert _next_price(prices, datetime(2026, 1, 5, 20, tzinfo=timezone.utc))[1] == "2026-01-06"
    rates = [{"date": "2026-01-06", "available_at": "2026-01-06T17:00:00Z", "rate": 2},
             {"date": "2026-01-05", "available_at": "2026-01-05T17:00:00Z", "rate": 1}]
    assert _rate_at(rates, datetime(2026, 1, 5, 18, tzinfo=timezone.utc)) == 1


def test_order_costs_apply_fee_and_slippage():
    portfolio = {"cash": 10000, "positions": {"AAPL": {"long": 0, "long_cost_basis": 0, "short": 0,
      "short_cost_basis": 0, "short_margin_used": 0}}, "margin_used": 0}
    fill = _execute_order(portfolio, "AAPL", "buy", 10, 100, 0.001, 0.01, 0.5)
    assert fill["fill_price"] == pytest.approx(101)
    assert fill["fee"] == pytest.approx(1.01)
    assert portfolio["positions"]["AAPL"]["long"] == 10


def test_backtest_grid_snapshots_once_resumes_and_never_signals_on_end_date(tmp_path, monkeypatch):
    import src.backtest_evaluation as backtest

    bars = []
    tw_bars = []
    for day, close in [("2026-01-02", 100), ("2026-01-05", 101), ("2026-01-06", 102),
                       ("2026-01-07", 103), ("2026-01-08", 104)]:
        bars.append({"time": day, "close": close, "available_at": f"{day}T21:00:00Z", "source_id": "fixture"})
        tw_bars.append({"time": day, "close": close, "available_at": f"{day}T05:30:00Z", "source_id": "fixture"})
    snapshots = {"AAPL:price": bars, "benchmark:SPY:price": bars,
                 "2330.TW:price": tw_bars, "benchmark:0050.TW:price": tw_bars,
                 "AAPL:corporate_actions": [], "2330.TW:corporate_actions": []}
    fetch_count = {"count": 0}
    def fetch_bundle(tickers, benchmarks, start, end, is_crypto):
        fetch_count["count"] += 1
        return snapshots, ["fixture"]
    monkeypatch.setattr(backtest, "_fetch_snapshot_bundle", fetch_bundle)
    monkeypatch.setattr(backtest, "_fetch_fx_series", lambda source, target, start, end: [
        {"date": day, "available_at": f"{day}T00:00:00Z", "rate": 1.0}
        for day in ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    ])
    calls = []
    def agent(**kwargs):
        calls.append(kwargs["end_date"])
        action = "buy" if len(calls) == 1 else "hold"
        decisions = {ticker: {"action": action, "quantity": 10} for ticker in kwargs["tickers"]}
        return {"decisions": decisions,
                "analyst_signals": {"fixture_analyst": {ticker: {"signal": "neutral"} for ticker in kwargs["tickers"]}}}

    store_path = str(tmp_path / "grid.sqlite3")
    result = backtest.run_backtest_grid(
        run_id="grid-1", tickers=["AAPL", "2330.TW"], start_date="2026-01-05", end_date="2026-01-08",
        cutoff_time_utc="16:00:00Z", agent=agent, initial_cash=100000, database_path=store_path,
        transaction_fee_rate=0.001, slippage_rate=0.0005,
    )
    assert result["completed_sessions"] == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert calls == result["completed_sessions"]
    assert result["portfolio"]["positions"]["AAPL"]["long"] == 10
    assert result["portfolio"]["positions"]["2330.TW"]["long"] == 10
    assert result["portfolio"]["pending_orders"] == []
    assert result["completed_ticker_date_cells"] == 6
    assert result["benchmark"]["weights"] == {"SPY": 0.5, "0050.TW": 0.5}
    assert result["coverage"]["dividend_cash_flows"] == "not_modeled"
    assert result["coverage"]["historical_universe"] == "current_registry_survivorship_biased"
    assert fetch_count["count"] == 1

    monkeypatch.setattr(backtest, "_fetch_snapshot_bundle", lambda *args: (_ for _ in ()).throw(AssertionError("must reuse saved inputs")))
    resumed = backtest.run_backtest_grid(
        run_id="grid-1", tickers=["AAPL", "2330.TW"], start_date="2026-01-05", end_date="2026-01-08",
        cutoff_time_utc="16:00:00Z", agent=agent, initial_cash=100000, database_path=store_path,
        transaction_fee_rate=0.001, slippage_rate=0.0005,
    )
    assert resumed == json.loads(json.dumps(result))
    assert len(calls) == 3


def test_future_split_is_reversed_and_historical_universe_is_disclosed():
    from src.tools.api import _reverse_future_split_adjustments
    from src.backtest_evaluation import _historical_share_basis
    price = Price(open=25, high=26, low=24, close=25, volume=400, time="2024-01-01")
    class SplitDate:
        def date(self):
            from datetime import date
            return date(2025, 1, 1)
    class Splits:
        empty = False
        def items(self): return [(SplitDate(), 4.0)]
    corrected = _reverse_future_split_adjustments([price], Splits(), "2024-12-31")[0]
    assert corrected.close == 100
    assert corrected.volume == 100
    with pytest.raises(ValueError, match="split history is unavailable"):
        _reverse_future_split_adjustments([price], None, "2024-12-31")
    with pytest.raises(ValueError, match="split history is unavailable"):
        _historical_share_basis([{"time": "2024-01-01", "close": 25}], [{"kind": "unavailable"}])
    _, report = filter_point_in_time([], cutoff="2026-01-01T00:00:00Z", strict=True)
    assert report["historical_universe"] == "current_registry_survivorship_biased"


def test_unmapped_instrument_reports_no_regional_benchmark():
    from src.backtest_evaluation import _benchmark_for
    assert _benchmark_for("BTC-USD") is None


def test_fx_rate_uses_precise_fill_availability_cutoff():
    rates = [
        {"date": "2026-01-05", "available_at": "2026-01-05T17:00:00Z", "rate": 1.0},
        {"date": "2026-01-06", "available_at": "2026-01-06T17:00:00Z", "rate": 2.0},
    ]
    assert _rate_at(rates, "2026-01-06T16:30:00Z") == 1.0
    assert _rate_at(rates, "2026-01-06T17:30:00Z") == 2.0


def test_short_position_nav_includes_collateral_and_marks_liability():
    from src.backtest_evaluation import _portfolio_value
    portfolio = {"cash": 10000, "margin_used": 0, "positions": {"AAPL": {
        "long": 0, "short": 0, "long_cost_basis": 0, "short_cost_basis": 0, "short_margin_used": 0,
    }}}
    _execute_order(portfolio, "AAPL", "short", 10, 100, 0, 0, 0.5)
    assert _portfolio_value(portfolio, {"AAPL": 100}) == pytest.approx(10000)
    assert _portfolio_value(portfolio, {"AAPL": 90}) == pytest.approx(10100)
    _execute_order(portfolio, "AAPL", "cover", 10, 90, 0, 0, 0.5)
    assert _portfolio_value(portfolio, {"AAPL": 90}) == pytest.approx(10100)


def test_portfolio_nav_marks_all_requested_tickers_before_sizing():
    from src.data.portfolio import mark_portfolio_to_market
    positions = {
        "AAPL": {"long": 10, "short": 0},
        "MSFT": {"long": 5, "short": 0},
    }
    nav = mark_portfolio_to_market(1000, 0, positions, {"AAPL": 100, "MSFT": 200})
    assert nav == 3000
