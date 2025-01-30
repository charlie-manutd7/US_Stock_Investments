from langchain_core.messages import HumanMessage
from agents.state import AgentState, show_agent_reasoning
import json

def valuation_agent(state: AgentState):
    """Performs detailed valuation analysis using multiple methodologies."""
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]
    metrics = data["financial_metrics"][0]
    current_financial_line_item = data["financial_line_items"][0]
    previous_financial_line_item = data["financial_line_items"][1]
    market_cap = data["market_cap"]
    current_price = data["price"]

    reasoning = {}

    # Calculate working capital change
    working_capital_change = (current_financial_line_item.get('working_capital') or 0) - (previous_financial_line_item.get('working_capital') or 0)
    
    # Get and validate key metrics
    net_income = current_financial_line_item.get('net_income', 0)
    free_cash_flow = current_financial_line_item.get('free_cash_flow', 0)
    shares_outstanding = market_cap / current_price if current_price > 0 else 0
    
    # Calculate per-share metrics
    eps = net_income / shares_outstanding if shares_outstanding > 0 else 0
    fcf_per_share = free_cash_flow / shares_outstanding if shares_outstanding > 0 else 0
    
    # Normalize growth rate - cap at reasonable levels
    growth_rate = metrics.get("earnings_growth", 0.10)  # Default to 10% if not available
    normalized_growth_rate = min(max(growth_rate, 0.02), 0.20)  # Cap between 2% and 20%
    
    # Calculate base metrics for sanity checks
    pe_ratio = metrics.get("price_to_earnings_ratio", 20)
    pb_ratio = metrics.get("price_to_book_ratio", 3)
    ps_ratio = metrics.get("price_to_sales_ratio", 2)
    
    # Owner Earnings Valuation (Buffett Method)
    owner_earnings_value = calculate_owner_earnings_value(
        net_income=net_income,
        depreciation=current_financial_line_item.get('depreciation_and_amortization'),
        capex=current_financial_line_item.get('capital_expenditure'),
        working_capital_change=working_capital_change,
        growth_rate=normalized_growth_rate,
        required_return=0.12,  # Reduced from 15% to be less conservative
        margin_of_safety=0.15  # Reduced from 25% to be less conservative
    )
    
    # DCF Valuation
    dcf_value = calculate_intrinsic_value(
        free_cash_flow=free_cash_flow,
        growth_rate=normalized_growth_rate,
        discount_rate=0.10,
        terminal_growth_rate=0.02,
        num_years=5,
    )
    
    # Calculate per share values
    dcf_price_target = dcf_value / shares_outstanding if shares_outstanding > 0 else 0
    owner_earnings_price_target = owner_earnings_value / shares_outstanding if shares_outstanding > 0 else 0
    
    # Calculate PE-based valuation
    if eps > 0:
        # Use industry average PE or historical average PE if available
        # For now, use a range of PE ratios based on growth rate
        if normalized_growth_rate > 0.15:
            target_pe = min(max(pe_ratio, 25), 40)  # Higher PE for high growth
        elif normalized_growth_rate > 0.10:
            target_pe = min(max(pe_ratio, 20), 30)  # Moderate PE for moderate growth
        else:
            target_pe = min(max(pe_ratio, 15), 25)  # Lower PE for low growth
            
        pe_based_value = eps * target_pe
        
        # Weight the different valuation methods
        # Give more weight to fundamental valuations when they're more reliable
        if owner_earnings_price_target > 0 and dcf_price_target > 0:
            weights = {
                'dcf': 0.35,
                'owner_earnings': 0.35,
                'pe': 0.20,
                'current_price': 0.10  # Reduced weight of current price
            }
        else:
            weights = {
                'dcf': 0.25,
                'owner_earnings': 0.25,
                'pe': 0.30,
                'current_price': 0.20
            }
            
        # Calculate weighted average while filtering out zeros and extreme values
        total_weight = 0
        weighted_sum = 0
        
        # Function to check if a value is reasonable
        def is_reasonable_value(value):
            if value <= 0:
                return False
            # Check if value is within 50% of current price
            return 0.5 <= (value / current_price) <= 1.5
        
        if is_reasonable_value(dcf_price_target):
            weighted_sum += dcf_price_target * weights['dcf']
            total_weight += weights['dcf']
        
        if is_reasonable_value(owner_earnings_price_target):
            weighted_sum += owner_earnings_price_target * weights['owner_earnings']
            total_weight += weights['owner_earnings']
            
        if is_reasonable_value(pe_based_value):
            weighted_sum += pe_based_value * weights['pe']
            total_weight += weights['pe']
        
        weighted_sum += current_price * weights['current_price']
        total_weight += weights['current_price']
        
        # If we lost too much weight due to filtering, adjust weights
        if total_weight < 0.7:  # If we lost more than 30% of weights
            weighted_sum = current_price * 0.7 + pe_based_value * 0.3  # Use current price and PE as fallback
            total_weight = 1.0
            
        avg_price_target = weighted_sum / total_weight
    else:
        # If no earnings, use price-to-book or price-to-sales as fallback
        if pb_ratio > 0:
            book_value_per_share = current_price / pb_ratio
            avg_price_target = book_value_per_share * min(max(pb_ratio, 2), 4)
        else:
            avg_price_target = current_price  # Default to current price if no valid metrics
    
    # Calculate valuation gaps
    dcf_gap = (dcf_price_target - current_price) / current_price if dcf_price_target > 0 else 0
    owner_earnings_gap = (owner_earnings_price_target - current_price) / current_price if owner_earnings_price_target > 0 else 0
    
    # Calculate final valuation gap using only valid metrics
    valid_gaps = [g for g in [dcf_gap, owner_earnings_gap] if abs(g) <= 0.5]  # Filter out extreme gaps
    valuation_gap = sum(valid_gaps) / len(valid_gaps) if valid_gaps else 0
    
    # Set buy and sell targets based on fair value and valuation gap
    if abs(valuation_gap) > 0.15:  # Significant mispricing
        # Use larger spreads when valuation gap is significant
        target_spread = 0.20  # 20% spread from fair value
        
        # If undervalued (positive gap), set buy target closer to current price
        if valuation_gap > 0:
            buy_target = min(avg_price_target * (1 - target_spread), current_price * 1.05)  # Buy up to 5% above current
            sell_target = avg_price_target * (1 + target_spread)  # Sell at 20% above fair value
        # If overvalued (negative gap), set sell target closer to current price
        else:
            buy_target = avg_price_target * (1 - target_spread)  # Buy at 20% below fair value
            sell_target = max(avg_price_target * (1 + target_spread), current_price * 0.95)  # Sell down to 5% below current
    else:
        # Use smaller spreads when price is closer to fair value
        target_spread = 0.10  # 10% spread from fair value
        buy_target = avg_price_target * (1 - target_spread)  # Buy at 10% below fair value
        sell_target = avg_price_target * (1 + target_spread)  # Sell at 10% above fair value
    
    # Ensure minimum spread between buy and sell targets
    min_spread = current_price * 0.10  # Minimum 10% spread
    if (sell_target - buy_target) < min_spread:
        mid_point = (buy_target + sell_target) / 2
        buy_target = mid_point - (min_spread / 2)
        sell_target = mid_point + (min_spread / 2)
    
    # Ensure targets don't suggest extreme moves
    max_down = current_price * 0.25  # Maximum 25% down from current price
    max_up = current_price * 0.25    # Maximum 25% up from current price
    
    buy_target = max(current_price - max_down, buy_target)   # Can't go more than 25% below current
    sell_target = min(current_price + max_up, sell_target)   # Can't go more than 25% above current

    if valuation_gap > 0.15:  # More than 15% undervalued
        signal = 'bullish'
    elif valuation_gap < -0.15:  # More than 15% overvalued
        signal = 'bearish'
    else:
        signal = 'neutral'

    reasoning["dcf_analysis"] = {
        "signal": "bullish" if dcf_gap > 0.15 else "bearish" if dcf_gap < -0.15 else "neutral",
        "details": f"Intrinsic Value: ${dcf_value:,.2f}, Market Cap: ${market_cap:,.2f}, Gap: {dcf_gap:.1%}",
        "price_target": f"${dcf_price_target:.2f}"
    }

    reasoning["owner_earnings_analysis"] = {
        "signal": "bullish" if owner_earnings_gap > 0.15 else "bearish" if owner_earnings_gap < -0.15 else "neutral",
        "details": f"Owner Earnings Value: ${owner_earnings_value:,.2f}, Market Cap: ${market_cap:,.2f}, Gap: {owner_earnings_gap:.1%}",
        "price_target": f"${owner_earnings_price_target:.2f}"
    }

    reasoning["price_targets"] = {
        "current_price": f"${current_price:.2f}",
        "fair_value": f"${avg_price_target:.2f}",
        "buy_target": f"${buy_target:.2f}",
        "sell_target": f"${sell_target:.2f}"
    }

    message_content = {
        "signal": signal,
        "confidence": f"{abs(valuation_gap):.0%}",
        "reasoning": reasoning
    }

    message = HumanMessage(
        content=json.dumps(message_content),
        name="valuation_agent",
    )

    if show_reasoning:
        show_agent_reasoning(message_content, "Valuation Analysis Agent")

    return {
        "messages": [message],
        "data": data,
    }

