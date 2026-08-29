import os
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
import json
from typing import List, Dict, Any, Optional
from functools import lru_cache

from data.cache import get_cache
from data.models import (
    CompanyNews,
    CompanyNewsResponse,
    FinancialMetrics,
    FinancialMetricsResponse,
    Price,
    PriceResponse,
    LineItem,
    LineItemResponse,
    InsiderTrade,
    InsiderTradeResponse,
)

# Global cache instance
_cache = get_cache()

# Define API keys and fallback order
def get_api_keys():
    """Get all available API keys with fallback options."""
    return {
        "alpha_vantage": os.environ.get("ALPHA_VANTAGE_API_KEY"),
        "stockdata": os.environ.get("STOCKDATA_API_KEY"),
        "finnhub": os.environ.get("FINNHUB_API_KEY"),
        "eodhd": os.environ.get("EODHD_API_KEY"),
        "coingecko": os.environ.get("COINGECKO_API_KEY"),
        "cryptocompare": os.environ.get("CRYPTOCOMPARE_API_KEY"),
    }

def _format_ticker_for_yfinance(ticker: str) -> str:
    """
    根據股票代號自動判斷並轉換為 yfinance 套件所需的正確格式
    
    Args:
        ticker: 原始股票代號
        
    Returns:
        格式化後的股票代號
        
    Examples:
        - 台股: "2330" -> "2330.TW"
        - 港股: "0001.hk" -> "0001.HK", "1" -> "0001.HK"
        - 中國股市: "600519" -> "600519.SS", "000001" -> "000001.SZ"
        - 美股: "AAPL" -> "AAPL" (不變)
        - 已有後綴: "AAPL.US" -> "AAPL.US" (不變)
    """
    # 如果已經包含點號，直接使用（但處理港股的特殊情況）
    if '.' in ticker:
        if ticker.lower().endswith('.hk'):
            # 港股：將 .hk 轉換為 .HK
            base_ticker = ticker[:-3]
            # 確保港股代號為4位數，不足的前面補0
            if base_ticker.isdigit():
                base_ticker = base_ticker.zfill(4)
            return f"{base_ticker}.HK"
        else:
            # 其他已有後綴的直接返回
            return ticker
    
    # 純數字代號的處理
    if ticker.isdigit():
        ticker_len = len(ticker)
        ticker_int = int(ticker)
        
        # 台股：4位數字代號
        if ticker_len == 4:
            return f"{ticker}.TW"
        
        # 港股：1-4位數字代號（香港股票代號範圍通常是1-9999）
        if ticker_len <= 4 and ticker_int <= 9999:
            # 港股代號補齊為4位數
            formatted_ticker = ticker.zfill(4)
            return f"{formatted_ticker}.HK"
        
        # 中國股市：6位數字代號
        if ticker_len == 6:
            # 上海證券交易所：以6開頭
            if ticker.startswith('6'):
                return f"{ticker}.SS"
            # 深圳證券交易所：以0、2、3開頭
            elif ticker.startswith(('0', '2', '3')):
                return f"{ticker}.SZ"
            else:
                # 其他6位數代號，預設為上海
                return f"{ticker}.SS"
    
    # 字母代號（美股等）直接返回
    return ticker

def get_prices(ticker: str, start_date: str, end_date: str, is_crypto: bool = False) -> list[Price]:
    """Fetch price data with multi-source fallback strategy."""
    # Check cache first
    cache_key = f"crypto_{ticker}" if is_crypto else ticker
    if cached_data := _cache.get_prices(cache_key):
        filtered_data = [Price(**price) for price in cached_data if start_date <= price["time"] <= end_date]
        if filtered_data:
            return filtered_data

    if is_crypto:
        return get_crypto_prices(ticker, start_date, end_date)
    
    # Format ticker for different APIs
    yf_ticker_str = _format_ticker_for_yfinance(ticker)
    sd_ticker_str = ticker
    av_ticker_str = ticker

    # StockData/AlphaVantage symbols differ slightly for TW stocks
    if "." not in ticker and ticker.isdigit():
        sd_ticker_str = f"{ticker}.TWSE"  # StockData uses .TWSE
        av_ticker_str = f"{ticker}.TW"
    
    # Try primary source: Yahoo Finance
    try:
        yf_ticker = yf.Ticker(yf_ticker_str)
        df = yf_ticker.history(start=start_date, end=end_date)
        
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            elif len(df.columns) > 0 and isinstance(df.columns[0], tuple):
                df.columns = [i[0] for i in df.columns]
                
            prices = []
            for index, row in df.iterrows():
                date_str = index.strftime('%Y-%m-%d')
                try:
                    close_val = float(row['Close'])
                    if pd.isna(close_val) or np.isnan(close_val) or close_val <= 0:
                        continue
                    open_val = float(row['Open']) if not pd.isna(row['Open']) else close_val
                    high_val = float(row['High']) if not pd.isna(row['High']) else close_val
                    low_val = float(row['Low']) if not pd.isna(row['Low']) else close_val
                    vol_val = int(row['Volume']) if not pd.isna(row['Volume']) else 0
                    price = Price(
                        open=open_val,
                        close=close_val,
                        high=high_val,
                        low=low_val,
                        volume=vol_val,
                        time=date_str
                    )
                    prices.append(price)
                except Exception:
                    continue
            
            if prices:
                # Cache the results
                _cache.set_prices(cache_key, [p.model_dump() for p in prices])
                return prices
    except Exception as e:
        print(f"Yahoo Finance error for {ticker}: {str(e)}")
    
    # Fallback to StockData.org if Yahoo fails
    try:
        api_keys = get_api_keys()
        if api_key := api_keys.get("stockdata"):
            url = f"https://api.stockdata.org/v1/data/eod?symbols={sd_ticker_str}&date_from={start_date}&date_to={end_date}&api_key={api_key}"
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if "data" in data and data["data"]:
                    prices = []
                    for item in data["data"]:
                        price = Price(
                            open=float(item["open"]),
                            close=float(item["close"]),
                            high=float(item["high"]),
                            low=float(item["low"]),
                            volume=int(item["volume"]),
                            time=item["date"]
                        )
                        prices.append(price)
                    
                    # Cache the results
                    _cache.set_prices(cache_key, [p.model_dump() for p in prices])
                    return prices
    except Exception as e:
        print(f"StockData.org error for {ticker}: {str(e)}")
        
    # Last resort: Alpha Vantage
    try:
        api_keys = get_api_keys()
        if api_key := api_keys.get("alpha_vantage"):
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={av_ticker_str}&outputsize=full&apikey={api_key}"
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if "Time Series (Daily)" in data:
                    time_series = data["Time Series (Daily)"]
                    prices = []
                    
                    for date, values in time_series.items():
                        if start_date <= date <= end_date:
                            price = Price(
                                open=float(values["1. open"]),
                                close=float(values["4. close"]),
                                high=float(values["2. high"]),
                                low=float(values["3. low"]),
                                volume=int(values["6. volume"]),
                                time=date
                            )
                            prices.append(price)
                    
                    # Sort by date, newest first
                    prices.sort(key=lambda x: x.time, reverse=True)
                    
                    # Cache the results
                    _cache.set_prices(cache_key, [p.model_dump() for p in prices])
                    return prices
    except Exception as e:
        print(f"Alpha Vantage error for {ticker}: {str(e)}")
    
    # Return empty list if all sources fail
    return []

