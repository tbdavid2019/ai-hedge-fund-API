from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

import webui2


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webui2, "resolve_ticker", lambda ticker: ticker)
    return webui2.app.test_client()


@pytest.mark.parametrize("path", ["/api/analysis", "/api/analysis/async"])
def test_analysis_routes_reject_unknown_analyst_before_work(client, monkeypatch, path):
    def unexpected_work(*args, **kwargs):
        pytest.fail("analysis work must not start for an unknown analyst key")

    monkeypatch.setattr(webui2, "run_hedge_fund", unexpected_work)
    response = client.post(path, json={"tickers": ["MSFT"], "selectedAnalysts": ["technicals"]})

    assert response.status_code == 400
    assert "technicals" in response.get_json()["error"]


def test_backtest_grid_rejects_unknown_analyst_before_creating_run(client, monkeypatch):
    def unexpected_work(**kwargs):
        pytest.fail("backtest run must not start for an unknown analyst key")

    monkeypatch.setattr(webui2, "run_backtest_grid", unexpected_work)
    response = client.post("/api/backtest/grid", json={
        "runId": "invalid-analyst-test",
        "tickers": ["MSFT"],
        "startDate": "2026-01-01",
        "endDate": "2026-01-03",
        "selectedAnalysts": ["technicals"],
    })

    assert response.status_code == 400
    assert "technicals" in response.get_json()["error"]


def test_backtest_grid_rejects_non_array_analyst_selection(client, monkeypatch):
    def unexpected_work(**kwargs):
        pytest.fail("backtest run must not start for a malformed analyst selection")

    monkeypatch.setattr(webui2, "run_backtest_grid", unexpected_work)
    response = client.post("/api/backtest/grid", json={
        "runId": "non-array-analyst-test",
        "tickers": ["MSFT"],
        "startDate": "2026-01-01",
        "endDate": "2026-01-03",
        "selectedAnalysts": "technical_analyst",
    })

    assert response.status_code == 400
    assert "must be an array" in response.get_json()["error"]


def test_backtest_grid_rejects_explicit_null_analyst_selection(client, monkeypatch):
    def unexpected_work(**kwargs):
        pytest.fail("backtest run must not start for a null analyst selection")

    monkeypatch.setattr(webui2, "run_backtest_grid", unexpected_work)
    response = client.post("/api/backtest/grid", json={
        "runId": "null-analyst-test",
        "tickers": ["MSFT"],
        "startDate": "2026-01-01",
        "endDate": "2026-01-03",
        "selectedAnalysts": None,
    })

    assert response.status_code == 400
    assert "must be an array" in response.get_json()["error"]
