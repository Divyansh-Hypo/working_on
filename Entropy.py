import pandas as pd
import numpy as np
import asyncio
import websockets 
import time
import datetime
import json
import requests
import math
import socket # NEW: For detecting your local IP
from collections import Counter, deque

# --- 1. THE "SERVER" BRAIN ---
from flask import Flask, jsonify, send_file
from flask_cors import CORS
from threading import Thread
from flask_socketio import SocketIO

app = Flask(__name__)
CORS(app) 

# 2. THE BRIDGE (Initialize SocketIO in threading mode)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- 2. THE "DATA OFFICE" ---
latest_stats = {}

@app.route('/')
def serve_dashboard():
    return send_file('dashboard.html')

@app.route('/api/data')
def get_data():
    return jsonify(latest_stats)

def push_to_cloud(data):
    URL = "https://api.jsonbin.io/v3/b/69c3f2eeaa77b81da91ad9f7"
    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': '$2a$10$2DYlbo.m2VpFI6hg8cNrdeVP4XB/lVJ1R4v0bvL7W4hw6bDzvAbPq'
    }
    try:
        requests.put(URL, json=data, headers=headers, timeout=2)
    except Exception:
       pass

# --- GLOBAL VARIABLES INITIALIZATION ---
last_update = datetime.datetime.now().strftime('%H:%M:%S')
collection = []
joint_data = []
sliding_W = deque(maxlen=20)
volume_history = deque(maxlen=20)
price_history = []
flow_history = []
Trade_Entropy = 0.5
trade_count = 0
bid_entropy = 0.0
ask_entropy = 0.0
buy_volume = 0.0
sell_volume = 0.0
total_bid_volume = 0.0
total_ask_volume = 0.0
last_price = 0.0
entropy_rate = 0
market_state = 'COLLECTING DATA...'
sync_strength = 'COLLECTING DATA...'
Mutual_Info = 0.0
Free_Energy = 0.0
Joint_Entropy = 0.0
energy_history = []
Average_EH = 0.0
current_energy = 0.0
energy_state = "WAITING"
energy_trend = "WAITING"

