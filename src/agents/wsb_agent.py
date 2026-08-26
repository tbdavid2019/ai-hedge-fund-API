from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from graph.state import AgentState, show_agent_reasoning
from pydantic import BaseModel, Field
import json
from typing_extensions import Literal
from utils.progress import progress
from utils.llm import call_llm
import praw
from datetime import datetime, timedelta
import os

from tools.api import get_financial_metrics, get_market_cap, search_line_items, get_company_news


class WSBSignal(BaseModel):
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float
    reasoning: str


class RedditPost(BaseModel):
    title: str
    score: int
    upvote_ratio: float
    num_comments: int
    created_utc: float
    url: str
    text: str = ""
    sentiment: str = "neutral"  # Will be filled in with analysis


def wsb_agent(state: AgentState):
    """
    Analyzes stocks using WallStreetBets-style metrics:
    1. Meme potential and social media hype
    2. Short squeeze candidates
    3. Options chain analysis for YOLO potential
    4. Contrarian plays against institutional perspectives
    5. Momentum-based technical indicators
    """
    data = state["data"]
    end_date = data["end_date"]
    start_date = data.get("start_date")  # This might be None
    tickers = data["tickers"]
    
    analysis_data = {}
    wsb_analysis = {}
    
    for ticker in tickers:
        progress.update_status("wsb_agent", ticker, "Fetching financial metrics")
        # Fetch required data
        metrics = get_financial_metrics(ticker, end_date, period="annual", limit=5)
        
        progress.update_status("wsb_agent", ticker, "Gathering financial line items")
        financial_line_items = search_line_items(
            ticker,
            [
                "revenue", 
                "net_income",
                "outstanding_shares",
                "cash_and_equivalents",
                "total_debt",
                "research_and_development",
            ],
            end_date,
            period="annual",
            limit=5,
        )
        
        progress.update_status("wsb_agent", ticker, "Getting market cap")
        market_cap = get_market_cap(ticker, end_date)
        
        progress.update_status("wsb_agent", ticker, "Fetching Reddit WSB posts")
        # Get a small number of high-quality, recent Reddit posts
        print(f"\n--- FETCHING TOP RECENT WSB POSTS FOR ${ticker} ---\n")
        reddit_posts = get_reddit_posts(ticker, start_date, end_date, limit=10)
        
        progress.update_status("wsb_agent", ticker, "Analyzing social media hype")
        # Get company news to analyze social sentiment
        company_news = get_company_news(ticker, end_date, limit=100)
        
        progress.update_status("wsb_agent", ticker, "Analyzing meme potential")
        meme_analysis = analyze_meme_potential(company_news, ticker, market_cap, reddit_posts)
        
        progress.update_status("wsb_agent", ticker, "Identifying short squeeze potential")
        squeeze_analysis = analyze_short_squeeze_potential(metrics, financial_line_items, market_cap, ticker)
        
        progress.update_status("wsb_agent", ticker, "Analyzing YOLO options potential")
        options_analysis = analyze_options_potential(metrics, financial_line_items, market_cap)
        
        # Calculate total score
        total_score = (
            meme_analysis["score"] + 
            squeeze_analysis["score"] + 
            options_analysis["score"]
        )
        max_possible_score = 15  # Normalize scores to be out of 15
        
        # Generate trading signal based on WSB mentality
        if total_score >= 0.6 * max_possible_score:  # Lower threshold for bullish - WSB is optimistic!
            signal = "bullish"
        elif total_score <= 0.3 * max_possible_score:
            signal = "bearish"
        else:
            signal = "neutral"
        
        # Store analysis data
        analysis_data[ticker] = {
            "signal": signal,
            "score": total_score,
            "max_score": max_possible_score,
            "meme_analysis": meme_analysis,
            "squeeze_analysis": squeeze_analysis,
            "options_analysis": options_analysis,
            "market_cap": market_cap,
            "reddit_data": {
                "post_count": len(reddit_posts),
                "top_posts": [post.model_dump() for post in reddit_posts[:5]] if reddit_posts else []
            }
        }
        
        progress.update_status("wsb_agent", ticker, "Generating WSB-style analysis")
        wsb_output = generate_wsb_output(
            ticker=ticker,
            analysis_data=analysis_data,
            model_name=state["metadata"]["model_name"],
            model_provider=state["metadata"]["model_provider"],
        )
        
        # Store analysis in consistent format with other agents
        wsb_analysis[ticker] = {
            "signal": wsb_output.signal,
            "confidence": wsb_output.confidence,
            "reasoning": wsb_output.reasoning,
        }
        
        progress.update_status("wsb_agent", ticker, "Done")
        
        # Remove testimonial feature and simplified sentiment summary
        if reddit_posts:
            # Display simple stats about the posts
            bullish_count = sum(1 for post in reddit_posts if post.sentiment == "bullish")
            bearish_count = sum(1 for post in reddit_posts if post.sentiment == "bearish")
            neutral_count = len(reddit_posts) - bullish_count - bearish_count
            
            print(f"\nWSB Stats for {ticker}: {len(reddit_posts)} posts found.")
            print(f"Sentiment: {bullish_count} bullish, {bearish_count} bearish, {neutral_count} neutral\n")
    
    # Create the message
    message = HumanMessage(
        content=json.dumps(wsb_analysis),
        name="wsb_agent"
    )
    
    # Show reasoning if requested
    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(wsb_analysis, "WallStreetBets Agent")
    
    # Add the signal to the analyst_signals list
    state["data"]["analyst_signals"]["wsb_agent"] = wsb_analysis
    
    return {
        "messages": [message],
        "data": state["data"]
    }


