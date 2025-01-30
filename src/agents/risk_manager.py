import math
import numpy as np

from langchain_core.messages import HumanMessage

from .state import AgentState, show_agent_reasoning
from ..tools.api import prices_to_df

import json
import ast

##### Risk Management Agent #####

def get_position_value(portfolio, prices_df):
    """Calculate current position value"""
    try:
        current_price = prices_df['close'].iloc[-1]
        return portfolio.get('stock', 0) * current_price
    except Exception as e:
        print(f"Error calculating position value: {e}")
        return 0.0

def get_position_size_percentage(portfolio, prices_df):
    """Calculate position size as percentage of portfolio"""
    try:
        position_value = get_position_value(portfolio, prices_df)
        total_value = position_value + portfolio.get('cash', 0)
        return position_value / total_value if total_value > 0 else 0
    except Exception as e:
        print(f"Error calculating position size: {e}")
        return 0.0

def calculate_portfolio_beta(prices_df, market_data=None):
    """Calculate portfolio beta using price data"""
    try:
        # For simplicity, using historical volatility as proxy
        returns = prices_df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)
        return volatility / 0.16  # Assuming market volatility of 16%
    except Exception as e:
        print(f"Error calculating beta: {e}")
        return 1.0  # Default to market beta

def calculate_max_drawdown(prices_df, window=252):
    """Calculate maximum drawdown over specified window"""
    try:
        rolling_max = prices_df['close'].rolling(window=window, min_periods=1).max()
        drawdown = prices_df['close'] / rolling_max - 1
        return drawdown.min()
    except Exception as e:
        print(f"Error calculating max drawdown: {e}")
        return 0.0

def calculate_volatility(df, window):
    """Calculate rolling volatility"""
    returns = df['close'].pct_change()
    volatility = returns.rolling(window=window).std() * np.sqrt(252)  # Annualize
    return volatility.iloc[-1] if not volatility.empty else 0.0

def calculate_var(prices_df, confidence=0.95):
    """Calculate Value at Risk"""
    try:
        returns = prices_df['close'].pct_change().dropna()
        return np.percentile(returns, (1 - confidence) * 100) * prices_df['close'].iloc[-1]
    except Exception as e:
        print(f"Error calculating VaR: {e}")
        return 0.0

def calculate_cvar(prices_df, confidence=0.95):
    """Calculate Conditional Value at Risk (Expected Shortfall)"""
    try:
        returns = prices_df['close'].pct_change().dropna()
        var = np.percentile(returns, (1 - confidence) * 100)
        cvar = returns[returns <= var].mean() * prices_df['close'].iloc[-1]
        return cvar if not np.isnan(cvar) else 0.0
    except Exception as e:
        print(f"Error calculating CVaR: {e}")
        return 0.0

def get_portfolio_risk_assessment(portfolio, prices_df):
    """Provide detailed portfolio risk assessment"""
    position_size = get_position_size_percentage(portfolio, prices_df)
    beta = calculate_portfolio_beta(prices_df)
    
    if position_size > 0.25 and beta > 1.5:
        return "High risk - Large position size with high beta"
    elif position_size > 0.25:
        return "Moderate risk - Large position size but moderate beta"
    elif beta > 1.5:
        return "Moderate risk - Small position size but high beta"
    return "Low risk - Conservative position size and beta"

def get_market_risk_assessment(prices_df):
    """Provide detailed market risk assessment"""
    vol_20 = calculate_volatility(prices_df, 20)
    vol_60 = calculate_volatility(prices_df, 60)
    
    if vol_20 > vol_60 * 1.5:
        return "High risk - Rising volatility trend"
    elif vol_20 < vol_60 * 0.5:
        return "Low risk - Declining volatility trend"
    return "Moderate risk - Stable volatility environment"

def get_signal_risk_assessment(agent_signals):
    """Assess risk based on signal agreement/disagreement"""
    signals = [s.get('signal', 'neutral') for s in agent_signals.values()]
    unique_signals = set(signals)
    
    if len(unique_signals) == 1:
        return "Low risk - Strong signal agreement"
    elif len(unique_signals) == 2:
        return "Moderate risk - Some signal divergence"
    return "High risk - Significant signal disagreement"

