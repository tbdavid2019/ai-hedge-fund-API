#!/usr/bin/env python3
"""
AI Hedge Fund MCP (Model Context Protocol) Server
Exposes 14 legendary investor personas, institutional quant models (VaR, CVaR, DCF sensitivity, Z-Score, F-Score),
and round-table committee debates as standard MCP tools for Cursor, Claude Desktop, Windsurf, and Antigravity.
"""

import os
import sys
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

# Ensure project root & src are in sys.path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

load_dotenv()

from mcp.server.fastmcp import FastMCP
from src.tools.api import get_prices, prices_to_df, get_financial_metrics, get_market_cap, search_line_items
from src.quant.risk import calculate_var_cvar, calculate_volatility_metrics, calculate_risk_adjusted_position_size
from src.quant.valuation import calculate_dcf_sensitivity, calculate_altman_z_score, calculate_piotroski_f_score
from src.quant.technicals import calculate_amihud_illiquidity, calculate_atr_dynamic_stops

# Initialize FastMCP Server
mcp = FastMCP(
    "ai-hedge-fund",
    instructions="Institutional AI Hedge Fund with 14 legendary investor personas (Buffett, Burry, Wood, Ackman, Pelosi, Lynch, etc.), quantitative risk/valuation models (VaR/CVaR/Altman Z/Piotroski F), and multi-round investment committee debates."
)


