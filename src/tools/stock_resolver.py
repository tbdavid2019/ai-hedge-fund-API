"""
src/tools/stock_resolver.py

High-performance, multi-market stock resolver and company profile cache.
Supports:
1. US Stocks (SEC EDGAR 10,400+ listings + curated Chinese aliases + SpaceX/SPCX)
2. Hong Kong Stocks (HKEX official 3,200+ securities with native Traditional Chinese names)
3. Taiwan Stocks (TWSE 1,331 listed stocks [.TW] + TPEx 903 OTC stocks [.TWO])

Features:
- Fast in-memory hash maps (< 1ms lookup)
- Numeric ticker disambiguation (TW vs HK)
- Native Chinese & English company name resolution
- Anti-hallucination company profile & industry metadata binding
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Registries storage
_TWSE_REGISTRY: Dict[str, str] = {}
_TPEX_REGISTRY: Dict[str, str] = {}
_TW_NAME_TO_CODE: Dict[str, str] = {}

_HK_STOCKS: Dict[str, Dict[str, Any]] = {}
_HK_CODE_MAP: Dict[str, str] = {}
_HK_NAME_TO_CODE: Dict[str, str] = {}

_US_STOCKS: Dict[str, Dict[str, Any]] = {}
_US_NAME_TO_TICKER: Dict[str, str] = {}

_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}
_REGISTRIES_INITIALIZED: bool = False


def _find_data_dir() -> str:
    """Find absolute path to data directory across development and Docker environments."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(os.path.join(current_dir, "..", "..", "data")),
        os.path.abspath(os.path.join(current_dir, "..", "data")),
        os.path.abspath(os.path.join(current_dir, "data")),
        os.path.abspath(os.path.join(os.getcwd(), "data")),
        "/app/data",
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isdir(c):
            return c
    return candidates[0]


def init_registries():
    """Load and index US, HK, and TW stock registries into memory."""
    global _TWSE_REGISTRY, _TPEX_REGISTRY, _TW_NAME_TO_CODE
    global _HK_STOCKS, _HK_CODE_MAP, _HK_NAME_TO_CODE
    global _US_STOCKS, _US_NAME_TO_TICKER
    global _REGISTRIES_INITIALIZED

    if _REGISTRIES_INITIALIZED:
        return
    _REGISTRIES_INITIALIZED = True

    data_dir = _find_data_dir()

    # 1. Taiwan Registry (TWSE & TPEx)
    tw_file = os.path.join(data_dir, "tw_stock_registry.json")
    if os.path.exists(tw_file):
        try:
            with open(tw_file, "r", encoding="utf-8") as f:
                reg = json.load(f)
                stocks = reg.get("stocks", {})
                for code, info in stocks.items():
                    c = str(code).strip().upper()
                    market = info.get("market", "TWSE")
                    name = info.get("name", "").strip()
                    suffix = info.get("suffix", ".TW" if market == "TWSE" else ".TWO")
                    if market == "TWSE":
                        _TWSE_REGISTRY[c] = name
                    else:
                        _TPEX_REGISTRY[c] = name
                    if name:
                        _TW_NAME_TO_CODE[name] = f"{c}{suffix}"
        except Exception as e:
            logger.warning(f"[StockResolver] Failed to load {tw_file}: {e}")

    # 2. Hong Kong Registry (HKEX ListOfSecurities)
    hk_file = os.path.join(data_dir, "hk_stock_registry.json")
    if os.path.exists(hk_file):
        try:
            with open(hk_file, "r", encoding="utf-8") as f:
                reg = json.load(f)
                stocks = reg.get("stocks", {})
                for code, info in stocks.items():
                    _HK_STOCKS[code] = info
                    ticker = info.get("ticker", "")
                    int_code = info.get("int_code", "")
                    if ticker:
                        _HK_CODE_MAP[code] = ticker
                        if int_code:
                            _HK_CODE_MAP[int_code] = ticker
                            try:
                                _HK_CODE_MAP[f"{int(int_code):04d}"] = ticker
                            except Exception:
                                pass
                aliases = reg.get("aliases", {})
                for name, ticker in aliases.items():
                    _HK_NAME_TO_CODE[name] = ticker
        except Exception as e:
            logger.warning(f"[StockResolver] Failed to load {hk_file}: {e}")

    # 3. US Registry (SEC EDGAR + High-Frequency Curated Aliases)
    us_file = os.path.join(data_dir, "us_stock_registry.json")
    if os.path.exists(us_file):
        try:
            with open(us_file, "r", encoding="utf-8") as f:
                reg = json.load(f)
                _US_STOCKS.update(reg.get("stocks", {}))
                aliases = reg.get("aliases", {})
                for name, ticker in aliases.items():
                    _US_NAME_TO_TICKER[name] = ticker
        except Exception as e:
            logger.warning(f"[StockResolver] Failed to load {us_file}: {e}")