# Add new function for crypto prices
def get_crypto_prices(ticker: str, start_date: str, end_date: str) -> list[Price]:
    """Fetch cryptocurrency price data from multiple sources with fallback strategy."""
    prices = []
    
    # Convert dates to unix timestamps for APIs that require it
    start_timestamp = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_timestamp = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
    
    # Try CoinCap API first (completely free, no API key required)
    try:
        # Normalize ticker symbol (remove -USD or /USD if present)
        coin_id = ticker.lower().replace("-usd", "").replace("/usd", "")
        
        # CoinCap uses lowercase, standard names like "bitcoin" instead of symbols
        if coin_id == "btc":
            coin_id = "bitcoin"
        elif coin_id == "eth":
            coin_id = "ethereum"
        elif coin_id == "sol":
            coin_id = "solana"
        
        # Calculate interval in days for history API
        interval = "d1"  # daily interval
        
        # CoinCap API for historical data
        url = f"https://api.coincap.io/v2/assets/{coin_id}/history"
        params = {
            "interval": interval,
            "start": start_timestamp * 1000,  # Convert to milliseconds
            "end": end_timestamp * 1000,
        }
        
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and data["data"]:
                price_data = data["data"]
                
                # Group data by day to create OHLC
                daily_data = {}
                
                for item in price_data:
                    timestamp_ms = int(item["time"])
                    price = float(item["priceUsd"])
                    date_str = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d')
                    
                    if start_date <= date_str <= end_date:
                        if date_str not in daily_data:
                            daily_data[date_str] = {
                                "open": price,
                                "high": price,
                                "low": price,
                                "close": price,
                                "prices": [price]
                            }
                        else:
                            daily_data[date_str]["high"] = max(daily_data[date_str]["high"], price)
                            daily_data[date_str]["low"] = min(daily_data[date_str]["low"], price)
                            daily_data[date_str]["close"] = price
                            daily_data[date_str]["prices"].append(price)
                
                # Get volume data from asset endpoint
                volume_url = f"https://api.coincap.io/v2/assets/{coin_id}"
                volume_response = requests.get(volume_url)
                volume_data = {}
                
                if volume_response.status_code == 200:
                    asset_data = volume_response.json()
                    if "data" in asset_data and asset_data["data"]:
                        volume = float(asset_data["data"]["volumeUsd24Hr"])
                        # Use the same volume for all days as an approximation
                        for date_str in daily_data:
                            volume_data[date_str] = volume
                
                # Create price objects from the daily data
                for date_str, data in daily_data.items():
                    price_obj = Price(
                        open=data["open"],
                        close=data["close"],
                        high=data["high"],
                        low=data["low"],
                        volume=volume_data.get(date_str, 0),
                        time=date_str
                    )
                    prices.append(price_obj)
                
                if prices:
                    # Sort by date for consistency
                    prices.sort(key=lambda x: x.time)
                    # Cache the results
                    _cache.set_prices(f"crypto_{ticker}", [p.model_dump() for p in prices])
                    return prices
    except Exception as e:
        print(f"CoinCap error for {ticker}: {str(e)}")
    
    # Fallback to other APIs as they were already implemented
    # ... existing code for CoinGecko, CryptoCompare, and Binance ...