def get_reddit_posts(ticker: str, start_date: str = None, end_date: str = None, limit: int = 10) -> list[RedditPost]:
    """
    Fetch a small number of recent, high-quality Reddit posts from r/wallstreetbets about a specific ticker.
    Supports PRAW official API with automatic fallback to 2md search engine.
    """
    all_posts = []

    # 1. Try PRAW official API
    try:
        reddit_client_id = os.environ.get("REDDIT_CLIENT_ID")
        reddit_client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        reddit_user_agent = os.environ.get("REDDIT_USER_AGENT", "wsb_agent:v1.0")
        
        if reddit_client_id and reddit_client_secret:
            reddit = praw.Reddit(
                client_id=reddit_client_id,
                client_secret=reddit_client_secret,
                user_agent=reddit_user_agent
            )
            
            subreddit = reddit.subreddit("wallstreetbets")
            search_terms = [f"${ticker}", ticker]
            initial_fetch_limit = 20
            
            for term in search_terms:
                new_results = subreddit.search(
                    term,
                    sort="new",
                    time_filter="day",
                    limit=initial_fetch_limit // len(search_terms)
                )
                
                for post in new_results:
                    if post.score >= 10:
                        reddit_post = create_reddit_post(post)
                        all_posts.append(reddit_post)
            
            if len(all_posts) < limit:
                for term in search_terms:
                    hot_results = subreddit.search(
                        term,
                        sort="hot",
                        time_filter="week",
                        limit=initial_fetch_limit // len(search_terms)
                    )
                    
                    for post in hot_results:
                        if any(p.url == f"https://reddit.com{post.permalink}" for p in all_posts):
                            continue
                        reddit_post = create_reddit_post(post)
                        all_posts.append(reddit_post)
                        if len(all_posts) >= limit:
                            break
    except Exception as e:
        print(f"PRAW Reddit API error: {str(e)}")

    # 2. Fallback to 2md web search for Reddit/WSB posts
    if not all_posts:
        try:
            from tools.url2md import search_web_2md
            print(f"[WSB Agent] Searching Reddit discussions via 2md for ${ticker}...")
            queries = [
                f"site:reddit.com/r/wallstreetbets {ticker}",
                f"{ticker} reddit wallstreetbets stock",
                f"{ticker} stock discussion reddit",
            ]
            
            seen_urls = set()
            for q in queries:
                items = search_web_2md(q, limit=limit)
                for item in items:
                    url = item.get("url", "")
                    title = item.get("title", "")
                    desc = item.get("description", "")
                    
                    if url and url not in seen_urls and ("reddit.com" in url or "wallstreetbets" in title.lower() or ticker.lower() in title.lower()):
                        seen_urls.add(url)
                        # Determine sentiment
                        full_text = f"{title} {desc}".lower()
                        bullish_words = ["bull", "buy", "calls", "moon", "rocket", "yolo", "tendies", "gain", "long", "hold", "pump"]
                        bearish_words = ["bear", "put", "short", "drill", "crash", "tank", "loss", "guh", "dump", "sell"]
                        
                        b_cnt = sum(1 for w in bullish_words if w in full_text)
                        s_cnt = sum(1 for w in bearish_words if w in full_text)
                        
                        sentiment = "bullish" if b_cnt > s_cnt else ("bearish" if s_cnt > b_cnt else "neutral")
                        
                        post = RedditPost(
                            title=title,
                            score=max(10, (b_cnt + s_cnt) * 50 + 25),
                            upvote_ratio=0.85 if sentiment == "bullish" else 0.65,
                            num_comments=max(5, (b_cnt + s_cnt) * 15 + 10),
                            created_utc=datetime.now().timestamp() - 3600,
                            url=url,
                            text=desc,
                            sentiment=sentiment
                        )
                        all_posts.append(post)
                        print(f"2md WSB Result: {title} ({sentiment}) - {url}")
                        
                    if len(all_posts) >= limit:
                        break
                if len(all_posts) >= limit:
                    break
        except Exception as e:
            print(f"[WSB Agent] 2md search fallback error: {str(e)}")

    return all_posts[:limit]