# High-priority manual overrides & common financial nicknames
KNOWN_TICKER_MAP: Dict[str, str] = {
    # SpaceX Nasdaq listing
    "SPACEX": "SPCX",
    "SPACE X": "SPCX",
    "SPCX": "SPCX",
    "太空探索": "SPCX",

    # Taiwan key bellwethers
    "TSMC": "2330.TW",
    "台積電": "2330.TW",
    "聯發科": "2454.TW",
    "鴻海": "2317.TW",
    "聯電": "2303.TW",
    "廣達": "2382.TW",
    "緯創": "3231.TW",
    "技嘉": "2376.TW",
    "華碩": "2357.TW",
    "富邦金": "2881.TW",
    "國泰金": "2882.TW",
    "中信金": "2891.TW",
    "兆豐金": "2886.TW",
    "長榮": "2603.TW",
    "陽明": "2609.TW",
    "萬海": "2615.TW",
    "儒鴻": "1476.TW",
    "聚陽": "1477.TW",
    "鈊象": "3293.TWO",
    "元太": "8069.TWO",
    "環球晶": "6488.TWO",
    "信驊": "5274.TWO",

    # US tech giants & bluechips
    "輝達": "NVDA",
    "英偉達": "NVDA",
    "特斯拉": "TSLA",
    "蘋果": "AAPL",
    "蘋果公司": "AAPL",
    "微軟": "MSFT",
    "亞馬遜": "AMZN",
    "谷歌": "GOOGL",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "臉書": "META",
    "META": "META",
    "超微": "AMD",
    "博通": "AVGO",
    "美光": "MU",
    "高通": "QCOM",
    "台積電ADR": "TSM",
    "台積電美股": "TSM",
    "波克夏": "BRK-B",
    "巴菲特公司": "BRK-B",
    "好市多": "COST",
    "星巴克": "SBUX",
    "網飛": "NFLX",
    "奈飛": "NFLX",
    "英特爾": "INTC",

    # Hong Kong key market leaders
    "騰訊": "0700.HK",
    "騰訊控股": "0700.HK",
    "阿里巴巴": "9988.HK",
    "阿里": "9988.HK",
    "美團": "3690.HK",
    "小米": "1810.HK",
    "小米集團": "1810.HK",
    "比亞迪": "1211.HK",
    "比亞迪股份": "1211.HK",
    "匯豐控股": "0005.HK",
    "匯豐": "0005.HK",
    "中芯國際": "0981.HK",
    "中芯": "0981.HK",
    "網易": "9999.HK",
    "京東": "9618.HK",
    "百度": "9888.HK",
    "快手": "1024.HK",
    "港交所": "0388.HK",
    "吉利汽車": "0175.HK",
}


