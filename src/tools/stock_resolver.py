"""
src/tools/stock_resolver.py

High-performance, multi-market global stock resolver with SWR (Stale-While-Revalidate)
Double-Buffering cache engine.

Covered Global Market Pillars (~32,000+ Listings):
1. 🇹🇼 Taiwan (TWSE listed [.TW] + TPEx OTC [.TWO])
2. 🇺🇸 United States (SEC EDGAR: NASDAQ, NYSE, AMEX, ARCA, BATS, IEX + CIK + SPCX)
3. 🇭🇰 Hong Kong (HKEX equities, ETFs, REITs with native Traditional Chinese names)
4. 🇨🇳 China A-Shares (SSE Shanghai [.SS] + SZSE Shenzhen [.SZ])
5. 🇯🇵 Japan (JPX Tokyo Stock Exchange [.T])
6. 🇪🇺 Europe (Euronext: Paris [.PA], Amsterdam [.AS], Brussels [.BR], Lisbon [.LS], Oslo [.OL])
7. 🇬🇧 United Kingdom (LSE London Stock Exchange [.L])

Architectural Highlights:
- Asynchronous Double-Buffering (SWR): Caller never waits on network update; returns existing cache in < 1ms.
- Taipei Calendar Day Boundary: Triggered on first request of the day after 00:00 (Asia/Taipei).
- Single-Flight Protection: Concurrent requests are merged; only one background worker runs.
- Graceful Degradation: Preserves previous data and flags stale=True if an upstream source fails.
"""

import os
import re
import json
import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Registry in-memory stores
_TWSE_REGISTRY: Dict[str, str] = {}
_TPEX_REGISTRY: Dict[str, str] = {}
_TW_NAME_TO_CODE: Dict[str, str] = {}

_HK_STOCKS: Dict[str, Dict[str, Any]] = {}
_HK_CODE_MAP: Dict[str, str] = {}
_HK_NAME_TO_CODE: Dict[str, str] = {}

_US_STOCKS: Dict[str, Dict[str, Any]] = {}
_US_NAME_TO_TICKER: Dict[str, str] = {}

_CN_STOCKS: Dict[str, Dict[str, Any]] = {}
_CN_NAME_TO_TICKER: Dict[str, str] = {}

_JP_STOCKS: Dict[str, Dict[str, Any]] = {}
_JP_NAME_TO_TICKER: Dict[str, str] = {}

_EU_STOCKS: Dict[str, Dict[str, Any]] = {}
_EU_NAME_TO_TICKER: Dict[str, str] = {}

_UK_STOCKS: Dict[str, Dict[str, Any]] = {}
_UK_NAME_TO_TICKER: Dict[str, str] = {}

_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}

# SWR Double-Buffering State
_REGISTRIES_INITIALIZED: bool = False
_IS_UPDATING: bool = False
_IS_STALE: bool = False
_LAST_UPDATE_DATE_TAIPEI: str = ""
_UPDATE_MUTEX = threading.Lock()


def _find_data_dir() -> str:
    """Locate data directory across dev, local, and Docker container paths."""
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