def generate_html_dashboard():
    """ Writes the static HTML file ONCE at startup to save disk I/O """
    html_content = r"""
    <!doctype html>
    <html lang="en">
    <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
    <title>Thermo Entropy Algo</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        :root { --bg:#000000; --panel:#050505; --line:#222; --txt:#f3f3f3; --muted:#b0b0b0; --warn:#ffd900; }
        *{box-sizing:border-box;min-width:0}
        html,body{width:100%;height:100%;margin:0;overflow:hidden}
        body{font-family:"JetBrains Mono",monospace;background:var(--bg);color:var(--txt);display:grid;place-items:center;padding:6px}
        .terminal{width:min(100vw - 12px,430px);height:min(100vh - 12px,932px);padding:8px;border:1px solid #2b2b2b;border-radius:16px;background:#000;display:grid;grid-template-rows:auto auto 1fr auto;gap:7px;overflow:hidden}
        .box,.zone{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:8px;overflow:hidden}
        .headline{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
        .title{font-size:14px;font-weight:700;letter-spacing:.8px;text-transform:uppercase}
        .sub{font-size:10px;color:var(--muted)}
        .price{font-size:14px;font-weight:700;padding:4px 10px;border-radius:999px;border:1px solid var(--line);background:#0a0a0a}
        .row{display:grid;grid-template-columns:1fr .58fr;gap:7px}
        .k{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
        .big{font-size:22px;font-weight:700;line-height:1.0;margin-top:3px}
        .mono{font-family:"JetBrains Mono",monospace}
        .sync-chip{padding:2px 8px;border-radius:6px;border:1px solid var(--line);background:#0b0b0b;font-size:11px;font-weight:700}
        .zone-wrap{display:grid;grid-template-rows:repeat(4,1fr);gap:8px;overflow:hidden}
        .zone h4{margin:0 0 4px 0;font-size:10px;color:#d0d0d0;letter-spacing:.65px;text-transform:uppercase}
        .metrics{display:flex;flex-direction:column;gap:7px;height:calc(100% - 16px)}
        .mrow{display:grid;grid-template-columns:1fr auto;align-items:center;gap:8px;padding:8px 10px;border:1px solid #1f1f1f;border-radius:10px;background:#080808;min-height:0;flex:1}
        .mname{font-size:18px;color:#e2e2e2;line-height:1}
        .mval{font-size:30px;font-weight:700;color:#fff;text-align:right;line-height:1}
        .sync-alert{background:rgba(255,217,0,.16);border-color:#b89e00}
        .foot{text-align:center;color:#888;font-size:9px}
    </style>
    </head>
    <body>
    <main class="terminal">
    <section class="headline">
        <div><div class="title">THERMO ENTROPY ALGO</div><div class="sub" id="ui-time">--:--:-- PM</div></div>
        <div class="price" id="ui-price">BTC --</div>
    </section>

    <section class="row">
        <article class="box">
        <div class="k">Market State</div>
        <div class="big mono" id="ui-state">WAITING</div>
        <div class="sub">Trend: <span id="ui-energy-trend">--</span></div>
        </article>
        <article class="box">
        <div class="k">$ Internal USD</div>
        <div class="mono" style="font-size:20px;font-weight:700;line-height:1" id="ui-ieusd-top">0.00</div>
        <div class="sub">Energy USD</div>
        </article>
    </section>

    <section class="zone-wrap">
        <article class="zone" id="zone-system">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <h4 style="margin:0">System Status</h4>
            <div class="sync-chip" id="sync-chip">SYNC <span id="ui-sync">--</span></div>
        </div>
        <div class="metrics">
            <div class="mrow"><span class="mname">Free Energy (G)</span><span class="mval" id="ui-g">0.0000</span></div>
            <div class="mrow"><span class="mname">Energy State</span><span class="mval" id="ui-energy-color-text">--</span></div>
            <div class="mrow"><span class="mname">Energy Trend</span><span class="mval" id="ui-energy-trend-chip">--</span></div>
            <div class="mrow"><span class="mname">Sync_S</span><span class="mval" id="ui-sync-row">--</span></div>
        </div>
        </article>
        <article class="zone" id="zone-a">
        <h4>Zone A • Thermodynamics</h4>
        <div class="metrics">
            <div class="mrow"><span class="mname">Free Energy (G)</span><span class="mval" id="z-g">0.0000</span></div>
            <div class="mrow"><span class="mname">Internal_E</span><span class="mval" id="z-internal">0.0000</span></div>
            <div class="mrow"><span class="mname">Slope</span><span class="mval" id="z-slope">0.000000</span></div>
        </div>
        </article>
        <article class="zone" id="zone-b">
        <h4>Zone B • Order Book</h4>
        <div class="metrics">
            <div class="mrow"><span class="mname">Bid_E</span><span class="mval" id="z-bid">0.0000</span></div>
            <div class="mrow"><span class="mname">Ask_E</span><span class="mval" id="z-ask">0.0000</span></div>
            <div class="mrow"><span class="mname">Trade Entropy</span><span class="mval" id="z-te">0.0000</span></div>
        </div>
        </article>
        <article class="zone" id="zone-c">
        <h4>Zone C • System Health</h4>
        <div class="metrics">
            <div class="mrow"><span class="mname">Sync_S</span><span class="mval" id="z-sync">--</span></div>
            <div class="mrow"><span class="mname">Joint Entropy</span><span class="mval" id="z-hj">0.0000</span></div>
            <div class="mrow"><span class="mname">Mutual Info</span><span class="mval" id="z-mi">0.0000</span></div>
        </div>
        </article>
    </section>

    <div class="foot">made by DD</div>
    </main>

    <script>
    function colorState(s){ if(s==='STABLE') return '#ffd900'; return '#f3f3f3'; }
    function fmt(v,d=4){ const n=Number(v||0); if(Math.abs(n)>=1e6) return (n/1e6).toFixed(2)+'M'; if(Math.abs(n)>=1e3) return (n/1e3).toFixed(2)+'k'; return n.toFixed(d); }
    function to12h(hms){ if(!hms||hms.indexOf(':')===-1) return '--:--:--'; const [h,m,s]=hms.split(':').map(Number); const ampm=h>=12?'PM':'AM'; const hh=((h+11)%12)+1; return `${String(hh).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')} ${ampm}`; }

    // Connect to the Flask-SocketIO server dynamically
    const socket = io(); 
    
    socket.on('update', function(d) {
        const g=Number(d.G||0), mi=Number(d.MI||0), hj=Number(d.H_joint||0), slope=Number(d.Slope||0);
        const te=Number(d.TE||0), bid=Number(d.Bid_E||0), ask=Number(d.Ask_E||0), ie=Number(d.Internal_E||0), ieusd=Number(d.IE_USD||0), price=Number(d.Price||0);

        document.getElementById('ui-time').textContent=to12h(d.Last_Update);
        document.getElementById('ui-price').textContent=price?`BTC ${price.toFixed(2)}`:'BTC --';
        document.getElementById('ui-state').textContent=d.State||'WAITING'; document.getElementById('ui-state').style.color=colorState(d.State);
        document.getElementById('ui-energy-trend').textContent=d.Energy_T||'--';

        document.getElementById('ui-g').textContent=g.toFixed(4);
        document.getElementById('ui-energy-trend-chip').textContent=d.Energy_T||'--';
        document.getElementById('ui-energy-color-text').textContent=d.Energy_S||'--';

        document.getElementById('ui-ieusd-top').textContent='$'+Number(ieusd||0).toLocaleString(undefined,{minimumFractionDigits:0,maximumFractionDigits:0});
        document.getElementById('ui-sync').textContent=d.Sync_S||'--';
        document.getElementById('ui-sync-row').textContent=d.Sync_S||'--';
        document.getElementById('sync-chip').classList.toggle('sync-alert', d.Sync_S === 'HIGH');

        document.getElementById('z-g').textContent=g.toFixed(4); document.getElementById('z-internal').textContent=fmt(ie,4); document.getElementById('z-slope').textContent=slope.toFixed(6);
        document.getElementById('z-bid').textContent=bid.toFixed(4); document.getElementById('z-ask').textContent=ask.toFixed(4); document.getElementById('z-te').textContent=te.toFixed(4);
        document.getElementById('z-sync').textContent=d.Sync_S||'--'; document.getElementById('z-hj').textContent=hj.toFixed(4); document.getElementById('z-mi').textContent=mi.toFixed(4);
    });
    </script>
    </body>
    </html>
    """
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(html_content)

