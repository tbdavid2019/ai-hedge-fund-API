import math
import json
import pandas as pd
import numpy as np
from langchain_core.messages import HumanMessage
from graph.state import AgentState, show_agent_reasoning
from tools.api import get_prices, prices_to_df
from utils.progress import progress
from src.quant.technicals import calculate_amihud_illiquidity, calculate_atr_dynamic_stops


def safe_float(val, default=0.0):
    """Safely convert value to float, replacing NaN, Infinity, or None with default."""
    if val is None or pd.isna(val):
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:
        return default


##### Technical Analyst #####
def technical_analyst_agent(state: AgentState):
    """
    Sophisticated technical analysis system that combines multiple trading strategies for multiple tickers:
    1. Trend Following
    2. Mean Reversion
    3. Momentum
    4. Volatility Analysis
    5. Statistical Arbitrage Signals
    6. Amihud Liquidity Impact & ATR Dynamic Stops
    """
    data = state["data"]
    start_date = data["start_date"]
    end_date = data["end_date"]
    tickers = data["tickers"]

    # Initialize analysis for each ticker
    technical_analysis = {}

    for ticker in tickers:
        progress.update_status("technical_analyst_agent", ticker, "Analyzing price data")

        # Get the historical price data
        prices = get_prices(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
        )

        if not prices:
            progress.update_status("technical_analyst_agent", ticker, "Failed: No price data found")
            continue

        # Convert prices to a DataFrame
        prices_df = prices_to_df(prices)

        progress.update_status("technical_analyst_agent", ticker, "Calculating trend signals")
        trend_signals = calculate_trend_signals(prices_df)

        progress.update_status("technical_analyst_agent", ticker, "Calculating mean reversion")
        mean_reversion_signals = calculate_mean_reversion_signals(prices_df)

        progress.update_status("technical_analyst_agent", ticker, "Calculating momentum")
        momentum_signals = calculate_momentum_signals(prices_df)

        progress.update_status("technical_analyst_agent", ticker, "Analyzing volatility")
        volatility_signals = calculate_volatility_signals(prices_df)

        progress.update_status("technical_analyst_agent", ticker, "Statistical analysis")
        stat_arb_signals = calculate_stat_arb_signals(prices_df)

        progress.update_status("technical_analyst_agent", ticker, "Calculating liquidity & dynamic stops")
        amihud_metrics = calculate_amihud_illiquidity(prices_df)
        atr_metrics = calculate_atr_dynamic_stops(prices_df)

        # Combine all signals using a weighted ensemble approach
        strategy_weights = {
            "trend": 0.25,
            "mean_reversion": 0.20,
            "momentum": 0.25,
            "volatility": 0.15,
            "stat_arb": 0.15,
        }

        progress.update_status("technical_analyst_agent", ticker, "Combining signals")
        combined_signal = weighted_signal_combination(
            {
                "trend": trend_signals,
                "mean_reversion": mean_reversion_signals,
                "momentum": momentum_signals,
                "volatility": volatility_signals,
                "stat_arb": stat_arb_signals,
            },
            strategy_weights,
        )

        # Generate detailed analysis report for this ticker
        technical_analysis[ticker] = {
            "signal": combined_signal["signal"],
            "confidence": round(combined_signal["confidence"] * 100),
            "quant_technicals": {
                "amihud_illiquidity": amihud_metrics.get("amihud_illiquidity_ratio"),
                "liquidity_tier": amihud_metrics.get("liquidity_tier"),
                "atr_14": atr_metrics.get("atr_14"),
                "trailing_stop_long": atr_metrics.get("trailing_stop_long"),
                "trailing_stop_short": atr_metrics.get("trailing_stop_short"),
                "stop_distance_pct": atr_metrics.get("stop_distance_pct"),
            },
            "strategy_signals": {
                "trend_following": {
                    "signal": trend_signals["signal"],
                    "confidence": round(trend_signals["confidence"] * 100),
                    "metrics": normalize_pandas(trend_signals["metrics"]),
                },
                "mean_reversion": {
                    "signal": mean_reversion_signals["signal"],
                    "confidence": round(mean_reversion_signals["confidence"] * 100),
                    "metrics": normalize_pandas(mean_reversion_signals["metrics"]),
                },
                "momentum": {
                    "signal": momentum_signals["signal"],
                    "confidence": round(momentum_signals["confidence"] * 100),
                    "metrics": normalize_pandas(momentum_signals["metrics"]),
                },
                "volatility": {
                    "signal": volatility_signals["signal"],
                    "confidence": round(volatility_signals["confidence"] * 100),
                    "metrics": normalize_pandas(volatility_signals["metrics"]),
                },
                "statistical_arbitrage": {
                    "signal": stat_arb_signals["signal"],
                    "confidence": round(stat_arb_signals["confidence"] * 100),
                    "metrics": normalize_pandas(stat_arb_signals["metrics"]),
                },
                "liquidity_and_risk": {
                    "liquidity_tier": amihud_metrics.get("liquidity_tier"),
                    "trailing_stop_long": atr_metrics.get("trailing_stop_long"),
                    "trailing_stop_short": atr_metrics.get("trailing_stop_short"),
                }
            },
        }
        progress.update_status("technical_analyst_agent", ticker, "Done")

    # Create the technical analyst message
    message = HumanMessage(
        content=json.dumps(normalize_pandas(technical_analysis)),
        name="technical_analyst_agent",
    )

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(technical_analysis, "Technical Analyst")

    # Add the signal to the analyst_signals list
    state["data"]["analyst_signals"]["technical_analyst_agent"] = technical_analysis

    return {
        "messages": state["messages"] + [message],
        "data": data,
    }


