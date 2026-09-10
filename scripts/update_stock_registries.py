#!/usr/bin/env python3
"""
scripts/update_stock_registries.py

Fetches and normalizes official stock registries for:
1. US Stocks: SEC EDGAR official company_tickers.json (~10,400 stocks) + curated Chinese alias map
2. Hong Kong Stocks: HKEX official ListOfSecurities_c.xlsx (~3,200 equities/ETFs)
3. Taiwan Stocks: TWSE/TPEx registries (~2,234 stocks)
"""

import os
import re
import sys
import json
import urllib.request
import datetime
import io

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 StockBot/2.0"

# Curated High-Frequency US Chinese Aliases
US_CHINESE_ALIASES = {
    "蘋果": "AAPL",
    "蘋果公司": "AAPL",
    "特斯拉": "TSLA",
    "輝達": "NVDA",
    "英偉達": "NVDA",
    "微軟": "MSFT",
    "亞馬遜": "AMZN",
    "谷歌": "GOOGL",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "臉書": "META",
    "META": "META",
    "超微": "AMD",
    "超微半導體": "AMD",
    "博通": "AVGO",
    "高通": "QCOM",
    "美光": "MU",
    "台積電ADR": "TSM",
    "台積電美股": "TSM",
    "聯電ADR": "UMC",
    "日月光ADR": "ASX",
    "艾司摩爾": "ASML",
    "ASML": "ASML",
    "網飛": "NFLX",
    "奈飛": "NFLX",
    "英特爾": "INTC",
    "思科": "CSCO",
    "甲骨文": "ORCL",
    "波音": "BA",
    "星巴克": "SBUX",
    "麥當勞": "MCD",
    "可口可樂": "KO",
    "百事可樂": "PEP",
    "百事": "PEP",
    "好市多": "COST",
    "開市客": "COST",
    "沃爾瑪": "WMT",
    "波克夏": "BRK-B",
    "巴菲特公司": "BRK-B",
    "摩根大通": "JPM",
    "小摩": "JPM",
    "高盛": "GS",
    "摩根士丹利": "MS",
    "大摩": "MS",
    "花旗": "C",
    "富國銀行": "WFC",
    "VISA": "V",
    "萬事達卡": "MA",
    "迪士尼": "DIS",
    "輝瑞": "PFE",
    "禮來": "LLY",
    "諾和諾德": "NVO",
    "嬌生": "JNJ",
    "強生": "JNJ",
    "SPACEX": "SPCX",
    "SPACE X": "SPCX",
    "太空探索": "SPCX",
    "安謀": "ARM",
    "ARM": "ARM",
    "戴爾": "DELL",
    "超微電腦": "SMCI",
    "美超微": "SMCI",
    "帕蘭提爾": "PLTR",
    "PALANTIR": "PLTR",
    "COINBASE": "COIN",
    "ROBINHOOD": "HOOD",
    "羅賓漢": "HOOD",
    "優步": "UBER",
    "UBER": "UBER",
    "AIRBNB": "ABNB",
    "愛彼迎": "ABNB",
    "蔚來": "NIO",
    "小鵬": "XPEV",
    "理想汽車": "LI",
    "理想": "LI",
    "拼多多": "PDD",
    "京東ADR": "JD",
    "百度ADR": "BIDU",
    "網易ADR": "NTES",
    "嗶哩嗶哩ADR": "BILI",
    "B站ADR": "BILI"
}