def calculate_owner_earnings_value(
    net_income: float,
    depreciation: float,
    capex: float,
    working_capital_change: float,
    growth_rate: float = 0.05,
    required_return: float = 0.15,
    margin_of_safety: float = 0.25,
    num_years: int = 5
) -> float:
    """
    Calculates the intrinsic value using Buffett's Owner Earnings method.
    
    Owner Earnings = Net Income 
                    + Depreciation/Amortization
                    - Capital Expenditures
                    - Working Capital Changes
    
    Args:
        net_income: Annual net income
        depreciation: Annual depreciation and amortization
        capex: Annual capital expenditures
        working_capital_change: Annual change in working capital
        growth_rate: Expected growth rate (normalized and capped)
        required_return: Required rate of return (Buffett typically uses 15%)
        margin_of_safety: Margin of safety to apply to final value
        num_years: Number of years to project
    
    Returns:
        float: Intrinsic value with margin of safety
    """
    if not all([isinstance(x, (int, float)) for x in [net_income, depreciation, capex, working_capital_change]]):
        return 0
    
    # Calculate initial owner earnings
    owner_earnings = (
        net_income +
        depreciation -
        capex -
        working_capital_change
    )
    
    if owner_earnings <= 0:
        return 0

    # Project future owner earnings with normalized growth
    future_values = []
    for year in range(1, num_years + 1):
        future_value = owner_earnings * (1 + growth_rate) ** year
        discounted_value = future_value / (1 + required_return) ** year
        future_values.append(discounted_value)
    
    # Calculate terminal value with conservative growth
    terminal_growth = min(growth_rate / 2, 0.03)  # Cap terminal growth at 3% and half of growth rate
    terminal_value = (future_values[-1] * (1 + terminal_growth)) / (required_return - terminal_growth)
    terminal_value_discounted = terminal_value / (1 + required_return) ** num_years
    
    # Sum all values and apply margin of safety
    intrinsic_value = (sum(future_values) + terminal_value_discounted)
    value_with_safety_margin = intrinsic_value * (1 - margin_of_safety)
    
    return value_with_safety_margin

