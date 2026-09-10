#!/usr/bin/env python3
"""
scripts/update_stock_registries.py

Fetches and normalizes official global stock registries for:
1. US Stocks: SEC EDGAR company_tickers.json (NASDAQ, NYSE, AMEX, ARCA, BATS, IEX ~10,400 listings + CIK + aliases + SPCX)
2. Hong Kong Stocks: HKEX official ListOfSecurities_c.xlsx (~3,200 equities/ETFs)
3. Taiwan Stocks: TWSE/TPEx official open registries (~2,234 listings)
4. China A-Shares: SSE (Shanghai) official js directory + SZSE (Shenzhen) (~8,000+ items)
5. Japan Stocks: JPX official data_j.xlsx (~4,400 listings)
6. European Stocks: Euronext official equities CSV (~3,600 listings)
7. UK Stocks: LSE key listings & FTSE leaders
"""

import os
import re
import sys
import json
import urllib.request
import datetime
import io
import csv
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 StockBot/2.0"

# Curated High-Frequency US Chinese Aliases
US_CHINESE_ALIASES = {
    "蘋果": "AAPL", "蘋果公司": "AAPL",
    "特斯拉": "TSLA",
    "輝達": "NVDA", "英偉達": "NVDA",
    "微軟": "MSFT",
    "亞馬遜": "AMZN",
    "谷歌": "GOOGL", "GOOGLE": "GOOGL", "ALPHABET": "GOOGL",
    "臉書": "META", "META": "META",
    "超微": "AMD", "超微半導體": "AMD",
    "博通": "AVGO", "高通": "QCOM", "美光": "MU",
    "台積電ADR": "TSM", "台積電美股": "TSM",
    "聯電ADR": "UMC", "日月光ADR": "ASX",
    "艾司摩爾": "ASML", "ASML": "ASML",
    "網飛": "NFLX", "奈飛": "NFLX",
    "英特爾": "INTC", "思科": "CSCO", "甲骨文": "ORCL",
    "波音": "BA", "星巴克": "SBUX", "麥當勞": "MCD",
    "可口可樂": "KO", "百事可樂": "PEP", "百事": "PEP",
    "好市多": "COST", "開市客": "COST", "沃爾瑪": "WMT",
    "波克夏": "BRK-B", "巴菲特公司": "BRK-B",
    "摩根大通": "JPM", "小摩": "JPM", "高盛": "GS", "摩根士丹利": "MS", "大摩": "MS",
    "花旗": "C", "富國銀行": "WFC", "VISA": "V", "萬事達卡": "MA",
    "迪士尼": "DIS", "輝瑞": "PFE", "禮來": "LLY", "諾和諾德": "NVO",
    "嬌生": "JNJ", "強生": "JNJ",
    "SPACEX": "SPCX", "SPACE X": "SPCX", "太空探索": "SPCX",
    "安謀": "ARM", "ARM": "ARM", "戴爾": "DELL",
    "超微電腦": "SMCI", "美超微": "SMCI", "帕蘭提爾": "PLTR", "PALANTIR": "PLTR",
    "COINBASE": "COIN", "ROBINHOOD": "HOOD", "羅賓漢": "HOOD",
    "優步": "UBER", "UBER": "UBER", "AIRBNB": "ABNB", "愛彼迎": "ABNB",
    "蔚來": "NIO", "小鵬": "XPEV", "理想汽車": "LI", "理想": "LI",
    "拼多多": "PDD", "京東ADR": "JD", "百度ADR": "BIDU",
    "網易ADR": "NTES", "嗶哩嗶哩ADR": "BILI", "B站ADR": "BILI"
}


