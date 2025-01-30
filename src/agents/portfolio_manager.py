from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from ..tools.openrouter_config import get_chat_completion
import json

from .state import AgentState, show_agent_reasoning


##### Portfolio Management Agent #####
def parse_agent_message(msg):
    """Safely parse agent message content"""
    try:
        if msg is None or not hasattr(msg, 'content') or not msg.content:
            return None

        # Try to parse JSON content
        try:
            if isinstance(msg.content, dict):
                return msg.content
            return json.loads(msg.content)
        except json.JSONDecodeError as e:
            # If content is a string but not JSON, it might be the valuation agent's special format
            if msg.name == "valuation_agent" and isinstance(msg.content, str):
                # Extract the JSON part from the message
                try:
                    start_idx = msg.content.find('{')
                    end_idx = msg.content.rfind('}') + 1
                    if start_idx >= 0 and end_idx > start_idx:
                        json_str = msg.content[start_idx:end_idx]
                        return json.loads(json_str)
                except:
                    pass
            print(f"JSON parsing error in message from {msg.name}: {str(e)}")
            return None
            
    except Exception as e:
        print(f"Error parsing message: {str(e)}")
        return None

def safe_get_confidence(value):
    """Safely convert confidence value to float"""
    try:
        if not value:
            return 0.5
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace("%", "")) / 100
    except (ValueError, AttributeError):
        return 0.5

def format_options_details(strategy_dict):
    """Format options strategy details into a readable string."""
    if not strategy_dict or not isinstance(strategy_dict, dict):
        return "No options strategy recommended"
        
    try:
        # Basic strategy info
        details = []
        strategy = strategy_dict.get("strategy", "")
        rationale = strategy_dict.get("rationale", "")
        impl = strategy_dict.get("implementation", {})
        
        if not strategy or not rationale:
            return "No options strategy recommended"
            
        # Add strategy name and rationale
        details.append(f"{strategy.upper()}: {rationale}")
        
        # Add volatility context if available
        if "volatility" in strategy_dict:
            vol = strategy_dict["volatility"]
            details.append(f"Volatility: {vol.get('implied_volatility', 'Unknown')} ({vol.get('volatility_level', 'Unknown')})")
        
        # Add implementation details based on strategy type
        if impl:
            if "buy_leg" in impl and "sell_leg" in impl:
                # Spread strategy
                details.append("\nBUY LEG:")
                details.append(f"- Strike: ${impl['buy_leg']['recommended_strike']}")
                details.append(f"- Expiration: {impl['buy_leg']['recommended_expiration']}")
                details.append("\nSELL LEG:")
                details.append(f"- Strike: ${impl['sell_leg']['recommended_strike']}")
                details.append(f"- Expiration: {impl['sell_leg']['recommended_expiration']}")
            elif "strikes" in impl:
                # Single leg strategy
                details.append(f"\nStrike: ${impl['recommended_strike']}")
                details.append(f"Expiration: {impl['recommended_expiration']}")
            
            # Add risk metrics if available
            if "premium" in impl:
                details.append(f"\nTarget Premium: ${impl['premium']['target_premium']}")
                if "max_premium" in impl["premium"]:
                    details.append(f"Maximum Premium: ${impl['premium']['max_premium']}")
            if "max_loss" in impl:
                details.append(f"Maximum Loss: ${impl['max_loss']}")
            if "max_profit" in impl:
                details.append(f"Maximum Profit: ${impl['max_profit']}")
            if "break_even" in impl:
                details.append(f"Break Even: ${impl['break_even']}")
        
        return "\n".join(details)
    except Exception as e:
        print(f"Error formatting options details: {str(e)}")
        return "Error formatting options strategy details"

