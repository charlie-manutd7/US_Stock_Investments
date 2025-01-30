from langchain_core.messages import HumanMessage

from .state import AgentState, show_agent_reasoning

import json

# Add helper functions at the top of the file
def get_profitability_assessment(score):
    """Provide detailed profitability assessment"""
    if score >= 2:
        return "Strong profitability metrics indicating efficient operations and good management"
    elif score == 1:
        return "Mixed profitability metrics suggesting room for operational improvement"
    return "Weak profitability metrics indicating potential business model issues"

def get_growth_assessment(score):
    """Provide detailed growth assessment"""
    if score >= 2:
        return "Strong growth across key metrics indicating business expansion"
    elif score == 1:
        return "Moderate growth with some areas showing promise"
    return "Limited growth suggesting potential market saturation or competitive pressures"

def get_financial_health_assessment(score):
    """Provide detailed financial health assessment"""
    if score >= 2:
        return "Strong balance sheet with good liquidity and conservative leverage"
    elif score == 1:
        return "Adequate financial position but room for improvement"
    return "Potential financial stress requiring careful monitoring"

def get_fcf_conversion_rate(fcf_per_share, eps):
    """Assess free cash flow conversion quality"""
    if not fcf_per_share or not eps or eps == 0:
        return "Unable to assess - insufficient data"
    
    conversion_rate = fcf_per_share / eps
    if conversion_rate > 1.2:
        return "Excellent FCF conversion - earnings quality is high"
    elif conversion_rate > 0.8:
        return "Good FCF conversion - earnings appear sustainable"
    elif conversion_rate > 0.5:
        return "Moderate FCF conversion - monitor working capital"
    return "Poor FCF conversion - potential earnings quality issues"

def get_capital_allocation_assessment(metrics):
    """Assess management's capital allocation decisions"""
    roe = metrics.get("return_on_equity", 0)
    roic = metrics.get("return_on_invested_capital", 0)
    payout_ratio = metrics.get("payout_ratio", 0)
    
    if roe > 0.15 and roic > 0.12:
        if payout_ratio < 0.75:
            return "Excellent capital allocation - high returns and sustainable payout"
        return "Good capital allocation but high payout ratio"
    elif roe > 0.10 and roic > 0.08:
        return "Adequate capital allocation - returns above cost of capital"
    return "Poor capital allocation - returns suggest value destruction"

def get_business_model_assessment(metrics):
    """Assess the quality and sustainability of the business model"""
    gross_margin = metrics.get("gross_margin", 0)
    operating_margin = metrics.get("operating_margin", 0)
    asset_turnover = metrics.get("asset_turnover", 0)
    
    if gross_margin > 0.40 and operating_margin > 0.20:
        return "Strong business model with pricing power"
    elif gross_margin > 0.30 and operating_margin > 0.10:
        return "Solid business model with good economics"
    elif gross_margin > 0.20 and operating_margin > 0.05:
        return "Average business model - limited competitive advantage"
    return "Challenging business model - may lack differentiation"

def get_overall_signal(signals):
    """Determine overall signal based on signal counts"""
    bullish_count = signals.count('bullish')
    bearish_count = signals.count('bearish')
    
    if bullish_count > bearish_count:
        return 'bullish'
    elif bearish_count > bullish_count:
        return 'bearish'
    return 'neutral'

def get_signal_confidence(signals):
    """Calculate confidence level based on signal agreement"""
    total_signals = len(signals)
    if total_signals == 0:
        return 0
    
    bullish_count = signals.count('bullish')
    bearish_count = signals.count('bearish')
    max_count = max(bullish_count, bearish_count)
    
    return max_count / total_signals

