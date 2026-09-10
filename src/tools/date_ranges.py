"""Date-range helpers shared by data providers."""

from datetime import datetime, timedelta


def exclusive_end_date(end_date: str) -> str:
    """Return the next midnight for an inclusive YYYY-MM-DD end date."""
    return (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
