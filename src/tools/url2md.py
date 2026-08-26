"""
2md (888 URL to Markdown) Service Integration
Provides clean Markdown conversion, live web search, and social sentiment data fetching
with automatic fallback across primary and backup endpoints.
"""

import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Endpoints priority: Primary -> Fallback 1 -> Fallback 2
ENDPOINTS = [
    "https://2md.aiurl.tw",
    "https://2md.glsoft.ai",
    "https://create360.ai",
]


def _make_request(path: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 15) -> Optional[requests.Response]:
    """Execute HTTP GET with automatic failover across endpoints."""
    req_headers = {"User-Agent": "ai-hedge-fund/2.0", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    for base_url in ENDPOINTS:
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            resp = requests.get(url, params=params, headers=req_headers, timeout=timeout)
            if resp.status_code == 200:
                return resp
            logger.warning(f"[2md] {base_url} returned status {resp.status_code}")
        except Exception as e:
            logger.warning(f"[2md] {base_url} request failed: {e}")
            continue
    return None


def search_web_2md(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Perform live web search via 2md SERP search API.
    Returns list of items with title, url, description, and content.
    """
    resp = _make_request("search", params={"q": query})
    if not resp:
        # Try path-based search fallback
        resp = _make_request(f"s/{requests.utils.quote(query)}")
    
    if not resp:
        return []

    try:
        data = resp.json()
        if isinstance(data, dict):
            items = data.get("data", [])
            if isinstance(items, list):
                return items[:limit]
        elif isinstance(data, list):
            return data[:limit]
    except Exception as e:
        logger.error(f"[2md] Failed to parse search response: {e}")

    return []


def fetch_url_markdown_2md(target_url: str) -> str:
    """
    Fetch a single URL and convert it to clean Markdown using 2md service.
    """
    resp = _make_request(target_url, headers={"Accept": "text/plain"})
    if resp and resp.text:
        return resp.text
    return ""


def get_social_and_news_2md(ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for recent financial news and social discussions for a given stock/crypto ticker.
    Combines general news search and social forum search.
    """
    results: List[Dict[str, Any]] = []
    seen_urls = set()

    queries = [
        f"{ticker} stock news analysis",
        f"{ticker} reddit wallstreetbets",
        f"{ticker} investment discussion",
    ]

    for q in queries:
        items = search_web_2md(q, limit=limit)
        for item in items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                results.append({
                    "title": item.get("title", ""),
                    "url": url,
                    "description": item.get("description", ""),
                    "source": "2md_web",
                })
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    return results