def calculate_trend_signals(prices_df):
    """
    Advanced trend following strategy using multiple timeframes and indicators
    """
    # Calculate EMAs for multiple timeframes
    ema_8 = calculate_ema(prices_df, 8)
    ema_21 = calculate_ema(prices_df, 21)
    ema_55 = calculate_ema(prices_df, 55)

    # Calculate ADX for trend strength
    adx = calculate_adx(prices_df, 14)

    # Determine trend direction and strength
    short_trend = ema_8 > ema_21
    medium_trend = ema_21 > ema_55

    adx_val = safe_float(adx["adx"].iloc[-1] if not adx["adx"].empty else 25.0, 25.0)
    trend_strength = adx_val / 100.0

    if not short_trend.empty and not medium_trend.empty:
        if short_trend.iloc[-1] and medium_trend.iloc[-1]:
            signal = "bullish"
            confidence = trend_strength
        elif not short_trend.iloc[-1] and not medium_trend.iloc[-1]:
            signal = "bearish"
            confidence = trend_strength
        else:
            signal = "neutral"
            confidence = 0.5
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "adx": adx_val,
            "trend_strength": safe_float(trend_strength, 0.5),
        },
    }


def calculate_mean_reversion_signals(prices_df):
    """
    Mean reversion strategy using statistical measures and Bollinger Bands
    """
    # Calculate z-score of price relative to moving average
    ma_50 = prices_df["close"].rolling(window=50, min_periods=5).mean()
    std_50 = prices_df["close"].rolling(window=50, min_periods=5).std().replace(0, 0.01).fillna(0.01)
    z_score_series = (prices_df["close"] - ma_50) / std_50
    z_score = safe_float(z_score_series.iloc[-1] if not z_score_series.empty else 0.0, 0.0)

    # Calculate Bollinger Bands
    bb_upper, bb_lower = calculate_bollinger_bands(prices_df)

    # Calculate RSI with multiple timeframes
    rsi_14 = calculate_rsi(prices_df, 14)
    rsi_28 = calculate_rsi(prices_df, 28)

    # Mean reversion signals
    bb_width = bb_upper.iloc[-1] - bb_lower.iloc[-1] if not bb_upper.empty else 1.0
    if bb_width == 0:
        bb_width = 1.0
    price_vs_bb = safe_float((prices_df["close"].iloc[-1] - bb_lower.iloc[-1]) / bb_width, 0.5)

    rsi_14_val = safe_float(rsi_14.iloc[-1] if not rsi_14.empty else 50.0, 50.0)
    rsi_28_val = safe_float(rsi_28.iloc[-1] if not rsi_28.empty else 50.0, 50.0)

    # Combine signals
    if z_score < -2 and price_vs_bb < 0.2:
        signal = "bullish"
        confidence = min(abs(z_score) / 4, 1.0)
    elif z_score > 2 and price_vs_bb > 0.8:
        signal = "bearish"
        confidence = min(abs(z_score) / 4, 1.0)
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "z_score": z_score,
            "price_vs_bb": price_vs_bb,
            "rsi_14": rsi_14_val,
            "rsi_28": rsi_28_val,
        },
    }