def portfolio_management_agent(state: AgentState):
    """Makes the final trading decision by synthesizing all agent signals"""
    data = state["data"]
    current_price = data["price"]
    show_reasoning = state["metadata"]["show_reasoning"]
    
    # Initialize default result
    default_result = {
        "action": "hold",
        "quantity": 0,
        "confidence": 0.0,
        "price_targets": {
            "current_price": f"${current_price:.2f}",
            "fair_value": "Unknown",
            "buy_target": "Unknown",
            "sell_target": "Unknown"
        },
        "options_strategy": {
            "strategy": "No options strategy recommended",
            "rationale": "No suitable options strategy found",
            "implementation": {}
        },
        "agent_signals": [],
        "reasoning": {
            "summary": "Insufficient data for analysis",
            "price_analysis": "",
            "technical_context": "",
            "risk_factors": "",
            "options_context": ""
        }
    }
    
    try:
        # Get messages from other agents
        agent_messages = {msg.name: msg for msg in state["messages"] if msg and msg.name}
        
        # Parse agent signals with error handling
        agent_signals = []
        options_strategy = None
        price_targets = {
            "current_price": f"${current_price:.2f}",
            "fair_value": "Unknown",
            "buy_target": "Unknown",
            "sell_target": "Unknown"
        }
        
        # First pass: Extract price targets from valuation agent
        if "valuation_agent" in agent_messages:
            val_msg = parse_agent_message(agent_messages["valuation_agent"])
            if val_msg and "reasoning" in val_msg:
                targets = val_msg["reasoning"].get("price_targets", {})
                if targets:
                    for key in ["fair_value", "buy_target", "sell_target"]:
                        if key in targets and targets[key] not in ["Unknown", None, ""]:
                            price_targets[key] = targets[key]
                
                # If still unknown, try DCF analysis
                if price_targets["fair_value"] == "Unknown":
                    dcf = val_msg["reasoning"].get("dcf_analysis", {})
                    if dcf and "price_target" in dcf:
                        price_targets["fair_value"] = dcf["price_target"]
                        # Calculate buy/sell targets based on fair value
                        try:
                            fair_value = float(dcf["price_target"].replace("$", ""))
                            price_targets["buy_target"] = f"${fair_value * 0.95:.2f}"
                            price_targets["sell_target"] = f"${fair_value * 1.10:.2f}"
                        except:
                            pass
        
        # Second pass: Process all agent signals
        for agent_name, msg in agent_messages.items():
            parsed_msg = parse_agent_message(msg)
            if not parsed_msg:
                continue
                
            signal = parsed_msg.get("signal", "neutral")
            confidence = parsed_msg.get("confidence", "0%")
            
            # Extract options strategy if available
            if agent_name == "options_advisor" and parsed_msg:
                recommendations = parsed_msg.get("recommendations", [])
                if recommendations:
                    rec = recommendations[0]
                    # Basic strategy description
                    options_strategy = {
                        "strategy": rec["strategy"],
                        "rationale": rec["rationale"],
                        "implementation": rec.get("implementation", {})
                    }
                    
                    # Add volatility context if available
                    if parsed_msg.get("reasoning", {}).get("volatility_analysis"):
                        options_strategy["volatility"] = parsed_msg["reasoning"]["volatility_analysis"]
                        
                elif parsed_msg.get("reasoning", {}).get("market_context"):
                    # If no recommendations but we have market context, explain why
                    context = parsed_msg["reasoning"]["market_context"]
                    price_level = context.get("price_level", "")
                    tech_signal = context.get("technical_signal", "")
                    options_strategy = {
                        "strategy": "No strategy recommended",
                        "rationale": f"{price_level}, {tech_signal} technical signal",
                        "implementation": {}
                    }
            
            agent_signals.append({
                "agent": agent_name,
                "signal": signal,
                "confidence": confidence
            })
        
        # Create concise output with detailed reasoning
        result = {
            "action": "hold",  # Default action
            "quantity": 0,
            "confidence": 0.0,
            "price_targets": price_targets,
            "options_strategy": options_strategy if options_strategy else {
                "strategy": "No options strategy recommended",
                "rationale": "No suitable options strategy found",
                "implementation": {}
            },
            "agent_signals": agent_signals,
            "reasoning": {
                "summary": "",
                "price_analysis": "",
                "technical_context": "",
                "risk_factors": "",
                "options_context": ""
            }
        }
        
        # Get current price context and valuation signals
        try:
            fair_value = float(price_targets["fair_value"].replace("$", "")) if price_targets["fair_value"] != "Unknown" else current_price
            buy_target = float(price_targets["buy_target"].replace("$", "")) if price_targets["buy_target"] != "Unknown" else fair_value * 0.95
            sell_target = float(price_targets["sell_target"].replace("$", "")) if price_targets["sell_target"] != "Unknown" else fair_value * 1.10
            
            price_gap = ((fair_value - current_price) / current_price) * 100
            price_context = f"Trading at {'premium' if price_gap < 0 else 'discount'} to fair value (gap: {abs(price_gap):.1f}%)"
            
            # Add valuation signal based on price targets
            if current_price < buy_target:
                agent_signals.append({
                    "agent": "valuation_analysis",
                    "signal": "bullish",
                    "confidence": f"{min(abs(price_gap), 50):.0f}%"
                })
            elif current_price > sell_target:
                agent_signals.append({
                    "agent": "valuation_analysis",
                    "signal": "bearish",
                    "confidence": f"{min(abs(price_gap), 50):.0f}%"
                })
            else:
                agent_signals.append({
                    "agent": "valuation_analysis",
                    "signal": "neutral",
                    "confidence": "50%"
                })
        except:
            price_context = "Fair value comparison unavailable"
            fair_value = current_price
            buy_target = current_price * 0.95
            sell_target = current_price * 1.10
        
        # Extract technical and risk context
        tech_context = next((s for s in agent_signals if s["agent"] == "technical_analyst_agent"), {})
        risk_context = next((s for s in agent_signals if s["agent"] == "risk_management_agent"), {})
        
        # Update result based on both price targets and agent signals
        bullish_count = sum(1 for s in agent_signals if s["signal"] == "bullish")
        bearish_count = sum(1 for s in agent_signals if s["signal"] == "bearish")
        neutral_count = sum(1 for s in agent_signals if s["signal"] == "neutral")
        
        # Determine action based on both price targets and signals
        if current_price > sell_target:
            # Price above sell target - consider selling regardless of other signals
            if data.get("position", 0) > 0:
                result["action"] = "sell"
                result["quantity"] = data.get("position", 0)
                result["confidence"] = 0.7 + (bearish_count * 0.1)  # Higher confidence due to price target
                result["reasoning"]["summary"] = f"Price (${current_price:.2f}) above sell target (${sell_target:.2f})"
                result["reasoning"]["price_analysis"] = f"Current price significantly above fair value - {price_context}"
                result["reasoning"]["technical_context"] = f"Technical signals: {bullish_count} bullish, {bearish_count} bearish, {neutral_count} neutral"
                result["reasoning"]["risk_factors"] = "Consider taking profits and implementing protective stops"
            else:
                result["action"] = "hold"
                result["confidence"] = 0.6
                result["reasoning"]["summary"] = "No position to sell, but price above sell target - avoid new entries"
                result["reasoning"]["price_analysis"] = f"Current price: ${current_price:.2f} - {price_context}"
                result["reasoning"]["technical_context"] = "Avoiding new positions at current valuation"
                result["reasoning"]["risk_factors"] = "Price above fair value - high risk for new entries"
        
        elif current_price < buy_target:
            # Price below buy target - consider buying if other signals confirm
            if bullish_count >= bearish_count and data.get("cash", 0) > 0:
                result["action"] = "buy"
                result["quantity"] = int(data.get("cash", 0) / current_price)
                result["confidence"] = 0.6 + (bullish_count * 0.1)
                result["reasoning"]["summary"] = f"Price (${current_price:.2f}) below buy target (${buy_target:.2f}) with bullish signals"
                result["reasoning"]["price_analysis"] = f"Current price below fair value - {price_context}"
                result["reasoning"]["technical_context"] = f"Technical signals support entry with {bullish_count} bullish indicators"
                result["reasoning"]["risk_factors"] = "Monitor position sizing and set stops below recent support"
            else:
                result["action"] = "hold"
                result["confidence"] = 0.5
                result["reasoning"]["summary"] = f"Price attractive but mixed/bearish signals ({bearish_count} bearish vs {bullish_count} bullish)"
                result["reasoning"]["price_analysis"] = f"Current price: ${current_price:.2f} - {price_context}"
                result["reasoning"]["technical_context"] = "Waiting for technical confirmation"
                result["reasoning"]["risk_factors"] = "Mixed signals suggest caution despite attractive price"
        
        else:
            # Price between buy and sell targets - hold unless strong signals
            result["action"] = "hold"
            result["confidence"] = 0.5 + (max(bullish_count, bearish_count) * 0.1)
            result["reasoning"]["summary"] = f"Price (${current_price:.2f}) within fair value range (${buy_target:.2f} - ${sell_target:.2f})"
            result["reasoning"]["price_analysis"] = f"Current price near fair value - {price_context}"
            result["reasoning"]["technical_context"] = f"Mixed signals: {bullish_count} bullish, {bearish_count} bearish, {neutral_count} neutral"
            result["reasoning"]["risk_factors"] = "Maintain current positions with standard risk controls"
        
        # Add options context
        result["reasoning"]["options_context"] = format_options_details(options_strategy)
        
        if show_reasoning:
            show_agent_reasoning(result, "Portfolio Management Agent")
        
        return {
            "messages": [HumanMessage(content=json.dumps(result, indent=2))],
            "data": data,
        }
        
    except Exception as e:
        print(f"Error in portfolio manager: {str(e)}")
        return {
            "messages": [HumanMessage(content=json.dumps(default_result, indent=2))],
            "data": data,
        }