def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    is_crypto: bool = False
) -> list[FinancialMetrics]:
    """Fetch financial metrics from cache or APIs."""
    # Use different approach for crypto
    if is_crypto:
        return get_crypto_metrics(ticker, end_date, period, limit)
    
    yf_ticker_str = _format_ticker_for_yfinance(ticker)
    
    # Normalize end_date to string format
    if isinstance(end_date, datetime):
        end_date_str = end_date.strftime('%Y-%m-%d')
    else:
        end_date_str = str(end_date)[:10]  # Ensure it's YYYY-MM-DD format
    
    # Check cache first
    if cached_data := _cache.get_financial_metrics(ticker):
        # Filter cached data by date and limit
        filtered_data = [FinancialMetrics(**metric) for metric in cached_data if metric["report_period"] <= end_date_str]
        filtered_data.sort(key=lambda x: x.report_period, reverse=True)
        if filtered_data:
            return filtered_data[:limit]

    # If not in cache or insufficient data, fetch from Yahoo Finance
    try:
        yf_ticker = yf.Ticker(yf_ticker_str)
        
        # Get various metrics
        info = yf_ticker.info
        financial_data = yf_ticker.financials
        balance_sheet = yf_ticker.balance_sheet
        cash_flow = yf_ticker.cashflow
        
        # Get quarterly data too for more data points if needed
        quarterly_financials = yf_ticker.quarterly_financials
        quarterly_balance_sheet = yf_ticker.quarterly_balance_sheet
        quarterly_cashflow = yf_ticker.quarterly_cashflow
        
        # Helper function to get value from annual or quarterly data
        def get_value_with_fallback(annual_df, quarterly_df, field_name, date):
            """Try annual data first, then fall back to quarterly data."""
            value = get_value_from_df(annual_df, field_name, date)
            if value is None and quarterly_df is not None and not quarterly_df.empty:
                value = get_value_from_df(quarterly_df, field_name, date)
            return value
        
        # Use only annual data dates for consistency (if period is annual)
        # For quarterly or TTM, include quarterly dates
        if period == "annual":
            all_dates = set()
            for df in [financial_data, balance_sheet, cash_flow]:
                if df is not None and not df.empty:
                    all_dates.update(df.columns)
        else:
            # Include quarterly data for other periods
            all_dates = set()
            for df in [financial_data, balance_sheet, cash_flow, 
                      quarterly_financials, quarterly_balance_sheet, quarterly_cashflow]:
                if df is not None and not df.empty:
                    all_dates.update(df.columns)
        
        # Sort dates in descending order
        sorted_dates = sorted(all_dates, reverse=True)
        
        # Create financial metrics for each date
        financial_metrics = []
        for i, date in enumerate(sorted_dates):
            if i >= limit:
                break
                
            report_date = date.strftime('%Y-%m-%d')
            if report_date > end_date_str:
                continue
                
            # Gather metrics that we can calculate
            try:
                # Basic metrics from info
                market_cap = info.get('marketCap')
                enterprise_value = info.get('enterpriseValue')
                
                # Price ratios
                pe_ratio = info.get('trailingPE')
                pb_ratio = info.get('priceToBook')
                ps_ratio = info.get('priceToSalesTrailing12Months')
                
                # Get financial data for this period if available (with fallback to quarterly)
                net_income = get_value_with_fallback(financial_data, quarterly_financials, 'Net Income', date)
                total_revenue = get_value_with_fallback(financial_data, quarterly_financials, 'Total Revenue', date)
                
                # Balance sheet items (with fallback to quarterly)
                total_assets = get_value_with_fallback(balance_sheet, quarterly_balance_sheet, 'Total Assets', date)
                total_liabilities = get_value_with_fallback(balance_sheet, quarterly_balance_sheet, 'Total Liabilities Net Minority Interest', date)
                total_equity = total_assets - total_liabilities if total_assets and total_liabilities else None
                
                # Cash flow items (with fallback to quarterly)
                operating_cash_flow = get_value_with_fallback(cash_flow, quarterly_cashflow, 'Operating Cash Flow', date)
                capital_expenditure = get_value_with_fallback(cash_flow, quarterly_cashflow, 'Capital Expenditure', date)
                free_cash_flow = operating_cash_flow + capital_expenditure if operating_cash_flow and capital_expenditure else None
                
                # Calculate derived metrics
                gross_profit = get_value_with_fallback(financial_data, quarterly_financials, 'Gross Profit', date)
                gross_margin = gross_profit / total_revenue if gross_profit and total_revenue else None
                operating_income = get_value_with_fallback(financial_data, quarterly_financials, 'Operating Income', date)
                operating_margin = operating_income / total_revenue if operating_income and total_revenue else None
                net_margin = net_income / total_revenue if net_income and total_revenue else None
                
                # Return ratios
                return_on_equity = net_income / total_equity if net_income and total_equity else None
                return_on_assets = net_income / total_assets if net_income and total_assets else None
                
                # Liquidity ratios
                current_assets = get_value_with_fallback(balance_sheet, quarterly_balance_sheet, 'Current Assets', date)
                current_liabilities = get_value_with_fallback(balance_sheet, quarterly_balance_sheet, 'Current Liabilities', date)
                current_ratio = current_assets / current_liabilities if current_assets and current_liabilities else None
                
                # Debt ratios
                debt_to_equity = total_liabilities / total_equity if total_liabilities and total_equity else None
                
                # Growth metrics (calculate if previous period available)
                prev_date = sorted_dates[i+1] if i+1 < len(sorted_dates) else None
                if prev_date:
                    prev_revenue = get_value_with_fallback(financial_data, quarterly_financials, 'Total Revenue', prev_date)
                    prev_net_income = get_value_with_fallback(financial_data, quarterly_financials, 'Net Income', prev_date)
                    
                    revenue_growth = (total_revenue / prev_revenue - 1) if total_revenue and prev_revenue else None
                    earnings_growth = (net_income / prev_net_income - 1) if net_income and prev_net_income else None
                else:
                    revenue_growth = None
                    earnings_growth = None
                
                # Per share values
                shares_outstanding = info.get('sharesOutstanding')
                if shares_outstanding:
                    earnings_per_share = net_income / shares_outstanding if net_income else None
                    book_value_per_share = total_equity / shares_outstanding if total_equity else None
                    free_cash_flow_per_share = free_cash_flow / shares_outstanding if free_cash_flow else None
                else:
                    earnings_per_share = info.get('trailingEps')
                    book_value_per_share = None
                    free_cash_flow_per_share = None
                
                # Create the metrics object
                metrics = FinancialMetrics(
                    ticker=ticker,
                    report_period=report_date,
                    period=period,
                    currency=info.get('currency', 'USD'),
                    market_cap=market_cap,
                    enterprise_value=enterprise_value,
                    price_to_earnings_ratio=pe_ratio,
                    price_to_book_ratio=pb_ratio,
                    price_to_sales_ratio=ps_ratio,
                    enterprise_value_to_ebitda_ratio=info.get('enterpriseToEbitda'),
                    enterprise_value_to_revenue_ratio=enterprise_value / total_revenue if enterprise_value and total_revenue else None,
                    free_cash_flow_yield=free_cash_flow / market_cap if free_cash_flow and market_cap else None,
                    peg_ratio=info.get('pegRatio'),
                    gross_margin=gross_margin,
                    operating_margin=operating_margin,
                    net_margin=net_margin,
                    return_on_equity=return_on_equity,
                    return_on_assets=return_on_assets,
                    return_on_invested_capital=info.get('returnOnAssets'),  # Approximation
                    asset_turnover=total_revenue / total_assets if total_revenue and total_assets else None,
                    inventory_turnover=None,  # Not easily available
                    receivables_turnover=None,  # Not easily available
                    days_sales_outstanding=None,  # Not easily available
                    operating_cycle=None,  # Not easily available
                    working_capital_turnover=None,  # Not easily available
                    current_ratio=current_ratio,
                    quick_ratio=None,  # Not easily available
                    cash_ratio=None,  # Not easily available
                    operating_cash_flow_ratio=operating_cash_flow / current_liabilities if operating_cash_flow and current_liabilities else None,
                    debt_to_equity=debt_to_equity,
                    debt_to_assets=total_liabilities / total_assets if total_liabilities and total_assets else None,
                    interest_coverage=None,  # Not easily available
                    revenue_growth=revenue_growth,
                    earnings_growth=earnings_growth,
                    book_value_growth=None,  # Requires more historical data
                    earnings_per_share_growth=None,  # Requires more historical data
                    free_cash_flow_growth=None,  # Requires more historical data
                    operating_income_growth=None,  # Requires more historical data
                    ebitda_growth=None,  # Requires more historical data
                    payout_ratio=info.get('payoutRatio'),
                    earnings_per_share=earnings_per_share,
                    book_value_per_share=book_value_per_share,
                    free_cash_flow_per_share=free_cash_flow_per_share,
                )
                
                financial_metrics.append(metrics)
                
            except Exception as e:
                print(f"Error processing metrics for {ticker} on {report_date}: {str(e)}")
                continue
        
        # Cache the results
        if financial_metrics:
            _cache.set_financial_metrics(ticker, [m.model_dump() for m in financial_metrics])
            
        return financial_metrics
        
    except Exception as e:
        print(f"Error fetching financial metrics for {ticker}: {str(e)}")
        return []

