from langchain_core.messages import HumanMessage
import json
import pandas as pd
import numpy as np
from .state import AgentState, show_agent_reasoning
from ..tools.api import prices_to_df

def short_term_technical_analyst_agent(state: AgentState):
    """
    Short-term technical analysis system focused on intraday and near-term signals:
    1. Price Action Analysis
    2. Volume Analysis
    3. Momentum Indicators
    4. Support/Resistance Levels
    5. Volatility Analysis
    """
    try:
        show_reasoning = state["metadata"]["show_reasoning"]
        data = state["data"]
        prices = data["prices"]
        prices_df = prices_to_df(prices)
        current_price = float(prices_df['close'].iloc[-1])

        # Calculate short-term indicators
        rsi = calculate_short_term_rsi(prices_df)
        macd, signal = calculate_short_term_macd(prices_df)
        support, resistance = calculate_short_term_levels(prices_df)
        volume_profile = analyze_volume_profile(prices_df)
        momentum = calculate_short_term_momentum(prices_df)
        
        # Create message content
        message_content = {
            "signal": momentum["signal"],
            "confidence": f"{momentum['confidence']:.0%}",
            "analysis": {
                "momentum_analysis": {
                    "price_momentum": momentum["price_momentum"],
                    "volume_momentum": momentum["volume_momentum"],
                    "rsi": momentum["rsi"],
                    "current_price": momentum["current_price"],
                    "target_price": momentum["target_price"],
                    "support_level": momentum["support_level"],
                    "resistance_level": momentum["resistance_level"],
                    "stop_loss": momentum["stop_loss"],
                    "signal": momentum["signal"],
                    "timeframe": momentum["timeframe"],
                    "confidence": momentum["confidence"],
                    "reasoning": momentum["reasoning"]
                }
            },
            "reasoning": {
                "momentum_analysis": f"Price momentum is {momentum['signal']} with {momentum['confidence']:.1%} confidence, {momentum['acceleration']}",
                "volume_analysis": f"Volume profile shows {volume_profile['pattern']} pattern with {volume_profile['trend']}",
                "support_resistance": f"Trading {'below support' if current_price < support else 'above resistance' if current_price > resistance else 'within range'} (Support: ${support:.2f}, Resistance: ${resistance:.2f})"
            }
        }

        if show_reasoning:
            show_agent_reasoning(message_content, "Short-term Technical Analyst")

        return {
            "messages": [HumanMessage(name="short_term_technical_analyst_agent", content=json.dumps(message_content))],
            "data": data
        }
    except Exception as e:
        print(f"Error in short-term technical analyst: {str(e)}")
        return {
            "messages": [HumanMessage(name="short_term_technical_analyst_agent", content=json.dumps({
                "signal": "neutral",
                "confidence": "0%",
                "analysis": {
                    "momentum_analysis": {
                        "price_momentum": {"signal": "neutral", "value": "0"},
                        "volume_momentum": {"signal": "neutral", "value": "0"},
                        "rsi": 50.0,
                        "current_price": current_price if 'current_price' in locals() else 0.0,
                        "target_price": 0.0,
                        "support_level": 0.0,
                        "resistance_level": 0.0,
                        "stop_loss": 0.0,
                        "signal": "neutral",
                        "timeframe": "Short-term",
                        "confidence": 0.5,
                        "reasoning": ["Error calculating momentum indicators"]
                    }
                },
                "reasoning": {
                    "momentum_analysis": "Error calculating momentum",
                    "volume_analysis": "Error analyzing volume",
                    "support_resistance": "Error calculating levels"
                }
            }))],
            "data": data
        }

def calculate_short_term_rsi(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate RSI with 2 and 5 period windows for shorter-term signals"""
    rsi = pd.DataFrame()
    for period in [2, 5]:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # Handle division by zero
        avg_loss = avg_loss.replace(0, np.finfo(float).eps)  # Replace 0 with small number
        rs = avg_gain / avg_loss
        rsi[f'{period}-period'] = 100 - (100 / (1 + rs))
    return rsi.fillna(50)  # Fill NaN values with neutral RSI

def calculate_short_term_macd(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Calculate MACD with shorter periods for faster signals"""
    ema_fast = df['close'].ewm(span=6, adjust=False).mean()  # 6 period EMA
    ema_slow = df['close'].ewm(span=13, adjust=False).mean()  # 13 period EMA
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=4, adjust=False).mean()  # 4 period signal
    return macd, signal

def calculate_short_term_levels(df: pd.DataFrame) -> tuple[float, float]:
    """Calculate short-term support and resistance levels"""
    window = 10  # Short window for recent levels
    recent_highs = df['high'].rolling(window=window).max()
    recent_lows = df['low'].rolling(window=window).min()
    
    support = recent_lows.iloc[-1]
    resistance = recent_highs.iloc[-1]
    
    return support, resistance

