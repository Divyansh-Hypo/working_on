import asyncio
import json
import time
import threading
from collections import deque

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import websockets

# ==========================================
# 1. BULLETPROOF BACKGROUND DATA ENGINE
# ==========================================
class InstitutionalPainMap:
    def __init__(self, bin_size: float = 10.0, window_minutes: int = 120):
        self.bin_size = bin_size
        self.window_minutes = window_minutes
        self.current_price = None
        self.history = {}
        self.recent_trades = deque(maxlen=30)
        self.last_trade_ts_ms = None
        self.total_trades = 0
        self.cumulative_delta = 0.0
        self.lock = threading.Lock()

    def add_trade(self, timestamp_ms: int, price: float, volume: float, is_buy: bool):
        minute_ts = timestamp_ms // 60000
        bin_price = round(price / self.bin_size) * self.bin_size

        with self.lock:
            self.current_price = price
            self.last_trade_ts_ms = timestamp_ms
            self.total_trades += 1
            
            if is_buy:
                self.cumulative_delta += volume
            else:
                self.cumulative_delta -= volume

            self.recent_trades.append({
                "ts": timestamp_ms,
                "price": price,
                "volume": volume,
                "side": "BUY" if is_buy else "SELL",
            })

            key = (minute_ts, bin_price)
            if key not in self.history:
                self.history[key] = {"buy": 0.0, "sell": 0.0}

            if is_buy:
                self.history[key]["buy"] += volume
            else:
                self.history[key]["sell"] += volume

    def prune_old_data(self):
        # FIX: Use Binance's last trade time, NOT local system time.
        if self.last_trade_ts_ms is None:
            return
            
        current_minute = self.last_trade_ts_ms // 60000
        cutoff_minute = current_minute - self.window_minutes

        with self.lock:
            keys_to_delete = [k for k in self.history.keys() if k[0] < cutoff_minute]
            for k in keys_to_delete:
                del self.history[k]

    def get_snapshot(self):
        trapped_longs = {}
        trapped_shorts = {}

        with self.lock:
            if self.current_price is None:
                return {"current_price": None}

            for (_, bin_price), vols in self.history.items():
                if bin_price > self.current_price:
                    trapped_longs[bin_price] = trapped_longs.get(bin_price, 0.0) + vols["buy"]
                elif bin_price < self.current_price:
                    trapped_shorts[bin_price] = trapped_shorts.get(bin_price, 0.0) + vols["sell"]

            return {
                "trapped_longs": trapped_longs,
                "trapped_shorts": trapped_shorts,
                "current_price": self.current_price,
                "last_trade_ts_ms": self.last_trade_ts_ms,
                "total_trades": self.total_trades,
                "cvd": self.cumulative_delta,
                "recent_trades": list(self.recent_trades),
                "long_volume_total": sum(trapped_longs.values()),
                "short_volume_total": sum(trapped_shorts.values()),
            }

async def binance_futures_ws_loop(pain_map: InstitutionalPainMap):
    uri = "wss://fstream.binance.com/ws/btcusdt@aggTrade"
    trades_logged = 0
    
    while True:
        try:
            print("⏳ Connecting to Binance USDⓈ-M Futures WebSocket...")
            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
                print("✅ Connected! Streaming live leverage trades...")
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)

                    price = float(data["p"])
                    qty = float(data["q"])
                    is_buy = not data["m"]
                    ts = int(data["T"])

                    pain_map.add_trade(ts, price, qty, is_buy)
                    
                    # Print first 3 trades to terminal to prove data is flowing
                    if trades_logged < 3:
                        print(f"📥 Received Trade: {'BUY' if is_buy else 'SELL'} {qty} BTC @ ${price}")
                        trades_logged += 1

        except Exception as e:
            print(f"❌ WebSocket error: {e}. Reconnecting in 3 seconds...")
            await asyncio.sleep(3)

def start_background_loop(pain_map: InstitutionalPainMap):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(binance_futures_ws_loop(pain_map))

pain_map = InstitutionalPainMap(bin_size=10.0, window_minutes=120)
threading.Thread(target=start_background_loop, args=(pain_map,), daemon=True).start()

# ==========================================
# 2. INSTITUTIONAL DASHBOARD UI
# ==========================================
app = dash.Dash(__name__)

BG_COLOR = "#06090e"
CARD_BG = "#0d131c"
BORDER = "1px solid #1a2332"
TEXT_MAIN = "#d1d5db"
TEXT_MUTED = "#6b7280"
BUY_COLOR = "#10b981"
SELL_COLOR = "#ef4444"

CARD_STYLE = {
    "background": CARD_BG,
    "border": BORDER,
    "borderRadius": "8px",
    "padding": "16px",
    "boxShadow": "0 4px 6px -1px rgba(0, 0, 0, 0.5)",
}