# Add new function for crypto metrics
def get_crypto_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10
) -> list[FinancialMetrics]:
    """Fetch cryptocurrency metrics from CoinGecko or other sources."""
    # Check cache first
    cache_key = f"crypto_{ticker}"
    if cached_data := _cache.get_financial_metrics(cache_key):
        # Filter cached data by date and limit
        filtered_data = [FinancialMetrics(**metric) for metric in cached_data if metric["report_period"] <= end_date]
        filtered_data.sort(key=lambda x: x.report_period, reverse=True)
        if filtered_data:
            return filtered_data[:limit]
    
    # Normalize ticker symbol
    coin_id = ticker.lower().replace("-usd", "").replace("/usd", "")
    
    try:
        # Get coin data from CoinGecko
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "true",
            "developer_data": "true"
        }
        
        # Add API key if available
        api_keys = get_api_keys()
        if api_key := api_keys.get("coingecko"):
            params["x_cg_pro_api_key"] = api_key
        
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            market_data = data.get("market_data", {})
            
            report_date = datetime.now().strftime('%Y-%m-%d')
            
            # Create a financial metrics object with cryptocurrency-specific data
            metrics = FinancialMetrics(
                ticker=ticker,
                report_period=report_date,
                period="ttm",
                currency="USD",
                market_cap=market_data.get("market_cap", {}).get("usd"),
                enterprise_value=market_data.get("market_cap", {}).get("usd"),  # Same as market cap for crypto
                price_to_earnings_ratio=None,  # Not applicable for most crypto
                price_to_book_ratio=None,  # Not applicable for most crypto
                price_to_sales_ratio=None,  # Not applicable for most crypto
                enterprise_value_to_ebitda_ratio=None,  # Not applicable for most crypto
                enterprise_value_to_revenue_ratio=None,  # Not applicable for most crypto
                free_cash_flow_yield=None,  # Not applicable for most crypto
                peg_ratio=None,  # Not applicable for most crypto
                gross_margin=None,  # Not applicable for most crypto
                operating_margin=None,  # Not applicable for most crypto
                net_margin=None,  # Not applicable for most crypto
                return_on_equity=None,  # Not applicable for most crypto
                return_on_assets=None,  # Not applicable for most crypto
                return_on_invested_capital=None,  # Not applicable for most crypto
                asset_turnover=None,  # Not applicable for most crypto
                inventory_turnover=None,  # Not applicable for most crypto
                receivables_turnover=None,  # Not applicable for most crypto
                days_sales_outstanding=None,  # Not applicable for most crypto
                operating_cycle=None,  # Not applicable for most crypto
                working_capital_turnover=None,  # Not applicable for most crypto
                current_ratio=None,  # Not applicable for most crypto
                quick_ratio=None,  # Not applicable for most crypto
                cash_ratio=None,  # Not applicable for most crypto
                operating_cash_flow_ratio=None,  # Not applicable for most crypto
                debt_to_equity=None,  # Not applicable for most crypto
                debt_to_assets=None,  # Not applicable for most crypto
                interest_coverage=None,  # Not applicable for most crypto
                revenue_growth=market_data.get("price_change_percentage_30d"),
                earnings_growth=market_data.get("price_change_percentage_1y"),
                book_value_growth=None,  # Not applicable for most crypto
                earnings_per_share_growth=None,  # Not applicable for most crypto
                free_cash_flow_growth=None,  # Not applicable for most crypto
                operating_income_growth=None,  # Not applicable for most crypto
                ebitda_growth=None,  # Not applicable for most crypto
                payout_ratio=None,  # Not applicable for most crypto
                earnings_per_share=None,  # Not applicable for most crypto
                book_value_per_share=None,  # Not applicable for most crypto
                free_cash_flow_per_share=None,  # Not applicable for most crypto
            )
            
            # Cache the result
            _cache.set_financial_metrics(cache_key, [metrics.model_dump()])
            
            return [metrics]
    except Exception as e:
        print(f"CoinGecko metrics error for {ticker}: {str(e)}")
    
    # Create an empty metrics object if no data was found
    empty_metrics = FinancialMetrics(
        ticker=ticker,
        report_period=datetime.now().strftime('%Y-%m-%d'),
        period="ttm",
        currency="USD",
        market_cap=None,
        enterprise_value=None,
        price_to_earnings_ratio=None,
        # ... all other fields default to None
    )
    
    return [empty_metrics]

