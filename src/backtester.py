from datetime import datetime, timedelta
import json
import time
import logging
import matplotlib.pyplot as plt
import pandas as pd
import os
import sys
import matplotlib
import pandas_market_calendars as mcal
import warnings

from main import run_hedge_fund
from tools.api import get_price_data

# Configure Chinese font based on OS
if sys.platform.startswith('win'):
    matplotlib.rc('font', family='Microsoft YaHei')
elif sys.platform.startswith('linux'):
    matplotlib.rc('font', family='WenQuanYi Micro Hei')
else:
    matplotlib.rc('font', family='PingFang SC')

# Enable minus sign display
matplotlib.rcParams['axes.unicode_minus'] = False

# Disable matplotlib warnings
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
warnings.filterwarnings('ignore', category=UserWarning,
                        module='pandas.plotting')
# 禁用所有与plotting相关的警告
logging.getLogger('matplotlib').setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.ERROR)


class Backtester:
    def __init__(self, agent, ticker, start_date, end_date, initial_capital, num_of_news=5):
        self.agent = agent
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.portfolio = {
            "cash": initial_capital,
            "stock": 0,
            "options": []  # List to track options positions
        }
        self.portfolio_values = []
        self.options_trades = []  # Track options trades
        self.num_of_news = num_of_news

        # Setup logging
        self.setup_backtest_logging()
        self.logger = self.setup_logging()

        # Initialize API call management
        self._api_call_count = 0
        self._api_window_start = time.time()
        self._last_api_call = 0

        # Initialize market calendar
        self.nyse = mcal.get_calendar('NYSE')

        # Validate inputs
        self.validate_inputs()

    def setup_logging(self):
        """Setup logging system"""
        logger = logging.getLogger('backtester')
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def validate_inputs(self):
        """Validate input parameters"""
        try:
            start = datetime.strptime(self.start_date, "%Y-%m-%d")
            end = datetime.strptime(self.end_date, "%Y-%m-%d")
            if start >= end:
                raise ValueError("Start date must be earlier than end date")
            if self.initial_capital <= 0:
                raise ValueError("Initial capital must be greater than 0")
            if not isinstance(self.ticker, str) or len(self.ticker) == 0:
                raise ValueError("Invalid stock code format")
            # 支持美股代码（如AAPL）和A股代码（如600519）
            if not (self.ticker.isalpha() or (len(self.ticker) == 6 and self.ticker.isdigit())):
                self.backtest_logger.warning(
                    f"Stock code {self.ticker} might be in an unusual format")
            self.backtest_logger.info("Input parameters validated")
        except Exception as e:
            self.backtest_logger.error(
                f"Input parameter validation failed: {str(e)}")
            raise

    def setup_backtest_logging(self):
        """Setup backtest logging"""
        log_dir = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)

        self.backtest_logger = logging.getLogger('backtest')
        self.backtest_logger.setLevel(logging.INFO)

        if self.backtest_logger.handlers:
            self.backtest_logger.handlers.clear()

        current_date = datetime.now().strftime('%Y%m%d')
        backtest_period = f"{self.start_date.replace('-', '')}_{self.end_date.replace('-', '')}"
        log_file = os.path.join(
            log_dir, f"backtest_{self.ticker}_{current_date}_{backtest_period}.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(formatter)
        self.backtest_logger.addHandler(file_handler)

        self.backtest_logger.info(
            f"Backtest Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.backtest_logger.info(f"Stock Code: {self.ticker}")
        self.backtest_logger.info(
            f"Backtest Period: {self.start_date} to {self.end_date}")
        self.backtest_logger.info(
            f"Initial Capital: {self.initial_capital:,.2f}\n")
        self.backtest_logger.info("-" * 100)

    def is_market_open(self, date_str):
        """Check if the market is open on a given date"""
        schedule = self.nyse.schedule(start_date=date_str, end_date=date_str)
        return not schedule.empty

    def get_previous_trading_day(self, date_str):
        """Get the previous trading day for a given date"""
        date = pd.Timestamp(date_str)
        schedule = self.nyse.schedule(
            start_date=date - pd.Timedelta(days=10),
            end_date=date
        )
        if schedule.empty:
            return None
        return schedule.index[-2].strftime('%Y-%m-%d')

    def get_agent_decision(self, current_date, lookback_start, portfolio, num_of_news):
        """Get agent decision with API rate limiting"""
        max_retries = 3
        current_time = time.time()

        if current_time - self._api_window_start >= 60:
            self._api_call_count = 0
            self._api_window_start = current_time

        if self._api_call_count >= 8:
            wait_time = 60 - (current_time - self._api_window_start)
            if wait_time > 0:
                self.backtest_logger.info(
                    f"API limit reached, waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                self._api_call_count = 0
                self._api_window_start = time.time()

        for attempt in range(max_retries):
            try:
                if self._last_api_call:
                    time_since_last_call = time.time() - self._last_api_call
                    if time_since_last_call < 6:
                        time.sleep(6 - time_since_last_call)

                self._last_api_call = time.time()
                self._api_call_count += 1

                result = self.agent(
                    ticker=self.ticker,
                    start_date=lookback_start,
                    end_date=current_date,
                    portfolio=portfolio,
                    num_of_news=num_of_news
                )

                try:
                    if isinstance(result, str):
                        result = result.replace(
                            '```json\n', '').replace('\n```', '').strip()
                        parsed_result = json.loads(result)

                        formatted_result = {
                            "decision": parsed_result,
                            "analyst_signals": {}
                        }

                        if "agent_signals" in parsed_result:
                            formatted_result["analyst_signals"] = {
                                signal["agent"]: {
                                    "signal": signal.get("signal", "unknown"),
                                    "confidence": signal.get("confidence", 0)
                                }
                                for signal in parsed_result["agent_signals"]
                            }

                        return formatted_result
                    return result
                except json.JSONDecodeError as e:
                    self.backtest_logger.warning(
                        f"JSON parsing error: {str(e)}")
                    self.backtest_logger.warning(f"Raw result: {result}")
                    return {"decision": {"action": "hold", "quantity": 0}, "analyst_signals": {}}

            except Exception as e:
                if "AFC is enabled" in str(e):
                    self.backtest_logger.warning(
                        f"AFC limit triggered, waiting 60 seconds...")
                    time.sleep(60)
                    self._api_call_count = 0
                    self._api_window_start = time.time()
                    continue

                self.backtest_logger.warning(
                    f"Failed to get agent decision (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    return {"decision": {"action": "hold", "quantity": 0}, "analyst_signals": {}}
                time.sleep(2 ** attempt)

    def execute_trade(self, action, quantity, current_price):
        """Execute trade with portfolio constraints"""
        if action == "buy" and quantity > 0:
            cost = quantity * current_price
            if cost <= self.portfolio["cash"]:
                self.portfolio["stock"] += quantity
                self.portfolio["cash"] -= cost
                return quantity
            else:
                max_quantity = int(self.portfolio["cash"] // current_price)
                if max_quantity > 0:
                    self.portfolio["stock"] += max_quantity
                    self.portfolio["cash"] -= max_quantity * current_price
                    return max_quantity
                return 0
        elif action == "sell" and quantity > 0:
            quantity = min(quantity, self.portfolio["stock"])
            if quantity > 0:
                self.portfolio["cash"] += quantity * current_price
                self.portfolio["stock"] -= quantity
                return quantity
            return 0
        return 0

    def calculate_options_value(self, current_price, current_date):
        """Calculate the value of options positions"""
        total_value = 0
        expired_positions = []
        
        for position in self.portfolio["options"]:
            # Check if option has expired
            expiry_date = datetime.strptime(position["expiry_date"], "%Y-%m-%d")
            if datetime.strptime(current_date, "%Y-%m-%d") >= expiry_date:
                # Calculate expiration value
                if position["type"] == "call":
                    value = max(0, current_price - position["strike"]) * 100 * position["contracts"]
                else:  # put
                    value = max(0, position["strike"] - current_price) * 100 * position["contracts"]
                total_value += value
                expired_positions.append(position)
                self.portfolio["cash"] += value
            else:
                # Estimate current value using intrinsic value (simplified)
                if position["type"] == "call":
                    value = max(0, current_price - position["strike"]) * 100 * position["contracts"]
                else:  # put
                    value = max(0, position["strike"] - current_price) * 100 * position["contracts"]
                total_value += value
        
        # Remove expired positions
        for position in expired_positions:
            self.portfolio["options"].remove(position)
        
        return total_value

    def execute_options_trade(self, strategy, current_price, current_date):
        """Execute options trade based on strategy recommendation"""
        if not strategy or not isinstance(strategy, dict):
            return 0
            
        try:
            implementation = strategy.get("implementation", {})
            if not implementation:
                return 0
                
            cost = 0
            trade_details = {
                "date": current_date,
                "strategy": strategy["strategy"],
                "price": current_price
            }
            
            if "buy_leg" in implementation and "sell_leg" in implementation:
                # Spread strategy
                buy_premium = implementation["premium"]["target_premium"]
                contracts = min(5, int(self.portfolio["cash"] / (buy_premium * 100)))  # Max 5 contracts
                if contracts > 0:
                    expiry_days = int(implementation["buy_leg"]["recommended_expiration"].split()[0].split("-")[0])
                    expiry_date = (datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=expiry_days)).strftime("%Y-%m-%d")
                    
                    # Add buy leg
                    self.portfolio["options"].append({
                        "type": implementation["buy_leg"]["type"],
                        "strike": implementation["buy_leg"]["recommended_strike"],
                        "contracts": contracts,
                        "premium_paid": buy_premium * 100 * contracts,
                        "expiry_date": expiry_date
                    })
                    
                    # Add sell leg
                    self.portfolio["options"].append({
                        "type": implementation["sell_leg"]["type"],
                        "strike": implementation["sell_leg"]["recommended_strike"],
                        "contracts": -contracts,  # Negative for short position
                        "premium_received": implementation["premium"]["target_premium"] * 100 * contracts,
                        "expiry_date": expiry_date
                    })
                    
                    cost = (buy_premium - implementation["premium"]["target_premium"]) * 100 * contracts
                    self.portfolio["cash"] -= cost
                    
                    trade_details.update({
                        "type": "spread",
                        "contracts": contracts,
                        "net_cost": cost,
                        "expiry_date": expiry_date
                    })
                    
            elif "strikes" in implementation:
                # Single leg strategy
                premium = implementation["premium"]["target_premium"]
                contracts = min(5, int(self.portfolio["cash"] / (premium * 100)))  # Max 5 contracts
                if contracts > 0:
                    expiry_days = int(implementation["recommended_expiration"].split()[0].split("-")[0])
                    expiry_date = (datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=expiry_days)).strftime("%Y-%m-%d")
                    
                    position_type = "call" if "call" in strategy["strategy"].lower() else "put"
                    self.portfolio["options"].append({
                        "type": position_type,
                        "strike": implementation["recommended_strike"],
                        "contracts": contracts,
                        "premium_paid": premium * 100 * contracts,
                        "expiry_date": expiry_date
                    })
                    
                    cost = premium * 100 * contracts
                    self.portfolio["cash"] -= cost
                    
                    trade_details.update({
                        "type": "single",
                        "contracts": contracts,
                        "cost": cost,
                        "expiry_date": expiry_date
                    })
            
            if cost > 0:
                self.options_trades.append(trade_details)
            return cost
            
        except Exception as e:
            self.backtest_logger.error(f"Error executing options trade: {str(e)}")
            return 0

    def run_backtest(self):
        """Run backtest simulation"""
        # Get valid trading days from market calendar
        schedule = self.nyse.schedule(start_date=self.start_date, end_date=self.end_date)
        dates = pd.DatetimeIndex([dt.strftime('%Y-%m-%d') for dt in schedule.index])

        self.backtest_logger.info("\nStarting backtest...")
        print(f"{'Date':<12} {'Code':<6} {'Action':<6} {'Qty':>8} {'Price':>8} {'Options':>12} {'Cash':>12} {'Total':>12} {'Return':>8}")
        print("-" * 110)

        for current_date in dates:
            current_date_str = current_date.strftime("%Y-%m-%d")

            # Check if market is open
            if not self.is_market_open(current_date_str):
                continue

            # Get previous trading day
            decision_date = self.get_previous_trading_day(current_date_str)
            if decision_date is None:
                continue

            # Use 365-day lookback window
            lookback_start = (pd.Timestamp(current_date_str) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")

            try:
                df = get_price_data(self.ticker, current_date_str, current_date_str)
                if df is None or df.empty:
                    continue

                current_price = df.iloc[0]['open']
            except Exception as e:
                self.backtest_logger.error(f"Error getting price data: {str(e)}")
                continue

            # Get agent decision
            output = self.get_agent_decision(decision_date, lookback_start, self.portfolio, self.num_of_news)
            
            # Execute stock trades
            agent_decision = output.get("decision", {"action": "hold", "quantity": 0})
            action, quantity = agent_decision.get("action", "hold"), agent_decision.get("quantity", 0)
            executed_quantity = self.execute_trade(action, quantity, current_price)
            
            # Execute options trades if recommended
            options_strategy = agent_decision.get("options_strategy")
            if isinstance(options_strategy, dict) and options_strategy.get("strategy") != "No strategy recommended":
                options_cost = self.execute_options_trade(options_strategy, current_price, current_date_str)
            else:
                options_cost = 0
            
            # Calculate portfolio value including options
            options_value = self.calculate_options_value(current_price, current_date_str)
            stock_value = self.portfolio["stock"] * current_price
            total_value = self.portfolio["cash"] + stock_value + options_value
            
            # Record portfolio value
            self.portfolio_values.append({
                "Date": current_date_str,
                "Portfolio Value": total_value,
                "Stock Value": stock_value,
                "Options Value": options_value,
                "Cash": self.portfolio["cash"],
                "Daily Return": (total_value / self.portfolio_values[-1]["Portfolio Value"] - 1) * 100 if self.portfolio_values else 0
            })

            # Print trade record
            print(
                f"{current_date_str:<12} {self.ticker:<6} {action:<6} {executed_quantity:>8} "
                f"{current_price:>8.2f} {options_value:>12.2f} {self.portfolio['cash']:>12.2f} "
                f"{total_value:>12.2f} {self.portfolio_values[-1]['Daily Return']:>8.2f}%"
            )

        # Analyze backtest results
        self.analyze_performance()

    def analyze_performance(self):
        """Analyze backtest performance"""
        if not self.portfolio_values:
            return

        try:
            performance_df = pd.DataFrame(self.portfolio_values)
            performance_df['Date'] = pd.to_datetime(performance_df['Date'])
            performance_df = performance_df.set_index('Date')

            # Calculate returns
            performance_df["Cumulative Return"] = (performance_df["Portfolio Value"] / self.initial_capital - 1) * 100
            performance_df["Stock Return"] = (performance_df["Stock Value"] / self.initial_capital) * 100
            performance_df["Options Return"] = (performance_df["Options Value"] / self.initial_capital) * 100

            # Create visualization
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 15))
            fig.suptitle("Backtest Analysis", fontsize=12)

            # Plot portfolio value
            ax1.plot(performance_df.index, performance_df["Portfolio Value"], label="Total Value", color='blue')
            ax1.plot(performance_df.index, performance_df["Stock Value"], label="Stock Value", color='green')
            ax1.plot(performance_df.index, performance_df["Options Value"], label="Options Value", color='red')
            ax1.set_ylabel("Value ($)")
            ax1.set_title("Portfolio Components")
            ax1.legend()

            # Plot cumulative returns
            ax2.plot(performance_df.index, performance_df["Cumulative Return"], label="Total Return", color='blue')
            ax2.plot(performance_df.index, performance_df["Stock Return"], label="Stock Return", color='green')
            ax2.plot(performance_df.index, performance_df["Options Return"], label="Options Return", color='red')
            ax2.set_ylabel("Return (%)")
            ax2.set_title("Component Returns")
            ax2.legend()

            # Plot options trades
            if self.options_trades:
                trade_dates = [trade["date"] for trade in self.options_trades]
                trade_costs = [trade.get("net_cost", trade.get("cost", 0)) for trade in self.options_trades]
                ax3.bar(trade_dates, trade_costs, color='purple')
                ax3.set_ylabel("Trade Cost ($)")
                ax3.set_title("Options Trades")
                plt.xticks(rotation=45)

            plt.tight_layout()
            plt.savefig("backtest_results.png", bbox_inches='tight', dpi=300)
            plt.close()

            # Print summary
            self.backtest_logger.info("\nBacktest Summary")
            self.backtest_logger.info("=" * 50)
            self.backtest_logger.info(f"Initial Capital: ${self.initial_capital:,.2f}")
            self.backtest_logger.info(f"Final Portfolio Value: ${performance_df['Portfolio Value'].iloc[-1]:,.2f}")
            self.backtest_logger.info(f"Final Stock Value: ${performance_df['Stock Value'].iloc[-1]:,.2f}")
            self.backtest_logger.info(f"Final Options Value: ${performance_df['Options Value'].iloc[-1]:,.2f}")
            self.backtest_logger.info(f"Total Return: {performance_df['Cumulative Return'].iloc[-1]:.2f}%")
            
            # Options trading summary
            if self.options_trades:
                self.backtest_logger.info("\nOptions Trading Summary")
                self.backtest_logger.info("-" * 50)
                for trade in self.options_trades:
                    self.backtest_logger.info(f"Date: {trade['date']}")
                    self.backtest_logger.info(f"Strategy: {trade['strategy']}")
                    self.backtest_logger.info(f"Contracts: {trade['contracts']}")
                    self.backtest_logger.info(f"Cost: ${trade.get('net_cost', trade.get('cost', 0)):,.2f}")
                    self.backtest_logger.info("-" * 25)

            return performance_df
        except Exception as e:
            self.backtest_logger.error(f"Error in performance analysis: {str(e)}")
            return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run backtest simulation')
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock code (e.g., 600519)')
    parser.add_argument('--end-date', type=str,
                        default=datetime.now().strftime('%Y-%m-%d'),
                        help='End date (YYYY-MM-DD)')
    parser.add_argument('--start-date', type=str,
                        default=(datetime.now() - timedelta(days=90)
                                 ).strftime('%Y-%m-%d'),
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--initial-capital', type=float,
                        default=100000,
                        help='Initial capital (default: 100000)')
    parser.add_argument('--num-of-news', type=int,
                        default=5,
                        help='Number of news articles to analyze (default: 5)')

    args = parser.parse_args()

    backtester = Backtester(
        agent=run_hedge_fund,
        ticker=args.ticker,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.initial_capital,
        num_of_news=args.num_of_news
    )

    backtester.run_backtest()
    