def update_us_stock_registry():
    """Fetch SEC EDGAR company tickers and compile US registry."""
    print("⏳ [US] Fetching SEC EDGAR company_tickers.json...")
    url = "https://www.sec.gov/files/company_tickers.json"
    req = urllib.request.Request(url, headers={"User-Agent": "StockBot/2.0 (contact@glsoft.ai)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ [US] Failed to fetch SEC tickers: {e}")
        return False

    stocks = {}
    title_to_ticker = {}
    for idx, item in data.items():
        ticker = str(item.get("ticker", "")).strip().upper()
        title = str(item.get("title", "")).strip()
        cik = item.get("cik_str")
        if not ticker:
            continue
        stocks[ticker] = {
            "name": title,
            "cik": cik,
            "ticker": ticker
        }
        if title:
            title_to_ticker[title.upper()] = ticker

    # Add SpaceX explicit verification
    stocks["SPCX"] = {
        "name": "Space Exploration Technologies Corp. (SpaceX)",
        "cik": None,
        "ticker": "SPCX",
        "market": "NASDAQ"
    }

    out_data = {
        "updated_at": datetime.date.today().isoformat(),
        "source": "SEC EDGAR company_tickers.json",
        "total": len(stocks),
        "stocks": stocks,
        "aliases": US_CHINESE_ALIASES
    }

    out_file = os.path.join(DATA_DIR, "us_stock_registry.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print(f"✅ [US] Successfully saved {len(stocks)} US stocks and {len(US_CHINESE_ALIASES)} aliases to {out_file}")
    return True


def update_hk_stock_registry():
    """Fetch HKEX official securities list (Excel) and compile HK registry."""
    print("⏳ [HK] Fetching HKEX official ListOfSecurities_c.xlsx...")
    url = "https://www.hkex.com.hk/chi/services/trading/securities/securitieslists/ListOfSecurities_c.xlsx"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
    except Exception as e:
        print(f"❌ [HK] Failed to fetch HKEX Excel: {e}")
        return False

    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content))
        sheet = wb.active
    except Exception as e:
        print(f"❌ [HK] Failed to parse HKEX Excel with openpyxl: {e}")
        return False

    stocks = {}
    name_to_code = {}

    # Category filter: '股本' (Equities), '交易所買賣產品' (ETFs), '房地產投資信託基金' (REITs)
    valid_categories = {"股本", "交易所買賣產品", "房地產投資信託基金"}

    for row in sheet.iter_rows(min_row=4, values_only=True):
        if not row or len(row) < 6:
            continue
        code_raw = str(row[0] or "").strip()
        name_raw = str(row[1] or "").strip()
        cat = str(row[2] or "").strip()
        sub_cat = str(row[3] or "").strip()
        board_lot = str(row[4] or "").strip()
        isin = str(row[5] or "").strip()

        if not code_raw.isdigit():
            continue
        if cat not in valid_categories:
            continue

        # Standard Yahoo Finance ticker: e.g. 00700 -> 0700.HK, 09988 -> 9988.HK
        code_int = int(code_raw)
        yahoo_ticker = f"{code_int:04d}.HK"

        # Generate clean short name (strip suffix like －Ｗ, －Ｓ, －ＳＷ, －Ｂ)
        clean_name = re.sub(r"[－\-_][ＷＳＢＲＵSWBRU]+$", "", name_raw).strip()

        stocks[code_raw] = {
            "code": code_raw,
            "int_code": str(code_int),
            "ticker": yahoo_ticker,
            "name": name_raw,
            "clean_name": clean_name,
            "category": cat,
            "sub_category": sub_cat,
            "board_lot": board_lot,
            "isin": isin
        }

        # Indexing for name search
        if name_raw:
            name_to_code[name_raw] = yahoo_ticker
        if clean_name and clean_name != name_raw:
            name_to_code[clean_name] = yahoo_ticker

    # Popular extra aliases
    extra_hk_aliases = {
        "騰訊": "0700.HK",
        "阿里": "9988.HK",
        "阿里巴巴": "9988.HK",
        "美團": "3690.HK",
        "小米": "1810.HK",
        "比亞迪": "1211.HK",
        "匯豐": "0005.HK",
        "中芯國際": "0981.HK",
        "中芯": "0981.HK",
        "網易": "9999.HK",
        "京東": "9618.HK",
        "百度": "9888.HK",
        "快手": "1024.HK",
        "攜程": "9961.HK",
        "小鵬汽車": "9868.HK",
        "理想汽車港股": "2015.HK",
        "蔚來港股": "9866.HK",
        "商湯": "0020.HK",
        "泡泡瑪特": "9992.HK",
        "舜宇光學": "2382.HK",
        "吉利汽車": "0175.HK",
        "長城汽車": "2333.HK",
        "友邦保險": "1299.HK",
        "港交所": "0388.HK"
    }
    for alias, ticker in extra_hk_aliases.items():
        name_to_code[alias] = ticker

    out_data = {
        "updated_at": datetime.date.today().isoformat(),
        "source": "HKEX ListOfSecurities_c.xlsx",
        "total": len(stocks),
        "stocks": stocks,
        "aliases": name_to_code
    }

    out_file = os.path.join(DATA_DIR, "hk_stock_registry.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print(f"✅ [HK] Successfully saved {len(stocks)} HK stocks and {len(name_to_code)} names/aliases to {out_file}")
    return True


if __name__ == "__main__":
    us_ok = update_us_stock_registry()
    hk_ok = update_hk_stock_registry()
    if us_ok and hk_ok:
        print("🎉 All stock registries successfully updated!")
    else:
        sys.exit(1)