def get_concentration_risk_assessment(portfolio, prices_df):
    """Assess portfolio concentration risk"""
    position_size = get_position_size_percentage(portfolio, prices_df)
    if position_size > 0.25:
        return "High concentration risk - Consider reducing position"
    elif position_size > 0.15:
        return "Moderate concentration risk - Monitor closely"
    return "Low concentration risk - Well diversified"

def get_market_conditions_assessment(prices_df):
    """Assess overall market conditions"""
    vol_20d = calculate_volatility(prices_df, 20)
    vol_60d = calculate_volatility(prices_df, 60)
    beta = calculate_portfolio_beta(prices_df)
    
    if vol_20d > vol_60d * 1.5 or beta > 2:
        return "High risk market conditions - Exercise caution"
    elif vol_20d > vol_60d * 1.2 or beta > 1.5:
        return "Moderate risk market conditions - Normal vigilance"
    return "Low risk market conditions - Favorable environment"

def get_signal_divergence_assessment(agent_signals):
    """Assess signal divergence risk"""
    signals = [s.get('signal', 'neutral') for s in agent_signals.values()]
    unique_signals = set(signals)
    
    if len(unique_signals) >= 3:
        return "Strong signal divergence - High uncertainty"
    elif len(unique_signals) == 2:
        return "Weak signal convergence - Low confidence"
    return "Strong signal convergence - High confidence"

def get_tail_risk_assessment(prices_df):
    """Assess tail risk exposure"""
    returns = prices_df['close'].pct_change().dropna()
    skew = returns.skew()
    kurt = returns.kurtosis()
    
    if abs(skew) > 1 and kurt > 5:
        return "High tail risk - Fat tails present"
    elif abs(skew) > 0.5 or kurt > 3:
        return "Moderate tail risk - Some skewness"
    return "Low tail risk - Normal distribution"

def get_position_sizing_recommendation(portfolio, prices_df):
    """Get position sizing recommendation"""
    position_size = get_position_size_percentage(portfolio, prices_df)
    beta = calculate_portfolio_beta(prices_df)
    
    if beta > 2:
        return f"Reduce position size to maximum {position_size * 0.5:.1%}"
    elif beta > 1.5:
        return f"Reduce position size to maximum {position_size * 0.7:.1%}"
    return f"Maintain position size at maximum {position_size:.1%}"

def get_stop_loss_recommendation(prices_df):
    """Calculate stop loss recommendations"""
    current_price = prices_df['close'].iloc[-1]
    atr = calculate_volatility(prices_df, 14)  # Using volatility as ATR proxy
    
    return {
        "tight": f"${round(current_price * 0.95, 2)}",
        "wide": f"${round(current_price * 0.90, 2)}",
        "trailing": f"{atr:.1%}"
    }

def get_risk_mitigation_recommendation(portfolio, prices_df, agent_signals):
    """Get risk mitigation recommendations"""
    position_size = get_position_size_percentage(portfolio, prices_df)
    vol_20d = calculate_volatility(prices_df, 20)
    
    if position_size > 0.25 or vol_20d > 0.4:
        return "Implement tighter stops and reduce new position sizing"
    elif position_size > 0.15 or vol_20d > 0.3:
        return "Monitor closely and maintain current risk controls"
    return "Standard risk management protocols sufficient"

def get_hedging_recommendation(portfolio, prices_df):
    """Get hedging strategy recommendations"""
    beta = calculate_portfolio_beta(prices_df)
    vol_20d = calculate_volatility(prices_df, 20)
    
    if beta > 2 or vol_20d > 0.4:
        return "Consider put options or inverse ETF hedge"
    elif beta > 1.5 or vol_20d > 0.3:
        return "Consider collar strategy for protection"
    return "No additional hedging needed at this time"

def calculate_market_risk_score(prices_df):
    """Calculate market risk score (0-10)"""
    try:
        vol_20d = calculate_volatility(prices_df, 20)
        vol_60d = calculate_volatility(prices_df, 60)
        beta = calculate_portfolio_beta(prices_df)
        max_dd = calculate_max_drawdown(prices_df)
        
        score = 0
        score += min(4, vol_20d * 10)  # Up to 4 points for current volatility
        score += min(3, max(0, (vol_20d/vol_60d - 1) * 10))  # Up to 3 points for volatility trend
        score += min(3, max(0, (beta - 1) * 2))  # Up to 3 points for high beta
        
        return min(10, score)
    except Exception as e:
        print(f"Error calculating market risk score: {e}")
        return 5.0  # Default to moderate risk

