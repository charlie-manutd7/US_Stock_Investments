from typing import Dict, Any
import json
from datetime import datetime

class RoutingAgent:
    def __init__(self):
        self.context = {}
        
    def process_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process user questions and route them to appropriate agents or provide direct answers.
        
        Args:
            question: The user's question
            context: Dictionary containing current analysis and backtest results
        
        Returns:
            Dict containing the response and any additional data
        """
        # Update context with new information
        self.context.update(context)
        
        # Categorize question type
        if any(word in question.lower() for word in ['price', 'target', 'fair value']):
            return self._handle_price_question()
        elif any(word in question.lower() for word in ['option', 'strategy', 'put', 'call']):
            return self._handle_options_question()
        elif any(word in question.lower() for word in ['backtest', 'performance', 'return']):
            return self._handle_backtest_question()
        elif any(word in question.lower() for word in ['risk', 'confidence']):
            return self._handle_risk_question()
        else:
            return self._handle_general_question(question)

    def _handle_price_question(self) -> Dict[str, Any]:
        """Handle questions about price targets and valuation."""
        analysis = self.context.get('current_analysis', {})
        price_targets = analysis.get('price_targets', {})
        
        if not price_targets:
            return {
                'type': 'price',
                'response': 'I apologize, but I don\'t have price target information in the current context.'
            }
        
        return {
            'type': 'price',
            'response': f"""
                Based on our analysis:
                - Current Price: {price_targets.get('current_price', 'Unknown')}
                - Fair Value: {price_targets.get('fair_value', 'Unknown')}
                - Buy Target: {price_targets.get('buy_target', 'Unknown')}
                - Sell Target: {price_targets.get('sell_target', 'Unknown')}
            """.strip(),
            'data': price_targets
        }

    def _handle_options_question(self) -> Dict[str, Any]:
        """Handle questions about options strategies."""
        analysis = self.context.get('current_analysis', {})
        strategy = analysis.get('options_strategy', {})
        
        if not strategy:
            return {
                'type': 'options',
                'response': 'I apologize, but I don\'t have options strategy information in the current context.'
            }
        
        implementation = strategy.get('implementation', {})
        return {
            'type': 'options',
            'response': f"""
                Recommended Strategy: {strategy.get('strategy', 'Unknown')}
                Rationale: {strategy.get('rationale', 'Unknown')}
                
                Implementation Details:
                - Recommended Strike: ${implementation.get('recommended_strike', 'Unknown')}
                - Expiration: {implementation.get('recommended_expiration', 'Unknown')}
                - Target Premium: ${implementation.get('premium', {}).get('target_premium', 'Unknown')}
                - Max Profit: ${implementation.get('max_profit', 'Unknown')}
                - Max Loss: ${implementation.get('max_loss', 'Unknown')}
            """.strip(),
            'data': strategy
        }

    def _handle_backtest_question(self) -> Dict[str, Any]:
        """Handle questions about backtest results."""
        backtest = self.context.get('backtest_results', {})
        
        if not backtest:
            return {
                'type': 'backtest',
                'response': 'I apologize, but I don\'t have backtest results in the current context.'
            }
        
        portfolio_values = backtest.get('portfolio_values', [])
        if not portfolio_values:
            return {
                'type': 'backtest',
                'response': 'No portfolio values available from the backtest.'
            }
        
        initial_value = portfolio_values[0]['Portfolio Value']
        final_value = portfolio_values[-1]['Portfolio Value']
        total_return = ((final_value / initial_value) - 1) * 100
        
        return {
            'type': 'backtest',
            'response': f"""
                Backtest Results:
                - Initial Portfolio Value: ${initial_value:,.2f}
                - Final Portfolio Value: ${final_value:,.2f}
                - Total Return: {total_return:.2f}%
                - Number of Options Trades: {len(backtest.get('options_trades', []))}
            """.strip(),
            'data': backtest
        }

    def _handle_risk_question(self) -> Dict[str, Any]:
        """Handle questions about risk and confidence levels."""
        analysis = self.context.get('current_analysis', {})
        
        confidence = analysis.get('confidence', 0)
        signals = analysis.get('agent_signals', [])
        
        if not signals:
            return {
                'type': 'risk',
                'response': 'I apologize, but I don\'t have risk information in the current context.'
            }
        
        signal_summary = '\n'.join([
            f"- {signal['agent']}: {signal['signal']} (confidence: {signal['confidence']})"
            for signal in signals
        ])
        
        return {
            'type': 'risk',
            'response': f"""
                Overall Confidence: {confidence:.2f}
                
                Individual Agent Signals:
                {signal_summary}
            """.strip(),
            'data': {
                'confidence': confidence,
                'signals': signals
            }
        }

    def _handle_general_question(self, question: str) -> Dict[str, Any]:
        """Handle general questions about the analysis."""
        analysis = self.context.get('current_analysis', {})
        
        return {
            'type': 'general',
            'response': f"""
                Based on our analysis:
                - Recommended Action: {analysis.get('action', 'Unknown')}
                - Quantity: {analysis.get('quantity', 0)}
                - Confidence: {analysis.get('confidence', 0):.2f}
                
                For more specific information, you can ask about:
                - Price targets and valuation
                - Options strategy details
                - Backtest performance
                - Risk assessment
            """.strip(),
            'data': analysis
        } 