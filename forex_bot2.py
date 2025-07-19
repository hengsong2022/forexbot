import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import time
import requests
from collections import defaultdict

# Telegram Configuration
TELEGRAM_TOKEN = "8069958504:AAFSBcJ7n0Ig2Vp9GFxhPttGJulQIj9FMnU"
TELEGRAM_CHAT_ID = "7627137646"

# Major Forex Pairs to Monitor
CURRENCY_PAIRS = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", 
    "AUDUSD=X", "USDCAD=X", "USDCHF=X",
    "GBPJPY=X", "EURJPY=X", "EURGBP=X"
]

# Store message IDs for deletion
last_status_message_id = None

def send_status_update(status_message):
    """Send or update the main status message"""
    global last_status_message_id
    
    # Delete previous status message if exists
    if last_status_message_id:
        try:
            delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
            requests.post(delete_url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "message_id": last_status_message_id
            }, timeout=5)
        except Exception:
            pass
    
    # Send new status message
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": status_message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, params=params, timeout=10).json()
        if response.get('ok'):
            last_status_message_id = response['result']['message_id']
    except Exception as e:
        print(f"Status update error: {e}")

class ForexTradingSignals:
    def __init__(self, pair):
        self.pair = pair
        self.hourly_data = pd.DataFrame()
        self.five_min_data = pd.DataFrame()
        self.current_price = 0.0
        self.price_change = 0.0
        self.price_change_percent = 0.0
        
        self.hourly_signals = {
            'current_trend': None,
            'trend_bars': 0,
            'trend_high': -np.inf,
            'trend_low': np.inf,
            'prev_trend': None,
            'prev_high': None,
            'prev_low': None,
            'swings': [],
            'current_sign': "no sign",
            'super_short_bar': False,
            'potential_reversal': False,
            'strong_reversal_signal': False
        }
        
        self.volatility_signals = {
            'volatility': "normal",
            'last_three_bars': [],
            'last_swing_break': None
        }
        
        self.pip_threshold = 0.0005 if "JPY" not in pair else 0.05
        self.swing_history = []
        self.last_update = None
    
    def fetch_data(self):
        try:
            ticker = yf.Ticker(self.pair)
            hourly = ticker.history(period='7d', interval='60m')
            if not hourly.empty:
                hourly = hourly[['Open', 'High', 'Low', 'Close']].dropna()
                hourly.index = hourly.index.tz_localize(None)
                self.hourly_data = hourly.sort_index()
                
                # Update current price and change
                if len(self.hourly_data) >= 2:
                    self.current_price = self.hourly_data['Close'].iloc[-1]
                    prev_price = self.hourly_data['Close'].iloc[-2]
                    self.price_change = self.current_price - prev_price
                    self.price_change_percent = (self.price_change / prev_price) * 100
            
            five_min = ticker.history(period='2d', interval='5m')
            if not five_min.empty:
                five_min = five_min[['Open', 'High', 'Low', 'Close']].dropna()
                five_min.index = five_min.index.tz_localize(None)
                self.five_min_data = five_min.sort_index()
            
            self.last_update = datetime.utcnow()
            return not self.hourly_data.empty and not self.five_min_data.empty
        except Exception as e:
            print(f"Data fetch error for {self.pair}: {e}")
            return False
    
    def get_status_emoji(self, signal):
        """Get appropriate emoji for signal status"""
        signal_lower = signal.lower()
        
        if "bullish" in signal_lower or "support" in signal_lower:
            return "🟢"
        elif "bearish" in signal_lower or "resistance" in signal_lower:
            return "🔴"
        elif "reversal" in signal_lower:
            return "🔄"
        elif "breakthrough" in signal_lower:
            return "💥"
        elif "volatility" in signal_lower:
            return "⚡"
        elif "stable" in signal_lower:
            return "🟡"
        else:
            return "⚪"
    
    def get_volatility_emoji(self, volatility):
        """Get appropriate emoji for volatility status"""
        vol_lower = volatility.lower()
        
        if "super high" in vol_lower:
            return "🚨"
        elif "high" in vol_lower:
            return "⚡"
        elif "execute" in vol_lower:
            return "🎯"
        elif "continuation" in vol_lower:
            return "📈" if "up" in vol_lower else "📉"
        else:
            return "🔵"
    
    def format_price_change(self):
        """Format price change with appropriate emoji"""
        if self.price_change > 0:
            return f"📈 +{self.price_change:.5f} ({self.price_change_percent:+.2f}%)"
        elif self.price_change < 0:
            return f"📉 {self.price_change:.5f} ({self.price_change_percent:+.2f}%)"
        else:
            return f"➖ {self.price_change:.5f} ({self.price_change_percent:+.2f}%)"
    
    def check_three_consecutive_bars(self):
        if len(self.hourly_data) >= 3:
            last_three = self.hourly_data.iloc[-3:]
            all_bullish = all(bar['Close'] > bar['Open'] for _, bar in last_three.iterrows())
            all_bearish = all(bar['Close'] < bar['Open'] for _, bar in last_three.iterrows())
            
            if all_bearish:
                self.hourly_signals['current_sign'] = "bearish"
            elif all_bullish:
                self.hourly_signals['current_sign'] = "bullish"
    
    def detect_hourly_trend(self, new_bar, prev_bar):
        is_bullish = new_bar['Close'] > new_bar['Open']
        is_bearish = new_bar['Close'] < new_bar['Open']
        
        if self.hourly_signals['current_trend'] is None:
            self.hourly_signals['current_trend'] = 'bullish' if is_bullish else 'bearish'
            self.hourly_signals['trend_bars'] = 1
            self.hourly_signals['trend_high'] = new_bar['High']
            self.hourly_signals['trend_low'] = new_bar['Low']
            return
        
        if (self.hourly_signals['current_trend'] == 'bullish' and is_bullish) or \
           (self.hourly_signals['current_trend'] == 'bearish' and is_bearish):
            self.hourly_signals['trend_bars'] += 1
            self.hourly_signals['trend_high'] = max(self.hourly_signals['trend_high'], new_bar['High'])
            self.hourly_signals['trend_low'] = min(self.hourly_signals['trend_low'], new_bar['Low'])
        else:
            current_range = abs(new_bar['Close'] - new_bar['Open'])
            prev_range = abs(prev_bar['Close'] - prev_bar['Open'])
            
            if current_range > 0.4 * prev_range:
                self.hourly_signals['prev_trend'] = self.hourly_signals['current_trend']
                self.hourly_signals['prev_high'] = self.hourly_signals['trend_high']
                self.hourly_signals['prev_low'] = self.hourly_signals['trend_low']
                
                self.hourly_signals['current_trend'] = 'bullish' if is_bullish else 'bearish'
                self.hourly_signals['trend_bars'] = 1
                self.hourly_signals['trend_high'] = new_bar['High']
                self.hourly_signals['trend_low'] = new_bar['Low']
    
    def check_super_short_bar(self, prev_bar, prev_prev_bar):
        prev_trend_bullish = (prev_prev_bar['Close'] > prev_prev_bar['Open'])
        prev_trend_bearish = (prev_prev_bar['Close'] < prev_prev_bar['Open'])
        
        if prev_trend_bullish or prev_trend_bearish:
            prev_prev_range = abs(prev_prev_bar['Close'] - prev_prev_bar['Open'])
            prev_range = abs(prev_bar['Close'] - prev_bar['Open'])
            
            if prev_range <= 0.3 * prev_prev_range:
                self.hourly_signals['super_short_bar'] = True
                self.hourly_signals['potential_reversal'] = True
                self.hourly_signals['current_sign'] = "potential reversal"
    
    def check_holding_confirmation(self, current_bar):
        if self.hourly_signals['potential_reversal']:
            if current_bar['Close'] > current_bar['Open']:
                self.hourly_signals['current_sign'] = "bullish reversal"
            else:
                self.hourly_signals['current_sign'] = "bearish reversal"
            self.hourly_signals['potential_reversal'] = False
    
    def check_strong_reversal(self, prev_bar, prev_prev_bar):
        if len(self.hourly_data) < 3:
            return
        
        trend_confirmed = (self.hourly_signals['trend_bars'] >= 2)
        
        if trend_confirmed:
            prev_prev_range = abs(prev_prev_bar['Close'] - prev_prev_bar['Open'])
            prev_range = abs(prev_bar['Close'] - prev_bar['Open'])
            
            is_reversal = ((self.hourly_signals['current_trend'] == 'bullish' and prev_bar['Close'] < prev_bar['Open']) or
                          (self.hourly_signals['current_trend'] == 'bearish' and prev_bar['Close'] > prev_bar['Open']))
            
            if is_reversal and prev_range > 0.8 * prev_prev_range:
                self.hourly_signals['strong_reversal_signal'] = True
                self.hourly_signals['current_sign'] = "strong reversal"
    
    def analyze_swings(self, new_bar):
        if self.hourly_signals['prev_trend'] is not None:
            high_diff = abs(self.hourly_signals['trend_high'] - self.hourly_signals['prev_high'])
            low_diff = abs(self.hourly_signals['trend_low'] - self.hourly_signals['prev_low'])
            
            swing = {
                'high': (self.hourly_signals['prev_high'] + self.hourly_signals['trend_high']) / 2,
                'low': (self.hourly_signals['prev_low'] + self.hourly_signals['trend_low']) / 2,
                'mean_price': (self.hourly_signals['prev_high'] + self.hourly_signals['prev_low'] + 
                              self.hourly_signals['trend_high'] + self.hourly_signals['trend_low']) / 4,
                'high_diff': high_diff,
                'low_diff': low_diff,
                'trend': self.hourly_signals['current_trend']
            }
            self.swing_history.append(swing)
            
            if len(self.swing_history) >= 2:
                last_two_swings = self.swing_history[-2:]
                if all(abs(s1['high'] - s2['high']) < self.pip_threshold and 
                       abs(s1['low'] - s2['low']) < self.pip_threshold 
                       for s1, s2 in zip(last_two_swings, last_two_swings[1:])):
                    self.hourly_signals['current_sign'] = "stable swing"
            
            price_diff = swing['high'] - swing['low']
            enhanced_diff = new_bar['High'] - swing['mean_price'] if new_bar['Close'] > new_bar['Open'] else swing['mean_price'] - new_bar['Low']
            
            if enhanced_diff > 0.4 * price_diff:
                if enhanced_diff > price_diff:
                    self.hourly_signals['current_sign'] = "bullish breakthrough"
                else:
                    self.hourly_signals['current_sign'] = "bearish breakthrough"
    
    def detect_support_resistance(self):
        if len(self.swing_history) >= 2:
            last_swing = self.swing_history[-1]
            prev_swing = self.swing_history[-2]
            
            if (prev_swing['high_diff'] > 2 * self.pip_threshold and 
                last_swing['low_diff'] < self.pip_threshold and
                abs(last_swing['high'] - prev_swing['high']) > 2 * self.pip_threshold and
                last_swing['trend'] == 'bullish'):
                self.hourly_signals['current_sign'] = "strong support"
            
            elif (prev_swing['low_diff'] > 2 * self.pip_threshold and 
                  last_swing['high_diff'] < self.pip_threshold and
                  abs(last_swing['low'] - prev_swing['low']) > 2 * self.pip_threshold and
                  last_swing['trend'] == 'bearish'):
                self.hourly_signals['current_sign'] = "strong resistance"
    
    def analyze_five_min(self):
        if len(self.five_min_data) < 3:
            return
        
        last_three = self.five_min_data.iloc[-3:]
        self.volatility_signals['last_three_bars'] = last_three
        
        ranges = [bar['High'] - bar['Low'] for _, bar in last_three.iterrows()]
        range_diff = max(ranges) - min(ranges)
        
        all_bullish = all(bar['Close'] > bar['Open'] for _, bar in last_three.iterrows())
        all_bearish = all(bar['Close'] < bar['Open'] for _, bar in last_three.iterrows())
        
        if (all_bullish or all_bearish) and range_diff < self.pip_threshold:
            self.volatility_signals['volatility'] = "high - execute now"
        
        current_bar = self.five_min_data.iloc[-1]
        current_range = current_bar['High'] - current_bar['Low']
        avg_range = np.mean([b['High'] - b['Low'] for _, b in self.five_min_data.iloc[-10:-1].iterrows()])
        
        if current_range > 3 * avg_range:
            self.volatility_signals['volatility'] = "super high"
        
        if len(self.five_min_data) > 10:
            recent_high = self.five_min_data['High'].rolling(5).max().iloc[-1]
            recent_low = self.five_min_data['Low'].rolling(5).min().iloc[-1]
            
            if current_bar['Close'] > recent_high or current_bar['Close'] < recent_low:
                self.volatility_signals['last_swing_break'] = "up" if current_bar['Close'] > recent_high else "down"
                if all_bullish and self.volatility_signals['last_swing_break'] == "up":
                    self.volatility_signals['volatility'] = "high - uptrend"
                elif all_bearish and self.volatility_signals['last_swing_break'] == "down":
                    self.volatility_signals['volatility'] = "high - downtrend"
    
    def analyze_hourly(self):
        if len(self.hourly_data) < 4:
            return
        
        current_bar = self.hourly_data.iloc[-1]
        prev_bar = self.hourly_data.iloc[-2]
        prev_prev_bar = self.hourly_data.iloc[-3]
        
        self.check_three_consecutive_bars()
        self.detect_hourly_trend(current_bar, prev_bar)
        self.check_super_short_bar(prev_bar, prev_prev_bar)
        self.check_holding_confirmation(current_bar)
        self.check_strong_reversal(prev_bar, prev_prev_bar)
        self.analyze_swings(current_bar)
        self.detect_support_resistance()
    
    def get_status_line(self):
        """Get formatted status line for this pair"""
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        pair_name = self.pair.replace('=X', '')
        
        # Get emojis for status
        h_emoji = self.get_status_emoji(self.hourly_signals['current_sign'])
        v_emoji = self.get_volatility_emoji(self.volatility_signals['volatility'])
        
        # Price change indicator
        price_emoji = "📈" if self.price_change > 0 else "📉" if self.price_change < 0 else "➖"
        
        return (f"`{timestamp}` - **{pair_name}**\n"
                f"{price_emoji} `{self.current_price:.5f}` ({self.price_change_percent:+.2f}%)\n"
                f"{h_emoji} 1H: `{self.hourly_signals['current_sign']}`\n"
                f"{v_emoji} 5M: `{self.volatility_signals['volatility']}`\n")

