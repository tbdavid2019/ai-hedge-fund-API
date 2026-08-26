from langchain_core.messages import HumanMessage
from graph.state import AgentState, show_agent_reasoning
from utils.progress import progress
import pandas as pd
import numpy as np
import json

from tools.api import get_insider_trades, get_company_news


##### Sentiment Agent #####
def sentiment_agent(state: AgentState):
    """Analyzes market sentiment and generates trading signals for multiple tickers."""
    data = state.get("data", {})
    end_date = data.get("end_date")
    tickers = data.get("tickers")

    # Initialize sentiment analysis for each ticker
    sentiment_analysis = {}

    for ticker in tickers:
        progress.update_status("sentiment_agent", ticker, "Fetching insider trades")

        # Get the insider trades
        insider_trades = get_insider_trades(
            ticker=ticker,
            end_date=end_date,
            limit=1000,
        )

        progress.update_status("sentiment_agent", ticker, "Analyzing trading patterns")

        # Get the signals from the insider trades
        transaction_shares = pd.Series([t.transaction_shares for t in insider_trades]).dropna()
        insider_signals = np.where(transaction_shares < 0, "bearish", "bullish").tolist()

        progress.update_status("sentiment_agent", ticker, "Fetching company news")

        # Get the company news
        company_news = get_company_news(ticker, end_date, limit=100)

        # Get the sentiment from the company news
        sentiment = pd.Series([n.sentiment for n in company_news]).dropna()
        news_signals = np.where(sentiment == "negative", "bearish", 
                              np.where(sentiment == "positive", "bullish", "neutral")).tolist()
        
        progress.update_status("sentiment_agent", ticker, "Combining signals")
        # Dynamically set weights based on available data
        has_insiders = len(insider_signals) > 0
        has_news = len(news_signals) > 0

        if has_insiders and has_news:
            insider_weight = 0.3
            news_weight = 0.7
        elif has_insiders:
            insider_weight = 1.0
            news_weight = 0.0
        elif has_news:
            insider_weight = 0.0
            news_weight = 1.0
        else:
            insider_weight = 0.0
            news_weight = 0.0
        
        # Calculate weighted signal counts
        bullish_signals = (
            insider_signals.count("bullish") * insider_weight +
            news_signals.count("bullish") * news_weight
        )
        bearish_signals = (
            insider_signals.count("bearish") * insider_weight +
            news_signals.count("bearish") * news_weight
        )

        if bullish_signals > bearish_signals:
            overall_signal = "bullish"
        elif bearish_signals > bullish_signals:
            overall_signal = "bearish"
        else:
            overall_signal = "neutral"

        # Calculate confidence level based on the weighted proportion
        total_weighted_signals = len(insider_signals) * insider_weight + len(news_signals) * news_weight
        confidence = 50.0  # Default neutral confidence
        if total_weighted_signals > 0:
            confidence = round(max(bullish_signals, bearish_signals) / total_weighted_signals, 2) * 100
        
        insider_summary = f"{insider_signals.count('bullish')} buy / {insider_signals.count('bearish')} sell" if has_insiders else "No insider data"
        news_summary = f"{news_signals.count('bullish')} bullish / {news_signals.count('bearish')} bearish / {news_signals.count('neutral')} neutral" if has_news else "No news data"
        reasoning = (
            f"News Sentiment ({len(news_signals)} items): {news_summary}; Insider Trades: {insider_summary}.\n"
            f"【繁體中文解析】即時新聞情緒 ({len(news_signals)} 則)：{news_summary}；內部人交易：{insider_summary}，綜合評估為 {overall_signal} (信心度 {confidence}%)。"
        )

        sentiment_analysis[ticker] = {
            "signal": overall_signal,
            "confidence": confidence,
            "reasoning": reasoning,
        }

        progress.update_status("sentiment_agent", ticker, "Done")

    # Create the sentiment message
    message = HumanMessage(
        content=json.dumps(sentiment_analysis),
        name="sentiment_agent",
    )

    # Print the reasoning if the flag is set
    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(sentiment_analysis, "Sentiment Analysis Agent")

    # Add the signal to the analyst_signals list
    state["data"]["analyst_signals"]["sentiment_agent"] = sentiment_analysis

    return {
        "messages": [message],
        "data": data,
    }
