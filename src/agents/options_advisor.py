from langchain_core.messages import HumanMessage
from .state import AgentState, show_agent_reasoning
import json
import math

def calculate_implied_volatility(state: AgentState):
    """Calculate historical volatility as a proxy for implied volatility"""
    prices = state["data"].get("historical_prices", [])
    if not prices or len(prices) < 30:  # Need at least 30 days of data
        return None
    
    # Calculate daily returns
    returns = [(prices[i] - prices[i-1])/prices[i-1] for i in range(1, len(prices))]
    
    # Calculate standard deviation of returns
    mean_return = sum(returns) / len(returns)
    squared_diff = [(r - mean_return)**2 for r in returns]
    variance = sum(squared_diff) / (len(squared_diff) - 1)
    daily_volatility = math.sqrt(variance)
    
    # Annualize volatility (multiply by sqrt of trading days in a year)
    annual_volatility = daily_volatility * math.sqrt(252)
    
    return annual_volatility

def get_strike_recommendations(current_price, target_price, option_type):
    """Generate strike price recommendations"""
    return {
        "conservative": round(current_price * 0.95, 2),
        "moderate": round(current_price, 2),
        "aggressive": round(current_price * 1.05, 2)
    }

def get_expiration_recommendation(strategy_type):
    """Generate expiration recommendations"""
    return {
        "short_term": "30-45 DTE",
        "medium_term": "60-90 DTE",
        "long_term": "120-180 DTE"
    }

def get_premium_recommendations(current_price, implied_vol, strategy_type):
    """Generate premium recommendations"""
    base_premium = current_price * 0.05
    return {
        "target_premium": round(base_premium, 2),
        "max_premium": round(base_premium * 1.4, 2)
    }