def create_reddit_post(post) -> RedditPost:
    """Helper function to create a RedditPost from a PRAW post object"""
    reddit_post = RedditPost(
        title=post.title,
        score=post.score,
        upvote_ratio=post.upvote_ratio,
        num_comments=post.num_comments,
        created_utc=post.created_utc,
        url=f"https://reddit.com{post.permalink}",
        text=post.selftext if hasattr(post, "selftext") else ""
    )
    
    # Simple sentiment analysis based on keywords
    text = (post.title + " " + post.selftext).lower()
    bullish_words = ["bull", "buy", "calls", "moon", "rocket", "yolo", "tendies", "gain", "long"]
    bearish_words = ["bear", "put", "short", "drill", "crash", "tank", "loss", "guh", "dump"]
    
    bullish_count = sum(1 for word in bullish_words if word in text)
    bearish_count = sum(1 for word in bearish_words if word in text)
    
    if bullish_count > bearish_count:
        reddit_post.sentiment = "bullish"
    elif bearish_count > bullish_count:
        reddit_post.sentiment = "bearish"
    
    return reddit_post


def analyze_meme_potential(company_news: list, ticker: str, market_cap: float, reddit_posts: list[RedditPost] = None) -> dict:
    """
    Analyze a stock's potential as a meme stock.
    
    Factors:
    - Social media buzz/mentions
    - Stock price volatility
    - Brand recognition and story potential
    - Market cap (small to mid-cap preferred)
    - Narrative potential (disruption, short squeeze, etc.)
    - Reddit activity (post volume, sentiment, engagement)
    """
    score = 0
    details = []
    
    # Check for social media mentions in news
    social_keywords = [
        'reddit', 'twitter', 'wallstreetbets', 'wsb', 'social media', 'viral',
        'meme', 'trending', 'retail investors', 'robinhood', 'tiktok', 'hype',
        'discord', 'influencer', 'short sellers', 'squeeze'
    ]
    
    social_mentions = 0
    for news in company_news:
        title_lower = news.title.lower()
        for keyword in social_keywords:
            if keyword in title_lower:
                social_mentions += 1
                break
    
    # Score based on social mentions
    if social_mentions > 10:
        score += 5
        details.append(f"Major social media buzz: {social_mentions} mentions - peak meme potential")
    elif social_mentions > 5:
        score += 3
        details.append(f"Moderate social media presence: {social_mentions} mentions - gaining traction")
    elif social_mentions > 2:
        score += 1
        details.append(f"Some social media activity: {social_mentions} mentions - on the radar")
    else:
        details.append("Limited social media mentions - no meme buzz detected")
    
    # Reddit activity analysis
    if reddit_posts:
        # Count posts by sentiment
        bullish_posts = sum(1 for post in reddit_posts if post.sentiment == "bullish")
        bearish_posts = sum(1 for post in reddit_posts if post.sentiment == "bearish")
        
        # Total engagement (upvotes + comments)
        total_engagement = sum(post.score + post.num_comments for post in reddit_posts)
        avg_engagement = total_engagement / len(reddit_posts) if reddit_posts else 0
        
        # Calculate Reddit score component
        reddit_score = 0
        
        # Post volume scoring
        if len(reddit_posts) > 20:
            reddit_score += 2
            details.append(f"Massive Reddit activity: {len(reddit_posts)} recent posts - viral meme status")
        elif len(reddit_posts) > 10:
            reddit_score += 1.5
            details.append(f"Strong Reddit activity: {len(reddit_posts)} recent posts - high meme potential")
        elif len(reddit_posts) > 5:
            reddit_score += 1
            details.append(f"Moderate Reddit activity: {len(reddit_posts)} recent posts - growing meme interest")
        elif len(reddit_posts) > 0:
            reddit_score += 0.5
            details.append(f"Some Reddit activity: {len(reddit_posts)} recent posts - on WSB radar")
        
        # Sentiment scoring (WSB loves positivity)
        sentiment_ratio = bullish_posts / len(reddit_posts) if reddit_posts else 0
        if sentiment_ratio > 0.8:
            reddit_score += 1.5
            details.append(f"Overwhelmingly bullish Reddit sentiment: {sentiment_ratio:.0%} positive posts - rocket emoji territory")
        elif sentiment_ratio > 0.6:
            reddit_score += 1
            details.append(f"Bullish Reddit sentiment: {sentiment_ratio:.0%} positive posts - gaining ape followers")
        
        # Engagement scoring
        if avg_engagement > 1000:
            reddit_score += 1.5
            details.append(f"Massive Reddit engagement: {avg_engagement:.0f} avg upvotes+comments - peak meme energy")
        elif avg_engagement > 500:
            reddit_score += 1
            details.append(f"High Reddit engagement: {avg_engagement:.0f} avg upvotes+comments - strong meme potential")
        elif avg_engagement > 100:
            reddit_score += 0.5
            details.append(f"Decent Reddit engagement: {avg_engagement:.0f} avg upvotes+comments - respectable attention")
        
        score += min(reddit_score, 5)  # Cap Reddit score at 5 points
    
    # Market cap analysis for meme potential
    # WSB tends to prefer stocks they can actually move - small to mid cap
    if market_cap:
        if 100_000_000 <= market_cap <= 10_000_000_000:  # $100M to $10B
            score += 3
            details.append(f"Perfect market cap for memes: ${market_cap/1_000_000_000:.1f}B - small enough to move")
        elif market_cap < 100_000_000:  # < $100M
            score += 2
            details.append(f"Micro-cap: ${market_cap/1_000_000:.1f}M - moonshot potential but super risky")
        elif market_cap <= 50_000_000_000:  # < $50B
            score += 1
            details.append(f"Mid-cap: ${market_cap/1_000_000_000:.1f}B - still movable with enough retail interest")
        else:
            details.append(f"Too large: ${market_cap/1_000_000_000:.1f}B - hard for retail to influence")
    
    # Ticker symbol analysis - shorter is better for memes
    if len(ticker) <= 3:
        score += 2
        details.append(f"Short, catchy ticker: ${ticker} - perfect for memes")
    elif len(ticker) == 4:
        score += 1
        details.append(f"Decent ticker length: ${ticker} - workable for memes")
    
    # Check for brand recognition from company name or news mentions
    brand_score = 0
    
    # Special cases for well-known meme stocks
    if ticker in ["GME", "AMC", "BB", "PLTR", "TSLA", "HOOD", "BBBY", "NOK", "WISH", "CLOV"]:
        brand_score = 5
        details.append(f"Classic meme stock: ${ticker} - proven retail favorite")
    else:
        # Extract company name from news if available
        company_names = set([news.title.split(':')[0] for news in company_news[:5] if ':' in news.title])
        
        if len(company_names) > 0:
            brand_score = min(3, len(company_names))
            details.append(f"Some brand recognition: mentioned across {len(company_names)} sources")
    
    score += brand_score
    
    reddit_stats = {
        "post_count": len(reddit_posts) if reddit_posts else 0,
        "bullish_count": bullish_posts if 'bullish_posts' in locals() else 0,
        "bearish_count": bearish_posts if 'bearish_posts' in locals() else 0,
        "avg_engagement": avg_engagement if 'avg_engagement' in locals() else 0
    }
    
    return {
        "score": min(score, 10) / 2,  # Normalize to 0-5 scale
        "details": "; ".join(details),
        "social_mentions": social_mentions,
        "brand_score": brand_score,
        "reddit_stats": reddit_stats
    }


