
from flask import Flask, render_template_string
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

app = Flask(__name__)

# Your existing ForexTradingSignals class (simplified for web)
class ForexTradingSignals:
    def __init__(self, pair):
        self.pair = pair
        
    def fetch_data(self):
        try:
            ticker = yf.Ticker(self.pair)
            data = ticker.history(period='1d', interval='1h')
            return data.tail(5) if not data.empty else None
        except:
            return None

@app.route('/')
def dashboard():
    pairs = ["EURUSD=X", "GBPUSD=X", "USDJPY=X"]
    forex_data = {}
    
    for pair in pairs:
        monitor = ForexTradingSignals(pair)
        data = monitor.fetch_data()
        if data is not None:
            forex_data[pair] = {
                'current_price': data['Close'].iloc[-1],
                'change': data['Close'].iloc[-1] - data['Close'].iloc[-2],
                'high': data['High'].max(),
                'low': data['Low'].min()
            }
    
    template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Forex Trading Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { background: white; padding: 20px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .pair-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .pair-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .price { font-size: 24px; font-weight: bold; color: #333; }
            .positive { color: #4CAF50; }
            .negative { color: #f44336; }
            .pair-name { font-size: 18px; font-weight: bold; margin-bottom: 10px; }
            .webview-note { background: #e3f2fd; padding: 15px; border-radius: 8px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <h1>🚀 Forex Trading Dashboard</h1>
                <p>Real-time currency pair monitoring</p>
                <p><strong>Last updated:</strong> {{ current_time }}</p>
                
                <div class="webview-note">
                    <strong>📱 Web Preview URL:</strong> This app is accessible at your Replit webview URL. 
                    Look for the "Webview" tab in your console or find the URL format: 
                    <code>https://your-repl-name.your-username.repl.co</code>
                </div>
            </div>
            
            <div class="pair-grid">
                {% for pair, data in forex_data.items() %}
                <div class="pair-card">
                    <div class="pair-name">{{ pair.replace('=X', '') }}</div>
                    <div class="price">{{ "%.5f"|format(data.current_price) }}</div>
                    <div class="{{ 'positive' if data.change > 0 else 'negative' }}">
                        {{ "+" if data.change > 0 else "" }}{{ "%.5f"|format(data.change) }}
                    </div>
                    <div style="margin-top: 10px; font-size: 14px; color: #666;">
                        <div>High: {{ "%.5f"|format(data.high) }}</div>
                        <div>Low: {{ "%.5f"|format(data.low) }}</div>
                    </div>
                </div>
                {% endfor %}
            </div>
            
            <div class="card">
                <h3>📊 Monitor Status</h3>
                <p>Background forex monitor (main.py) can run separately for alerts.</p>
                <p>This web dashboard shows current market data.</p>
            </div>
        </div>
    </body>
    </html>
    '''
    
    return render_template_string(template, 
                                forex_data=forex_data, 
                                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