def init_registries(force_reload: bool = False):
    """Load or reload all 7 global stock registries into memory."""
    global _TWSE_REGISTRY, _TPEX_REGISTRY, _TW_NAME_TO_CODE
    global _HK_STOCKS, _HK_CODE_MAP, _HK_NAME_TO_CODE
    global _US_STOCKS, _US_NAME_TO_TICKER
    global _CN_STOCKS, _CN_NAME_TO_TICKER
    global _JP_STOCKS, _JP_NAME_TO_TICKER
    global _EU_STOCKS, _EU_NAME_TO_TICKER
    global _UK_STOCKS, _UK_NAME_TO_TICKER
    global _REGISTRIES_INITIALIZED, _LAST_UPDATE_DATE_TAIPEI

    if _REGISTRIES_INITIALIZED and not force_reload:
        return

    data_dir = _find_data_dir()

    # 1. Taiwan (TWSE & TPEx)
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

    # 2. Hong Kong (HKEX)
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

    # 3. US (SEC EDGAR)
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

    # 4. China A-Shares (SSE & SZSE)
    cn_file = os.path.join(data_dir, "cn_stock_registry.json")
    if os.path.exists(cn_file):
        try:
            with open(cn_file, "r", encoding="utf-8") as f:
                reg = json.load(f)
                _CN_STOCKS.update(reg.get("stocks", {}))
                aliases = reg.get("aliases", {})
                for name, ticker in aliases.items():
                    _CN_NAME_TO_TICKER[name] = ticker
        except Exception as e:
            logger.warning(f"[StockResolver] Failed to load {cn_file}: {e}")

    # 5. Japan (JPX)
    jp_file = os.path.join(data_dir, "jp_stock_registry.json")
    if os.path.exists(jp_file):
        try:
            with open(jp_file, "r", encoding="utf-8") as f:
                reg = json.load(f)
                _JP_STOCKS.update(reg.get("stocks", {}))
                aliases = reg.get("aliases", {})
                for name, ticker in aliases.items():
                    _JP_NAME_TO_TICKER[name] = ticker
        except Exception as e:
            logger.warning(f"[StockResolver] Failed to load {jp_file}: {e}")

    # 6. Europe (Euronext)
    eu_file = os.path.join(data_dir, "eu_stock_registry.json")
    if os.path.exists(eu_file):
        try:
            with open(eu_file, "r", encoding="utf-8") as f:
                reg = json.load(f)
                _EU_STOCKS.update(reg.get("stocks", {}))
                aliases = reg.get("aliases", {})
                for name, ticker in aliases.items():
                    _EU_NAME_TO_TICKER[name] = ticker
        except Exception as e:
            logger.warning(f"[StockResolver] Failed to load {eu_file}: {e}")

    # 7. United Kingdom (LSE)
    uk_file = os.path.join(data_dir, "uk_stock_registry.json")
    if not os.path.exists(uk_file):
        uk_file = os.path.join(data_dir, "lse_stock_registry.json")
    if os.path.exists(uk_file):
        try:
            with open(uk_file, "r", encoding="utf-8") as f:
                reg = json.load(f)
                _UK_STOCKS.update(reg.get("stocks", {}))
                aliases = reg.get("aliases", {})
                for name, ticker in aliases.items():
                    _UK_NAME_TO_TICKER[name] = ticker
        except Exception as e:
            logger.warning(f"[StockResolver] Failed to load {uk_file}: {e}")

    _REGISTRIES_INITIALIZED = True
    if not _LAST_UPDATE_DATE_TAIPEI:
        now_taipei = datetime.now(ZoneInfo("Asia/Taipei"))
        _LAST_UPDATE_DATE_TAIPEI = now_taipei.strftime("%Y-%m-%d")


def check_and_trigger_swr_update():
    """
    SWR Trigger:
    On the first request after 00:00 Asia/Taipei, spawn background thread to refresh registries.
    Single-Flight: Guarantees only one thread runs; all callers immediately use existing cache.
    """
    global _IS_UPDATING, _LAST_UPDATE_DATE_TAIPEI
    now_taipei = datetime.now(ZoneInfo("Asia/Taipei"))
    today_taipei = now_taipei.strftime("%Y-%m-%d")

    if _LAST_UPDATE_DATE_TAIPEI != today_taipei and not _IS_UPDATING:
        with _UPDATE_MUTEX:
            if _LAST_UPDATE_DATE_TAIPEI != today_taipei and not _IS_UPDATING:
                _IS_UPDATING = True
                worker = threading.Thread(
                    target=_background_refresh_worker,
                    args=(today_taipei,),
                    daemon=True,
                    name="GlobalRegistrySWRWorker"
                )
                worker.start()
                logger.info(f"[SWR] Started background registry update for Taipei date {today_taipei}")