def search_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    is_crypto: bool = False
) -> list[LineItem]:
    """Search financial line items for a ticker."""
    # Handle crypto differently
    if is_crypto:
        return search_crypto_line_items(ticker, line_items, end_date, period, limit)
    
    yf_ticker_str = _format_ticker_for_yfinance(ticker)
    
    # Normalize end_date to string format
    if isinstance(end_date, datetime):
        end_date_str = end_date.strftime('%Y-%m-%d')
    else:
        end_date_str = str(end_date)[:10]  # Ensure it's YYYY-MM-DD format
    
    try:
        yf_ticker = yf.Ticker(yf_ticker_str)
        
        # Get financial statements
        income_stmt = yf_ticker.income_stmt
        balance_sheet = yf_ticker.balance_sheet
        cash_flow = yf_ticker.cashflow
        
        # Also get quarterly data
        q_income_stmt = yf_ticker.quarterly_income_stmt
        q_balance_sheet = yf_ticker.quarterly_balance_sheet
        q_cash_flow = yf_ticker.quarterly_cashflow
        
        # Use info for some common items
        info = yf_ticker.info
        
        # Helper function to get value with fallback to quarterly data
        def get_value_with_fallback(annual_df, quarterly_df, field_name, date):
            """Try annual data first, then fall back to quarterly data."""
            value = get_value_from_df(annual_df, field_name, date)
            if value is None and quarterly_df is not None and hasattr(quarterly_df, 'empty') and not quarterly_df.empty:
                value = get_value_from_df(quarterly_df, field_name, date)
            return value
        
        # Use only annual data dates for consistency (if period is annual)
        # For quarterly or TTM, include quarterly dates
        if period == "annual":
            all_dates = set()
            for df in [income_stmt, balance_sheet, cash_flow]:
                if df is not None and hasattr(df, 'columns') and not df.empty:
                    all_dates.update(df.columns)
        else:
            all_dates = set()
            for df in [income_stmt, balance_sheet, cash_flow, 
                       q_income_stmt, q_balance_sheet, q_cash_flow]:
                if df is not None and hasattr(df, 'columns') and not df.empty:
                    all_dates.update(df.columns)
                
        # Sort dates in descending order
        sorted_dates = sorted(all_dates, reverse=True)
        
        # Create line items for each date
        result_items = []
        for i, date in enumerate(sorted_dates):
            if i >= limit:
                break
                
            report_date = date.strftime('%Y-%m-%d')
            if report_date > end_date_str:
                continue
                
            # Create a base line item with required fields
            line_item_data = {
                "ticker": ticker,
                "report_period": report_date,
                "period": period,
                "currency": info.get('currency', 'USD'),
            }
            # Initialize all requested line items to None to avoid missing attributes
            for item in line_items:
                line_item_data.setdefault(item, None)
            
            # Map requested line items to financial statement items
            line_item_mapping = {
                "revenue": ("Total Revenue", income_stmt),
                "net_income": ("Net Income", income_stmt),
                "operating_income": ("Operating Income", income_stmt),
                "gross_margin": (None, None),  # Will calculate from Gross Profit / Revenue
                "operating_margin": (None, None),  # Will calculate from Operating Income / Revenue
                "return_on_invested_capital": (None, None),  # Will calculate
                "free_cash_flow": (None, None),  # Will calculate from OCF - CapEx
                "earnings_per_share": ("Diluted EPS", income_stmt),  # Fallback to net income/shares later
                "ebit": ("Ebit", income_stmt),
                "ebitda": ("Ebitda", income_stmt),
                "cash_and_equivalents": ("Cash And Cash Equivalents", balance_sheet),
                "total_debt": ("Total Debt", balance_sheet),
                "current_assets": ("Current Assets", balance_sheet),
                "current_liabilities": ("Current Liabilities", balance_sheet),
                "total_assets": ("Total Assets", balance_sheet),
                "total_liabilities": ("Total Liabilities Net Minority Interest", balance_sheet),
                "shareholders_equity": ("Stockholders Equity", balance_sheet),
                "working_capital": (None, None),  # Will calculate
                "capital_expenditure": ("Capital Expenditure", cash_flow),
                "depreciation_and_amortization": ("Depreciation And Amortization", cash_flow),
                "research_and_development": ("Research And Development", income_stmt),
                "goodwill_and_intangible_assets": (None, None),  # Will calculate
                "outstanding_shares": (None, None),  # Will get from info
                "dividends_and_other_cash_distributions": ("Dividends Paid", cash_flow),
                "earnings_per_share": (None, None),  # Will get from info["trailingEPS"]
            }
            
            # Fill in values for each requested line item
            for item in line_items:
                if item in line_item_mapping:
                    field_name, source_df = line_item_mapping[item]
                    
                    # Determine quarterly fallback for source_df
                    q_source_df = None
                    if source_df is income_stmt:
                        q_source_df = q_income_stmt
                    elif source_df is balance_sheet:
                        q_source_df = q_balance_sheet
                    elif source_df is cash_flow:
                        q_source_df = q_cash_flow
                    
                    # Direct mapping to a field
                    if field_name and source_df is not None:
                        line_item_data[item] = get_value_with_fallback(source_df, q_source_df, field_name, date)
                    
                    # Special calculations
                    elif item == "gross_margin":
                        gross_profit = get_value_with_fallback(income_stmt, q_income_stmt, "Gross Profit", date)
                        revenue = get_value_with_fallback(income_stmt, q_income_stmt, "Total Revenue", date)
                        if gross_profit and revenue:
                            line_item_data[item] = gross_profit / revenue
                    
                    elif item == "operating_margin":
                        op_income = get_value_with_fallback(income_stmt, q_income_stmt, "Operating Income", date)
                        revenue = get_value_with_fallback(income_stmt, q_income_stmt, "Total Revenue", date)
                        if op_income and revenue:
                            line_item_data[item] = op_income / revenue
                        else:
                            line_item_data[item] = None
                    
                    elif item == "free_cash_flow":
                        ocf = get_value_with_fallback(cash_flow, q_cash_flow, "Operating Cash Flow", date)
                        capex = get_value_with_fallback(cash_flow, q_cash_flow, "Capital Expenditure", date)
                        if ocf and capex:
                            line_item_data[item] = ocf + capex  # CapEx is usually negative
                        elif ocf:
                            line_item_data[item] = ocf
                    
                    elif item == "earnings_per_share":
                        net_income = get_value_with_fallback(income_stmt, q_income_stmt, "Net Income", date)
                        shares_outstanding = info.get("sharesOutstanding")
                        eps_from_income = get_value_with_fallback(income_stmt, q_income_stmt, "Diluted EPS", date) or get_value_with_fallback(income_stmt, q_income_stmt, "Basic EPS", date)
                        if eps_from_income is not None:
                            line_item_data[item] = eps_from_income
                        elif net_income and shares_outstanding:
                            line_item_data[item] = net_income / shares_outstanding
                        else:
                            line_item_data[item] = None

                    elif item == "ebit":
                        ebit = get_value_with_fallback(income_stmt, q_income_stmt, "Ebit", date) or get_value_with_fallback(income_stmt, q_income_stmt, "EBIT", date)
                        if ebit is not None:
                            line_item_data[item] = ebit

                    elif item == "ebitda":
                        ebitda = get_value_with_fallback(income_stmt, q_income_stmt, "Ebitda", date) or get_value_with_fallback(income_stmt, q_income_stmt, "EBITDA", date)
                        if ebitda is not None:
                            line_item_data[item] = ebitda
                    
                    elif item == "working_capital":
                        current_assets = get_value_with_fallback(balance_sheet, q_balance_sheet, "Current Assets", date)
                        current_liabilities = get_value_with_fallback(balance_sheet, q_balance_sheet, "Current Liabilities", date)
                        if current_assets and current_liabilities:
                            line_item_data[item] = current_assets - current_liabilities
                    
                    elif item == "goodwill_and_intangible_assets":
                        goodwill = get_value_with_fallback(balance_sheet, q_balance_sheet, "Goodwill", date)
                        intangibles = get_value_with_fallback(balance_sheet, q_balance_sheet, "Intangible Assets", date)
                        if goodwill or intangibles:
                            line_item_data[item] = (goodwill or 0) + (intangibles or 0)
                    
                    elif item == "outstanding_shares":
                        line_item_data[item] = info.get("sharesOutstanding")
                    
                    elif item == "return_on_invested_capital":
                        net_income = get_value_with_fallback(income_stmt, q_income_stmt, "Net Income", date)
                        total_equity = get_value_with_fallback(balance_sheet, q_balance_sheet, "Stockholders Equity", date)
                        total_debt = get_value_with_fallback(balance_sheet, q_balance_sheet, "Total Debt", date)
                        if net_income and (total_equity or total_debt):
                            invested_capital = (total_equity or 0) + (total_debt or 0)
                            if invested_capital > 0:
                                line_item_data[item] = net_income / invested_capital
                    
                    elif item == "debt_to_equity":
                        total_debt = get_value_with_fallback(balance_sheet, q_balance_sheet, "Total Debt", date)
                        total_equity = get_value_with_fallback(balance_sheet, q_balance_sheet, "Stockholders Equity", date)
                        if total_debt and total_equity and total_equity > 0:
                            line_item_data[item] = total_debt / total_equity
                    
                    elif item == "earnings_per_share":
                        # 首先嘗試從 info 字典中獲取 trailingEPS
                        eps = info.get("trailingEPS")
                        if eps is None:
                            # 如果 info 中沒有，嘗試從 income_stmt 中獲取
                            eps = get_value_with_fallback(income_stmt, q_income_stmt, "Diluted EPS", date)
                        if eps is None:
                            # 如果還是沒有，嘗試從 income_stmt 中獲取 Basic EPS
                            eps = get_value_with_fallback(income_stmt, q_income_stmt, "Basic EPS", date)
                        line_item_data[item] = eps
            
            # Create the LineItem object
            result_items.append(LineItem(**line_item_data))
        
        return result_items
        
    except Exception as e:
        print(f"Error fetching line items for {ticker}: {str(e)}")
        return []

