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
    ticker = data["ticker"]

    reasoning = {}

    # Enhanced Industry Analysis
    industry_metrics = get_industry_metrics(ticker)
    industry_pe = industry_metrics.get('pe_ratio', 20)
    industry_growth = industry_metrics.get('growth_rate', 0.10)
    industry_position = industry_metrics.get('market_position', 'average')
    industry_moat = industry_metrics.get('competitive_moat', 'none')
    industry_margins = industry_metrics.get('industry_margins', {})

    # Strategic Value Assessment
    strategic_value_premium = 1.0
    if industry_position == 'leader':
        strategic_value_premium = 1.3  # 30% premium for industry leaders
    elif industry_position == 'challenger':
        strategic_value_premium = 1.15  # 15% premium for strong challengers
    
    # Competitive Moat Assessment
    moat_premium = 1.0
    if industry_moat == 'wide':
        moat_premium = 1.25  # 25% premium for wide moat
    elif industry_moat == 'narrow':
        moat_premium = 1.15  # 15% premium for narrow moat

    # Calculate working capital change
    working_capital_change = (current_financial_line_item.get('working_capital') or 0) - (previous_financial_line_item.get('working_capital') or 0)
    
    # Get and validate key metrics
    net_income = current_financial_line_item.get('net_income', 0)
    free_cash_flow = current_financial_line_item.get('free_cash_flow', 0)
    shares_outstanding = market_cap / current_price if current_price > 0 else 0
    
    # Calculate per-share metrics
    eps = net_income / shares_outstanding if shares_outstanding > 0 else 0
    fcf_per_share = free_cash_flow / shares_outstanding if shares_outstanding > 0 else 0
    
    # Enhanced Growth Rate Analysis
    company_growth = metrics.get("earnings_growth", industry_growth)
    normalized_growth_rate = min(max(company_growth * strategic_value_premium, 0.05), 0.25)
    
    # Calculate base metrics with industry comparison
    pe_ratio = metrics.get("price_to_earnings_ratio", industry_pe)
    pb_ratio = metrics.get("price_to_book_ratio", 3)
    ps_ratio = metrics.get("price_to_sales_ratio", 2)
    
    # Enhanced Risk Assessment
    base_required_return = 0.10
    risk_discount = 0.0
    if industry_position == 'leader':
        risk_discount = 0.02
    elif industry_position == 'challenger':
        risk_discount = 0.01
    
    # Additional risk adjustments based on moat
    if industry_moat == 'wide':
        risk_discount += 0.01
    elif industry_moat == 'narrow':
        risk_discount += 0.005
        
    required_return = base_required_return - risk_discount

    # Calculate DCF Value
    dcf_value = calculate_intrinsic_value(
        free_cash_flow=free_cash_flow,
        growth_rate=normalized_growth_rate,
        discount_rate=required_return,
        terminal_growth_rate=min(normalized_growth_rate * 0.4, 0.04),  # Terminal growth capped at 4%
        num_years=5,
    )
    
    # Calculate Owner Earnings Value
    owner_earnings_value = calculate_owner_earnings_value(
        net_income=net_income,
        depreciation=current_financial_line_item.get('depreciation_and_amortization'),
        capex=current_financial_line_item.get('capital_expenditure'),
        working_capital_change=working_capital_change,
        growth_rate=normalized_growth_rate,
        required_return=required_return,
        margin_of_safety=0.15
    )
    
    # Calculate per share values
    dcf_price_target = dcf_value / shares_outstanding if shares_outstanding > 0 else 0
    owner_earnings_price_target = owner_earnings_value / shares_outstanding if shares_outstanding > 0 else 0

    # Weight the different valuation methods based on reliability and strategic value
    if owner_earnings_price_target > 0 and dcf_price_target > 0:
        weights = {
            'dcf': 0.30,
            'owner_earnings': 0.30,
            'pe': 0.20,
            'strategic_value': 0.15,  # New weight for strategic value
            'current_price': 0.05
        }
    else:
        weights = {
            'dcf': 0.25,
            'owner_earnings': 0.25,
            'pe': 0.25,
            'strategic_value': 0.15,  # New weight for strategic value
            'current_price': 0.10
        }

    # Calculate strategic value component
    strategic_value = current_price * strategic_value_premium * moat_premium

    # Initialize weighted calculation
    weighted_sum = 0
    total_weight = 0

    # Function to check if a value is reasonable
    def is_reasonable_value(value):
        if value <= 0:
            return False
        return 0.5 <= (value / current_price) <= 1.5

    # Add components to weighted calculation
    if is_reasonable_value(dcf_price_target):
        weighted_sum += dcf_price_target * weights['dcf']
        total_weight += weights['dcf']
    
    if is_reasonable_value(owner_earnings_price_target):
        weighted_sum += owner_earnings_price_target * weights['owner_earnings']
        total_weight += weights['owner_earnings']
    
    if is_reasonable_value(strategic_value):
        weighted_sum += strategic_value * weights['strategic_value']
        total_weight += weights['strategic_value']

    weighted_sum += current_price * weights['current_price']
    total_weight += weights['current_price']

    # Calculate final fair value
    if total_weight < 0.7:  # If we lost more than 30% of weights
        avg_price_target = current_price * 0.7 + strategic_value * 0.3  # Use current price and strategic value as fallback
    else:
        avg_price_target = weighted_sum / total_weight

    # Calculate valuation gaps
    dcf_gap = (dcf_price_target - current_price) / current_price if dcf_price_target > 0 else 0
    owner_earnings_gap = (owner_earnings_price_target - current_price) / current_price if owner_earnings_price_target > 0 else 0
    
    # Calculate final valuation gap using only valid metrics
    valid_gaps = [g for g in [dcf_gap, owner_earnings_gap] if abs(g) <= 0.5]  # Filter out extreme gaps
    valuation_gap = sum(valid_gaps) / len(valid_gaps) if valid_gaps else 0

    # Set signal based on valuation gap
    if valuation_gap > 0.15:  # More than 15% undervalued
        signal = 'bullish'
    elif valuation_gap < -0.15:  # More than 15% overvalued
        signal = 'bearish'
    else:
        signal = 'neutral'

    # Build reasoning dictionary
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
        "buy_target": f"${avg_price_target * 0.9:.2f}",  # 10% below fair value
        "sell_target": f"${avg_price_target * 1.1:.2f}"  # 10% above fair value
    }

    reasoning["industry_analysis"] = {
        "position": industry_position,
        "competitive_moat": industry_moat,
        "strategic_premium": f"{(strategic_value_premium * moat_premium - 1) * 100:.1f}%",
        "industry_comparison": {
            "margins": {
                "company": f"{metrics.get('operating_margin', 0):.1%}",
                "industry": f"{industry_margins.get('operating_margin', 0):.1%}"
            },
            "growth": {
                "company": f"{company_growth:.1%}",
                "industry": f"{industry_growth:.1%}"
            },
            "valuation": {
                "company_pe": f"{pe_ratio:.1f}x",
                "industry_pe": f"{industry_pe:.1f}x"
            }
        }
    }

    reasoning["strategic_value"] = {
        "base_value": f"${current_price:.2f}",
        "adjusted_value": f"${strategic_value:.2f}",
        "premium_factors": [
            f"Industry Position Premium: {(strategic_value_premium - 1) * 100:.1f}%",
            f"Competitive Moat Premium: {(moat_premium - 1) * 100:.1f}%"
        ]
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

def get_industry_metrics(ticker: str) -> dict:
    """
    Get industry-specific metrics for valuation adjustments.
    This function provides industry averages and company positioning.
    """
    # Technology sector leaders
    tech_leaders = {'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'AVGO', 'ORCL', 'CRM', 'ADBE'}
    tech_challengers = {'AMD', 'INTC', 'TSM', 'QCOM', 'TXN', 'MU', 'AMAT', 'KLAC', 'LRCX', 'ASML'}
    
    # Semiconductor industry metrics
    semiconductor_metrics = {
        'pe_ratio': 25,  # Higher PE due to growth and cyclicality
        'growth_rate': 0.15,  # Strong growth expectations
        'market_position': 'average'
    }
    
    # Technology sector metrics
    tech_metrics = {
        'pe_ratio': 30,  # Higher PE for tech sector
        'growth_rate': 0.20,  # Strong growth expectations
        'market_position': 'average'
    }
    
    # Default metrics for other industries
    default_metrics = {
        'pe_ratio': 20,
        'growth_rate': 0.10,
        'market_position': 'average'
    }
    
    # Determine company's market position
    if ticker in tech_leaders:
        market_position = 'leader'
    elif ticker in tech_challengers:
        market_position = 'challenger'
    else:
        market_position = 'average'
    
    # Select appropriate industry metrics
    if ticker in {'NVDA', 'AMD', 'INTC', 'TSM', 'QCOM'}:
        metrics = semiconductor_metrics.copy()
    elif ticker in tech_leaders.union(tech_challengers):
        metrics = tech_metrics.copy()
    else:
        metrics = default_metrics.copy()
    
    # Update market position based on company's standing
    metrics['market_position'] = market_position
    
    # Adjust metrics based on market position
    if market_position == 'leader':
        metrics['pe_ratio'] *= 1.2  # 20% premium for leaders
        metrics['growth_rate'] *= 1.2  # 20% higher growth expectations
    elif market_position == 'challenger':
        metrics['pe_ratio'] *= 1.1  # 10% premium for challengers
        metrics['growth_rate'] *= 1.1  # 10% higher growth expectations
    
    return metrics

def clean_price_value(value):
    """Clean price values by removing currency symbols and converting to float."""
    if value is None:
        return 0.0
    
    if isinstance(value, (int, float)):
        return float(value)
    # ... rest of the function