def resolve_ticker(company_or_query: str) -> str:
    """
    Resolve company name or ticker query across US, Hong Kong, and Taiwan markets.
    
    Examples:
        - "1476" -> "1476.TW" (Taiwan TWSE)
        - "3293" -> "3293.TWO" (Taiwan TPEx OTC)
        - "700" -> "0700.HK" (Hong Kong HKEX)
        - "9988" -> "9988.HK" (Hong Kong HKEX)
        - "騰訊" -> "0700.HK"
        - "儒鴻" -> "1476.TW"
        - "鈊象" -> "3293.TWO"
        - "蘋果" -> "AAPL"
        - "SpaceX" -> "SPCX"
    """
    if not company_or_query:
        return ""
    
    init_registries()
    query = str(company_or_query).strip()
    upper_query = query.upper()

    # 1. Exact match in curated override map
    if upper_query in KNOWN_TICKER_MAP:
        return KNOWN_TICKER_MAP[upper_query]
    if query in KNOWN_TICKER_MAP:
        return KNOWN_TICKER_MAP[query]

    # Clean exchange prefixes
    clean_query = (
        upper_query.replace("NASDAQ:", "")
        .replace("NYSE:", "")
        .replace("TWSE:", "")
        .replace("TPEX:", "")
        .replace("HKEX:", "")
        .replace("HK:", "")
        .replace("TW:", "")
        .replace("US:", "")
        .strip()
    )
    if clean_query in KNOWN_TICKER_MAP:
        return KNOWN_TICKER_MAP[clean_query]

    # 2. Exact match in Registry Chinese Alias Dictionaries
    if query in _US_NAME_TO_TICKER:
        return _US_NAME_TO_TICKER[query]
    if upper_query in _US_NAME_TO_TICKER:
        return _US_NAME_TO_TICKER[upper_query]

    if query in _HK_NAME_TO_CODE:
        return _HK_NAME_TO_CODE[query]
    if upper_query in _HK_NAME_TO_CODE:
        return _HK_NAME_TO_CODE[upper_query]

    if query in _TW_NAME_TO_CODE:
        return _TW_NAME_TO_CODE[query]

    # 3. Already formatted with international market suffix
    if re.match(r"^\d{4,6}\.(TW|TWO|HK|SS|SZ)$", upper_query):
        return upper_query

    # 4. Explicit HK prefix/suffix pattern (e.g. "HK0700", "0700HK", "HK700")
    m_hk = re.search(r"\bHK(\d{3,5})\b", upper_query) or re.search(r"\b(\d{3,5})HK\b", upper_query)
    if m_hk:
        code_int = int(m_hk.group(1))
        return f"{code_int:04d}.HK"

    # 5. Numeric ticker resolution (Taiwan vs Hong Kong vs China)
    m_num = re.search(r"\b(\d{3,6}[A-Z]?)\b", upper_query)
    if m_num:
        c = m_num.group(1)

        # Starts with '0' or is 5 digits
        if c.startswith("0") or len(c) == 5:
            # Check Taiwan ETFs (0050, 0056, 00878, etc.)
            if c in _TWSE_REGISTRY:
                return f"{c}.TW"
            if c in _TPEX_REGISTRY:
                return f"{c}.TWO"
            # HK stock code (e.g. 00700 -> 0700.HK, 09988 -> 9988.HK)
            if c in _HK_CODE_MAP:
                return _HK_CODE_MAP[c]
            try:
                c_int = int(re.sub(r"\D", "", c))
                return f"{c_int:04d}.HK"
            except Exception:
                pass

        # 3-digit number (e.g. 700) -> HK stock
        if len(c) == 3 and c.isdigit():
            if c in _HK_CODE_MAP:
                return _HK_CODE_MAP[c]
            return f"{int(c):04d}.HK"

        # 4-digit number:
        # Check Taiwan TPEx first (OTC stocks like 3293, 8069)
        if c in _TPEX_REGISTRY:
            return f"{c}.TWO"
        # Check Taiwan TWSE (Listed stocks like 1476, 2330)
        if c in _TWSE_REGISTRY:
            return f"{c}.TW"

        # If not in Taiwan registry, check Hong Kong (e.g. 9988, 3690, 1211, 9618)
        if c in _HK_CODE_MAP:
            return _HK_CODE_MAP[c]

        # 6-digit number (China A-shares)
        if len(c) == 6 and c.isdigit():
            if c.startswith("6"):
                return f"{c}.SS"
            elif c.startswith(("0", "2", "3")):
                return f"{c}.SZ"

        # Default fallback for 4 digits is Taiwan TWSE
        return f"{c}.TW"

    # 6. US Ticker pattern (1-5 capital letters like NVDA, AAPL, SPCX)
    if re.match(r"^[A-Z]{1,5}$", upper_query):
        return upper_query

    # 7. Substring name matching across markets (Taiwan -> HK -> US)
    for name, ticker in _TW_NAME_TO_CODE.items():
        if len(name) >= 2 and (name == query or query in name or name in query):
            return ticker

    for name, ticker in _HK_NAME_TO_CODE.items():
        if len(name) >= 2 and (name == query or query in name or name in query):
            return ticker

    for name, ticker in _US_NAME_TO_TICKER.items():
        if len(name) >= 2 and (name == query or query in name or name in query):
            return ticker

    # 8. Live web search fallback via 2MD (if available)
    try:
        try:
            from tools.url2md import search_web_2md
        except ImportError:
            from src.tools.url2md import search_web_2md

        results = search_web_2md(f"{query} stock ticker 股票代碼", limit=3)
        for item in results:
            title = item.get("title", "")
            desc = item.get("description", "")
            # Check for standard suffix
            m_suf = re.search(r"\b(\d{4,6})\.(TW|TWO|HK)\b", title, re.I) or re.search(r"\b(\d{4,6})\.(TW|TWO|HK)\b", desc, re.I)
            if m_suf:
                return f"{m_suf.group(1)}.{m_suf.group(2).upper()}"
            # Check for US ticker in parenthesis (e.g. (AAPL))
            match = re.search(r"\(([A-Z]{1,5})\)", title) or re.search(r"\(([A-Z]{1,5})\)", desc)
            if match:
                return match.group(1)
            # Check for TW code
            tw_code_match = re.search(r"\b(\d{4,6})\b", title) or re.search(r"\b(\d{4,6})\b", desc)
            if tw_code_match:
                cand = tw_code_match.group(1)
                if cand in _TPEX_REGISTRY:
                    return f"{cand}.TWO"
                if cand in _TWSE_REGISTRY:
                    return f"{cand}.TW"
    except Exception:
        pass

    return upper_query