def calculate_momentum_signals(prices_df):
    """
    Multi-factor momentum strategy
    """
    # Price momentum
    returns = prices_df["close"].pct_change().fillna(0)
    mom_1m = returns.rolling(21, min_periods=1).sum().fillna(0)
    mom_3m = returns.rolling(63, min_periods=1).sum().fillna(0)
    mom_6m = returns.rolling(126, min_periods=1).sum().fillna(0)

    # Volume momentum
    volume_ma = prices_df["volume"].rolling(21, min_periods=1).mean().replace(0, 1).fillna(1)
    volume_momentum = (prices_df["volume"] / volume_ma).fillna(1.0)

    # Calculate momentum score
    m1 = safe_float(mom_1m.iloc[-1] if not mom_1m.empty else 0.0, 0.0)
    m3 = safe_float(mom_3m.iloc[-1] if not mom_3m.empty else 0.0, 0.0)
    m6 = safe_float(mom_6m.iloc[-1] if not mom_6m.empty else 0.0, 0.0)
    vm = safe_float(volume_momentum.iloc[-1] if not volume_momentum.empty else 1.0, 1.0)

    momentum_score = 0.4 * m1 + 0.3 * m3 + 0.3 * m6
    volume_confirmation = vm > 1.0

    if momentum_score > 0.05 and volume_confirmation:
        signal = "bullish"
        confidence = min(abs(momentum_score) * 5, 1.0)
    elif momentum_score < -0.05 and volume_confirmation:
        signal = "bearish"
        confidence = min(abs(momentum_score) * 5, 1.0)
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "momentum_1m": m1,
            "momentum_3m": m3,
            "momentum_6m": m6,
            "volume_momentum": vm,
        },
    }


def calculate_volatility_signals(prices_df):
    """
    Volatility-based trading strategy
    """
    # Calculate various volatility metrics
    returns = prices_df["close"].pct_change().fillna(0)

    # Historical volatility
    hist_vol = returns.rolling(21, min_periods=2).std() * math.sqrt(252)
    hist_vol = hist_vol.fillna(0.2)

    # Volatility regime detection
    vol_ma = hist_vol.rolling(63, min_periods=1).mean().replace(0, 0.01).fillna(0.2)
    vol_regime = (hist_vol / vol_ma).fillna(1.0)

    # Volatility mean reversion
    vol_std = hist_vol.rolling(63, min_periods=2).std().replace(0, 0.01).fillna(0.05)
    vol_z_score = ((hist_vol - vol_ma) / vol_std).fillna(0.0)

    # ATR ratio
    atr = calculate_atr(prices_df).fillna(1.0)
    close_price = prices_df["close"].replace(0, 1.0)
    atr_ratio = (atr / close_price).fillna(0.02)

    # Generate signal based on volatility regime
    current_vol_regime = safe_float(vol_regime.iloc[-1] if not vol_regime.empty else 1.0, 1.0)
    vol_z = safe_float(vol_z_score.iloc[-1] if not vol_z_score.empty else 0.0, 0.0)
    h_vol = safe_float(hist_vol.iloc[-1] if not hist_vol.empty else 0.2, 0.2)
    a_ratio = safe_float(atr_ratio.iloc[-1] if not atr_ratio.empty else 0.02, 0.02)

    if current_vol_regime < 0.8 and vol_z < -1:
        signal = "bullish"  # Low vol regime, potential for expansion
        confidence = min(abs(vol_z) / 3, 1.0)
    elif current_vol_regime > 1.2 and vol_z > 1:
        signal = "bearish"  # High vol regime, potential for contraction
        confidence = min(abs(vol_z) / 3, 1.0)
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "historical_volatility": h_vol,
            "volatility_regime": current_vol_regime,
            "volatility_z_score": vol_z,
            "atr_ratio": a_ratio,
        },
    }


def calculate_stat_arb_signals(prices_df):
    """
    Statistical arbitrage signals based on price action analysis
    """
    # Calculate price distribution statistics
    returns = prices_df["close"].pct_change().fillna(0)

    # Skewness and kurtosis
    skew = returns.rolling(63, min_periods=3).skew().fillna(0.0)
    kurt = returns.rolling(63, min_periods=4).kurt().fillna(0.0)

    # Test for mean reversion using Hurst exponent
    hurst = safe_float(calculate_hurst_exponent(prices_df["close"]), 0.5)
    skew_val = safe_float(skew.iloc[-1] if not skew.empty else 0.0, 0.0)
    kurt_val = safe_float(kurt.iloc[-1] if not kurt.empty else 0.0, 0.0)

    # Generate signal based on statistical properties
    if hurst < 0.4 and skew_val > 1:
        signal = "bullish"
        confidence = (0.5 - hurst) * 2
    elif hurst < 0.4 and skew_val < -1:
        signal = "bearish"
        confidence = (0.5 - hurst) * 2
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "hurst_exponent": hurst,
            "skewness": skew_val,
            "kurtosis": kurt_val,
        },
    }


