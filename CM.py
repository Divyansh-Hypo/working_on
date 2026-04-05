import asyncio
import threading
import time
import ccxt.pro as ccxtpro
import pandas as pd
import numpy as np
from datetime import datetime
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
from scipy.stats import skew

# --- DASHBOARD IMPORTS ---
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go

# ==========================================
# 1. SHARED MEMORY STATE (The Brain)
# ==========================================
class MarketState:
    def __init__(self):
        # 1. UPDATED SYMBOL FOR PERPETUAL FUTURES
        self.symbol = 'BTC/USDT:USDT'
        self.current_price = 0.0
        self.order_book = {'bids': [], 'asks': []}
        self.recent_trades = []
        self.hvn_data = pd.DataFrame()
        self.heatmap_data = pd.DataFrame()
        self.alerts = []  # Spoofing & Iceberg Alerts
        self.tracked_walls = {} # For spoofing detection

state = MarketState()

# ==========================================
# 2. MATH & ANALYSIS ENGINE
# ==========================================
def process_hvn_and_magnets():
    """Runs periodically to calculate HVNs and Wall clusters based on live data"""
    if not state.order_book['bids'] or not state.order_book['asks']:
        return

    # 1. Process Order Book into Heatmap
    bin_size = 50
    bids_df = pd.DataFrame(state.order_book['bids'], columns=['price', 'size'])
    asks_df = pd.DataFrame(state.order_book['asks'], columns=['price', 'size'])

    if bids_df.empty or asks_df.empty: return

    bids_df['price_bin'] = (bids_df['price'] / bin_size).round() * bin_size
    asks_df['price_bin'] = (asks_df['price'] / bin_size).round() * bin_size

    bids_grouped = bids_df.groupby('price_bin')['size'].sum().reset_index()
    bids_grouped['type'] = 'BID_WALL'
    
    asks_grouped = asks_df.groupby('price_bin')['size'].sum().reset_index()
    asks_grouped['type'] = 'ASK_WALL'

    heatmap_df = pd.concat([bids_grouped, asks_grouped], ignore_index=True)
    
    # Filter for institutional sizes (e.g., > 20 BTC)
    state.heatmap_data = heatmap_df[heatmap_df['size'] >= 20].sort_values(by='price_bin')

# ==========================================
# 3. ANTI-SPOOFING & ICEBERG ENGINE
# ==========================================
def analyze_order_flow():
    """Cross-references live order book changes with live trades"""
    if state.heatmap_data.empty or not state.recent_trades:
        return

    current_walls = {row['price_bin']: row['size'] for _, row in state.heatmap_data.iterrows()}
    
    # Check for Spoofing (Wall disappeared, but price didn't reach it and no trades executed)
    for price, old_size in state.tracked_walls.items():
        if price not in current_walls or current_walls[price] < (old_size * 0.2): # 80% drop
            # Did trades happen here?
            trades_at_price = sum(t['amount'] for t in state.recent_trades if abs(t['price'] - price) < 10)
            if trades_at_price < (old_size * 0.1): # Barely any trades hit it
                distance = abs(state.current_price - price)
                if distance > 50: # Price wasn't even close
                    alert_msg = f"🚨 SPOOF DETECTED: {old_size:.1f} BTC pulled at ${price}"
                    if alert_msg not in state.alerts:
                        state.alerts.insert(0, alert_msg)

    # Check for Icebergs (Massive trades hitting a level, but wall size doesn't drop)
    trade_df = pd.DataFrame(state.recent_trades)
    if not trade_df.empty:
        trade_df['price_bin'] = (trade_df['price'] / 50).round() * 50
        vol_by_price = trade_df.groupby('price_bin')['amount'].sum()

        for price, vol in vol_by_price.items():
            if vol > 30 and price in current_walls:
                wall_size = current_walls[price]
                if wall_size > 20: # Wall is still massive despite heavy trading
                    alert_msg = f"🧊 HIDDEN ICEBERG: {vol:.1f} BTC absorbed at ${price}"
                    if alert_msg not in state.alerts:
                        state.alerts.insert(0, alert_msg)

    # Keep alerts list clean
    state.alerts = state.alerts[:10]
    state.tracked_walls = current_walls