def calculate_position_risk_score(portfolio, prices_df):
    """Calculate position risk score (0-10)"""
    try:
        position_size = get_position_size_percentage(portfolio, prices_df)
        max_dd = calculate_max_drawdown(prices_df)
        
        score = 0
        score += min(5, position_size * 20)  # Up to 5 points for position size
        score += min(5, abs(max_dd) * 10)  # Up to 5 points for drawdown
        
        return min(10, score)
    except Exception as e:
        print(f"Error calculating position risk score: {e}")
        return 5.0  # Default to moderate risk

def calculate_signal_risk_score(agent_signals):
    """Calculate signal risk score (0-10)"""
    signals = [s.get('signal', 'neutral') for s in agent_signals.values()]
    confidences = [float(s.get('confidence', '0').replace('%', '')) / 100 for s in agent_signals.values()]
    
    score = 0
    score += (len(set(signals)) - 1) * 3  # Up to 6 points for divergence
    score += (1 - min(confidences)) * 4  # Up to 4 points for low confidence
    
    return min(10, score)

def calculate_max_position_size(portfolio, prices_df, risk_score):
    """Calculate maximum position size based on risk score"""
    total_value = get_position_value(portfolio, prices_df) + portfolio['cash']
    base_size = total_value * 0.25  # Base size of 25%
    
    if risk_score >= 8:
        return base_size * 0.4  # 10% max
    elif risk_score >= 6:
        return base_size * 0.6  # 15% max
    elif risk_score >= 4:
        return base_size * 0.8  # 20% max
    return base_size  # 25% max

def get_risk_level(risk_score):
    """Convert risk score to risk level"""
    if risk_score >= 8:
        return "High"
    elif risk_score >= 5:
        return "Moderate"
    return "Low"

def get_trading_action(risk_score, portfolio, prices_df):
    """Determine trading action based on risk score"""
    position_size = get_position_size_percentage(portfolio, prices_df)
    max_size = calculate_max_position_size(portfolio, prices_df, risk_score)
    
    if position_size > max_size * 1.1:  # 10% buffer
        return "reduce"
    elif risk_score >= 8:
        return "hold"
    return "normal"

def get_risk_confidence(risk_score):
    """Calculate confidence in risk assessment"""
    # Higher confidence when risk score is at extremes
    if risk_score <= 2 or risk_score >= 8:
        return 0.9
    elif risk_score <= 4 or risk_score >= 6:
        return 0.7
    return 0.5

