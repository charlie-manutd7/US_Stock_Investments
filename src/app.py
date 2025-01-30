import os
from flask import Flask, request, jsonify, render_template, send_from_directory
from datetime import datetime, timedelta
import sys
import json
import logging
import werkzeug
import re
from flask_cors import CORS

# Add src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from .main import run_hedge_fund
from .backtester import Backtester

# Get absolute paths for static and template folders
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_folder = os.path.join(root_dir, 'src', 'web', 'static')
template_folder = os.path.join(root_dir, 'src', 'web', 'templates')

app = Flask(__name__, 
    static_folder=static_folder,
    template_folder=template_folder
)

# Enable CORS for all routes with proper configuration
CORS(app, resources={
    r"/*": {
        "origins": [
            "http://localhost:5000",
            "http://localhost:8080",
            "https://stock-options-tool.web.app",
            "https://stock-options-tool.firebaseapp.com",
            "https://stock-options-tool-api.onrender.com"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Configure basic logging
app.logger.setLevel(logging.INFO)

# Configure logging to ignore swarm requests completely
werkzeug_logger = logging.getLogger('werkzeug')
original_log = werkzeug_logger.log
original_warning = werkzeug_logger.warning
original_info = werkzeug_logger.info

def should_ignore_request(msg, *args, **kwargs):
    # Check if any of the args contain swarm-related paths
    return any('/api/v0/swarm/' in str(arg) for arg in args)

def custom_log(level, msg, *args, **kwargs):
    if should_ignore_request(msg, *args, **kwargs):
        return
    original_log(level, msg, *args, **kwargs)

def custom_warning(msg, *args, **kwargs):
    if should_ignore_request(msg, *args, **kwargs):
        return
    original_warning(msg, *args, **kwargs)

def custom_info(msg, *args, **kwargs):
    if should_ignore_request(msg, *args, **kwargs):
        return
    original_info(msg, *args, **kwargs)

werkzeug_logger.log = custom_log
werkzeug_logger.warning = custom_warning
werkzeug_logger.info = custom_info

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        app.logger.error(f"Error rendering index: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/favicon.ico')
def favicon():
    try:
        return send_from_directory(os.path.join(static_folder, 'img'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')
    except Exception as e:
        app.logger.error(f"Error serving favicon: {str(e)}")
        return '', 404

@app.route('/static/<path:filename>')
def serve_static(filename):
    try:
        return send_from_directory(static_folder, filename)
    except Exception as e:
        app.logger.error(f"Error serving static file {filename}: {str(e)}")
        return jsonify({'error': 'File not found'}), 404

# Add specific handler for swarm endpoints to return immediately
@app.route('/api/v0/swarm/<path:subpath>', methods=['GET', 'POST'])
def handle_swarm(subpath):
    return '', 404

# Handle unknown routes
@app.errorhandler(404)
def not_found(e):
    # Don't log swarm API calls at all
    if request.path.startswith('/api/v0/swarm/'):
        return '', 404
    app.logger.warning(f"404 error for path: {request.path}")
    return jsonify({'error': 'Route not found'}), 404

def clean_price_value(value):
    """Clean price values by removing currency symbols and converting to float."""
    if value is None:
        return 0.0
    
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        try:
            # First attempt: direct float conversion
            return float(value)
        except ValueError:
            try:
                # Second attempt: remove currency symbols and other characters
                cleaned = value.replace('$', '').replace(',', '').replace('£', '').replace('€', '').strip()
                return float(cleaned)
            except ValueError:
                try:
                    # Third attempt: extract first number using regex
                    numbers = re.findall(r'[-+]?\d*\.?\d+', cleaned)
                    if numbers:
                        return float(numbers[0])
                    return 0.0
                except Exception:
                    return 0.0
    
    return 0.0

def clean_analysis_result(result):
    """Clean and validate the analysis result structure."""
    if not isinstance(result, dict):
        return result
        
    cleaned_result = result.copy()  # Create a copy to avoid modifying the original
    
    try:
        # Clean price targets
        if 'price_targets' in cleaned_result:
            price_targets = cleaned_result['price_targets']
            if isinstance(price_targets, dict):
                for key in ['current_price', 'fair_value', 'buy_target', 'sell_target']:
                    if key in price_targets:
                        try:
                            price_targets[key] = clean_price_value(price_targets[key])
                        except Exception as e:
                            app.logger.error(f"Error cleaning price target {key}: {str(e)}")
                            price_targets[key] = 0.0
        
        # Clean momentum analysis prices
        if 'momentum_analysis' in cleaned_result:
            momentum = cleaned_result['momentum_analysis']
            if isinstance(momentum, dict):
                # Clean main price values
                for key in ['current_price', 'target_price', 'support_level', 'resistance_level', 'stop_loss']:
                    if key in momentum:
                        try:
                            momentum[key] = clean_price_value(momentum[key])
                        except Exception as e:
                            app.logger.error(f"Error cleaning momentum price {key}: {str(e)}")
                            momentum[key] = 0.0
                
                # Clean nested price values in price_momentum and volume_momentum
                for key in ['price_momentum', 'volume_momentum']:
                    if key in momentum and isinstance(momentum[key], dict):
                        value = momentum[key].get('value')
                        if value is not None:
                            try:
                                if isinstance(value, str):
                                    momentum[key]['value'] = clean_price_value(value)
                                else:
                                    momentum[key]['value'] = float(value)
                            except (ValueError, TypeError) as e:
                                app.logger.error(f"Error cleaning momentum value {key}: {str(e)}")
                                momentum[key]['value'] = 0.0
        
        return cleaned_result
    except Exception as e:
        app.logger.error(f"Error in clean_analysis_result: {str(e)}")
        return result  # Return original if cleaning fails

def process_analysis_result(result):
    """Process and enhance the analysis result with all required fields."""
    if not isinstance(result, dict):
        result = {}

    # Ensure all required sections exist
    if 'options_strategy' in result:
        options = result['options_strategy']
        if isinstance(options, dict):
            # Fix options strategy fields
            if 'implementation' in options:
                impl = options['implementation']
                if isinstance(impl, dict):
                    # Convert object Object to proper values
                    if 'strikes' in impl and str(impl['strikes']) == '[object Object]':
                        impl['strikes'] = {
                            'conservative': float(current_price * 0.95),
                            'moderate': float(current_price),
                            'aggressive': float(current_price * 1.05)
                        }
                    if 'premium' in impl and str(impl['premium']) == '[object Object]':
                        impl['premium'] = {
                            'target_premium': float(impl.get('max_loss', 0.0)),
                            'max_premium': float(impl.get('max_loss', 0.0)) * 1.4
                        }
            # Add risk profile if missing
            if 'risk_profile' not in options or not options['risk_profile']:
                options['risk_profile'] = 'Moderate - Defined risk with premium cost'

    # Add momentum analysis if missing
    if 'momentum_analysis' not in result:
        current_price = float(result.get('price_targets', {}).get('current_price', 0.0))
        result['momentum_analysis'] = {
            'price_momentum': {
                'signal': 'neutral',
                'value': '0'
            },
            'volume_momentum': {
                'signal': 'neutral',
                'value': '0'
            },
            'rsi': 50.0,
            'current_price': current_price,
            'target_price': current_price * 1.05,
            'support_level': current_price * 0.95,
            'resistance_level': current_price * 1.05,
            'stop_loss': current_price * 0.95,
            'signal': 'neutral',
            'timeframe': 'Short-term',
            'confidence': 0.5,
            'reasoning': [
                'Technical indicators show mixed signals',
                'Volume analysis indicates neutral trend',
                'RSI in neutral territory'
            ]
        }

    # Enhance reasoning if missing or incomplete
    if 'reasoning' not in result:
        result['reasoning'] = {}
    
    reasoning = result['reasoning']
    price_targets = result.get('price_targets', {})
    current_price = float(price_targets.get('current_price', 0.0))
    fair_value = float(price_targets.get('fair_value', 0.0))
    
    if not reasoning.get('summary'):
        gap_pct = ((current_price - fair_value) / fair_value * 100) if fair_value > 0 else 0
        if gap_pct > 10:
            reasoning['summary'] = f"Stock appears overvalued by {gap_pct:.1f}% relative to fair value"
        elif gap_pct < -10:
            reasoning['summary'] = f"Stock appears undervalued by {abs(gap_pct):.1f}% relative to fair value"
        else:
            reasoning['summary'] = "Stock is trading near fair value"

    if not reasoning.get('price_analysis'):
        reasoning['price_analysis'] = (
            f"Current price: ${current_price:.2f} - "
            f"Fair value: ${fair_value:.2f} - "
            f"Gap: {((current_price - fair_value) / fair_value * 100):.1f}%"
        )

    if not reasoning.get('technical_context'):
        reasoning['technical_context'] = (
            "Technical analysis shows mixed signals. "
            "Consider multiple timeframes and confirmation from other indicators."
        )

    if not reasoning.get('risk_factors'):
        vol_level = result.get('options_strategy', {}).get('volatility', {}).get('volatility_level', 'moderate')
        reasoning['risk_factors'] = (
            f"Market volatility is {vol_level}. "
            "Monitor position sizing and use appropriate stop losses."
        )

    return result

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    if not data:
        return jsonify({
            'success': False,
            'error': 'No data provided',
            'current_analysis': None
        }), 400

    # Validate required fields
    ticker = data.get('ticker')
    if not ticker:
        return jsonify({
            'success': False,
            'error': 'Ticker symbol is required',
            'current_analysis': None
        }), 400

    try:
        # Get and validate other fields
        end_date = data.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        datetime.strptime(end_date, '%Y-%m-%d')  # Validate date format
        
        num_of_news = int(data.get('num_of_news', 5))
        if num_of_news < 1 or num_of_news > 100:
            raise ValueError('Number of news articles must be between 1 and 100')

        # Calculate start_date as 3 months before end_date
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        start_date = (end_date_obj - timedelta(days=90)).strftime('%Y-%m-%d')
        
        # Initialize portfolio with default values
        portfolio = {
            "cash": 100000,  # Initial cash amount
            "stock": 0  # No initial stock position
        }

        # Get current analysis
        analysis_result = run_hedge_fund(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            portfolio=portfolio,
            num_of_news=num_of_news
        )

        if not analysis_result:
            return jsonify({
                'success': False,
                'error': 'Analysis returned no results',
                'current_analysis': None
            }), 500

        # Parse the string result into JSON
        try:
            if isinstance(analysis_result, str):
                analysis_result = json.loads(analysis_result)
        except json.JSONDecodeError as e:
            app.logger.error(f"Error parsing analysis result: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Invalid analysis result format',
                'current_analysis': None
            }), 500

        # Clean and process the analysis result
        try:
            cleaned_result = clean_analysis_result(analysis_result)
            if not cleaned_result:
                raise ValueError("Cleaning result returned None")
            
            # Process and enhance the result
            processed_result = process_analysis_result(cleaned_result)
            
        except Exception as e:
            app.logger.error(f"Error processing analysis result: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Error processing analysis results: {str(e)}',
                'current_analysis': None
            }), 500

        # Wrap the analysis result in the expected structure
        response = {
            'success': True,
            'current_analysis': {
                'analysis': processed_result
            },
            'error': None
        }

        app.logger.info(f"Analysis response: {json.dumps(response)}")
        return jsonify(response)
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'current_analysis': None
        }), 400
    except Exception as e:
        app.logger.error(f"Error in analysis: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'current_analysis': None
        }), 500

if __name__ == "__main__":
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 8080))
    
    # In production, listen on all interfaces
    host = '0.0.0.0' if os.environ.get('PRODUCTION') else 'localhost'
    
    # Debug mode only in development
    debug = not os.environ.get('PRODUCTION')
    
    app.run(host=host, port=port, debug=debug) 