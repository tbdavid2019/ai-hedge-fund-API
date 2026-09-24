"""SEC EDGAR submissions adapter for trustworthy US filing availability times."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def _headers() -> dict[str, str]:
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not user_agent:
        raise RuntimeError("SEC_USER_AGENT must identify the application and provide a contact address")
    return {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate", "Host": "data.sec.gov"}


@lru_cache(maxsize=1)
def _ticker_to_cik() -> dict[str, str]:
    headers = _headers()
    response = requests.get(SEC_TICKERS_URL, headers={**headers, "Host": "www.sec.gov"}, timeout=15)
    response.raise_for_status()
    payload = response.json()
    return {
        str(item.get("ticker", "")).upper(): f"{int(item['cik_str']):010d}"
        for item in payload.values()
        if item.get("ticker") and item.get("cik_str")
    }


@lru_cache(maxsize=1024)
def _cached_sec_filing_availability(symbol: str) -> tuple[dict[str, Any], ...]:
    """Return filing metadata with SEC acceptance time separate from report period."""
    if not symbol or "." in symbol:
        return ()
    cik = _ticker_to_cik().get(symbol)
    if not cik:
        return ()
    response = requests.get(SEC_SUBMISSIONS_URL.format(cik=cik), headers=_headers(), timeout=15)
    response.raise_for_status()
    recent = response.json().get("filings", {}).get("recent", {})
    fields = (
        "accessionNumber",
        "filingDate",
        "acceptanceDateTime",
        "reportDate",
        "form",
        "primaryDocument",
    )
    count = min((len(recent.get(field, [])) for field in fields), default=0)
    output = []
    for index in range(count):
        acceptance_value = recent["acceptanceDateTime"][index]
        if not acceptance_value:
            continue
        accepted_at = datetime.fromisoformat(acceptance_value.replace("Z", "+00:00"))
        if accepted_at.tzinfo is None:
            accepted_at = accepted_at.replace(tzinfo=ZoneInfo("America/New_York"))
        # EDGAR notes accepted filings may take 1–3 minutes to appear publicly;
        # add a conservative 3-minute dissemination buffer to the acceptance time.
        available_at = (accepted_at + timedelta(minutes=3)).isoformat().replace("+00:00", "Z")
        filing_date = recent["filingDate"][index]
        output.append({
            "ticker": symbol,
            "form": recent["form"][index],
            "report_period": recent["reportDate"][index] or None,
            "business_date": recent["reportDate"][index] or None,
            "filing_date": filing_date,
            "available_at": available_at,
            "source_id": "sec_edgar_submissions",
            "point_in_time_status": "verified",
            "accession_number": recent["accessionNumber"][index],
            "primary_document": recent["primaryDocument"][index],
        })
    return tuple(output)


def get_sec_filing_availability(ticker: str) -> list[dict[str, Any]]:
    """Return filing metadata with SEC acceptance time separate from report period."""
    return [dict(record) for record in _cached_sec_filing_availability(ticker.strip().upper())]