# --- NEW: Function to find your PC's IP ---
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable, just forces the OS to route an IP
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

async def listen():
    global buy_volume, sell_volume, trade_count, Trade_Entropy
    global bid_entropy, ask_entropy, total_bid_volume, total_ask_volume
    global Mutual_Info, Free_Energy, last_price, joint_data, Joint_Entropy
    global collection, market_state, price_history, flow_history, entropy_rate
    global energy_history, energy_state, energy_trend, sync_strength
    global Average_EH, current_energy, latest_stats
    
    uri = "wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade/btcusdt@depth20"
    
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as websocket:
                print("CONNECTED TO BINANCE...")
                
                async for message in websocket:
                    raw_data = json.loads(message)
                    stream_name = raw_data.get('stream')
                    data = raw_data.get('data')
                    
                    collection.append(data)
                    if len(collection) > 5000:
                        collection = collection[-5000:]
                        
                    if stream_name == 'btcusdt@aggTrade':
                        Price = float(data['p'])
                        trade_count += 1
                        if trade_count > 1000:
                            buy_volume = 0
                            sell_volume = 0
                            trade_count = 0
                            
                        if data['m'] == False:
                            buy_volume += float(data['q'])
                        elif data['m'] == True:
                            sell_volume += float(data['q'])
                            
                        volume_history.append(float(data['q']))
                        total_volume = (buy_volume + sell_volume)
                        
                        if total_volume > 0:
                            P_buy = (buy_volume / total_volume) 
                            P_sell = (sell_volume / total_volume)
                            if P_buy > 0 and P_sell > 0:
                                Trade_Entropy = -((P_buy * math.log2(P_buy)) + (P_sell * math.log2(P_sell)))
                        
                        S_p = 0  
                        S_f = 0
                        if last_price > 0:
                            if Price > last_price:
                                S_p = 1
                            elif Price < last_price:
                                S_p = -1
                            
                        if data['m'] == False:
                            S_f = 1
                        elif data['m'] == True:
                            S_f = -1
                            
                        joint_data.append((S_p, S_f))
                        joint_data = joint_data[-1000:]
                        
                        counts = Counter(joint_data)
                        total = len(joint_data)
                        Joint_Entropy = 0
                        for count in counts.values():
                            P_pf = (count/total)
                            Joint_Entropy -= (P_pf) * math.log2(P_pf)
                        
                        price_history.append(S_p)
                        flow_history.append(S_f)
                        price_history = price_history[-1000:]
                        flow_history = flow_history[-1000:]
                        PH = Counter(price_history)
                        total_PH = len(price_history)
                        FH = Counter(flow_history)
                        total_FH = len(flow_history)
                        
                        H_price = sum(- (count/total_PH) * math.log2(count/total_PH) for count in PH.values())
                        H_flow = sum(- (count/total_FH) * math.log2(count/total_FH) for count in FH.values())
                        
                        Mutual_Info = max(0.0, H_price + H_flow - Joint_Entropy)
                        
                        Internal_Energy = sum(volume_history)
                        Temp = np.std(price_history) if len(price_history) > 0 else 0
                        Free_Energy = Internal_Energy - (Temp * Joint_Entropy)
        
                        last_price = Price
                        sliding_W.append(Joint_Entropy)
                        if len(sliding_W) == 20:
                            y = np.array((sliding_W))  
                            x = np.arange(len(y))
                            slope = np.polyfit(x, y, 1)                   
                            entropy_rate = slope[0]
                           
                            if entropy_rate < -0.002:
                                market_state = 'ORDER BUILDING'
                            elif entropy_rate > 0.002:
                                market_state = 'DECAYING'
                            else:
                                market_state = 'STABLE'
                    
                    elif stream_name == 'btcusdt@depth20':
                        bids_data = data['bids']
                        asks_data = data['asks']
                        
                        bid_quant = [float(item[1]) for item in bids_data]
                        ask_quant = [float(item[1]) for item in asks_data]
                        
                        total_bid_volume = sum(bid_quant)
                        total_ask_volume = sum(ask_quant)
                        
                        bid_entropy = 0
                        if total_bid_volume > 0:
                            P_bids = [q / total_bid_volume for q in bid_quant]
                            bid_entropy = sum(-prob * math.log2(prob) for prob in P_bids if prob > 0)
                                
                        ask_entropy = 0
                        if total_ask_volume > 0:
                            P_asks = [q / total_ask_volume for q in ask_quant]
                            ask_entropy = sum(-prob * math.log2(prob) for prob in P_asks if prob > 0)
                        
                    current_price = last_price    
                    Internal_Energy = sum(volume_history)
                    Internal_E_USD = (Internal_Energy * current_price)
                    
                    Sync_gap = abs(Joint_Entropy - Mutual_Info)
                    sync_den = max(abs(Joint_Entropy) + abs(Mutual_Info), 1e-9)
                    sync_percent = max(0.0, min(100.0, 100.0 * (1.0 - (Sync_gap / sync_den))))
                    
                    if sync_percent > 70:
                       sync_strength = "HIGH"
                    elif sync_percent > 40:
                        sync_strength = "MEDIUM"
                    else:
                        sync_strength = "LOW"
                    
                    energy_history.append(Internal_Energy)
                    energy_history = energy_history[-200:]
                    Average_EH = sum(energy_history) / len(energy_history) if len(energy_history) > 0 else 0
                    current_energy = sum(volume_history)
                    
                    if current_energy > Average_EH:
                        energy_state = "ACCUMULATING"
                        energy_trend = "UP"
                    else:
                        energy_state = "EXHAUSTING"
                        energy_trend = "DOWN"
                        
                    payload = {
                        "Last_Update": datetime.datetime.now().strftime("%H:%M:%S"),
                        "Price": current_price,
                        "G": round(Free_Energy, 4),
                        "MI": round(Mutual_Info, 4),
                        "H_joint": round(Joint_Entropy, 4),
                        "Slope": round(entropy_rate, 6),
                        "TE": round(Trade_Entropy, 4),
                        "Bid_E": round(bid_entropy, 4),
                        "Ask_E": round(ask_entropy, 4),
                        "Internal_E": Internal_Energy,
                        "IE_USD": Internal_E_USD,
                        "State": market_state,
                        "Energy_T": energy_trend,
                        "Energy_S": energy_state,
                        "Sync_S": sync_strength
                    }
                    
                    latest_stats = payload
                    socketio.emit('update', payload)

                    try:
                        with open("live_data.json", "w", encoding="utf-8") as f:
                            json.dump(payload, f)
                    except Exception:
                        pass
        
                    try:
                        if trade_count % 50 == 0:
                            push_to_cloud(payload)
                    except Exception:
                        pass
                        
        except Exception as e:
            print(f"\nCONNECTION LOST: {e}. RECONNECTING IN 5 SECONDS...\n")
            await asyncio.sleep(5)

# --- 4. THE "IGNITION" ---
if __name__ == "__main__":
    generate_html_dashboard()
    
    # Grab the local IP and print it cleanly for the user
    local_ip = get_local_ip()
    print("\n" + "="*50)
    print("🚀 SERVER IS RUNNING!")
    print(f"💻 Access on Desktop: http://localhost:5000")
    print(f"📱 Access on Mobile : http://{local_ip}:5000")
    print("="*50 + "\n")
    
    Thread(target=lambda: socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)).start()
    asyncio.run(listen())