def run_all_pairs():
    """Monitor all currency pairs simultaneously"""
    print("Starting Multi-Currency Forex Monitor...")
    monitors = {pair: ForexTradingSignals(pair) for pair in CURRENCY_PAIRS}
    
    # Send initial status
    send_status_update("🤖 **Forex Monitor Started**\n⏰ Initializing all currency pairs...")
    
    while True:
        now = datetime.utcnow()
        
        # Update data every 5 minutes or on startup
        if now.minute % 5 == 0 or any(monitor.hourly_data.empty for monitor in monitors.values()):
            updated_pairs = []
            
            for pair, monitor in monitors.items():
                if monitor.fetch_data():
                    monitor.analyze_hourly()
                    monitor.analyze_five_min()
                    updated_pairs.append(pair)
            
            # Send consolidated status update
            if updated_pairs:
                status_lines = []
                status_lines.append(f"📊 **Forex Status Update**")
                status_lines.append(f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                status_lines.append("")
                
                # Only include pairs with active signals (not "no sign")
                active_pairs = []
                for pair in CURRENCY_PAIRS:
                    if (pair in updated_pairs and 
                        monitors[pair].hourly_signals['current_sign'] != "no sign"):
                        active_pairs.append(pair)
                        status_lines.append(monitors[pair].get_status_line())
                
                # Only send update if there are active signals
                if active_pairs:
                    status_message = "\n".join(status_lines)
                    send_status_update(status_message)
                else:
                    # Send a brief "no active signals" message
                    send_status_update(f"📊 **Forex Status Update**\n⏰ {now.strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n🔵 No active signals detected")
        
        # Print console status
        active_signals = sum(1 for m in monitors.values() if m.hourly_signals['current_sign'] != "no sign")
        print(f"\r{now.strftime('%H:%M:%S')} - Active signals: {active_signals}/{len(monitors)}", end='')
        
        time.sleep(60 - now.second)

if __name__ == "__main__":
    run_all_pairs()  # Monitor all pairs
    # OR for single pair: ForexTradingSignals("EURUSD=X").run()