def _background_refresh_worker(target_date: str):
    """Background worker for non-blocking registry revalidation."""
    global _IS_UPDATING, _LAST_UPDATE_DATE_TAIPEI, _IS_STALE
    try:
        from scripts.update_stock_registries import update_all_registries
        results = update_all_registries()
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"[SWR] Background refresh finished: {results} ({success_count}/{len(results)} successful)")

        # Reload newly written files into memory
        init_registries(force_reload=True)
        _LAST_UPDATE_DATE_TAIPEI = target_date
        _IS_STALE = not all(results.values())
    except Exception as e:
        logger.error(f"[SWR] Background update encountered exception: {e}")
        _IS_STALE = True
    finally:
        _IS_UPDATING = False


def get_registry_status() -> Dict[str, Any]:
    """Return live diagnostics on the global stock cache and SWR double-buffering state."""
    init_registries()
    check_and_trigger_swr_update()
    now_taipei = datetime.now(ZoneInfo("Asia/Taipei"))

    total = (
        len(_TWSE_REGISTRY) + len(_TPEX_REGISTRY) +
        len(_US_STOCKS) + len(_HK_STOCKS) +
        len(_CN_STOCKS) + len(_JP_STOCKS) +
        len(_EU_STOCKS) + len(_UK_STOCKS)
    )

    return {
        "timezone": "Asia/Taipei",
        "current_time_taipei": now_taipei.isoformat(),
        "registry_date_taipei": _LAST_UPDATE_DATE_TAIPEI,
        "is_updating": _IS_UPDATING,
        "stale": _IS_STALE,
        "total_securities": total,
        "markets": {
            "TW_TWSE": len(_TWSE_REGISTRY),
            "TW_TPEX": len(_TPEX_REGISTRY),
            "US_SEC_ALL": len(_US_STOCKS),
            "HK_HKEX": len(_HK_STOCKS),
            "CN_A_SHARES": len(_CN_STOCKS),
            "JP_JPX": len(_JP_STOCKS),
            "EU_EURONEXT": len(_EU_STOCKS),
            "UK_LSE": len(_UK_STOCKS),
        }
    }


# High-priority manual overrides & common financial nicknames
KNOWN_TICKER_MAP: Dict[str, str] = {
    # SpaceX NASDAQ listing
    "SPACEX": "SPCX",
    "SPACE X": "SPCX",
    "SPCX": "SPCX",
    "太空探索": "SPCX",

    # Taiwan key bellwethers
    "TSMC": "2330.TW", "台積電": "2330.TW", "聯發科": "2454.TW", "鴻海": "2317.TW",
    "聯電": "2303.TW", "廣達": "2382.TW", "緯創": "3231.TW", "技嘉": "2376.TW",
    "華碩": "2357.TW", "富邦金": "2881.TW", "國泰金": "2882.TW", "中信金": "2891.TW",
    "兆豐金": "2886.TW", "長榮": "2603.TW", "陽明": "2609.TW", "萬海": "2615.TW",
    "儒鴻": "1476.TW", "聚陽": "1477.TW", "鈊象": "3293.TWO", "元太": "8069.TWO",
    "環球晶": "6488.TWO", "信驊": "5274.TWO",

    # US tech giants & bluechips
    "輝達": "NVDA", "英偉達": "NVDA", "特斯拉": "TSLA", "蘋果": "AAPL", "蘋果公司": "AAPL",
    "微軟": "MSFT", "亞馬遜": "AMZN", "谷歌": "GOOGL", "GOOGLE": "GOOGL", "ALPHABET": "GOOGL",
    "臉書": "META", "META": "META", "超微": "AMD", "博通": "AVGO", "美光": "MU",
    "高通": "QCOM", "台積電ADR": "TSM", "台積電美股": "TSM", "波克夏": "BRK-B",
    "巴菲特公司": "BRK-B", "好市多": "COST", "星巴克": "SBUX", "網飛": "NFLX",
    "奈飛": "NFLX", "英特爾": "INTC",

    # Hong Kong key market leaders
    "騰訊": "0700.HK", "騰訊控股": "0700.HK", "阿里巴巴": "9988.HK", "阿里": "9988.HK",
    "美團": "3690.HK", "小米": "1810.HK", "小米集團": "1810.HK", "比亞迪": "1211.HK",
    "比亞迪股份": "1211.HK", "匯豐控股": "0005.HK", "匯豐": "0005.HK", "中芯國際": "0981.HK",
    "中芯": "0981.HK", "網易": "9999.HK", "京東": "9618.HK", "百度": "9888.HK",
    "快手": "1024.HK", "港交所": "0388.HK", "吉利汽車": "0175.HK",

    # China A-Shares leaders
    "茅台": "600519.SS", "貴州茅台": "600519.SS", "五糧液": "000858.SZ",
    "寧德時代": "300750.SZ", "比亞迪A股": "002594.SZ", "中國平安": "601318.SS",
    "招商銀行": "600036.SS", "長江電力": "600900.SS",

    # Japan leaders
    "豐田": "7203.T", "豐田汽車": "7203.T", "TOYOTA": "7203.T",
    "索尼": "6758.T", "SONY": "6758.T",
    "軟銀": "9984.T", "軟銀集團": "9984.T", "SOFTBANK": "9984.T",
    "任天堂": "7974.T", "NINTENDO": "7974.T",
    "三菱日聯": "8306.T", "MUFG": "8306.T",
    "優衣庫": "9983.T", "UNIQLO": "9983.T", "迅銷": "9983.T",

    # Europe leaders
    "LVMH": "MC.PA", "路易威登": "MC.PA", "ASML歐股": "ASML.AS",
    "歐萊雅": "OR.PA", "愛馬仕": "RMS.PA", "空中巴士": "AIR.PA",

    # UK leaders
    "殼牌": "SHEL.L", "阿斯利康": "AZN.L", "匯豐倫敦": "HSBA.L", "英國石油": "BP.L",
}