# ==========================================
# 4. ASYNCIO WEBSOCKET ENGINE
# ==========================================
async def watch_market_data():
    # 2. STRICTLY ENFORCE 'SWAP' (Perpetuals) IN CCXT OPTIONS
    exchange = ccxtpro.bybit({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
        }
    })
    
    symbol = state.symbol

    print("🟢 [ASYNC CORE] Connecting to Bybit Linear WebSockets...")

    async def fetch_order_book():
        while True:
            try:
                # 3. FORCE CATEGORY='LINEAR' IN PARAMS
                orderbook = await exchange.watch_order_book(symbol, limit=50, params={'category': 'linear'})
                state.order_book['bids'] = orderbook['bids']
                state.order_book['asks'] = orderbook['asks']
                process_hvn_and_magnets()
            except Exception as e:
                print(f"OB Error: {e}")
                await asyncio.sleep(1)

    async def fetch_trades():
        while True:
            try:
                # 3. FORCE CATEGORY='LINEAR' IN PARAMS
                trades = await exchange.watch_trades(symbol, params={'category': 'linear'})
                state.current_price = trades[-1]['price']
                
                # Keep last 1000 trades for Iceberg detection
                state.recent_trades.extend(trades)
                state.recent_trades = state.recent_trades[-1000:]
                
                analyze_order_flow()
            except Exception as e:
                print(f"Trade Error: {e}")
                await asyncio.sleep(1)

    await asyncio.gather(fetch_order_book(), fetch_trades())
    await exchange.close()

def start_async_loop():
    """Runs the asyncio loop in a background thread so Dash can run in the main thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(watch_market_data())

# ==========================================
# 5. REAL-TIME VISUAL DASHBOARD
# ==========================================
app = dash.Dash(__name__, title="Institutional Radar")

app.layout = html.Div(style={'backgroundColor': '#0a0a0a', 'color': '#00ffcc', 'fontFamily': 'Consolas, monospace', 'padding': '20px'}, children=[
    html.H1("☢️ INSTITUTIONAL RADAR (BEAST MODE) ☢️", style={'textAlign': 'center', 'textShadow': '0px 0px 10px #00ffcc'}),
    
    html.Div(id='live-price', style={'fontSize': '40px', 'textAlign': 'center', 'margin': '20px', 'color': '#ffffff'}),
    
    html.Div([
        html.Div([
            html.H3("🔥 Live Order Book Heatmap"),
            dcc.Graph(id='heatmap-graph')
        ], style={'width': '65%', 'display': 'inline-block', 'verticalAlign': 'top'}),
        
        html.Div([
            html.H3("🚨 Anti-Spoofing & Iceberg Alerts"),
            html.Div(id='alerts-box', style={
                'border': '1px solid #ff003c', 'padding': '15px', 'height': '400px', 
                'overflowY': 'auto', 'backgroundColor': '#1a0005', 'color': '#ff003c',
                'boxShadow': '0px 0px 15px #ff003c'
            })
        ], style={'width': '30%', 'display': 'inline-block', 'marginLeft': '2%', 'verticalAlign': 'top'})
    ]),

    dcc.Interval(id='interval-component', interval=1000, n_intervals=0) # Update every 1 second
])

@app.callback(
    [Output('live-price', 'children'),
     Output('heatmap-graph', 'figure'),
     Output('alerts-box', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_dashboard(n):
    # 1. Update Price
    price_text = f"Live Price: ${state.current_price:,.2f}"

    # 2. Update Heatmap
    fig = go.Figure()
    if not state.heatmap_data.empty:
        bids = state.heatmap_data[state.heatmap_data['type'] == 'BID_WALL']
        asks = state.heatmap_data[state.heatmap_data['type'] == 'ASK_WALL']

        fig.add_trace(go.Bar(
            x=bids['size'], y=bids['price_bin'], orientation='h',
            name='Bids (Support)', marker=dict(color='rgba(0, 255, 128, 0.7)')
        ))
        fig.add_trace(go.Bar(
            x=asks['size'], y=asks['price_bin'], orientation='h',
            name='Asks (Resistance)', marker=dict(color='rgba(255, 0, 60, 0.7)')
        ))

        # Add current price line
        fig.add_hline(y=state.current_price, line_dash="dash", line_color="#ffffff", annotation_text="Current Price")

    fig.update_layout(
        plot_bgcolor='#0a0a0a', paper_bgcolor='#0a0a0a', font=dict(color='#00ffcc'),
        barmode='overlay', xaxis_title='Volume (BTC)', yaxis_title='Price (USDT)',
        yaxis=dict(range=[state.current_price - 2000, state.current_price + 2000]), # Auto-zoom around price
        margin=dict(l=20, r=20, t=20, b=20)
    )

    # 3. Update Alerts
    alerts_html = [html.P(alert, style={'margin': '5px 0', 'fontWeight': 'bold'}) for alert in state.alerts]
    if not alerts_html:
        alerts_html = [html.P("Scanning for anomalies...", style={'color': '#555555'})]

    return price_text, fig, alerts_html

# ==========================================
# 6. IGNITION SEQUENCE
# ==========================================
if __name__ == '__main__':
    # Start the Asyncio WebSocket engine in a background thread
    print("🚀 Starting Async Background Engine...")
    bg_thread = threading.Thread(target=start_async_loop, daemon=True)
    bg_thread.start()

    # Wait a moment for WebSockets to connect and fetch initial data
    time.sleep(3)

    # Start the Dash Web Server in the main thread
    print("🌐 Starting Web Dashboard... Open http://127.0.0.1:8050 in your browser.")
    app.run(debug=False, use_reloader=False)
