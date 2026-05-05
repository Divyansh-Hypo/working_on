import asyncio
import json
import time
import threading
import websockets
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go

# ==========================================
# 1. DATA PROCESSING (BACKGROUND)
# ==========================================
class PainMap:
    def __init__(self, bin_size: float = 50.0, window_minutes: int = 120):
        self.bin_size = bin_size
        self.window_minutes = window_minutes
        self.current_price = None
        self.history = {}
        self.lock = threading.Lock()

    def add_trade(self, timestamp_ms: int, price: float, volume: float, is_buy: bool):
        minute_ts = timestamp_ms // 60000
        bin_price = int(price / self.bin_size) * self.bin_size

        with self.lock:
            self.current_price = price
            key = (minute_ts, bin_price)
            
            if key not in self.history:
                self.history[key] = {'buy': 0.0, 'sell': 0.0}

            if is_buy:
                self.history[key]['buy'] += volume
            else:
                self.history[key]['sell'] += volume

    def prune_old_data(self, current_ts_ms: int):
        current_minute = current_ts_ms // 60000
        cutoff_minute = current_minute - self.window_minutes

        with self.lock:
            keys_to_delete = [k for k in self.history.keys() if k[0] < cutoff_minute]
            for k in keys_to_delete:
                del self.history[k]

    def get_trapped_delta(self):
        trapped_longs = {}   
        trapped_shorts = {}  

        with self.lock:
            if self.current_price is None:
                return {}, {}, None

            for (minute_ts, bin_price), vols in self.history.items():
                if bin_price > self.current_price:
                    trapped_longs[bin_price] = trapped_longs.get(bin_price, 0.0) + vols['buy']
                elif bin_price < self.current_price:
                    trapped_shorts[bin_price] = trapped_shorts.get(bin_price, 0.0) + vols['sell']

            return trapped_longs, trapped_shorts, self.current_price


async def binance_ws_loop(pain_map: PainMap):
    # FIXED: Switched to Binance Spot to bypass Regional Futures Geo-Blocking
    uri = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
    trades_received = 0
    
    while True:
        try:
            print("⏳ Connecting to Binance WebSocket (Spot)...")
            # Added ping timeout settings to prevent silent hangs
            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
                print("✅ Connected! Streaming live trades...")
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    price = float(data['p'])
                    qty = float(data['q'])
                    is_buy = not data['m']  
                    ts = int(data['T'])

                    pain_map.add_trade(ts, price, qty, is_buy)
                    
                    # Debugging: Print the first 5 trades to the terminal to verify data flow
                    if trades_received < 5:
                        side = "BUY" if is_buy else "SELL"
                        print(f"[{trades_received+1}/5] Received {side} trade at ${price}")
                        trades_received += 1
                    
        except Exception as e:
            print(f"❌ WebSocket error: {e}. Reconnecting in 3s...")
            await asyncio.sleep(3)

def start_background_loop(pain_map: PainMap):
    # FIXED: Modern, safer way to run asyncio in a separate thread on Windows
    asyncio.run(binance_ws_loop(pain_map))


# Initialize Data Structure
pain_map = PainMap(bin_size=50.0, window_minutes=120)

# Start WebSocket in a background thread
t = threading.Thread(target=start_background_loop, args=(pain_map,), daemon=True)
t.start()


# ==========================================
# 2. WEB BROWSER VISUALIZATION (DASH)
# ==========================================
app = dash.Dash(__name__)

app.layout = html.Div(style={'backgroundColor': '#111111', 'color': 'white', 'fontFamily': 'Arial'}, children=[
    html.H1("BTCUSDT Real-Time Pain Map", style={'textAlign': 'center', 'paddingTop': '20px'}),
    
    dcc.Graph(id='live-update-graph', style={'height': '80vh'}),
    
    dcc.Interval(
        id='interval-component',
        interval=1000, 
        n_intervals=0
    )
])

@app.callback(Output('live-update-graph', 'figure'),
              Input('interval-component', 'n_intervals'))
def update_graph_live(n):
    current_time_ms = int(time.time() * 1000)
    pain_map.prune_old_data(current_time_ms)

    trapped_longs, trapped_shorts, current_price = pain_map.get_trapped_delta()

    if current_price is None:
        return go.Figure(layout=go.Layout(
            title="Waiting for live trades from Binance...",
            template="plotly_dark",
            plot_bgcolor='#111111',
            paper_bgcolor='#111111'
        ))

    long_bins = list(trapped_longs.keys())
    long_vols = list(trapped_longs.values())

    short_bins = list(trapped_shorts.keys())
    short_vols = [-v for v in trapped_shorts.values()]

    trace_longs = go.Bar(
        y=long_bins,
        x=long_vols,
        orientation='h',
        name='Trapped Longs',
        marker=dict(color='#00ff00'),
        hoverinfo='x+y+name',
        customdata=long_vols,
        hovertemplate="Price: %{y}<br>Volume: %{customdata:.2f} BTC<extra></extra>"
    )

    trace_shorts = go.Bar(
        y=short_bins,
        x=short_vols,
        orientation='h',
        name='Trapped Shorts',
        marker=dict(color='#ff0000'),
        customdata=[abs(v) for v in short_vols],
        hovertemplate="Price: %{y}<br>Volume: %{customdata:.2f} BTC<extra></extra>"
    )

    layout = go.Layout(
        template="plotly_dark",
        plot_bgcolor='#111111',
        paper_bgcolor='#111111',
        barmode='relative', 
        yaxis=dict(
            title="Price Level (USDT)",
            range=[current_price - 1500, current_price + 1500], 
            tickformat=".2f"
        ),
        xaxis=dict(
            title="Trapped Volume (BTC)",
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='white'
        ),
        shapes=[
            dict(
                type="line",
                y0=current_price, y1=current_price,
                x0=0, x1=1,
                xref="paper", yref="y",
                line=dict(color="blue", width=2, dash="dash")
            )
        ],
        annotations=[
            dict(
                x=0.05, y=current_price,
                xref="paper", yref="y",
                text=f"Current Price: ${current_price:,.2f}",
                showarrow=False,
                font=dict(color="blue", size=14),
                yshift=15
            )
        ],
        margin=dict(l=50, r=50, t=50, b=50),
        uirevision='constant'
    )

    return go.Figure(data=[trace_shorts, trace_longs], layout=layout)

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Server starting! Open http://127.0.0.1:8050 in your browser.")
    print("="*50 + "\n")
    
    app.run(debug=False, use_reloader=False)