def calculate_intrinsic_value(
    free_cash_flow: float,
    growth_rate: float = 0.05,
    discount_rate: float = 0.10,
    terminal_growth_rate: float = 0.02,
    num_years: int = 5,
) -> float:
    """
    Computes the discounted cash flow (DCF) for a given company based on the current free cash flow.
    Use this function to calculate the intrinsic value of a stock.
    """
    if not free_cash_flow or free_cash_flow <= 0:
        return 0

    # Normalize growth rate for DCF
    normalized_growth = min(max(growth_rate, 0.02), 0.25)  # Cap between 2% and 25%
    
    # Estimate the future cash flows based on the normalized growth rate
    cash_flows = [free_cash_flow * (1 + normalized_growth) ** i for i in range(num_years)]

    # Calculate the present value of projected cash flows
    present_values = []
    for i in range(num_years):
        present_value = cash_flows[i] / (1 + discount_rate) ** (i + 1)
        present_values.append(present_value)

    # Calculate the terminal value with conservative growth
    terminal_growth = min(normalized_growth / 2, terminal_growth_rate)  # Use the more conservative rate
    terminal_value = cash_flows[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
    terminal_present_value = terminal_value / (1 + discount_rate) ** num_years

    # Sum up the present values and terminal value
    dcf_value = sum(present_values) + terminal_present_value

    return dcf_value

def calculate_working_capital_change(
    current_working_capital: float,
    previous_working_capital: float,
) -> float:
    """
    Calculate the absolute change in working capital between two periods.
    A positive change means more capital is tied up in working capital (cash outflow).
    A negative change means less capital is tied up (cash inflow).
    
    Args:
        current_working_capital: Current period's working capital
        previous_working_capital: Previous period's working capital
    
    Returns:
        float: Change in working capital (current - previous)
    """
    return current_working_capital - previous_working_capital