def analyze_volume_profile(df: pd.DataFrame) -> dict:
    """Analyze recent volume profile for accumulation/distribution patterns"""
    window = 5  # Look at last 5 periods
    recent_df = df.tail(window)
    
    # Calculate price-volume relationship
    up_days = recent_df['close'] > recent_df['open']
    down_days = recent_df['close'] < recent_df['open']
    
    up_volume = recent_df.loc[up_days, 'volume'].sum()
    down_volume = recent_df.loc[down_days, 'volume'].sum()
    
    # Determine volume trend
    if up_volume > down_volume * 1.5:
        trend = "Increasing on up moves"
        pattern = "Accumulation"
        signal = "accumulation"
    elif down_volume > up_volume * 1.5:
        trend = "Increasing on down moves"
        pattern = "Distribution"
        signal = "distribution"
    else:
        trend = "Mixed volume pattern"
        pattern = "Neutral"
        signal = "neutral"
    
    return {
        "trend": trend,
        "pattern": pattern,
        "signal": signal
    }

def calculate_short_term_momentum(df: pd.DataFrame) -> dict:
    """Calculate short-term momentum indicators"""
    try:
        # Ensure we have enough data points
        if len(df) < 14:  # Need at least 14 periods for RSI
            raise ValueError("Not enough data points for momentum calculation")

        # Calculate price momentum using ROC (Rate of Change)
        price_roc = ((df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5]) * 100
        
        # Calculate volume momentum using exponential moving average
        volume_ema = df['volume'].ewm(span=5, adjust=False).mean()
        volume_momentum = ((df['volume'].iloc[-1] - volume_ema.iloc[-1]) / volume_ema.iloc[-1]) * 100
        
        # Calculate RSI properly
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        
        # Handle division by zero in RSI calculation
        rs = avg_gain / avg_loss.replace(0, float('inf'))
        rsi = 100 - (100 / (1 + rs))
        current_rsi = float(rsi.iloc[-1])
        
        # Determine price momentum signal with more granular thresholds
        if price_roc > 3:  # Strong upward momentum
            price_signal = "bullish"
            strength = min(abs(price_roc) / 10, 1.0)
        elif price_roc < -3:  # Strong downward momentum
            price_signal = "bearish"
            strength = min(abs(price_roc) / 10, 1.0)
        else:
            price_signal = "neutral"
            strength = 0.5
            
        # Determine volume signal with adjusted thresholds
        if volume_momentum > 10:
            volume_signal = "bullish"
        elif volume_momentum < -10:
            volume_signal = "bearish"
        else:
            volume_signal = "neutral"
        
        # Calculate acceleration
        price_roc_prev = ((df['close'].iloc[-2] - df['close'].iloc[-6]) / df['close'].iloc[-6]) * 100
        acceleration = "accelerating" if abs(price_roc) > abs(price_roc_prev) else "decelerating"
        
        # Calculate price levels with more sophisticated logic
        current_price = float(df['close'].iloc[-1])
        
        # Calculate support and resistance using recent price action
        recent_window = 20
        support_level = float(df['low'].rolling(window=recent_window).min().iloc[-1])
        resistance_level = float(df['high'].rolling(window=recent_window).max().iloc[-1])
        
        # Adjust target price based on momentum and volatility
        atr = calculate_atr(df)
        if price_signal == "bullish":
            target_price = current_price + (1.5 * atr)  # 1.5x ATR for bullish target
        elif price_signal == "bearish":
            target_price = current_price - (1.5 * atr)  # 1.5x ATR for bearish target
        else:
            target_price = current_price  # Neutral case
            
        # Set stop loss based on ATR and support
        stop_loss = max(support_level - atr, current_price * 0.95)  # Greater of support - ATR or 5% below current
        
        return {
            "signal": price_signal,
            "timeframe": "Short-term",
            "confidence": strength,
            "acceleration": acceleration,
            "price_momentum": {
                "signal": price_signal,
                "value": str(round(price_roc, 2))
            },
            "volume_momentum": {
                "signal": volume_signal,
                "value": str(round(volume_momentum, 2))
            },
            "rsi": current_rsi,
            "current_price": current_price,
            "target_price": float(target_price),
            "support_level": support_level,
            "resistance_level": resistance_level,
            "stop_loss": float(stop_loss),
            "reasoning": [
                f"Price momentum is {price_signal} ({round(price_roc, 2)}%) and {acceleration}",
                f"Volume momentum shows {volume_signal} trend ({round(volume_momentum, 2)}%)",
                f"RSI at {round(current_rsi, 2)} indicates {'oversold' if current_rsi < 30 else 'overbought' if current_rsi > 70 else 'neutral'} conditions"
            ]
        }
    except Exception as e:
        print(f"Error calculating momentum: {str(e)}")
        # Return default values for error case
        return {
            "signal": "neutral",
            "timeframe": "Short-term",
            "confidence": 0.5,
            "acceleration": "stable",
            "price_momentum": {"signal": "neutral", "value": "0"},
            "volume_momentum": {"signal": "neutral", "value": "0"},
            "rsi": 50.0,
            "current_price": float(df['close'].iloc[-1]) if not df.empty else 0.0,
            "target_price": 0.0,
            "support_level": 0.0,
            "resistance_level": 0.0,
            "stop_loss": 0.0,
            "reasoning": ["Error calculating momentum indicators"]
        }

def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average True Range"""
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    
    return true_range.rolling(period).mean().iloc[-1] 