def search_crypto_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10
) -> list[LineItem]:
    """Create appropriate line items for cryptocurrencies."""
    # Normalize ticker symbol
    coin_id = ticker.lower().replace("-usd", "").replace("/usd", "")
    
    try:
        # Get coin data from CoinGecko
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "true",
            "developer_data": "true"
        }
        
        # Add API key if available
        api_keys = get_api_keys()
        if api_key := api_keys.get("coingecko"):
            params["x_cg_pro_api_key"] = api_key
        
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            market_data = data.get("market_data", {})
            
            # Create a result for today
            result = LineItem(
                ticker=ticker,
                report_period=datetime.now().strftime('%Y-%m-%d'),
                period=period,
                currency="USD"
            )
            
            # Map requested line items to available crypto data
            for item in line_items:
                if item == "revenue":
                    # For crypto, use trading volume as a proxy for revenue
                    result.revenue = market_data.get("total_volume", {}).get("usd")
                
                elif item == "net_income":
                    # For crypto, there's no real net income, but can use market cap change
                    price_change_24h = market_data.get("price_change_24h", 0)
                    circulating_supply = market_data.get("circulating_supply", 0)
                    if price_change_24h and circulating_supply:
                        result.net_income = price_change_24h * circulating_supply
                
                elif item == "outstanding_shares":
                    # Use circulating supply as equivalent to outstanding shares
                    result.outstanding_shares = market_data.get("circulating_supply")
                
                elif item == "total_assets":
                    # Use market cap as a proxy for total assets
                    result.total_assets = market_data.get("market_cap", {}).get("usd")
                
                elif item == "free_cash_flow":
                    # Not directly applicable for crypto
                    result.free_cash_flow = None
                
                elif item == "capital_expenditure":
                    # Not applicable for crypto
                    result.capital_expenditure = None
                
                elif item == "working_capital":
                    # Not applicable for crypto
                    result.working_capital = None
                
                elif item == "research_and_development":
                    # Could use developer metrics as a very rough proxy
                    result.research_and_development = None
                
                elif item == "total_liabilities":
                    # Not applicable for crypto
                    result.total_liabilities = None
                
                elif item == "current_assets":
                    # Not applicable for crypto
                    result.current_assets = None
                
                elif item == "current_liabilities":
                    # Not applicable for crypto
                    result.current_liabilities = None
                
                elif item == "depreciation_and_amortization":
                    # Not applicable for crypto
                    result.depreciation_and_amortization = None
                
                elif item == "dividends_and_other_cash_distributions":
                    # Not applicable for most crypto, though some have staking rewards
                    result.dividends_and_other_cash_distributions = None
                
                elif item == "book_value_per_share":
                    # Not applicable for crypto
                    result.book_value_per_share = None
                
                elif item == "goodwill_and_intangible_assets":
                    # Not applicable for crypto
                    result.goodwill_and_intangible_assets = None
                
            return [result]
    except Exception as e:
        print(f"Error getting crypto line items for {ticker}: {str(e)}")
    
    # Return empty result if we couldn't get data
    result = LineItem(
        ticker=ticker,
        report_period=datetime.now().strftime('%Y-%m-%d'),
        period=period,
        currency="USD"
    )
    
    return [result]