def analyze_short_squeeze_potential(metrics: list, financial_line_items: list, market_cap: float, ticker: str) -> dict:
    """
    Analyze potential for a short squeeze.
    
    Factors:
    - Short interest ratio (higher is better for a squeeze)
    - Days to cover (higher is better for a squeeze)
    - Float size (smaller is better)
    - Recent price momentum
    - Institutional vs. retail ownership
    """
    score = 0
    details = []
    
    # For a real implementation, you would pull short interest data from an API
    # Here we'll simulate it based on available metrics
    
    if not metrics or not financial_line_items:
        return {
            "score": 0,
            "details": "Insufficient data to analyze short squeeze potential"
        }
    
    # Check for price volatility - a prerequisite for a squeeze
    # In a real implementation, you'd calculate the actual volatility
    if len(metrics) >= 2:
        # Simulate high volatility for stocks with high debt and low cash
        latest = financial_line_items[0]
        if hasattr(latest, 'cash_and_equivalents') and hasattr(latest, 'total_debt'):
            if latest.cash_and_equivalents and latest.total_debt:
                cash_to_debt = latest.cash_and_equivalents / latest.total_debt if latest.total_debt > 0 else float('inf')
                if cash_to_debt < 0.3:
                    score += 2
                    details.append("High cash/debt pressure - boosts squeeze potential")
                elif cash_to_debt < 0.7:
                    score += 1
                    details.append("Moderate cash/debt pressure - some squeeze potential")
    
    # Estimated float based on market cap and financial data
    float_score = 0
    if market_cap and financial_line_items[0].outstanding_shares:
        shares = financial_line_items[0].outstanding_shares
        avg_price = market_cap / shares
        
        # Small float is better for squeezes
        if shares < 50_000_000:
            float_score = 3
            details.append(f"Small float ({shares/1_000_000:.1f}M shares) - perfect for a squeeze!")
        elif shares < 200_000_000:
            float_score = 2
            details.append(f"Medium float ({shares/1_000_000:.1f}M shares) - decent squeeze potential")
        elif shares < 500_000_000:
            float_score = 1
            details.append(f"Large float ({shares/1_000_000:.1f}M shares) - harder to squeeze but possible")
        else:
            details.append(f"Huge float ({shares/1_000_000:.1f}M shares) - would take massive volume to squeeze")
    
    score += float_score
    
    # Profitability factor - unprofitable companies often have higher short interest
    profit_score = 0
    if len(financial_line_items) >= 2:
        recent_profits = [item.net_income for item in financial_line_items[:2] if hasattr(item, 'net_income') and item.net_income is not None]
        if recent_profits and all(profit < 0 for profit in recent_profits):
            profit_score = 3
            details.append("Consistently unprofitable - likely high short interest")
        elif recent_profits and any(profit < 0 for profit in recent_profits):
            profit_score = 2
            details.append("Mixed profitability - moderate short interest likely")
    
    score += profit_score
    
    # Industry factor - some industries are more prone to short squeezes
    # This would be better with real industry classification data
    industry_score = 0
    if ticker.startswith(('GME', 'AMC', 'BB', 'NOK')):  # Legacy tech or entertainment
        industry_score = 2
        details.append("Industry with historical squeeze precedent")
    elif ticker.startswith(('TSLA', 'LCID', 'RIVN')):  # EV sector
        industry_score = 2
        details.append("EV sector with high short interest history")
    elif ticker.startswith(('PLTR', 'AI', 'PATH')):  # Tech/AI
        industry_score = 1
        details.append("Tech sector with moderate short interest potential")
    
    score += industry_score
    
    return {
        "score": min(score, 10) / 2,  # Normalize to 0-5 scale
        "details": "; ".join(details),
        "float_score": float_score,
        "profit_score": profit_score,
        "industry_score": industry_score
    }