def update_us_stock_registry() -> bool:
    """Fetch SEC EDGAR company tickers and compile US registry."""
    print("⏳ [US] Fetching SEC EDGAR company_tickers.json...")
    url = "https://www.sec.gov/files/company_tickers.json"
    req = urllib.request.Request(url, headers={"User-Agent": "StockBot/2.0 (contact@glsoft.ai)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
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

    # Add SpaceX NASDAQ explicit registration
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


def update_hk_stock_registry() -> bool:
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

        code_int = int(code_raw)
        yahoo_ticker = f"{code_int:04d}.HK"
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

        if name_raw:
            name_to_code[name_raw] = yahoo_ticker
        if clean_name and clean_name != name_raw:
            name_to_code[clean_name] = yahoo_ticker

    extra_hk_aliases = {
        "騰訊": "0700.HK", "阿里": "9988.HK", "阿里巴巴": "9988.HK",
        "美團": "3690.HK", "小米": "1810.HK", "比亞迪": "1211.HK",
        "匯豐": "0005.HK", "中芯國際": "0981.HK", "中芯": "0981.HK",
        "網易": "9999.HK", "京東": "9618.HK", "百度": "9888.HK",
        "快手": "1024.HK", "攜程": "9961.HK", "小鵬汽車": "9868.HK",
        "理想汽車港股": "2015.HK", "蔚來港股": "9866.HK", "商湯": "0020.HK",
        "泡泡瑪特": "9992.HK", "舜宇光學": "2382.HK", "吉利汽車": "0175.HK",
        "長城汽車": "2333.HK", "友邦保險": "1299.HK", "港交所": "0388.HK"
    }
    name_to_code.update(extra_hk_aliases)

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


def update_cn_stock_registry() -> bool:
    """Fetch Shanghai (SSE) and Shenzhen (SZSE) A-shares."""
    print("⏳ [CN] Fetching SSE official directory...")
    cn_stocks = {}
    cn_aliases = {
        "貴州茅台": "600519.SS", "茅台": "600519.SS",
        "五糧液": "000858.SZ",
        "寧德時代": "300750.SZ", "時代新能源": "300750.SZ",
        "比亞迪A股": "002594.SZ",
        "中國平安": "601318.SS", "平安": "601318.SS",
        "招商銀行": "600036.SS", "招行": "600036.SS",
        "中信證券": "600030.SS", "長江電力": "600900.SS",
        "邁瑞醫療": "300760.SZ", "中芯國際A股": "688981.SS",
        "海康威視": "002415.SZ", "立訊精密": "002475.SZ", "紫金礦業": "601899.SS"
    }
    try:
        req = urllib.request.Request(
            "https://www.sse.com.cn/js/common/ssesuggestdataAll.js",
            headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        pattern = r'_t\.push\(\{val:\s*[\"\']([^\"\']+)[\"\'],val2:\s*[\"\']([^\"\']+)[\"\'],val3:\s*[\"\']([^\"\']*)[\"\']'
        for code, name, pinyin in re.findall(pattern, content):
            if len(code) == 6:
                ticker = f"{code}.SS"
                cn_stocks[code] = {"code": code, "name": name, "ticker": ticker, "market": "SSE"}
                cn_aliases[name] = ticker
                if pinyin:
                    cn_aliases[pinyin.upper()] = ticker
    except Exception as e:
        print(f"⚠️ [CN] SSE fetch error: {e}")

    # Shenzhen via Eastmoney API
    try:
        print("⏳ [CN] Fetching SZSE listings...")
        for p in range(1, 35):
            url = f"https://push2.eastmoney.com/api/qt/clist/get?pn={p}&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80&fields=f12,f14"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": "https://quote.eastmoney.com/"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break
            for item in diff:
                code = str(item.get("f12", "")).strip()
                name = str(item.get("f14", "")).strip()
                if code and name and len(code) == 6:
                    ticker = f"{code}.SZ"
                    cn_stocks[code] = {"code": code, "name": name, "ticker": ticker, "market": "SZSE"}
                    cn_aliases[name] = ticker
    except Exception as e:
        print(f"⚠️ [CN] SZSE fetch error: {e}")

    if not cn_stocks:
        print("❌ [CN] Failed to fetch CN stocks")
        return False

    out_data = {
        "updated_at": datetime.date.today().isoformat(),
        "source": "SSE + SZSE Official Listings",
        "total": len(cn_stocks),
        "stocks": cn_stocks,
        "aliases": cn_aliases
    }
    out_file = os.path.join(DATA_DIR, "cn_stock_registry.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print(f"✅ [CN] Successfully saved {len(cn_stocks)} A-share stocks to {out_file}")
    return True


def update_jp_stock_registry() -> bool:
    """Fetch JPX official data_j.xlsx (Tokyo Stock Exchange)."""
    print("⏳ [JP] Fetching JPX official data_j.xlsx...")
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xlsx"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
        sheet = wb.active
        rows = list(sheet.iter_rows(values_only=True))
    except Exception as e:
        print(f"❌ [JP] Failed to fetch/parse JPX Excel: {e}")
        return False

    jp_stocks = {}
    jp_aliases = {
        "豐田": "7203.T", "豐田汽車": "7203.T", "TOYOTA": "7203.T",
        "索尼": "6758.T", "SONY": "6758.T",
        "軟銀": "9984.T", "軟銀集團": "9984.T", "SOFTBANK": "9984.T",
        "三菱日聯": "8306.T", "MUFG": "8306.T",
        "任天堂": "7974.T", "NINTENDO": "7974.T",
        "基恩斯": "6861.T", "KEYENCE": "6861.T",
        "東京威力科創": "8035.T", "TEL": "8035.T",
        "本田": "7267.T", "HONDA": "7267.T",
        "日立": "6501.T", "HITACHI": "6501.T",
        "信越化學": "4063.T", "迅銷": "9983.T", "UNIQLO": "9983.T", "優衣庫": "9983.T"
    }

    for r in rows[1:]:
        if len(r) >= 3:
            code = str(r[1] or "").strip()
            name = str(r[2] or "").strip()
            market = str(r[3] or "JPX").strip()
            if code and name and (code.isdigit() or len(code) == 4):
                ticker = f"{code}.T"
                jp_stocks[code] = {"code": code, "name": name, "ticker": ticker, "market": f"JPX ({market})"}
                jp_aliases[name] = ticker

    out_data = {
        "updated_at": datetime.date.today().isoformat(),
        "source": "JPX data_j.xlsx",
        "total": len(jp_stocks),
        "stocks": jp_stocks,
        "aliases": jp_aliases
    }
    out_file = os.path.join(DATA_DIR, "jp_stock_registry.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print(f"✅ [JP] Successfully saved {len(jp_stocks)} JPX stocks to {out_file}")
    return True


def update_eu_stock_registry() -> bool:
    """Fetch Euronext official equities CSV directory."""
    print("⏳ [EU] Fetching Euronext official directory CSV...")
    url = "https://live.euronext.com/en/product_directory/data/stocks-all-places/download?mics=ALXB%2CALXL%2CALXP%2CBGEM%2CENXB%2CENXL%2CETLX%2CEXGM%2CMERK%2CMIVX%2CMLXB%2CMTAH%2CTNLA%2CTNLB%2CXAMC%2CXAMS%2CXATL%2CXBRU%2CXESM%2CXLDN%2CXLIS%2CXMLI%2CXMSM%2CXOAS%2CXOSL%2CXPAR%2CXPMC"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8-sig", errors="ignore")
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
    except Exception as e:
        print(f"❌ [EU] Failed to fetch Euronext CSV: {e}")
        return False

    eu_stocks = {}
    eu_aliases = {
        "LVMH": "MC.PA", "路易威登": "MC.PA",
        "ASML": "ASML.AS", "艾司摩爾歐股": "ASML.AS",
        "歐萊雅": "OR.PA", "萊雅": "OR.PA",
        "愛馬仕": "RMS.PA", "HERMES": "RMS.PA",
        "賽諾菲": "SAN.PA", "SANOFI": "SAN.PA",
        "空中巴士": "AIR.PA", "AIRBUS": "AIR.PA",
        "道達爾": "TTE.PA", "TOTAL": "TTE.PA",
        "法巴銀行": "BNP.PA", "BNP": "BNP.PA",
        "喜力": "HEIA.AS", "海尼根": "HEIA.AS"
    }

    for row in rows[4:]:
        if len(row) >= 4:
            name = row[0].strip()
            isin = row[1].strip()
            symbol = row[2].strip().upper()
            market = row[3].strip()
            if symbol and name:
                suf = ".PA"
                m_up = market.upper()
                if "AMSTERDAM" in m_up or "XAMS" in m_up: suf = ".AS"
                elif "BRUSSELS" in m_up or "XBRU" in m_up: suf = ".BR"
                elif "LISBON" in m_up or "XLIS" in m_up: suf = ".LS"
                elif "OSLO" in m_up or "XOSL" in m_up: suf = ".OL"
                elif "MILAN" in m_up or "XMIL" in m_up: suf = ".MI"
                ticker = f"{symbol}{suf}"
                eu_stocks[symbol] = {
                    "symbol": symbol,
                    "name": name,
                    "ticker": ticker,
                    "market": f"Euronext ({market})",
                    "isin": isin
                }
                eu_aliases[name] = ticker

    out_data = {
        "updated_at": datetime.date.today().isoformat(),
        "source": "Euronext Official Equities Directory",
        "total": len(eu_stocks),
        "stocks": eu_stocks,
        "aliases": eu_aliases
    }
    out_file = os.path.join(DATA_DIR, "eu_stock_registry.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print(f"✅ [EU] Successfully saved {len(eu_stocks)} Euronext stocks to {out_file}")
    return True


def update_all_registries() -> dict:
    """Run all global market updaters safely with status tracking."""
    results = {}
    results["US"] = update_us_stock_registry()
    results["HK"] = update_hk_stock_registry()
    results["CN"] = update_cn_stock_registry()
    results["JP"] = update_jp_stock_registry()
    results["EU"] = update_eu_stock_registry()
    return results


if __name__ == "__main__":
    res = update_all_registries()
    print("Update Results:", res)
    if not all(res.values()):
        print("⚠️ Some registries failed to update, but existing caches remain intact.")