def get_company_profile(ticker: str) -> Dict[str, Any]:
    """
    Retrieve standardized company profile & metadata for anti-hallucination.
    Includes official Chinese/English name, market/exchange, sector, industry, and summary.
    """
    global _PROFILE_CACHE
    if ticker in _PROFILE_CACHE:
        return _PROFILE_CACHE[ticker]

    init_registries()
    clean_t = ticker.strip().upper()
    clean_c = re.sub(r"\.(TW|TWO|HK|SS|SZ)$", "", clean_t, flags=re.I).strip()

    tw_name = _TWSE_REGISTRY.get(clean_c) or _TPEX_REGISTRY.get(clean_c) or _TW_NAME_TO_CODE.get(ticker)
    hk_info = _HK_STOCKS.get(f"{int(clean_c):05d}") if (clean_t.endswith(".HK") and clean_c.isdigit()) else None
    us_info = _US_STOCKS.get(clean_t)

    # Special case: SpaceX
    if clean_t in ("SPCX", "SPACEX"):
        profile = {
            "ticker": "SPCX",
            "name": "Space Exploration Technologies Corp. (SpaceX / 太空探索)",
            "market": "NASDAQ",
            "sector": "Industrials / Aerospace & Defense",
            "industry": "Commercial Spaceflight, Satellite Telecom (Starlink) & Deep Space Systems",
            "business_summary": "Space Exploration Technologies Corp. (SpaceX) designs, manufactures, and launches advanced rockets and spacecraft, operating Falcon 9, Falcon Heavy, Starship, and the Starlink satellite internet constellation.",
        }
        _PROFILE_CACHE[ticker] = profile
        return profile

    market_name = "Global Market"
    display_name = ticker

    if tw_name:
        market_name = "TWSE (台灣證券交易所)" if clean_t.endswith(".TW") else "TPEx (證券櫃檯買賣中心)"
        display_name = f"{tw_name} ({clean_t})"
    elif hk_info:
        market_name = "HKEX (香港交易所)"
        c_name = hk_info.get("name", "")
        display_name = f"{c_name} ({clean_t})"
    elif us_info:
        market_name = "US Market (NYSE/NASDAQ)"
        display_name = f"{us_info.get('name', clean_t)} ({clean_t})"

    sector = "N/A"
    industry = "N/A"
    summary = "N/A"

    # Optional yfinance enrichment
    try:
        import yfinance as yf
        t_obj = yf.Ticker(clean_t)
        info = t_obj.info or {}
        long_name = info.get("longName") or info.get("shortName")
        if long_name and long_name != clean_t:
            if tw_name:
                display_name = f"{tw_name} ({long_name})"
            elif hk_info:
                display_name = f"{hk_info.get('name', '')} ({long_name})"
            elif not us_info:
                display_name = f"{long_name} ({clean_t})"

        sector = info.get("sector") or sector
        industry = info.get("industry") or industry
        raw_summary = info.get("longBusinessSummary")
        if raw_summary:
            summary = raw_summary[:400] + "..." if len(raw_summary) > 400 else raw_summary
    except Exception:
        pass

    profile = {
        "ticker": clean_t,
        "name": display_name,
        "market": market_name,
        "sector": sector,
        "industry": industry,
        "business_summary": summary,
    }
    _PROFILE_CACHE[ticker] = profile
    return profile