app.layout = html.Div(
    style={
        "background": BG_COLOR, "color": TEXT_MAIN, "fontFamily": "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
        "height": "100vh", "padding": "12px", "boxSizing": "border-box", "display": "flex", "flexDirection": "column", "gap": "12px"
    },
    children=[
        html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "padding": "0 8px"}, children=[
            html.Div([
                html.H1("QUANTITATIVE ORDER FLOW", style={"margin": "0", "fontSize": "22px", "letterSpacing": "1px", "fontWeight": "600"}),
                html.P("BTC/USDT Perpetual Futures | Live Tape & Trapped Liquidity", style={"margin": "2px 0 0", "color": TEXT_MUTED, "fontSize": "13px"}),
            ]),
            html.Div(id="connection-badge", style={"padding": "6px 12px", "borderRadius": "4px", "fontSize": "12px", "fontWeight": "bold", "letterSpacing": "0.5px"}),
        ]),
        
        html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(5, 1fr)", "gap": "12px"}, children=[
            html.Div([html.Div("MARKET PRICE", style={"color": TEXT_MUTED, "fontSize": "11px", "fontWeight": "bold"}), html.Div(id="metric-price", style={"fontSize": "24px", "fontFamily": "monospace"})], style=CARD_STYLE),
            html.Div([html.Div("TRAPPED LONGS (OVERHEAD)", style={"color": TEXT_MUTED, "fontSize": "11px", "fontWeight": "bold"}), html.Div(id="metric-longs", style={"fontSize": "24px", "fontFamily": "monospace", "color": BUY_COLOR})], style=CARD_STYLE),
            html.Div([html.Div("TRAPPED SHORTS (UNDERWATER)", style={"color": TEXT_MUTED, "fontSize": "11px", "fontWeight": "bold"}), html.Div(id="metric-shorts", style={"fontSize": "24px", "fontFamily": "monospace", "color": SELL_COLOR})], style=CARD_STYLE),
            html.Div([html.Div("PAIN IMBALANCE", style={"color": TEXT_MUTED, "fontSize": "11px", "fontWeight": "bold"}), html.Div(id="metric-imbalance", style={"fontSize": "24px", "fontFamily": "monospace"})], style=CARD_STYLE),
            html.Div([html.Div("SESSION DELTA (CVD)", style={"color": TEXT_MUTED, "fontSize": "11px", "fontWeight": "bold"}), html.Div(id="metric-cvd", style={"fontSize": "24px", "fontFamily": "monospace"})], style=CARD_STYLE),
        ]),

        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 350px", "gap": "12px", "flex": "1", "minHeight": "0"}, children=[
            html.Div(style={**CARD_STYLE, "display": "flex", "flexDirection": "column", "padding": "0"}, children=[
                html.Div(style={"padding": "16px 16px 0", "display": "flex", "justifyContent": "space-between"}, children=[
                    html.H3("LIQUIDITY PAIN PROFILE", style={"margin": "0", "fontSize": "14px", "color": TEXT_MUTED}),
                    html.Div("Resolution: $10/bin | Range: ±$1000", style={"fontSize": "12px", "color": TEXT_MUTED})
                ]),
                dcc.Graph(id="live-update-graph", style={"flex": "1"}, config={"displaylogo": False}),
            ]),
            
            html.Div(style={**CARD_STYLE, "display": "flex", "flexDirection": "column", "overflow": "hidden"}, children=[
                html.H3("AGGRESSIVE TAPE", style={"margin": "0 0 12px", "fontSize": "14px", "color": TEXT_MUTED}),
                html.Div(
                    style={"display": "grid", "gridTemplateColumns": "60px 1fr 80px", "paddingBottom": "8px", "borderBottom": BORDER, "fontSize": "11px", "color": TEXT_MUTED, "fontWeight": "bold"},
                    children=[html.Div("TIME"), html.Div("PRICE"), html.Div("SIZE (BTC)", style={"textAlign": "right"})]
                ),
                html.Div(id="recent-trades-table", style={"flex": "1", "overflowY": "auto", "paddingTop": "8px"})
            ])
        ]),
        
        dcc.Interval(id="interval-component", interval=1000, n_intervals=0),
    ]
)