def resolve_ticker(company_or_query: str) -> str:
    """
    Resolve company name or ticker query across 7 global market pillars.
    
    Examples:
        - "1476" -> "1476.TW" (Taiwan TWSE)
        - "3293" -> "3293.TWO" (Taiwan TPEx)
        - "700" -> "0700.HK" (Hong Kong HKEX)
        - "9988" -> "9988.HK" (Hong Kong HKEX)
        - "600519" -> "600519.SS" (Shanghai SSE)
        - "000858" -> "000858.SZ" (Shenzhen SZSE)
        - "7203" -> "7203.T" (Tokyo JPX)
        - "MC" -> "MC.PA" (Euronext)
        - "SHEL" -> "SHEL.L" (LSE)
        - "豐田" -> "7203.T"
        - "茅台" -> "600519.SS"
        - "騰訊" -> "0700.HK"
        - "蘋果" -> "AAPL"
        - "SpaceX" -> "SPCX"
    """
    if not company_or_query:
        return ""

    init_registries()
    check_and_trigger_swr_update()

    query = str(company_or_query).strip()
    upper_query = query.upper()

    # 1. Exact match in curated override map
    if upper_query in KNOWN_TICKER_MAP:
        return KNOWN_TICKER_MAP[upper_query]
    if query in KNOWN_TICKER_MAP:
        return KNOWN_TICKER_MAP[query]

    # 1.5 Handle explicit exchange prefixes
    if upper_query.startswith(("LSE:", "UK:")):
        code = re.sub(r"^(LSE|UK):", "", upper_query).strip()
        clean_code = re.sub(r"^(LSE|UK):", "", str(company_or_query).strip(), flags=re.I).strip()
        if code in _UK_STOCKS:
            return _UK_STOCKS[code]["ticker"]
        if clean_code in _UK_NAME_TO_TICKER:
            return _UK_NAME_TO_TICKER[clean_code]
        if code in _UK_NAME_TO_TICKER:
            return _UK_NAME_TO_TICKER[code]
        if clean_code in KNOWN_TICKER_MAP:
            return KNOWN_TICKER_MAP[clean_code]
        return f"{code}.L"

    if upper_query.startswith(("EURONEXT:", "EU:")):
        code = re.sub(r"^(EURONEXT|EU):", "", upper_query).strip()
        clean_code = re.sub(r"^(EURONEXT|EU):", "", str(company_or_query).strip(), flags=re.I).strip()
        if clean_code in _EU_NAME_TO_TICKER:
            return _EU_NAME_TO_TICKER[clean_code]
        if code in _EU_NAME_TO_TICKER:
            return _EU_NAME_TO_TICKER[code]
        if clean_code in KNOWN_TICKER_MAP:
            return KNOWN_TICKER_MAP[clean_code]
        if code in _EU_STOCKS:
            return _EU_STOCKS[code]["ticker"]
        return f"{code}.PA"

    if upper_query.startswith(("JPX:", "JP:")):
        code = re.sub(r"^(JPX|JP):", "", upper_query).strip()
        clean_code = re.sub(r"^(JPX|JP):", "", str(company_or_query).strip(), flags=re.I).strip()
        if clean_code in KNOWN_TICKER_MAP:
            return KNOWN_TICKER_MAP[clean_code]
        if code in _JP_STOCKS:
            return f"{code}.T"
        if clean_code in _JP_NAME_TO_TICKER:
            return _JP_NAME_TO_TICKER[clean_code]
        return f"{code}.T"

    if upper_query.startswith("SSE:"):
        code = upper_query.replace("SSE:", "").strip()
        return f"{code}.SS"

    if upper_query.startswith("SZSE:"):
        code = upper_query.replace("SZSE:", "").strip()
        return f"{code}.SZ"

    if upper_query.startswith("TWSE:"):
        code = upper_query.replace("TWSE:", "").strip()
        clean_code = re.sub(r"^TWSE:", "", str(company_or_query).strip(), flags=re.I).strip()
        if clean_code in KNOWN_TICKER_MAP:
            return KNOWN_TICKER_MAP[clean_code]
        if clean_code in _TW_NAME_TO_CODE:
            return _TW_NAME_TO_CODE[clean_code]
        return f"{code}.TW"

    if upper_query.startswith("TPEX:"):
        code = upper_query.replace("TPEX:", "").strip()
        clean_code = re.sub(r"^TPEX:", "", str(company_or_query).strip(), flags=re.I).strip()
        if clean_code in KNOWN_TICKER_MAP:
            return KNOWN_TICKER_MAP[clean_code]
        if clean_code in _TW_NAME_TO_CODE:
            return _TW_NAME_TO_CODE[clean_code]
        return f"{code}.TWO"

    if upper_query.startswith(("HKEX:", "HK:")):
        code = re.sub(r"^(HKEX|HK):", "", upper_query).strip()
        clean_code = re.sub(r"^(HKEX|HK):", "", str(company_or_query).strip(), flags=re.I).strip()
        if clean_code in KNOWN_TICKER_MAP:
            return KNOWN_TICKER_MAP[clean_code]
        if clean_code in _HK_NAME_TO_CODE:
            return _HK_NAME_TO_CODE[clean_code]
        if code in _HK_CODE_MAP:
            return _HK_CODE_MAP[code]
        try:
            return f"{int(code):04d}.HK"
        except Exception:
            return f"{code}.HK"

    # Clean exchange prefixes for generic matching
    clean_query = (
        upper_query.replace("NASDAQ:", "")
        .replace("NYSE:", "")
        .replace("TWSE:", "")
        .replace("TPEX:", "")
        .replace("HKEX:", "")
        .replace("JPX:", "")
        .replace("SSE:", "")
        .replace("SZSE:", "")
        .replace("EURONEXT:", "")
        .replace("LSE:", "")
        .replace("HK:", "")
        .replace("TW:", "")
        .replace("US:", "")
        .strip()
    )
    if clean_query in KNOWN_TICKER_MAP:
        return KNOWN_TICKER_MAP[clean_query]


    # 2. Exact match in Registry Chinese Alias Dictionaries
    for alias_dict in (
        _US_NAME_TO_TICKER,
        _HK_NAME_TO_CODE,
        _TW_NAME_TO_CODE,
        _CN_NAME_TO_TICKER,
        _JP_NAME_TO_TICKER,
        _EU_NAME_TO_TICKER,
        _UK_NAME_TO_TICKER,
    ):
        if query in alias_dict:
            return alias_dict[query]
        if upper_query in alias_dict:
            return alias_dict[upper_query]

    # 3. Already formatted with international market suffix
    if re.match(r"^[A-Z0-9.\-_]{1,12}\.(TW|TWO|HK|SS|SZ|T|PA|AS|BR|LS|OL|MI|L)$", upper_query):
        return upper_query

    # 4. Explicit HK prefix/suffix pattern (e.g. "HK0700", "0700HK", "HK700")
    m_hk = re.search(r"\bHK(\d{3,5})\b", upper_query) or re.search(r"\b(\d{3,5})HK\b", upper_query)
    if m_hk:
        code_int = int(m_hk.group(1))
        return f"{code_int:04d}.HK"

    # 5. Numeric ticker resolution (Taiwan vs Hong Kong vs China vs Japan)
    m_num = re.search(r"\b(\d{3,6}[A-Z]?)\b", upper_query)
    if m_num:
        c = m_num.group(1)

        # Starts with '0' or is 5 digits
        if c.startswith("0") or len(c) == 5:
            if c in _TWSE_REGISTRY:
                return f"{c}.TW"
            if c in _TPEX_REGISTRY:
                return f"{c}.TWO"
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

        # 6-digit number: China A-shares (Shanghai 6xxxx, Shenzhen 0xxxx, 2xxxx, 3xxxx)
        if len(c) == 6 and c.isdigit():
            if c in _CN_STOCKS:
                return _CN_STOCKS[c]["ticker"]
            if c.startswith("6"):
                return f"{c}.SS"
            elif c.startswith(("0", "2", "3")):
                return f"{c}.SZ"

        # 4-digit number:
        # 1. Taiwan TPEx OTC (e.g. 3293, 8069)
        if c in _TPEX_REGISTRY:
            return f"{c}.TWO"
        # 2. Taiwan TWSE Listed (e.g. 1476, 2330)
        if c in _TWSE_REGISTRY:
            return f"{c}.TW"
        # 3. Hong Kong HKEX (e.g. 9988, 3690, 1211, 1810)
        if c in _HK_CODE_MAP:
            return _HK_CODE_MAP[c]
        # 4. Japan JPX (e.g. 7203, 6758, 9984)
        if c in _JP_STOCKS:
            return f"{c}.T"

        # Fallback 4 digits -> Taiwan TWSE
        return f"{c}.TW"

    # 6. Global Ticker Patterns
    # US Stock direct match (takes precedence for standard US symbols like NVDA, AAPL, SHEL, AZN)
    if upper_query in _US_STOCKS:
        return upper_query

    # Euronext direct match
    if upper_query in _EU_STOCKS:
        return _EU_STOCKS[upper_query]["ticker"]

    # UK LSE direct match (e.g. HSBA, ABDX, 4BB, 88E, LLOY)
    if upper_query in _UK_STOCKS:
        return _UK_STOCKS[upper_query]["ticker"]

    # US Ticker pattern (1-5 capital letters like SPCX)
    if re.match(r"^[A-Z]{1,5}$", upper_query):
        return upper_query

    # 7. Substring name matching across markets
    for alias_dict in (
        _TW_NAME_TO_CODE,
        _HK_NAME_TO_CODE,
        _US_NAME_TO_TICKER,
        _CN_NAME_TO_TICKER,
        _JP_NAME_TO_TICKER,
        _EU_NAME_TO_TICKER,
        _UK_NAME_TO_TICKER,
    ):
        for name, ticker in alias_dict.items():
            if len(name) >= 2 and (name == query or query in name or name in query):
                return ticker

    # 8. Live web search fallback via 2MD
    try:
        try:
            from tools.url2md import search_web_2md
        except ImportError:
            from src.tools.url2md import search_web_2md

        results = search_web_2md(f"{query} stock ticker 股票代碼", limit=3)
        for item in results:
            title = item.get("title", "")
            desc = item.get("description", "")
            m_suf = re.search(r"\b(\d{4,6})\.(TW|TWO|HK|SS|SZ|T)\b", title, re.I) or re.search(r"\b(\d{4,6})\.(TW|TWO|HK|SS|SZ|T)\b", desc, re.I)
            if m_suf:
                return f"{m_suf.group(1)}.{m_suf.group(2).upper()}"
            match = re.search(r"\(([A-Z]{1,5})\)", title) or re.search(r"\(([A-Z]{1,5})\)", desc)
            if match:
                return match.group(1)
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
    Retrieve standardized company profile & metadata across all 7 global markets.
    Includes official Chinese/English name, market/exchange, sector, industry, and summary.
    """
    global _PROFILE_CACHE
    if ticker in _PROFILE_CACHE:
        return _PROFILE_CACHE[ticker]

    init_registries()
    check_and_trigger_swr_update()

    clean_t = ticker.strip().upper()
    clean_c = re.sub(r"\.(TW|TWO|HK|SS|SZ|T|PA|AS|BR|LS|OL|MI|L)$", "", clean_t, flags=re.I).strip()

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
    display_name = clean_t

    tw_name = _TWSE_REGISTRY.get(clean_c) or _TPEX_REGISTRY.get(clean_c) or _TW_NAME_TO_CODE.get(clean_t)
    hk_info = _HK_STOCKS.get(f"{int(clean_c):05d}") if (clean_t.endswith(".HK") and clean_c.isdigit()) else None
    us_info = _US_STOCKS.get(clean_t)
    cn_info = _CN_STOCKS.get(clean_c)
    jp_info = _JP_STOCKS.get(clean_c)
    eu_info = _EU_STOCKS.get(clean_c)
    uk_info = _UK_STOCKS.get(clean_c)

    if tw_name:
        market_name = "TWSE (台灣證券交易所)" if clean_t.endswith(".TW") else "TPEx (證券櫃檯買賣中心)"
        display_name = f"{tw_name} ({clean_t})"
    elif hk_info:
        market_name = "HKEX (香港交易所)"
        display_name = f"{hk_info.get('name', '')} ({clean_t})"
    elif cn_info:
        market_name = f"China ({cn_info.get('market', 'A-Share')})"
        display_name = f"{cn_info.get('name', '')} ({clean_t})"
    elif jp_info:
        market_name = jp_info.get('market', 'JPX (東京證券交易所)')
        display_name = f"{jp_info.get('name', '')} ({clean_t})"
    elif eu_info:
        market_name = eu_info.get('market', 'Euronext')
        display_name = f"{eu_info.get('name', '')} ({clean_t})"
    elif uk_info:
        market_name = "LSE (倫敦證券交易所)"
        display_name = f"{uk_info.get('name', '')} ({clean_t})"
    elif us_info:
        market_name = "US Market (NYSE/NASDAQ/AMEX)"
        display_name = f"{us_info.get('name', clean_t)} ({clean_t})"

    sector = "N/A"
    industry = "N/A"
    summary = "N/A"

    # yfinance optional enrichment
    try:
        import yfinance as yf
        t_obj = yf.Ticker(clean_t)
        info = t_obj.info or {}
        long_name = info.get("longName") or info.get("shortName")
        if long_name and long_name != clean_t:
            if tw_name:
                display_name = f"{tw_name} ({long_name})"
            elif hk_info or cn_info or jp_info or eu_info or uk_info:
                base_c = (hk_info or cn_info or jp_info or eu_info or uk_info).get('name', '')
                display_name = f"{base_c} ({long_name})" if base_c else f"{long_name} ({clean_t})"
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