@mcp.tool()
def analyze_stock_with_committee(
    tickers: str,
    analysts: str = "warren_buffett,charlie_munger,cathie_wood,michael_burry,bill_ackman,technicals,valuation,risk_manager",
    enable_round_table: bool = True,
    round_table_rounds: int = 1,
    initial_cash: float = 100000.0,
    model_name: Optional[str] = None
) -> str:
    """
    Run an AI Hedge Fund Committee analysis on one or more stock tickers.
    
    Args:
        tickers: Comma-separated ticker symbols (e.g. "AAPL,TSLA" or "2330.TW" or "BTC-USD")
        analysts: Comma-separated list of analyst personas. Available:
                  warren_buffett, charlie_munger, ben_graham, cathie_wood, bill_ackman,
                  nancy_pelosi, michael_burry, peter_lynch, phil_fisher, wsb_agent,
                  technicals, fundamentals, sentiment, valuation, risk_manager
        enable_round_table: Whether to simulate a multi-round debate among selected personas
        round_table_rounds: Number of debate rounds (default: 1)
        initial_cash: Initial portfolio cash for position sizing (default: 100000.0)
        model_name: Optional LLM model override (defaults to deepseek-v4-flash or Groq)
        
    Returns:
        JSON string containing the final portfolio decision, confidence, analyst breakdown, and debate transcript.
    """
    try:
        from src.main import run_hedge_fund
    except ImportError as e:
        return json.dumps({
            "status": "error",
            "message": f"Required agent dependencies not installed in current environment: {e}. Please install requirements.txt or run inside Docker."
        }, ensure_ascii=False)

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    selected_list = [a.strip().lower() for a in analysts.split(",") if a.strip()]
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - relativedelta(months=3)).strftime("%Y-%m-%d")
    
    portfolio = {
        "cash": initial_cash,
        "cost_basis": {}
    }
    
    # Auto-detect crypto
    is_crypto = any("-USD" in t or "/USD" in t for t in ticker_list)
    
    # LLM configuration
    effective_model = model_name or os.getenv("PRIMARY_MODEL", "deepseek-v4-flash")
    effective_provider = os.getenv("PRIMARY_PROVIDER", "Groq")
    
    result = run_hedge_fund(
        tickers=ticker_list,
        start_date=start_date,
        end_date=end_date,
        portfolio=portfolio,
        show_reasoning=False,
        selected_analysts=selected_list,
        model_name=effective_model,
        model_provider=effective_provider,
        is_crypto=is_crypto,
        enable_round_table=enable_round_table,
        round_table_rounds=round_table_rounds
    )
    
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_stock_quant_audit(ticker: str) -> str:
    """
    Calculate comprehensive institutional quantitative metrics for a stock without running LLMs:
    - 95%/99% VaR & CVaR (Expected Shortfall)
    - Realized Volatility Regimes (20d, 60d, 120d)
    - DCF 5x5 Sensitivity Matrix (WACC vs. Terminal Growth)
    - Altman Z-Score (Bankruptcy Risk Model)
    - Piotroski F-Score (0-9 Financial Strength Metric)
    - Amihud Illiquidity Ratio & ATR Chandelier Dynamic Trailing Stops
    
    Args:
        ticker: Stock ticker symbol (e.g. "AAPL", "NVDA", "2330.TW", "TSLA")
    """
    clean_ticker = ticker.strip().upper()
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - relativedelta(months=6)).strftime("%Y-%m-%d")
    
    prices = get_prices(ticker=clean_ticker, start_date=start_date, end_date=end_date)
    prices_df = prices_to_df(prices) if prices else None
    
    quant_report: Dict[str, Any] = {
        "ticker": clean_ticker,
        "as_of_date": end_date,
    }
    
    if prices_df is not None and not prices_df.empty and "close" in prices_df.columns:
        close_series = prices_df["close"].dropna()
        current_price = float(close_series.iloc[-1])
        returns = close_series.pct_change().dropna()
        
        quant_report["price_summary"] = {
            "current_price": current_price,
            "period_high": float(prices_df["high"].max()) if "high" in prices_df else current_price,
            "period_low": float(prices_df["low"].min()) if "low" in prices_df else current_price,
        }
        quant_report["risk_metrics"] = calculate_var_cvar(returns)
        quant_report["volatility_regime"] = calculate_volatility_metrics(prices_df)
        quant_report["liquidity_and_stops"] = {
            **calculate_amihud_illiquidity(prices_df),
            **calculate_atr_dynamic_stops(prices_df)
        }
    else:
        quant_report["price_summary"] = "Price history unavailable"
        
    financial_metrics = get_financial_metrics(ticker=clean_ticker, end_date=end_date, period="ttm")
    market_cap = get_market_cap(ticker=clean_ticker, end_date=end_date) or 1.0
    
    if financial_metrics:
        m = financial_metrics[0]
        prev_m = financial_metrics[1] if len(financial_metrics) > 1 else None
        
        financial_line_items = search_line_items(
            ticker=clean_ticker,
            line_items=[
                "free_cash_flow", "net_income", "depreciation_and_amortization",
                "capital_expenditure", "working_capital", "total_assets",
                "total_liabilities", "retained_earnings", "operating_income", "total_revenue"
            ],
            end_date=end_date,
            period="ttm",
            limit=2
        )
        curr_item = financial_line_items[0] if financial_line_items else None
        prev_item = financial_line_items[1] if len(financial_line_items) > 1 else None
        
        fcf = getattr(curr_item, "free_cash_flow", None) or getattr(m, "free_cash_flow", 0.0) or 100_000.0
        cur_price = quant_report.get("price_summary", {}).get("current_price", 100.0)
        
        quant_report["dcf_sensitivity"] = calculate_dcf_sensitivity(
            free_cash_flow=float(fcf),
            current_price=float(cur_price),
            market_cap=float(market_cap),
            base_wacc=0.10,
            base_terminal_growth=0.025,
            forecast_growth=getattr(m, "earnings_growth", 0.08) or 0.08
        )
        
        quant_report["altman_z_score"] = calculate_altman_z_score(
            working_capital=getattr(curr_item, "working_capital", None),
            total_assets=getattr(curr_item, "total_assets", None) or getattr(m, "total_assets", None),
            retained_earnings=getattr(curr_item, "retained_earnings", None),
            ebit=getattr(curr_item, "operating_income", None) or getattr(m, "operating_income", None),
            market_cap=market_cap,
            total_liabilities=getattr(curr_item, "total_liabilities", None) or getattr(m, "total_liabilities", None),
            total_revenue=getattr(curr_item, "total_revenue", None) or getattr(m, "total_revenue", None)
        )
        
        curr_m_dict = {
            "net_income": getattr(curr_item, "net_income", 0.0) or getattr(m, "net_income", 0.0),
            "return_on_assets": getattr(m, "return_on_assets", 0.0),
            "operating_cash_flow": getattr(m, "operating_cash_flow", 0.0) or fcf,
            "current_ratio": getattr(m, "current_ratio", 1.0),
            "gross_margin": getattr(m, "gross_margin", 0.0),
            "debt_to_equity": getattr(m, "debt_to_equity", 0.0),
        }
        prev_m_dict = {
            "current_ratio": getattr(prev_m, "current_ratio", 1.0) if prev_m else 1.0,
            "gross_margin": getattr(prev_m, "gross_margin", 0.0) if prev_m else 0.0,
            "debt_to_equity": getattr(prev_m, "debt_to_equity", 0.0) if prev_m else 0.0,
        } if prev_m else None
        
        quant_report["piotroski_f_score"] = calculate_piotroski_f_score(curr_m_dict, prev_m_dict)
    
    return json.dumps(quant_report, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Run standard MCP server over stdio
    mcp.run(transport="stdio")