def analyze_options_potential(metrics: list, financial_line_items: list, market_cap: float) -> dict:
    """
    Analyze a stock's potential for options trading strategies popular on WSB.
    
    Factors:
    - Price volatility (higher is better for options)
    - Options chain liquidity (estimated)
    - Price point (not too low, not too high)
    - Catalyst potential from news or events
    - Earnings surprise history
    """
    score = 0
    details = []
    
    if not metrics or not financial_line_items or not market_cap:
        return {
            "score": 0,
            "details": "Insufficient data for options analysis"
        }
    
    # Calculate share price (market cap / outstanding shares)
    share_price = 0
    if financial_line_items[0].outstanding_shares and financial_line_items[0].outstanding_shares > 0:
        share_price = market_cap / financial_line_items[0].outstanding_shares
    
    # Analyze price point for options liquidity
    price_score = 0
    if 10 <= share_price <= 500:
        price_score = 3
        details.append(f"Perfect price range for options: ${share_price:.2f} - liquid chains")
    elif 5 <= share_price < 10:
        price_score = 2
        details.append(f"Affordable options but less liquid: ${share_price:.2f}")
    elif 500 < share_price <= 1000:
        price_score = 2
        details.append(f"High-priced options: ${share_price:.2f} - expensive premiums but good leverage")
    elif share_price > 1000:
        price_score = 1
        details.append(f"Very expensive options: ${share_price:.2f} - may need spreads")
    elif share_price > 0:
        price_score = 1
        details.append(f"Too cheap for good options: ${share_price:.2f} - penny stock territory")
    
    score += price_score
    
    # Analyze volatility potential (for real implementation, use actual volatility metrics)
    vol_score = 0
    if len(metrics) >= 2:
        # If price-to-earnings ratio is negative or extremely high, that often indicates volatility
        pe_ratio = metrics[0].price_to_earnings_ratio
        if pe_ratio is not None and (pe_ratio < 0 or pe_ratio > 100):
            vol_score = 3
            details.append(f"High expected volatility: P/E ratio {pe_ratio:.1f}")
        elif pe_ratio is not None and pe_ratio > 50:
            vol_score = 2
            details.append(f"Moderate expected volatility: P/E ratio {pe_ratio:.1f}")
        elif pe_ratio is not None:
            vol_score = 1
            details.append(f"Lower expected volatility: P/E ratio {pe_ratio:.1f}")
    
    score += vol_score
    
    # Analyze market cap for options liquidity
    mcap_score = 0
    if market_cap > 10_000_000_000:  # > $10B
        mcap_score = 3
        details.append(f"Large cap (${market_cap/1_000_000_000:.1f}B) - liquid options market")
    elif market_cap > 2_000_000_000:  # > $2B
        mcap_score = 2
        details.append(f"Mid cap (${market_cap/1_000_000_000:.1f}B) - decent options liquidity")
    elif market_cap > 300_000_000:  # > $300M
        mcap_score = 1
        details.append(f"Small cap (${market_cap/1_000_000:.1f}M) - limited options liquidity")
    else:
        details.append(f"Micro cap (${market_cap/1_000_000:.1f}M) - poor options liquidity")
    
    score += mcap_score
    
    # Additional factors for WSB-style options plays
    if financial_line_items[0].research_and_development and financial_line_items[0].revenue:
        # Check if R&D is high relative to revenue (tech/biotech plays popular on WSB)
        rd_to_revenue = financial_line_items[0].research_and_development / financial_line_items[0].revenue
        if rd_to_revenue > 0.2:  # >20% of revenue on R&D
            score += 1
            details.append(f"High R&D spending ({rd_to_revenue:.1%} of revenue) - potential for binary events")
    
    return {
        "score": min(score, 10) / 2,  # Normalize to 0-5 scale
        "details": "; ".join(details),
        "price": share_price,
        "price_score": price_score,
        "volatility_score": vol_score,
        "market_cap_score": mcap_score
    }


