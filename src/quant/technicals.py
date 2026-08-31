import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional


def calculate_amihud_illiquidity(
    prices_df: pd.DataFrame,
    window: int = 30
) -> Dict[str, Any]:
    """
    計算 Amihud (2002) 非流動性衝擊指標 (Illiquidity Ratio)。
    衡量每一百萬美元成交量對股價造成的絕對百分比價格衝擊。
    
    Amihud = 1/N * sum( |Return_t| / Dollar_Volume_t ) * 1e6
    """
    if prices_df is None or prices_df.empty or "close" not in prices_df.columns:
        return {"amihud_score": 0.0, "liquidity_tier": "Normal"}
        
    df = prices_df.copy()
    if "volume" not in df.columns or df["volume"].dropna().empty:
        return {"amihud_score": 0.0, "liquidity_tier": "Normal"}
        
    df["returns"] = df["close"].pct_change().abs()
    df["dollar_volume"] = df["close"] * df["volume"]
    
    # 避免除以零
    valid_mask = (df["dollar_volume"] > 1000) & (df["returns"].notna())
    valid_df = df[valid_mask]
    
    if len(valid_df) < 5:
        return {"amihud_score": 0.0, "liquidity_tier": "Normal"}
        
    tail_df = valid_df.tail(window)
    amihud_daily = (tail_df["returns"] / tail_df["dollar_volume"]) * 1e6
    amihud_mean = float(amihud_daily.mean())
    
    if amihud_mean < 0.05:
        tier = "Ultra High Liquidity (極高流動性，幾乎無滑價)"
    elif amihud_mean < 0.50:
        tier = "High Liquidity (高流動性，適合大額配置)"
    elif amihud_mean < 2.0:
        tier = "Moderate Liquidity (一般流動性，需注意衝擊成本)"
    else:
        tier = "Low Liquidity / High Slippage Risk (低流動性，嚴防滑價)"
        
    return {
        "amihud_illiquidity_ratio": round(amihud_mean, 6),
        "liquidity_tier": tier,
        "avg_daily_dollar_volume": round(float(tail_df["dollar_volume"].mean()), 2)
    }


def calculate_atr_dynamic_stops(
    prices_df: pd.DataFrame,
    period: int = 14,
    multiplier: float = 2.0
) -> Dict[str, Any]:
    """
    計算 ATR (Average True Range) 與 Chandelier Trailing Stop (吊燈動態停損位)。
    """
    if prices_df is None or prices_df.empty or len(prices_df) < period + 2:
        return {"atr": 0.0, "trailing_stop_long": 0.0, "trailing_stop_short": 0.0}
        
    df = prices_df.copy()
    high = df["high"] if "high" in df.columns else df["close"]
    low = df["low"] if "low" in df.columns else df["close"]
    close = df["close"]
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = float(tr.rolling(window=period).mean().iloc[-1])
    
    current_price = float(close.iloc[-1])
    recent_high_20 = float(high.tail(20).max())
    recent_low_20 = float(low.tail(20).min())
    
    # 吊燈停損 (Chandelier Exit)
    trailing_stop_long = max(0.0, recent_high_20 - multiplier * atr)
    trailing_stop_short = recent_low_20 + multiplier * atr
    
    # 停損距離百分比
    stop_distance_pct = ((current_price - trailing_stop_long) / current_price) * 100 if current_price > 0 else 0.0
    
    return {
        "atr_14": round(atr, 2),
        "current_price": round(current_price, 2),
        "trailing_stop_long": round(trailing_stop_long, 2),
        "trailing_stop_short": round(trailing_stop_short, 2),
        "stop_distance_pct": round(stop_distance_pct, 2)
    }