def risk_management_agent(state: AgentState):
    """Analyzes risk metrics and provides risk management recommendations"""
    try:
        show_reasoning = state["metadata"]["show_reasoning"]
        data = state["data"]
        portfolio = data["portfolio"]
        prices = data["prices"]
        prices_df = prices_to_df(prices)

        # Get agent signals
        agent_signals = {}
        for msg in state["messages"]:
            if msg.name != "risk_management_agent":
                try:
                    signal_data = json.loads(msg.content)
                    agent_signals[msg.name] = {
                        "signal": signal_data.get("signal", "neutral"),
                        "confidence": signal_data.get("confidence", "0%").replace("%", "")
                    }
                except:
                    continue

        # Calculate risk metrics
        position_value = float(get_position_value(portfolio, prices_df))
        position_size = float(get_position_size_percentage(portfolio, prices_df))
        beta = float(calculate_portfolio_beta(prices_df))
        max_dd = float(calculate_max_drawdown(prices_df))
        vol_20d = float(calculate_volatility(prices_df, 20))
        vol_60d = float(calculate_volatility(prices_df, 60))
        var_95 = float(calculate_var(prices_df, 0.95))
        cvar_95 = float(calculate_cvar(prices_df, 0.95))

        # Create expert system message
        expert_message = f"""You are Nassim Nicholas Taleb, renowned risk analyst and author of "The Black Swan", known for your expertise in risk management and antifragility.

        Based on the comprehensive risk analysis, here are the key findings:

        PORTFOLIO RISK METRICS:
        - Current Position Value: ${position_value:.2f}
        - Position Size: {position_size:.1%}
        - Portfolio Beta: {beta:.2f}
        - Max Drawdown: {max_dd:.1%}
        Assessment: {get_portfolio_risk_assessment(portfolio, prices_df)}

        MARKET RISK METRICS:
        - Volatility (20-day): {vol_20d:.1%}
        - Volatility (60-day): {vol_60d:.1%}
        - VaR (95%): ${var_95:.2f}
        - CVaR (95%): ${cvar_95:.2f}
        Assessment: {get_market_risk_assessment(prices_df)}

        SIGNAL ANALYSIS:
        - Technical Signal: {agent_signals.get('technical_analyst_agent', {}).get('signal', 'neutral')}
        - Fundamental Signal: {agent_signals.get('fundamentals_agent', {}).get('signal', 'neutral')}
        - Sentiment Signal: {agent_signals.get('sentiment_agent', {}).get('signal', 'neutral')}
        Assessment: {get_signal_risk_assessment(agent_signals)}

        RISK FACTORS:
        1. Position Concentration
           {get_concentration_risk_assessment(portfolio, prices_df)}
        
        2. Market Conditions
           {get_market_conditions_assessment(prices_df)}
        
        3. Signal Divergence
           {get_signal_divergence_assessment(agent_signals)}
        
        4. Tail Risk
           {get_tail_risk_assessment(prices_df)}

        RISK MANAGEMENT RECOMMENDATIONS:
        1. Position Sizing
           {get_position_sizing_recommendation(portfolio, prices_df)}
        
        2. Stop Loss Levels
           {get_stop_loss_recommendation(prices_df)}
        
        3. Risk Mitigation
           {get_risk_mitigation_recommendation(portfolio, prices_df, agent_signals)}
        
        4. Hedging Strategy
           {get_hedging_recommendation(portfolio, prices_df)}

        Please consider these risk factors in the context of:
        1. Portfolio concentration
        2. Market liquidity
        3. Correlation risk
        4. Tail event exposure"""

        # Calculate risk metrics and generate recommendations
        market_risk_score = calculate_market_risk_score(prices_df)
        position_risk_score = calculate_position_risk_score(portfolio, prices_df)
        signal_risk_score = calculate_signal_risk_score(agent_signals)
        
        total_risk_score = (
            market_risk_score * 0.4 +  # Market risk weight
            position_risk_score * 0.4 +  # Position risk weight
            signal_risk_score * 0.2  # Signal risk weight
        )

        # Determine risk-adjusted position size
        max_position_size = calculate_max_position_size(
            portfolio,
            prices_df,
            total_risk_score
        )

        # Generate the risk management message with enhanced expertise
        message = HumanMessage(
            content=json.dumps({
                "risk_level": get_risk_level(total_risk_score),
                "max_position_size": f"${max_position_size:.2f}",
                "trading_action": get_trading_action(total_risk_score, portfolio, prices_df),
                "stop_loss": get_stop_loss_recommendation(prices_df),
                "confidence": f"{get_risk_confidence(total_risk_score) * 100:.0f}%",
                "reasoning": {
                    "expert_analysis": expert_message,
                    "risk_metrics": {
                        "market_risk": f"{market_risk_score:.2f}",
                        "position_risk": f"{position_risk_score:.2f}",
                        "signal_risk": f"{signal_risk_score:.2f}",
                        "total_risk": f"{total_risk_score:.2f}"
                    }
                }
            }),
            name="risk_management_agent",
        )

        if show_reasoning:
            show_agent_reasoning({
                "risk_level": get_risk_level(total_risk_score),
                "max_position_size": f"${max_position_size:.2f}",
                "trading_action": get_trading_action(total_risk_score, portfolio, prices_df),
                "stop_loss": get_stop_loss_recommendation(prices_df),
                "confidence": f"{get_risk_confidence(total_risk_score) * 100:.0f}%",
                "reasoning": {
                    "expert_analysis": expert_message,
                    "risk_metrics": {
                        "market_risk": f"{market_risk_score:.2f}",
                        "position_risk": f"{position_risk_score:.2f}",
                        "signal_risk": f"{signal_risk_score:.2f}",
                        "total_risk": f"{total_risk_score:.2f}"
                    }
                }
            }, "Risk Management Agent")

        return {
            "messages": [message],
            "data": data,
        }
    except Exception as e:
        print(f"Error in risk_management_agent: {e}")
        return {
            "messages": [],
            "data": data,
        }