##### Fundamental Agent #####
def fundamentals_agent(state: AgentState):
    """Analyzes fundamental data and generates trading signals."""
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]
    metrics = data["financial_metrics"][0]
    current_financial_line_item = data["financial_line_items"][0]
    previous_financial_line_item = data["financial_line_items"][1]

    # Initialize signals list for different fundamental aspects
    signals = []
    reasoning = {}
    
    # 1. Profitability Analysis
    return_on_equity = metrics.get("return_on_equity")
    net_margin = metrics.get("net_margin")
    operating_margin = metrics.get("operating_margin")

    thresholds = [
        (return_on_equity, 0.15),  # Strong ROE above 15%
        (net_margin, 0.20),  # Healthy profit margins
        (operating_margin, 0.15)  # Strong operating efficiency
    ]
    profitability_score = sum(
        metric is not None and metric > threshold
        for metric, threshold in thresholds
    )
        
    signals.append('bullish' if profitability_score >= 2 else 'bearish' if profitability_score == 0 else 'neutral')
    reasoning["profitability_signal"] = {
        "signal": signals[0],
        "details": (
            f"ROE: {metrics['return_on_equity']:.2%}" if metrics["return_on_equity"] else "ROE: N/A"
        ) + ", " + (
            f"Net Margin: {metrics['net_margin']:.2%}" if metrics["net_margin"] else "Net Margin: N/A"
        ) + ", " + (
            f"Op Margin: {metrics['operating_margin']:.2%}" if metrics["operating_margin"] else "Op Margin: N/A"
        )
    }
    
    # 2. Growth Analysis
    revenue_growth = metrics.get("revenue_growth")
    earnings_growth = metrics.get("earnings_growth")
    book_value_growth = metrics.get("book_value_growth")

    thresholds = [
        (revenue_growth, 0.10),  # 10% revenue growth
        (earnings_growth, 0.10),  # 10% earnings growth
        (book_value_growth, 0.10)  # 10% book value growth
    ]
    growth_score = sum(
        metric is not None and metric > threshold
        for metric, threshold in thresholds
    )
        
    signals.append('bullish' if growth_score >= 2 else 'bearish' if growth_score == 0 else 'neutral')
    reasoning["growth_signal"] = {
        "signal": signals[1],
        "details": (
            f"Revenue Growth: {metrics['revenue_growth']:.2%}" if metrics["revenue_growth"] else "Revenue Growth: N/A"
        ) + ", " + (
            f"Earnings Growth: {metrics['earnings_growth']:.2%}" if metrics["earnings_growth"] else "Earnings Growth: N/A"
        )
    }
    
    # 3. Financial Health
    current_ratio = metrics.get("current_ratio")
    debt_to_equity = metrics.get("debt_to_equity")
    free_cash_flow_per_share = metrics.get("free_cash_flow_per_share")
    earnings_per_share = metrics.get("earnings_per_share")

    health_score = 0
    if current_ratio and current_ratio > 1.5:  # Strong liquidity
        health_score += 1
    if debt_to_equity and debt_to_equity < 0.5:  # Conservative debt levels
        health_score += 1
    if (free_cash_flow_per_share and earnings_per_share and
            free_cash_flow_per_share > earnings_per_share * 0.8):  # Strong FCF conversion
        health_score += 1
        
    signals.append('bullish' if health_score >= 2 else 'bearish' if health_score == 0 else 'neutral')
    reasoning["financial_health_signal"] = {
        "signal": signals[2],
        "details": (
            f"Current Ratio: {metrics['current_ratio']:.2f}" if metrics["current_ratio"] else "Current Ratio: N/A"
        ) + ", " + (
            f"D/E: {metrics['debt_to_equity']:.2f}" if metrics["debt_to_equity"] else "D/E: N/A"
        )
    }
    
    # 4. Price to X ratios
    pe_ratio = metrics.get("price_to_earnings_ratio")
    pb_ratio = metrics.get("price_to_book_ratio")
    ps_ratio = metrics.get("price_to_sales_ratio")

    thresholds = [
        (pe_ratio, 25),  # Reasonable P/E ratio
        (pb_ratio, 3),  # Reasonable P/B ratio
        (ps_ratio, 5)  # Reasonable P/S ratio
    ]
    price_ratio_score = sum(
        metric is not None and metric > threshold
        for metric, threshold in thresholds
    )
        
    signals.append('bullish' if price_ratio_score >= 2 else 'bearish' if price_ratio_score == 0 else 'neutral')
    reasoning["price_ratios_signal"] = {
        "signal": signals[3],
        "details": (
            f"P/E: {pe_ratio:.2f}" if pe_ratio else "P/E: N/A"
        ) + ", " + (
            f"P/B: {pb_ratio:.2f}" if pb_ratio else "P/B: N/A"
        ) + ", " + (
            f"P/S: {ps_ratio:.2f}" if ps_ratio else "P/S: N/A"
        )
    }
    
    # Determine overall signal
    bullish_signals = signals.count('bullish')
    bearish_signals = signals.count('bearish')
    
    if bullish_signals > bearish_signals:
        overall_signal = 'bullish'
    elif bearish_signals > bullish_signals:
        overall_signal = 'bearish'
    else:
        overall_signal = 'neutral'
    
    # Calculate confidence level
    total_signals = len(signals)
    confidence = max(bullish_signals, bearish_signals) / total_signals
    
    # Create expert system message
    expert_message = f"""You are Warren Buffett, legendary value investor and CEO of Berkshire Hathaway, known for your focus on fundamental analysis and long-term value creation.

    Based on the comprehensive fundamental analysis, here are the key findings:

    PROFITABILITY ANALYSIS:
    - Return on Equity: {metrics.get('return_on_equity', 'N/A'):.2%} if metrics.get('return_on_equity') else 'N/A'
    - Net Margin: {metrics.get('net_margin', 'N/A'):.2%} if metrics.get('net_margin') else 'N/A'
    - Operating Margin: {metrics.get('operating_margin', 'N/A'):.2%} if metrics.get('operating_margin') else 'N/A'
    Assessment: {get_profitability_assessment(profitability_score)}

    GROWTH METRICS:
    - Revenue Growth: {metrics.get('revenue_growth', 'N/A'):.2%} if metrics.get('revenue_growth') else 'N/A'
    - Earnings Growth: {metrics.get('earnings_growth', 'N/A'):.2%} if metrics.get('earnings_growth') else 'N/A'
    - Book Value Growth: {metrics.get('book_value_growth', 'N/A'):.2%} if metrics.get('book_value_growth') else 'N/A'
    Assessment: {get_growth_assessment(growth_score)}

    FINANCIAL HEALTH:
    - Current Ratio: {metrics.get('current_ratio', 'N/A'):.2f} if metrics.get('current_ratio') else 'N/A'
    - Debt to Equity: {metrics.get('debt_to_equity', 'N/A'):.2f} if metrics.get('debt_to_equity') else 'N/A'
    - FCF/Share: ${metrics.get('free_cash_flow_per_share', 'N/A'):.2f} if metrics.get('free_cash_flow_per_share') else 'N/A'
    Assessment: {get_financial_health_assessment(health_score)}

    QUALITY METRICS:
    - FCF Conversion: {get_fcf_conversion_rate(free_cash_flow_per_share, earnings_per_share)}
    - Capital Allocation: {get_capital_allocation_assessment(metrics)}
    - Business Model: {get_business_model_assessment(metrics)}

    FUNDAMENTAL CONFLUENCE:
    - Bullish Signals: {signals.count('bullish')}
    - Bearish Signals: {signals.count('bearish')}
    - Neutral Signals: {signals.count('neutral')}

    Please consider these fundamental factors in the context of:
    1. Competitive advantage (moat)
    2. Management quality
    3. Capital allocation
    4. Business predictability"""

    # Create the fundamentals message with enhanced expertise
    message = HumanMessage(
        content=json.dumps({
            "signal": get_overall_signal(signals),
            "confidence": f"{get_signal_confidence(signals) * 100:.0f}%",
            "reasoning": {
                "expert_analysis": expert_message,
                "fundamental_signals": reasoning
            }
        }),
        name="fundamentals_agent",
    )

    if show_reasoning:
        show_agent_reasoning({
            "signal": get_overall_signal(signals),
            "confidence": f"{get_signal_confidence(signals) * 100:.0f}%",
            "reasoning": {
                "expert_analysis": expert_message,
                "fundamental_signals": reasoning
            }
        }, "Fundamentals Analysis Agent")

    return {
        "messages": [message],
        "data": data,
    }