def generate_wsb_output(
    ticker: str,
    analysis_data: dict[str, any],
    model_name: str,
    model_provider: str,
) -> WSBSignal:
    """Generate WallStreetBets style investment decision from LLM."""
    template = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a WallStreetBets trader analyzing stocks using the distinctive WSB approach and vocabulary:

            1. Look for moonshot opportunities with asymmetric risk/reward
            2. Identify potential short squeeze candidates and meme stock momentum
            3. Consider YOLO-worthy options plays (particularly weeklies with high leverage)
            4. Value social sentiment and Reddit activity over traditional fundamentals
            5. Use WSB terminology correctly in your analysis

            Key WSB terminology to incorporate:
            - "Tendies" (profits/money)
            - "Diamond hands" (holding despite volatility)
            - "Paper hands" (selling too early)
            - "YOLO" (all-in bets)
            - "FD" (risky weekly options)
            - "Autist" (someone who does thorough analysis)
            - "Smooth brain" (someone who makes poor decisions)
            - "Apes" (WSB community members)
            - "To the moon" (stock with huge upside potential)
            - "Drilling" (stock rapidly declining)
            
            Your analysis style:
            - Focus on potential asymmetric gains over conservative investments
            - Consider both long plays and short squeeze opportunities
            - Emphasize options strategies with high leverage potential
            - Be contrarian when institutional investors are overly bearish
            - Consider Reddit activity and sentiment as key indicators
            - Maintain factual analysis while incorporating WSB culture
            
            Provide a signal (bullish/bearish/neutral) with confidence level and clear reasoning using appropriate WSB terminology.
            """
        ),
        (
            "human",
            """Based on the following WSB-style analysis, create an investment signal:

            Analysis Data for {ticker}:
            {analysis_data}

            Return the trading signal in the following JSON format:
            {{
              "signal": "bullish/bearish/neutral",
              "confidence": float (0-100),
              "reasoning": "string"
            }}
            """
        )
    ])

    # Generate the prompt
    prompt = template.invoke({
        "analysis_data": json.dumps(analysis_data, indent=2),
        "ticker": ticker
    })

    # Create default factory for WSBSignal
    def create_default_signal():
        return WSBSignal(signal="neutral", confidence=0.0, reasoning="Error in analysis, defaulting to neutral")

    return call_llm(
        prompt=prompt,
        model_name=model_name,
        model_provider=model_provider,
        pydantic_model=WSBSignal,
        agent_name="wsb_agent",
        default_factory=create_default_signal,
    ) 