def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
) -> list[InsiderTrade]:
    """Fetch insider trades from SEC API or Alpha Vantage."""
    # Insider trading data is typically only available for US-listed stocks
    if "." in ticker or ticker.isdigit():
        print(f"Insider trading data is not available for non-US stock {ticker}")
        return []

    # Check cache first
    if cached_data := _cache.get_insider_trades(ticker):
        # Filter cached data by date range
        filtered_data = [InsiderTrade(**trade) for trade in cached_data 
                        if (start_date is None or (trade.get("transaction_date") or trade["filing_date"]) >= start_date)
                        and (trade.get("transaction_date") or trade["filing_date"]) <= end_date]
        filtered_data.sort(key=lambda x: x.transaction_date or x.filing_date, reverse=True)
        if filtered_data:
            return filtered_data

    # If not in cache or insufficient data, fetch from a free API
    # Using Alpha Vantage (need to get a free API key)
    try:
        alpha_vantage_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
        
        if not alpha_vantage_key:
            print("No Alpha Vantage API key found. Set ALPHA_VANTAGE_API_KEY in your environment.")
            return []
        
        url = f"https://www.alphavantage.co/query?function=INSIDER_TRANSACTIONS&symbol={ticker}&apikey={alpha_vantage_key}"
        response = requests.get(url)
        
        if response.status_code != 200:
            print(f"Error fetching insider data from Alpha Vantage: {response.status_code}")
            return []
            
        data = response.json()
        
        # Extract insider trades
        insider_trades = []
        if 'transactions' in data:
            for trade in data['transactions']:
                filing_date = trade.get('filingDate', '')
                transaction_date = trade.get('transactionDate', '')
                
                # Apply date filtering
                if start_date and transaction_date < start_date:
                    continue
                if end_date and transaction_date > end_date:
                    continue
                
                # Parse values
                try:
                    shares_str = trade.get('numberOfShares', '0').replace(',', '')
                    shares = float(shares_str) if shares_str else 0
                    
                    price_str = trade.get('transactionPrice', '0').replace('$', '').replace(',', '')
                    price = float(price_str) if price_str else 0
                    
                    transaction_value = shares * price
                except (ValueError, TypeError):
                    shares = 0
                    price = 0
                    transaction_value = 0
                
                # Determine if it's a buy or sell
                transaction_type = 'Buy' if 'P - Purchase' in trade.get('transactionType', '') else 'Sale'
                
                insider_trade = InsiderTrade(
                    ticker=ticker,
                    issuer=data.get('symbol', ticker),
                    name=trade.get('reportingName', ''),
                    title=trade.get('reportingPerson', {}).get('title', ''),
                    is_board_director='Director' in trade.get('reportingPerson', {}).get('title', ''),
                    transaction_date=transaction_date,
                    transaction_shares=shares * (1 if transaction_type == 'Buy' else -1),
                    transaction_price_per_share=price,
                    transaction_value=transaction_value,
                    shares_owned_before_transaction=None,  # Not always available
                    shares_owned_after_transaction=None,   # Not always available
                    security_title=trade.get('securityTitle', ''),
                    filing_date=filing_date
                )
                
                insider_trades.append(insider_trade)
        
        # Sort by transaction date, newest first
        insider_trades.sort(key=lambda x: x.transaction_date or '', reverse=True)
        
        # Limit results
        insider_trades = insider_trades[:limit]
        
        # Cache the results
        if insider_trades:
            _cache.set_insider_trades(ticker, [trade.model_dump() for trade in insider_trades])
            
        return insider_trades
        
    except Exception as e:
        print(f"Error fetching insider trades for {ticker}: {str(e)}")
        
        # Fallback to empty result
        return []

def _classify_sentiment_text(text: str) -> str:
    """Classify sentiment of financial news headline or text into positive, negative, or neutral."""
    if not text:
        return "neutral"
    text_lower = text.lower()
    
    pos_words = [
        "surge", "soar", "jump", "rally", "gain", "beat", "upgrade", "growth",
        "bullish", "outperform", "record", "profit", "positive", "high", "breakout",
        "buy", "strong", "upside", "expansion", "partnership", "success", "innovat",
        "漲", "大漲", "飆", "利多", "突破", "買進", "獲利", "成長", "創新高"
    ]
    neg_words = [
        "drop", "fall", "plunge", "sink", "miss", "downgrade", "loss", "warning",
        "bearish", "underperform", "crash", "slump", "negative", "low", "breakdown",
        "sell", "weak", "downside", "lawsuit", "investigation", "debt", "risk",
        "跌", "重挫", "大跌", "利空", "虧損", "賣出", "下修", "警訊", "創新低"
    ]
    
    pos_score = sum(1 for w in pos_words if w in text_lower)
    neg_score = sum(1 for w in neg_words if w in text_lower)
    
    if pos_score > neg_score:
        return "positive"
    elif neg_score > pos_score:
        return "negative"
    return "neutral"