def weighted_signal_combination(signals, weights):
    """
    Combines multiple trading signals using a weighted approach
    """
    signal_values = {"bullish": 1, "neutral": 0, "bearish": -1}

    weighted_sum = 0
    total_confidence = 0

    for strategy, signal in signals.items():
        numeric_signal = signal_values.get(signal.get("signal", "neutral"), 0)
        weight = weights.get(strategy, 0.2)
        confidence = safe_float(signal.get("confidence", 0.5), 0.5)

        weighted_sum += numeric_signal * weight * confidence
        total_confidence += weight * confidence

    if total_confidence > 0:
        final_score = weighted_sum / total_confidence
    else:
        final_score = 0

    if final_score > 0.2:
        signal = "bullish"
    elif final_score < -0.2:
        signal = "bearish"
    else:
        signal = "neutral"

    return {"signal": signal, "confidence": abs(final_score)}


def normalize_pandas(obj):
    """Convert pandas/numpy types to primitive types, strictly replacing NaN/Inf with None."""
    if obj is None:
        return None
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (np.floating, np.integer)):
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    elif isinstance(obj, (np.ndarray, pd.Series)):
        return [normalize_pandas(item) for item in obj.tolist()]
    elif isinstance(obj, pd.DataFrame):
        return [{k: normalize_pandas(v) for k, v in row.items()} for row in obj.to_dict("records")]
    elif isinstance(obj, dict):
        return {k: normalize_pandas(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [normalize_pandas(item) for item in obj]
    return obj


def calculate_rsi(prices_df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = prices_df["close"].diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean().fillna(0)
    avg_loss = loss.rolling(window=period, min_periods=1).mean().replace(0, 1e-6).fillna(1e-6)
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def calculate_bollinger_bands(prices_df: pd.DataFrame, window: int = 20) -> tuple[pd.Series, pd.Series]:
    sma = prices_df["close"].rolling(window, min_periods=1).mean()
    std_dev = prices_df["close"].rolling(window, min_periods=1).std().fillna(0.0)
    upper_band = sma + (std_dev * 2)
    lower_band = sma - (std_dev * 2)
    return upper_band, lower_band


def calculate_ema(df: pd.DataFrame, window: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return df["close"].ewm(span=window, adjust=False).mean().fillna(df["close"])


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Calculate Average Directional Index (ADX)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # Calculate True Range
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=1).mean().replace(0, 1e-6).fillna(1e-6)

    # Directional Movement
    up_move = high - high.shift()
    down_move = low.shift() - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Directional Indicators
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(period, min_periods=1).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(period, min_periods=1).mean() / atr)

    # Directional Index
    di_diff = abs(plus_di - minus_di)
    di_sum = (plus_di + minus_di).replace(0, 1e-6).fillna(1e-6)
    dx = 100 * (di_diff / di_sum)

    # ADX is the smoothed moving average of DX
    adx = dx.rolling(period, min_periods=1).mean().fillna(25.0)

    return pd.DataFrame({
        "adx": adx,
        "plus_di": plus_di.fillna(0.0),
        "minus_di": minus_di.fillna(0.0),
    })


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR)."""
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)

    return true_range.rolling(period, min_periods=1).mean().fillna(1.0)


def calculate_hurst_exponent(price_series: pd.Series, max_lag: int = 20) -> float:
    """Calculate Hurst Exponent to determine long-term memory of time series."""
    if len(price_series) < max_lag:
        return 0.5
    lags = range(2, min(max_lag, len(price_series)))
    tau = [max(1e-8, np.sqrt(np.std(np.subtract(price_series.iloc[lag:].values, price_series.iloc[:-lag].values)))) for lag in lags]

    try:
        reg = np.polyfit(np.log(list(lags)), np.log(tau), 1)
        val = float(reg[0])
        if math.isnan(val) or math.isinf(val):
            return 0.5
        return val
    except Exception:
        return 0.5