@app.callback(
    [Output("live-update-graph", "figure"), Output("connection-badge", "children"), Output("connection-badge", "style"),
     Output("metric-price", "children"), Output("metric-longs", "children"), Output("metric-shorts", "children"),
     Output("metric-imbalance", "children"), Output("metric-cvd", "children"), Output("recent-trades-table", "children")],
    [Input("interval-component", "n_intervals")]
)
def update_dashboard(_):
    # FIX: Prune using the internal class method that relies on Binance time
    pain_map.prune_old_data()
    snap = pain_map.get_snapshot()

    if snap.get("current_price") is None:
        fig = go.Figure(layout=go.Layout(template="plotly_dark", plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG))
        badge = {"background": "#374151", "color": "#9ca3af", "border": "1px solid #4b5563"}
        return fig, "AWAITING DATA...", badge, "---", "---", "---", "---", "---", html.Div("Connecting to Binance...", style={"color": TEXT_MUTED, "fontSize": "13px"})

    cp = snap["current_price"]
    tl, ts = snap["trapped_longs"], snap["trapped_shorts"]
    
    prices = sorted(set(list(tl.keys()) + list(ts.keys())))
    long_vols = [tl.get(p, 0.0) for p in prices]
    short_vols = [-ts.get(p, 0.0) for p in prices] 

    fig = go.Figure()
    fig.add_trace(go.Bar(y=prices, x=short_vols, orientation="h", name="Trapped Shorts", marker=dict(color=SELL_COLOR, opacity=0.8), hovertemplate="Price: $%{y}<br>Vol: %{x} BTC<extra></extra>"))
    fig.add_trace(go.Bar(y=prices, x=long_vols, orientation="h", name="Trapped Longs", marker=dict(color=BUY_COLOR, opacity=0.8), hovertemplate="Price: $%{y}<br>Vol: %{x} BTC<extra></extra>"))

    max_vol = max(max(long_vols, default=0), max([abs(x) for x in short_vols], default=0), 1)

    fig.update_layout(
        template="plotly_dark", plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG, barmode="relative",
        margin=dict(l=40, r=40, t=20, b=30),
        yaxis=dict(range=[cp - 1000, cp + 1000], tickformat=",.0f", gridcolor="#1f2937", zeroline=False),
        xaxis=dict(range=[-max_vol*1.1, max_vol*1.1], gridcolor="#1f2937", zerolinecolor="#4b5563", zerolinewidth=2),
        showlegend=False, uirevision="constant",
        shapes=[dict(type="line", y0=cp, y1=cp, x0=0, x1=1, xref="paper", yref="y", line=dict(color="#fcd34d", width=1.5, dash="dot"))],
        annotations=[dict(x=0, y=cp, xref="paper", yref="y", text=f"${cp:,.1f}", showarrow=False, font=dict(color="#fcd34d", size=12), xanchor="left", yshift=10)]
    )

    imbalance = snap['long_volume_total'] - snap['short_volume_total']
    cvd = snap['cvd']
    
    imb_color = BUY_COLOR if imbalance > 0 else SELL_COLOR
    cvd_color = BUY_COLOR if cvd > 0 else SELL_COLOR

    tape_html = []
    for t in reversed(snap["recent_trades"]):
        time_str = time.strftime("%H:%M:%S", time.localtime(t["ts"] / 1000))
        color = BUY_COLOR if t["side"] == "BUY" else SELL_COLOR
        tape_html.append(
            html.Div(style={"display": "grid", "gridTemplateColumns": "60px 1fr 80px", "padding": "4px 0", "fontSize": "13px", "fontFamily": "monospace"}, children=[
                html.Div(time_str, style={"color": TEXT_MUTED}),
                html.Div(f"${t['price']:,.1f}", style={"color": color, "fontWeight": "bold"}),
                html.Div(f"{t['volume']:.3f}", style={"textAlign": "right", "color": TEXT_MAIN})
            ])
        )

    # Use Binance timestamp to check if stream is live
    now_ms = int(time.time() * 1000)
    last_seen_age = (now_ms - snap["last_trade_ts_ms"]) / 1000 if snap["last_trade_ts_ms"] else 999
    is_live = last_seen_age < 10
    badge = {
        "background": "rgba(16, 185, 129, 0.1)" if is_live else "rgba(239, 68, 68, 0.1)",
        "color": BUY_COLOR if is_live else SELL_COLOR,
        "border": f"1px solid {BUY_COLOR if is_live else SELL_COLOR}"
    }

    return (
        fig, 
        "● LIVE FEED" if is_live else "⚠ DELAYED", 
        badge,
        f"${cp:,.1f}", 
        f"{snap['long_volume_total']:,.1f}", 
        f"{snap['short_volume_total']:,.1f}",
        html.Span(f"{imbalance:+,.1f}", style={"color": imb_color}), 
        html.Span(f"{cvd:+,.1f}", style={"color": cvd_color}), 
        tape_html
    )

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🚀 INSTITUTIONAL PAIN MAP STARTING...")
    print("Open http://127.0.0.1:8050 in your browser.")
    print("=" * 60 + "\n")
    app.run(debug=False, use_reloader=False)
