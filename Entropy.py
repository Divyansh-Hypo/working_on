import pandas as pd
import numpy as np
import asyncio
import websockets 
import time
import datetime
import json
import requests
import math
from collections import Counter
from collections import deque

def push_to_cloud(data):
    URL = "https://api.jsonbin.io/v3/b/69c3f2eeaa77b81da91ad9f7"
    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': '$2a$10$2DYlbo.m2VpFI6hg8cNrdeVP4XB/lVJ1R4v0bvL7W4hw6bDzvAbPq'
    }
    try:
        requests.put(URL, json=data, headers = headers)
    except :
       pass


last_update = datetime.datetime.now().strftime('%H:%M:%S')
collection = []
joint_data = []
sliding_W = deque(maxlen = 20)
volume_history = deque(maxlen = 20)
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
async def listen():
    global buy_volume 
    global sell_volume 
    global trade_count
    global Trade_Entropy
    global bid_entropy
    global ask_entropy
    global total_bid_volume , total_ask_volume
    global Mutual_Info , Free_Energy
    global last_price
    global joint_data , Joint_Entropy
    global collection
    global market_state
    global price_history
    global flow_history
    global entropy_rate
    global energy_history , energy_state , energy_trend
    global sync_strength , Average_EH , current_energy
    uri = "wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade/btcusdt@depth20"
    async with websockets.connect(uri) as websocket:
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
                else:
                    print('data no found')
                volume_history.append(float(data['q']))
                total_volume = (buy_volume + sell_volume)
                if total_volume > 0:
                    P_buy = (buy_volume / total_volume) 
                    P_sell = (sell_volume / total_volume)
                else:
                    print('P_volume error')
                
                if P_buy > 0 and P_sell > 0:
                    Trade_Entropy = -((P_buy * math.log2(P_buy)) + (P_sell * math.log2(P_sell)))
                S_p = 0  
                S_f = 0
                if last_price > 0:
                    if Price > last_price:
                        S_p = 1
                    elif Price < last_price:
                        S_p = -1
                    else:
                        S_p = 0
                    
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
                H_price = 0
                for count in PH.values():
                    P_PH = (count/total_PH)
                    H_price -= (P_PH) * math.log2(P_PH)
                H_flow = 0
                for count in FH.values():
                    P_FH = (count/total_FH)
                    H_flow -= (P_FH) * math.log2(P_FH)
                Mutual_Info = H_price + H_flow - Joint_Entropy
        #---Thermodynamic "Free Energy" ($G = U - TS$)---
                Internal_Energy = sum(volume_history)
                
                Temp = np.std(price_history)
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
            
                #print(f"Trade Entropy: {Trade_Entropy:.2f}, Joint Entropy: {Joint_Entropy:.4f}, Memory: {len(joint_data)}, State: {market_state}")
                #print(f"State: {market_state} | MI:{Mutual_Info:.4f} | G: {Free_Energy:.2f} | Slope: {entropy_rate:.6f}")
            elif stream_name == 'btcusdt@depth20':
                
                bids_data = data['bids']
                asks_data = data['asks']
                
                bid_quant = [float(item[1]) for item in bids_data]
                ask_quant = [float(item[1]) for item in asks_data]
                
                total_bid_volume = sum(bid_quant)
                total_ask_volume = sum(ask_quant)
                #print(f"DEBUG: {total_bid_volume}")
                bid_entropy = 0
                if total_bid_volume > 0:
                    P_bids = [q / total_bid_volume for q in bid_quant]
                    for prob in P_bids:
                        if prob > 0:
                            bid_entropy -= prob * math.log2(prob)
                ask_entropy = 0
                if total_ask_volume > 0:
                    P_asks = [q / total_ask_volume for q in ask_quant]
                    for prob in P_asks:
                        if prob > 0:
                            ask_entropy -= prob * math.log2(prob)
            #print(f"Ask Entropy: {ask_entropy:.2f}, Bid Entropy: {bid_entropy:.2f}", end = "\r")   
            
                    
                
            current_price = (last_price)    
            Internal_Energy = sum(volume_history)
            Internal_E_USD = (Internal_Energy * current_price)
            
            Sync_gap = abs(Joint_Entropy - Mutual_Info)
            sync_percent = max(0, 100 * (1- Sync_gap))
            if sync_percent > 80:
               sync_strength = "HIGH"
               sync_color = "#ffd900"
            elif sync_percent > 50:
                sync_strength = "MEDIUM"
                sync_color = "#ff9100"
            else:
                sync_strength = "LOW"
                sync_color = "#ff0000"
            
            energy_history.append(Internal_Energy)
            energy_history = energy_history[-200:]
            Average_EH = sum(energy_history) / len(energy_history) if len(energy_history) > 0 else 0
            current_energy = sum(volume_history)
            
            if current_energy > Average_EH:
                energy_state = "ACCUMULATING"
                energy_trend = "UP"
                energy_color = "#ffd900"
            else:
                energy_state = "EXHAUSTING"
                energy_trend = "DOWN"
                energy_color = "#ff0000"
                  # Paste the $2b$10$... key here
                
            payload = {
                "Price": current_price,
                "G": round(Free_Energy, 4),
                "MI": round(Mutual_Info, 4),
                "State": market_state,
                "Slope": round(entropy_rate, 6),
                "H_joint": round(Joint_Entropy, 4),
                "Internal_E": sum(volume_history),
                "Ask_E": round(ask_entropy, 4),
                "Bid_E": round(bid_entropy, 4),
                "TE": round(Trade_Entropy, 4),
                "IE_USD": round(Internal_E_USD, 2),
                "Sync_S": sync_strength,
                "Sync_C": sync_color,
                "Energy_S": energy_state,
                "Energy_C": energy_color,
                "Energy_T": energy_trend
            }

            try:
                # Only push to cloud every 50 trades so you don't get banned!
                if trade_count % 50 == 0:
                    push_to_cloud(payload)
            except :
                pass

                    
            
        
        
            html_content = r"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Thermodynamic Command Center</title>
                <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
                <script src="https://cdn.tailwindcss.com"></script>
                <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                
                <script>
                    tailwind.config = {
                        theme: {
                            extend: {
                                fontFamily: { sans: ['Inter', 'sans-serif'], mono: ['JetBrains Mono', 'monospace'] },
                                colors: { panel: '#151619', borderDk: '#2a2d35', bgDk: '#050505' }
                            }
                        }
                    }
                </script>
                <style>
                    body { background-color: #050505; color: #e5e5e5; }
                    .card { background-color: #151619; border: 1px solid #2a2d35; border-radius: 0.75rem; overflow: hidden; }
                    ::-webkit-scrollbar { display: none; }
                    .text-green { color: #22c55e; text-shadow: 0 0 10px rgba(34,197,94,0.2); }
                    .text-red { color: #ef4444; text-shadow: 0 0 10px rgba(239,68,68,0.2); }
                </style>
            </head>
            <body class="min-h-screen flex justify-center items-center p-4">

            <div class="w-full max-w-md flex flex-col gap-3">
                <div class="flex justify-between items-end mb-1 px-1">
                    <h1 class="text-[12px] font-bold tracking-widest text-gray-200">THERMODYNAMIC COMMAND CENTER</h1>
                    <div class="text-[11px] font-bold tracking-wider text-[#3b82f6]">
                        BTC/USDT 15M <span class="text-[#f59e0b] ml-1" id="ui-price">--</span>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-3">
                    <div class="flex flex-col gap-2">
                        <div class="text-[12px] font-bold tracking-wider text-gray-400 ml-1">
                            STATE: <span class="text-[#22c55e]" id="ui-state">WAITING</span>
                        </div>
                        <div class="card flex-1 flex flex-col items-center justify-center p-3 border-[#22c55e]/30 bg-[#1a2e20]/40" id="g-card">
                            <div class="text-[11px] font-bold tracking-wider text-[#22c55e]/80 mb-1" id="g-title">FREE ENERGY (G):</div>
                            <div class="flex items-center gap-1 text-3xl font-bold font-mono text-white">
                                <span id="ui-g">0.00</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card h-full p-3 flex flex-col items-center justify-center relative">
                        <div class="text-[11px] text-gray-400 font-bold tracking-wider mb-2 text-center leading-tight">TOTAL<br>SYSTEM<br>EXERGY (Ω)</div>
                        <div class="relative w-full max-w-[150px] aspect-[2/1]">
                            <svg viewBox="0 0 100 50" class="w-full h-full overflow-visible">
                                <defs>
                                    <linearGradient id="gauge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                                        <stop offset="0%" stop-color="#ef4444" />
                                        <stop offset="50%" stop-color="#3b82f6" />
                                        <stop offset="100%" stop-color="#22c55e" />
                                    </linearGradient>
                                </defs>
                                <path d="M 10 50 A 40 40 0 0 1 90 50" fill="none" stroke="url(#gauge-grad)" stroke-width="8" stroke-linecap="round" />
                                <g stroke="#4b5563" stroke-width="1" class="font-mono text-[6px]" fill="#9ca3af" text-anchor="middle" dominant-baseline="middle">
                                    <line x1="10" y1="50" x2="12" y2="50" /><text x="6" y="50">-5</text>
                                    <line x1="50" y1="10" x2="50" y2="12" /><text x="50" y="6">0</text>
                                    <line x1="90" y1="50" x2="88" y2="50" /><text x="94" y="50">5</text>
                                </g>
                                <g id="needle-group" transform="translate(50, 50) rotate(-90)" class="transition-transform duration-500 ease-out">
                                    <polygon points="-2,0 2,0 0,-35" fill="#e5e5e5" />
                                    <circle cx="0" cy="0" r="4" fill="#e5e5e5" />
                                    <circle cx="0" cy="0" r="2" fill="#151619" />
                                </g>
                            </svg>
                        </div>
                        <div class="absolute bottom-2 left-2 text-[9px] text-[#ef4444] font-bold tracking-widest">DECAY</div>
                        <div class="absolute bottom-2 right-2 text-[9px] text-[#22c55e] font-bold tracking-widest">COMPRESSION</div>
                    </div>
                </div>

                <div class="card p-4 flex flex-col">
                    <div class="flex justify-between items-start mb-2">
                        <div class="text-[11px] font-bold tracking-wider text-gray-400">JOINT ENTROPY (H<sub class="text-[8px]">joint</sub>) vs. MI</div>
                        <div class="text-right">
                            <div class="text-[10px] font-bold tracking-wider text-gray-500">SYNC STRENGTH:</div>
                            <div class="text-[12px] font-bold tracking-wider text-[#22c55e]" id="ui-sync">--</div>
                        </div>
                    </div>
                    <div class="h-40 w-full relative">
                        <canvas id="mainChart"></canvas>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-3">
                    <div class="card p-4 flex gap-4 items-center">
                        <div class="w-8 h-20 rounded-md bg-[#0a0a0a] border border-[#2a2d35] relative overflow-hidden shrink-0 shadow-[inset_0_2px_10px_rgba(0,0,0,0.5)]">
                            <div id="bar-internal" class="absolute bottom-0 left-0 right-0 transition-all duration-500 ease-out" style="height: 0%; background: linear-gradient(to top, #1e3a8a, #60a5fa); box-shadow: 0 0 15px #60a5fa80;"></div>
                            <div class="absolute top-0 left-0 bottom-0 w-1/3 bg-white/10"></div>
                        </div>
                        <div class="flex flex-col justify-center">
                            <div class="text-[10px] font-bold tracking-wider text-gray-400 uppercase mb-1">INTERNAL ENERGY</div>
                            <div class="text-xl font-bold font-mono tracking-tight text-white mb-1" id="ui-internal">0.00</div>
                            <div class="inline-flex items-center px-2 py-0.5 rounded text-[9px] font-bold tracking-wider border border-gray-600 text-gray-300 bg-gray-800/50 w-fit">STATE: <span id="ui-e-state" class="ml-1">--</span></div>
                        </div>
                    </div>

                    <div class="card p-4 flex gap-4 items-center">
                        <div class="w-8 h-20 rounded-md bg-[#0a0a0a] border border-[#2a2d35] relative overflow-hidden shrink-0 shadow-[inset_0_2px_10px_rgba(0,0,0,0.5)]">
                            <div id="bar-slope" class="absolute bottom-0 left-0 right-0 transition-all duration-500 ease-out" style="height: 0%; background: linear-gradient(to top, #374151, #9ca3af); box-shadow: 0 0 15px #9ca3af80;"></div>
                            <div class="absolute top-0 left-0 bottom-0 w-1/3 bg-white/10"></div>
                        </div>
                        <div class="flex flex-col justify-center">
                            <div class="text-[10px] font-bold tracking-wider text-gray-400 uppercase mb-1">ENTROPY RATE (SLOPE)</div>
                            <div class="text-xl font-bold font-mono tracking-tight text-white mb-1" id="ui-slope">0.000</div>
                            <div class="inline-flex items-center px-2 py-0.5 rounded text-[9px] font-bold tracking-wider border border-gray-600 text-gray-300 bg-gray-800/50 w-fit mt-1">TREND: <span id="ui-slope-state" class="ml-1">--</span></div>
                        </div>
                    </div>
                </div>

                <div class="flex flex-col gap-2">
                    <div class="card p-3 flex items-center justify-between border-l-4 border-l-[#22c55e]">
                        <div><div class="text-[11px] font-bold tracking-wider text-gray-300">BID ENTROPY <span class="ml-2" id="tag-bid">-- </span> <span class="text-gray-500 font-mono ml-1" id="ui-bid">0.00</span></div><div class="text-[11px] text-gray-500 mt-0.5">Buyer Structure</div></div>
                    </div>
                    <div class="card p-3 flex items-center justify-between border-l-4 border-l-[#ef4444]">
                        <div><div class="text-[11px] font-bold tracking-wider text-gray-300">TRADE ENTROPY <span class="ml-2" id="tag-trade">-- </span> <span class="text-gray-500 font-mono ml-1" id="ui-trade">0.00</span></div><div class="text-[11px] text-gray-500 mt-0.5">Execution Chaos</div></div>
                    </div>
                    <div class="card p-3 flex items-center justify-between border-l-4 border-l-[#f59e0b]">
                        <div><div class="text-[11px] font-bold tracking-wider text-gray-300">ASK ENTROPY <span class="ml-2" id="tag-ask">-- </span> <span class="text-gray-500 font-mono ml-1" id="ui-ask">0.00</span></div><div class="text-[11px] text-gray-500 mt-0.5">Seller Structure</div></div>
                    </div>
                </div>
            </div>

            <script>
                const ctx = document.getElementById('mainChart').getContext('2d');
                Chart.defaults.color = '#6b7280';
                Chart.defaults.font.family = "'Inter', sans-serif";
                
                const mainChart = new Chart(ctx, {
                    type: 'line',
                    data: { labels: Array(30).fill(''), datasets: [
                        { label: 'H_Joint', data: [], borderColor: '#ef4444', borderWidth: 2, tension: 0.4, pointRadius: 0 },
                        { label: 'MI', data: [], borderColor: '#3b82f6', borderWidth: 2, tension: 0.4, pointRadius: 0 }
                    ]},
                    options: { 
                        responsive: true, maintainAspectRatio: false,
                        plugins: { legend: { display: false }, tooltip: { enabled: false } },
                        scales: { 
                        x: { display: false }, 
                        y: { display: false, min: 0 } 
                        },
                        animation: { duration: 0 }
                    }
                });
                
                function getEntropyTag(val) {
                    if (val > 1.5) return { text: "HIGH", color: "#ef4444" };
                    if (val > 0.8) return { text: "MED", color: "#f59e0b" };
                    return { text: "LOW", color: "#22c55e" };
                }

                async function updateDashboard() {
                    const BIN_ID = "69c3f2eeaa77b81da91ad9f7";
                    const MASTER_KEY = "$2a$10$2DYlbo.m2VpFI6hg8cNrdeVP4XB/lVJ1R4v0bvL7W4hw6bDzvAbPq";
                    const CLOUD_URL = `https://api.jsonbin.io/v3/b/${BIN_ID}/latest`;

                    try {
                        const response = await fetch(CLOUD_URL, { headers: { 'X-Master-Key': MASTER_KEY } });
                        const result = await response. json();
                        const data = result.record;
                        
                        // 1. Top Section
                        document.getElementById('ui-price').innerText = data.Price ? data.Price.toFixed(2) : "--";
                        document.getElementById('ui-state' ).innerText = data.State || "WAITING";

                        let gVal = data.G || 0;
                        let gArrow = gVal ≥ 0 ? '⬆️' : '⬇️';
                        let gColor = gVal ≥ 0 ? 'text-green' : 'text-red' ;
                        let gBorder = gVal ≥ 0 ? 'border-[#22c55e]/30 bg-[#1a2e20]/40' : 'border-[#ef4444]/30 bg-[#2e1a1a]/40';

                        document.getElementById('ui-g').innerHTML = `<span class="${gColor}">${gVal.toFixed(2)} ${gArrow}</span>`;
                        document.getElementById('g-card').className = `card flex-1 flex flex-col items-center justify-center p-3 ${gBorder}`;

                        // 2. Gauge (Mapped from -5 to +5)
                        let normalizedG = Math.max(0, Math.min(1, (gVal+5)/10));
                        let angle = (normalizedG * 180) - 90;
                        document.getElementById('needle-group').style.transform = `translate(50px, 50px) rotate(${angle}deg)`;

                        // 3. Sync & Chart
                        document.getElementById('ui-sync').innerText = data.Sync_S || " -- ";
                        document.getElementById('ui-sync').style.color = data.Sync_C || "#22c55e";

                        mainChart.data.datasets[0].data.push(data.H_joint || 0);
                        mainChart.data.datasets[1].data.push(data.MI || 0);
                        if(mainChart.data.datasets[0].data.length > 30) {
                            mainChart.data.datasets[0].data.shift();
                            mainChart.data.datasets[1].data.shift();
                        }
                        mainChart. update();

                        // 4. Energy & Slope Bars
                        let intE = data.Internal_E || 0;
                        document.getElementById('ui-internal').innerText = intE.toFixed(2) + " BTC";
                        document.getElementById('ui-e-state' ).innerText = data.Energy_S || "--";
                        document.getElementById('ui-e-state').style.color = data.Energy_C || "#fff";
                        // Fill bar assuming 50 BTC is a "high" 15m volume burst
                        document.getElementById('bar-internal').style.height= `${Math.min(100, (intE/50)*100)}%`;

                        let slope = data.Slope || 0;
                        document.getElementById('ui-slope').innerText = slope.toFixed(5);
                        document.getElementById('ui-slope-state').innerText = data.Energy_T || "--";
                        document.getElementById('ui-slope-state').style.color = data.Energy_C || "#fff";

                        document.getElementById('bar-slope').style.height = `${Math.min(100, Math.abs(slope) * 20000)}%`;

                        // 5. Entropy Tags
                        document.getElementById('ui-bid').innerText = data.Bid_E ? data.Bid_E.toFixed(2) : "0.00";
                        document.getElementById('ui-trade').innerText = data.TE ? data.TE.toFixed(2) : "0.00";
                        document.getElementById('ui-ask').innerText = data.Ask_E ? data.Ask_E.toFixed(2) : "0.00";

                        let bidTag = getEntropyTag(data.Bid_E || 0);
                        document.getElementById('tag-bid').innerText = bidTag.text;
                        document.getElementById('tag-bid').style.color = bidTag.color;
                        
                        let tradeTag = getEntropyTag(data.TE || 0);
                        document.getElementById('tag-trade').innerText = tradeTag.text;
                        document.getElementById('tag-trade').style.color = tradeTag.color;

                        let askTag = getEntropyTag(data.Ask_E || 0);
                        document.getElementById('tag-ask').innerText = askTag.text;
                        document.getElementById('tag-ask').style.color = askTag.color;

                    } catch (e) {
                        console.log("Awaiting Python Data...");
                    }
                }

                setInterval(updateDashboard, 2000);
                updateDashboard(); 
            </script>
            </body>
            </html>
            """
            # Save it as a webpage
            with open("dashboard.html", "w", encoding = "utf-8") as f:
                f.write(html_content)
asyncio.run(listen())