def options_advisor_agent(state: AgentState):
    """Analyzes market conditions and makes options trading recommendations"""
    try:
        show_reasoning = state["metadata"]["show_reasoning"]
        data = state["data"]
        current_price = data["price"]
        
        # Get signals from other agents
        technical_message = next(msg for msg in state["messages"] if msg.name == "technical_analyst_agent")
        valuation_message = next(msg for msg in state["messages"] if msg.name == "valuation_agent")
        sentiment_message = next(msg for msg in state["messages"] if msg.name == "sentiment_agent")
        
        # Parse messages with error handling
        try:
            technical_data = json.loads(technical_message.content)
        except:
            technical_data = {"signal": "neutral", "confidence": "0%"}
            
        try:
            valuation_data = json.loads(valuation_message.content)
            price_targets = valuation_data.get("reasoning", {}).get("price_targets", {})
            
            # Helper function to safely parse price string
            def safe_price_parse(price_str, default):
                if not price_str or price_str == "Unknown":
                    return default
                try:
                    return float(str(price_str).replace("$", "").strip())
                except (ValueError, AttributeError):
                    return default
            
            # Get price targets with fallbacks
            fair_value = safe_price_parse(price_targets.get("fair_value"), current_price)
            buy_target = safe_price_parse(price_targets.get("buy_target"), current_price * 0.9)
            sell_target = safe_price_parse(price_targets.get("sell_target"), current_price * 1.1)
            
            # If we still don't have valid targets, try DCF and owner earnings analysis
            if fair_value == current_price:
                dcf = valuation_data.get("reasoning", {}).get("dcf_analysis", {})
                if dcf and dcf.get("price_target"):
                    fair_value = safe_price_parse(dcf["price_target"], fair_value)
                    if fair_value != current_price:
                        buy_target = fair_value * 0.95
                        sell_target = fair_value * 1.10
                else:
                    oe = valuation_data.get("reasoning", {}).get("owner_earnings_analysis", {})
                    if oe and oe.get("price_target"):
                        fair_value = safe_price_parse(oe["price_target"], fair_value)
                        if fair_value != current_price:
                            buy_target = fair_value * 0.95
                            sell_target = fair_value * 1.10
        except:
            fair_value = current_price
            buy_target = current_price * 0.9
            sell_target = current_price * 1.1
            
        try:
            sentiment_data = json.loads(sentiment_message.content)
        except:
            sentiment_data = {"signal": "neutral", "confidence": "0%"}
        
        # Calculate implied volatility
        implied_vol = calculate_implied_volatility(state)

        # Format implied volatility string
        implied_vol_str = f"{implied_vol:.1%}" if implied_vol is not None else "Unknown"

        # Create the system message for options analysis
        system_message = {
            "role": "system",
            "content": """You are Mark Spitznagel, renowned options trader and founder of Universa Investments, known for your expertise in tail-risk hedging and options strategies.

                Your task is to analyze market conditions and recommend optimal options strategies that balance risk and reward.

                KEY PRINCIPLES:
                1. Asymmetric Risk-Reward
                   - Focus on trades with limited downside and large upside potential
                   - Consider cost of carry and time decay
                   - Look for mispriced volatility opportunities

                2. Volatility Analysis
                   - Assess implied vs historical volatility
                   - Consider volatility skew and term structure
                   - Factor in market regime (contango/backwardation)

                3. Strategic Positioning
                   - Match strategy to market outlook
                   - Consider position sizing and portfolio impact
                   - Plan for various market scenarios

                4. Risk Management
                   - Define maximum acceptable loss
                   - Consider correlation with existing positions
                   - Plan exit strategies before entry

                STRATEGY SELECTION FRAMEWORK:
                1. Directional Strategies (Bullish)
                   - Long Calls
                   - Bull Call Spreads
                   - Risk Reversal
                   - LEAPS for longer-term exposure

                2. Directional Strategies (Bearish)
                   - Long Puts
                   - Bear Put Spreads
                   - Put Back Spreads
                   - Protective Puts

                3. Neutral Strategies
                   - Iron Condors
                   - Calendar Spreads
                   - Butterfly Spreads
                   - Straddles/Strangles

                4. Income Strategies
                   - Covered Calls
                   - Cash-Secured Puts
                   - Credit Spreads
                   - Ratio Spreads

                IMPLEMENTATION CONSIDERATIONS:
                1. Strike Selection
                   - Delta targets for different strategies
                   - Distance from current price
                   - Support/resistance levels

                2. Expiration Selection
                   - Time decay curve optimization
                   - Event timing
                   - Volatility term structure

                3. Position Sizing
                   - Account for maximum loss
                   - Portfolio heat
                   - Margin requirements

                4. Entry/Exit Timing
                   - Volatility conditions
                   - Technical levels
                   - Greek exposures

                OUTPUT REQUIREMENTS:
                - Detailed strategy recommendations
                - Implementation specifics (strikes, expirations)
                - Risk/reward metrics
                - Maximum loss/profit calculations
                - Entry/exit criteria
                - Adjustment triggers"""
        }

        # Create the user message
        user_message = {
            "role": "user",
            "content": f"""Based on the current market conditions and analysis, recommend optimal options strategies.

                Market Context:
                Current Price: ${current_price:.2f}
                Fair Value: ${fair_value:.2f}
                Buy Target: ${buy_target:.2f}
                Sell Target: ${sell_target:.2f}
                Implied Volatility: {implied_vol_str}

                Technical Signal: {technical_data["signal"]}
                Sentiment Signal: {sentiment_data["signal"]}
                
                Please provide detailed options strategy recommendations including:
                1. Strategy selection and rationale
                2. Specific implementation details
                3. Risk/reward metrics
                4. Entry/exit criteria
                5. Position sizing considerations
                6. Adjustment triggers"""
        }
        
        reasoning = {}
        options_recommendations = []
        
        # Bullish Scenarios
        if current_price < buy_target and technical_data["signal"] == "bullish":
            if implied_vol and implied_vol > 0.3:  # High volatility
                strikes = {
                    "conservative": round(current_price * 0.95, 2),
                    "moderate": round(current_price, 2),
                    "aggressive": round(current_price * 1.05, 2)
                }
                expirations = {
                    "short_term": "30-45 DTE",
                    "medium_term": "60-90 DTE",
                    "long_term": "120-180 DTE"
                }
                premiums = {
                    "target_premium": round(current_price * 0.05, 2),
                    "max_premium": round(current_price * 0.07, 2)
                }
                
                options_recommendations.append({
                    "strategy": "bull call spread",
                    "rationale": "Bullish outlook with high volatility - spread reduces cost and limits risk",
                    "implementation": {
                        "buy_leg": {
                            "type": "call",
                            "strikes": strikes,
                            "recommended_strike": strikes["moderate"],
                            "expirations": expirations,
                            "recommended_expiration": expirations["medium_term"]
                        },
                        "sell_leg": {
                            "type": "call",
                            "strikes": {
                                "conservative": round(sell_target * 0.95, 2),
                                "moderate": round(sell_target, 2),
                                "aggressive": round(sell_target * 1.05, 2)
                            },
                            "recommended_strike": round(sell_target, 2),
                            "expirations": expirations,
                            "recommended_expiration": expirations["medium_term"]
                        },
                        "premium": premiums,
                        "max_profit": round(sell_target - current_price - premiums["target_premium"], 2),
                        "max_loss": round(premiums["target_premium"], 2)
                    }
                })
            else:
                strikes = {
                    "conservative": round(current_price * 0.95, 2),
                    "moderate": round(current_price, 2),
                    "aggressive": round(current_price * 1.05, 2)
                }
                expirations = {
                    "short_term": "30-45 DTE",
                    "medium_term": "60-90 DTE",
                    "long_term": "120-180 DTE"
                }
                premiums = {
                    "target_premium": round(current_price * 0.05, 2),
                    "max_premium": round(current_price * 0.07, 2)
                }
                
                options_recommendations.append({
                    "strategy": "long call",
                    "rationale": "Strong bullish outlook with moderate volatility",
                    "implementation": {
                        "strikes": strikes,
                        "recommended_strike": strikes["moderate"],
                        "expirations": expirations,
                        "recommended_expiration": expirations["medium_term"],
                        "premium": premiums,
                        "max_loss": round(premiums["target_premium"], 2),
                        "break_even": round(strikes["moderate"] + premiums["target_premium"], 2)
                    }
                })
        
        # Bearish Scenarios
        elif current_price > sell_target and technical_data["signal"] == "bearish":
            if implied_vol and implied_vol > 0.3:  # High volatility
                strikes = get_strike_recommendations(current_price, buy_target, "put")
                expirations = get_expiration_recommendation("directional")
                premiums = get_premium_recommendations(current_price, implied_vol, "spread")
                
                options_recommendations.append({
                    "strategy": "bear put spread",
                    "rationale": "Bearish outlook with high volatility - spread reduces cost and limits risk",
                    "implementation": {
                        "buy_leg": {
                            "type": "put",
                            "strikes": strikes,
                            "recommended_strike": strikes["moderate"],
                            "expirations": expirations,
                            "recommended_expiration": expirations["medium_term"]
                        },
                        "sell_leg": {
                            "type": "put",
                            "strikes": get_strike_recommendations(current_price, buy_target * 0.9, "put"),
                            "recommended_strike": round(buy_target, 2),
                            "expirations": expirations,
                            "recommended_expiration": expirations["medium_term"]
                        },
                        "premium": premiums,
                        "max_profit": round(current_price - buy_target - premiums["target_premium"], 2),
                        "max_loss": round(premiums["target_premium"], 2)
                    }
                })
            else:
                strikes = get_strike_recommendations(current_price, buy_target, "put")
                expirations = get_expiration_recommendation("directional")
                premiums = get_premium_recommendations(current_price, implied_vol, "put")
                
                options_recommendations.append({
                    "strategy": "long put",
                    "rationale": "Strong bearish outlook with moderate volatility",
                    "implementation": {
                        "strikes": strikes,
                        "recommended_strike": strikes["moderate"],
                        "expirations": expirations,
                        "recommended_expiration": expirations["medium_term"],
                        "premium": premiums,
                        "max_loss": round(premiums["target_premium"], 2),
                        "break_even": round(strikes["moderate"] - premiums["target_premium"], 2)
                    }
                })
        
        # Neutral Scenarios
        else:
            if implied_vol and implied_vol > 0.3:  # High volatility
                call_strikes = get_strike_recommendations(current_price, sell_target, "call")
                put_strikes = get_strike_recommendations(current_price, buy_target, "put")
                expirations = get_expiration_recommendation("income")
                premiums = get_premium_recommendations(current_price, implied_vol, "iron_condor")
                
                options_recommendations.append({
                    "strategy": "iron condor",
                    "rationale": "Neutral outlook with high volatility - profit from time decay",
                    "implementation": {
                        "call_side": {
                            "sell_strike": round(sell_target * 0.95, 2),
                            "buy_strike": round(sell_target * 1.05, 2)
                        },
                        "put_side": {
                            "sell_strike": round(buy_target * 1.05, 2),
                            "buy_strike": round(buy_target * 0.95, 2)
                        },
                        "expirations": expirations,
                        "recommended_expiration": expirations["short_term"],
                        "premium": premiums,
                        "max_profit": round(premiums["target_premium"], 2),
                        "max_loss": round((sell_target * 1.05 - sell_target * 0.95) - premiums["target_premium"], 2)
                    }
                })
            elif technical_data["signal"] == "neutral":
                strikes = get_strike_recommendations(current_price, sell_target, "call")
                expirations = get_expiration_recommendation("income")
                premiums = get_premium_recommendations(current_price, implied_vol, "call")
                
                options_recommendations.append({
                    "strategy": "covered call",
                    "rationale": "Neutral to slightly bullish outlook - generate income",
                    "implementation": {
                        "strikes": strikes,
                        "recommended_strike": strikes["conservative"],
                        "expirations": expirations,
                        "recommended_expiration": expirations["short_term"],
                        "premium": premiums,
                        "max_profit": round(strikes["conservative"] - current_price + premiums["target_premium"], 2),
                        "max_loss": round(current_price - premiums["target_premium"], 2)
                    }
                })
            else:
                # Add a cash-secured put recommendation for neutral-bearish conditions
                strikes = get_strike_recommendations(current_price, buy_target, "put")
                expirations = {
                    "conservative": "30-45 DTE",  # Shorter term for more premium decay
                    "moderate": "45-60 DTE",      # Balanced time decay and premium
                    "aggressive": "60-90 DTE"     # Longer term for more premium
                }
                premiums = get_premium_recommendations(current_price, implied_vol, "put")
                
                recommended_strike = strikes["conservative"]
                recommended_expiration = expirations["conservative"]
                target_premium = premiums["target_premium"]
                
                # For cash-secured puts:
                # Max profit is limited to the premium received
                # Max loss is strike price minus premium (if stock goes to zero)
                max_profit = target_premium
                max_loss = round(recommended_strike - target_premium, 2)
                
                options_recommendations.append({
                    "strategy": "cash-secured put",
                    "rationale": "Neutral to slightly bearish outlook - generate income while waiting for better entry",
                    "risk_profile": "Moderate - Defined risk with premium cost",
                    "implementation": {
                        "type": "put",
                        "recommended_expiration": recommended_expiration,
                        "recommended_strike": recommended_strike,
                        "expirations": expirations,
                        "strikes": strikes,
                        "premium": premiums,
                        "max_profit": max_profit,
                        "max_loss": max_loss
                    }
                })
        
        # Add volatility information to reasoning
        reasoning["volatility_analysis"] = {
            "implied_volatility": f"{implied_vol:.1%}" if implied_vol else "Unknown",
            "volatility_level": "High" if implied_vol and implied_vol > 0.3 else "Moderate" if implied_vol else "Unknown"
        }
        
        # Add market sentiment to reasoning
        reasoning["market_context"] = {
            "technical_signal": technical_data["signal"],
            "sentiment_signal": sentiment_data["signal"],
            "price_level": "Below fair value" if current_price < fair_value else "Above fair value",
            "price_targets": {
                "current_price": f"${current_price:.2f}",
                "fair_value": f"${fair_value:.2f}",
                "buy_target": f"${buy_target:.2f}",
                "sell_target": f"${sell_target:.2f}"
            }
        }
        
        # Create the output message with concise recommendations
        message_content = {
            "recommendations": options_recommendations,
            "reasoning": {
                "volatility_analysis": {
                    "implied_volatility": f"{implied_vol:.1%}" if implied_vol else "Unknown",
                    "volatility_level": "High" if implied_vol and implied_vol > 0.3 else "Moderate" if implied_vol else "Unknown"
                },
                "market_context": {
                    "technical_signal": technical_data["signal"],
                    "sentiment_signal": sentiment_data["signal"],
                    "price_level": "Below fair value" if current_price < fair_value else "Above fair value",
                    "price_targets": {
                        "current_price": f"${current_price:.2f}",
                        "fair_value": f"${fair_value:.2f}",
                        "buy_target": f"${buy_target:.2f}",
                        "sell_target": f"${sell_target:.2f}"
                    }
                }
            }
        }
        
    except Exception as e:
        print(f"Error in options advisor: {str(e)}")
        message_content = {
            "recommendations": [],
            "reasoning": {
                "volatility_analysis": {
                    "implied_volatility": "Unknown",
                    "volatility_level": "Unknown"
                },
                "market_context": {
                    "technical_signal": "neutral",
                    "sentiment_signal": "neutral",
                    "price_level": "Unknown",
                    "price_targets": {
                        "current_price": f"${current_price:.2f}" if 'current_price' in locals() else "Unknown",
                        "fair_value": "Unknown",
                        "buy_target": "Unknown",
                        "sell_target": "Unknown"
                    }
                },
                "error": str(e)
            }
        }
    
    message = HumanMessage(
        content=json.dumps(message_content),
        name="options_advisor",
    )
    
    if show_reasoning:
        show_agent_reasoning(message_content, "Options Advisor Agent")
    
    return {
        "messages": [message],
        "data": data,
    } 