def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 100,
    is_crypto: bool = False
) -> list[CompanyNews]:
    """Fetch news articles for a ticker prioritizing 2MD SERP Search with yfinance fallback and sentiment analysis."""
    if is_crypto:
        return get_crypto_news(ticker, end_date, start_date, limit)
    
    yf_ticker_str = _format_ticker_for_yfinance(ticker)
    
    # Check cache first
    if cached_data := _cache.get_company_news(ticker):
        filtered_data = [CompanyNews(**news) for news in cached_data 
                        if (start_date is None or news["date"] >= start_date)
                        and news["date"] <= end_date]
        filtered_data.sort(key=lambda x: x.date, reverse=True)
        if filtered_data:
            return filtered_data

    news_items = []
    seen_urls = set()

    # 1. Priority 1: High-Speed 2MD Financial SERP Search (Primary: 2md.aiurl.tw, Backups: 2md.glsoft.ai, create360.ai)
    try:
        from tools.url2md import search_web_2md
        if ".TW" in ticker.upper() or ".TWO" in ticker.upper() or ticker.isdigit():
            query = f"{ticker} 台灣 股票 財經 新聞"
        elif ".HK" in ticker.upper():
            query = f"{ticker} 港股 財經 新聞"
        else:
            query = f"{ticker} stock financial news analysis"
            
        search_results = search_web_2md(query, limit=limit)
        for item in search_results:
            title = item.get("title", "").strip()
            desc = item.get("description", "").strip()
            url = item.get("url", "").strip()
            
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            
            full_text = f"{title} {desc}"
            sentiment = _classify_sentiment_text(full_text)
            
            news_item = CompanyNews(
                ticker=ticker,
                title=title,
                author=item.get("publisher") or "2MD Search",
                source="2MD Web",
                date=end_date,
                url=url,
                sentiment=sentiment
            )
            news_items.append(news_item)
            if len(news_items) >= limit:
                break
    except Exception as e:
        print(f"2MD news search error for {ticker}: {str(e)}")

    # 2. Priority 2: Yahoo Finance News with Modern Content Dict Support
    if len(news_items) < limit:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else end_dt - timedelta(days=90)
            
            yf_ticker = yf.Ticker(yf_ticker_str)
            news_data = yf_ticker.news or []
            
            for news in news_data:
                title = "Title Unavailable"
                link = f"https://finance.yahoo.com/quote/{ticker}"
                publisher = "Yahoo Finance"
                published_ts = 0

                # Support both modern content dict and legacy flat dict
                if 'content' in news and isinstance(news['content'], dict):
                    c = news['content']
                    title = c.get('title', title)
                    if 'clickThroughUrl' in c and isinstance(c['clickThroughUrl'], dict) and 'url' in c['clickThroughUrl']:
                        link = c['clickThroughUrl']['url']
                    elif 'canonicalUrl' in c and isinstance(c['canonicalUrl'], dict) and 'url' in c['canonicalUrl']:
                        link = c['canonicalUrl']['url']
                    elif 'url' in c:
                        link = c['url']
                    publisher = news.get('publisher', publisher)
                    published_ts = news.get('providerPublishTime', 0)
                else:
                    title = news.get('title', title)
                    link = news.get('link', link)
                    publisher = news.get('publisher', publisher)
                    published_ts = news.get('providerPublishTime', 0)

                news_date = datetime.fromtimestamp(published_ts) if published_ts else datetime.now()
                date_str = news_date.strftime('%Y-%m-%d')
                
                if (published_ts and (news_date < start_dt or news_date > end_dt)) or link in seen_urls:
                    continue
                seen_urls.add(link)
                
                sentiment = _classify_sentiment_text(title)
                news_item = CompanyNews(
                    ticker=ticker,
                    title=title,
                    author=publisher,
                    source=publisher or "Yahoo Finance",
                    date=date_str,
                    url=link,
                    sentiment=sentiment
                )
                news_items.append(news_item)
                if len(news_items) >= limit:
                    break
        except Exception as e:
            print(f"Yahoo Finance news error for {ticker}: {str(e)}")

    # Sort by date, newest first
    news_items.sort(key=lambda x: x.date, reverse=True)
    
    # Cache the results
    if news_items:
        _cache.set_company_news(ticker, [news.model_dump() for news in news_items])
        
    return news_items

def get_crypto_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 100
) -> list[CompanyNews]:
    """Fetch news articles for a cryptocurrency."""
    # Normalize ticker symbol
    coin_id = ticker.lower().replace("-usd", "").replace("/usd", "")
    
    # Default start date to 30 days ago if not specified
    if not start_date:
        end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_date = (end_date_dt - timedelta(days=30)).strftime("%Y-%m-%d")
    
    try:
        # CryptoCompare News API (free tier)
        url = "https://min-api.cryptocompare.com/data/v2/news/"
        params = {
            "categories": coin_id,
            "lang": "EN"
        }
        
        # Add API key if available
        api_keys = get_api_keys()
        if api_key := api_keys.get("cryptocompare"):
            params["api_key"] = api_key
        
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if "Data" in data:
                news_list = []
                
                for article in data["Data"]:
                    # Convert published timestamp to date string
                    published_date = datetime.fromtimestamp(article["published_on"]).strftime("%Y-%m-%d")
                    
                    # Check if within date range
                    if start_date <= published_date <= end_date:
                        # Determine sentiment (basic approach)
                        title_lower = article["title"].lower()
                        if any(word in title_lower for word in ["surge", "soar", "jump", "rally", "bullish", "high"]):
                            sentiment = "positive"
                        elif any(word in title_lower for word in ["drop", "fall", "crash", "bearish", "low", "down"]):
                            sentiment = "negative"
                        else:
                            sentiment = "neutral"
                        
                        news = CompanyNews(
                            ticker=ticker,
                            title=article["title"],
                            author=article.get("author", "Unknown"),
                            source=article.get("source", "CryptoCompare"),
                            date=published_date,
                            url=article["url"],
                            sentiment=sentiment
                        )
                        
                        news_list.append(news)
                        
                        if len(news_list) >= limit:
                            break
                
                return news_list
    except Exception as e:
        print(f"CryptoCompare news error for {ticker}: {str(e)}")
    
    # Fallback to empty list if no news found
    return []

def get_market_cap(
    ticker: str,
    end_date: str,
) -> float | None:
    """Fetch market cap from Yahoo Finance."""
    try:
        # Format ticker for yfinance
        formatted_ticker = _format_ticker_for_yfinance(ticker)
        yf_ticker = yf.Ticker(formatted_ticker)
        info = yf_ticker.info
        
        # Get market cap directly
        market_cap = info.get('marketCap')
        
        if market_cap:
            return float(market_cap)
            
        # If not available, try to calculate from price * shares outstanding
        prev_close = info.get('previousClose')
        shares_outstanding = info.get('sharesOutstanding')
        
        if prev_close and shares_outstanding:
            return float(prev_close * shares_outstanding)
            
        return None
        
    except Exception as e:
        print(f"Error fetching market cap for {ticker}: {str(e)}")
        
        # Try to get from financial metrics as fallback
        financial_metrics = get_financial_metrics(ticker, end_date)
        if financial_metrics and financial_metrics[0].market_cap:
            return financial_metrics[0].market_cap
            
        return None

def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    """Convert prices to a DataFrame."""
    if not prices:
        return pd.DataFrame()
    df = pd.DataFrame([p.model_dump() for p in prices])
    df["Date"] = pd.to_datetime(df["time"])
    df.set_index("Date", inplace=True)
    numeric_cols = ["open", "close", "high", "low", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])
    df.sort_index(inplace=True)
    return df

def get_price_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Get price data as a DataFrame."""
    prices = get_prices(ticker, start_date, end_date)
    return prices_to_df(prices)

# Helper functions
def get_value_from_df(df, field_name, date):
    """Safely extract a value from a dataframe if it exists."""
    if df is None or df.empty or field_name not in df.index:
        return None
        
    try:
        value = df.loc[field_name, date]
        return float(value) if not pd.isna(value) else None
    except (KeyError, ValueError, TypeError):
        return None
