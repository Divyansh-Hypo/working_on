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
    while True:
        try:
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
                        "Last_Update": datetime.datetime.now().strftime("%H:%M:%S"),
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
                        with open("live_data.json", "w", encoding="utf-8") as f:
                            json.dump(payload, f)
                    except:
                        pass
        
                    try:
                        # Only push to cloud every 50 trades so you don't get banned!
                        if trade_count % 50 == 0:
                            push_to_cloud(payload)
                    except :
                        pass
        
                            
                    
                
                
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
                    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                    <style>
                        :root { --bg:#0a0e14; --panel:#111722; --line:#1e222d; --txt:#d7e4ff; --muted:#7e8da9; --up:#39d98a; --down:#ff5c6a; --warn:#ffcb52; --blue:#4da8ff; }
                        *{box-sizing:border-box;min-width:0}
                        html,body{width:100%;height:100%;margin:0;overflow:hidden}
                        body{font-family:"JetBrains Mono",monospace;background:radial-gradient(circle at top,#172238,var(--bg) 54%);color:var(--txt);display:grid;place-items:center;padding:6px}
                        .terminal{width:min(100vw - 12px,430px);height:min(100vh - 12px,932px);padding:8px;border:1px solid #2d3442;border-radius:16px;background:linear-gradient(180deg,#111827,#0a0e14);display:grid;grid-template-rows:auto auto 17% 18% 1fr auto;gap:7px;overflow:hidden}
                        .box,.zone,.energy,.meter{border:1px solid var(--line);border-radius:10px;background:linear-gradient(180deg,#121a27,#0f1521);padding:7px;box-shadow:0 0 0 1px rgba(77,168,255,.04), 0 0 16px rgba(77,168,255,.05) inset;overflow:hidden}
                        .headline{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
                        .title{font-size:14px;font-weight:700;letter-spacing:.8px;text-transform:uppercase}
                        .sub{font-size:10px;color:var(--muted)}
                        .price{font-size:14px;font-weight:700;color:#9fc7ff;padding:4px 10px;border-radius:999px;border:1px solid var(--line);background:#0f1724}
                        .row{display:grid;grid-template-columns:1fr .58fr;gap:7px}
                        .k{font-size:9px;color:#8b9dbd;text-transform:uppercase;letter-spacing:.5px}
                        .big{font-size:24px;font-weight:700;line-height:1.0;margin-top:3px}
                        .mono{font-family:"JetBrains Mono",monospace}
                        .led{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px;box-shadow:0 0 10px currentColor;animation:pulse 1.2s infinite ease-in-out}
                        @keyframes pulse{0%,100%{opacity:.45;transform:scale(1)}50%{opacity:1;transform:scale(1.2)}}
                        canvas{width:100%;height:100%;display:block}
                        .sync-chip{padding:2px 8px;border-radius:999px;border:1px solid var(--line);background:#101827;font-size:11px;font-weight:700}
                        .meter-grid{display:grid;grid-template-columns:1.35fr .85fr;gap:7px;height:100%}
                        .meter .hdr{display:flex;justify-content:space-between;align-items:center}
                        .meter .val{font-size:20px;font-weight:700}
                        .entry-alert{border-color:#d8b145!important;box-shadow:0 0 10px rgba(216,177,69,.45), inset 0 0 14px rgba(216,177,69,.14)!important}
                        .meter .scale{font-size:9px;color:var(--muted);display:flex;justify-content:space-between}
                        .scale-wide{display:grid!important;grid-template-columns:repeat(11,1fr);text-align:center;font-size:8px;letter-spacing:0}
                        .signed{position:relative;height:20px;border:1px solid #1c3155;border-radius:8px;background:#0a111d;overflow:hidden;margin-top:8px}
                        .signed .zero{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:#7f90ad}
                        .signed .neg{position:absolute;right:50%;top:0;bottom:0;width:0;background:linear-gradient(90deg,#ff5c6a,#f4c84a)}
                        .signed .pos{position:absolute;left:50%;top:0;bottom:0;width:0;background:linear-gradient(90deg,#f4c84a,#39d98a)}
                        .energy-state-main{margin-top:12px;font-size:20px;font-weight:700;line-height:1;text-align:center}
                        .energy-top{display:flex;justify-content:space-between;align-items:center}
                        .zone-wrap{display:flex;flex-direction:column;gap:6px;overflow:hidden}
                        .zone h4{margin:0 0 4px 0;font-size:10px;color:#9ab2d5;letter-spacing:.65px;text-transform:uppercase}
                        .mrow{display:grid;grid-template-columns:110px 1fr 70px;align-items:center;gap:6px;padding:2px 0}
                        .mname{font-size:10px;color:#8ca3c8}
                        .mval{font-size:14px;font-weight:700;color:#eaf2ff;text-align:center}
                        .spark{width:70px;height:16px;border:1px solid #1a2f55;border-radius:3px;background:#0b1321}
                        .energy{display:flex;justify-content:flex-end;align-items:center;padding:6px 8px}
                        .bars{width:48%}
                        .bars .trk{height:6px;border:1px solid #1c3155;background:#0a111d;border-radius:6px;overflow:hidden;margin-top:4px}
                        .bars .fill{height:100%;width:0;transition:width .28s linear}
                        .foot{text-align:center;color:#6f84a7;font-size:9px}
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
                        <div class="sub"><span id="state-led" class="led" style="color:var(--warn)"></span>Trend: <span id="ui-energy-trend">--</span></div>
                        </article>
                        <article class="box">
                        <div class="k">$ Internal USD</div>
                        <div class="mono" style="font-size:20px;font-weight:700;line-height:1" id="ui-ieusd-top">0.00</div>
                        <div class="sub">Energy USD</div>
                        </article>
                    </section>

                    <section class="meter-grid">
                        <article class="meter" id="free-box">
                        <div class="hdr"><div class="k" style="color:#adc5e8">Free Energy (G)</div><div class="val mono" id="ui-g">0.0000</div></div>
                        <div class="signed"><div class="neg" id="free-neg"></div><div class="pos" id="free-pos"></div><div class="zero"></div></div>
                        <div class="scale scale-wide"><span>-5</span><span>-4</span><span>-3</span><span>-2</span><span>-1</span><span>0</span><span>1</span><span>2</span><span>3</span><span>4</span><span>5</span></div>
                        </article>
                        <article class="meter">
                        <div class="energy-top"><div class="k" style="color:#adc5e8">Energy State</div><div class="val mono" id="ui-energy-trend-chip">--</div></div>
                        <div id="ui-energy-color-text" class="energy-state-main">--</div>
                        <div class="trk" style="margin-top:10px;height:8px"><div id="bar-energy-state" class="fill" style="width:0%;background:linear-gradient(90deg,#f4c84a,#39d98a)"></div></div>
                        </article>
                    </section>

                    <section class="box">
                        <div style="display:flex;justify-content:space-between;align-items:center"><div class="k" style="color:#c2d6f3">JOINT ENTROPY vs MUTUAL INFO</div><div class="sync-chip">SYNC <span id="ui-sync">--</span></div></div>
                        <div style="height:100%"><canvas id="lineChart"></canvas></div>
                    </section>

                    <section class="zone-wrap">
                        <article class="zone" id="zone-a">
                        <h4>Zone A • Thermodynamics</h4>
                        <div class="mrow"><span class="mname">Free Energy (G)</span><span class="mval" id="z-g">0.0000</span><canvas class="spark" id="sp-g"></canvas></div>
                        <div class="mrow"><span class="mname">Internal_E</span><span class="mval" id="z-internal">0.0000</span><canvas class="spark" id="sp-internal"></canvas></div>
                        <div class="mrow"><span class="mname">Slope</span><span class="mval" id="z-slope">0.000000</span><canvas class="spark" id="sp-slope"></canvas></div>
                        </article>
                        <article class="zone" id="zone-b">
                        <h4>Zone B • Order Book</h4>
                        <div class="mrow"><span class="mname">Bid_E</span><span class="mval" id="z-bid">0.0000</span><canvas class="spark" id="sp-bid"></canvas></div>
                        <div class="mrow"><span class="mname">Ask_E</span><span class="mval" id="z-ask">0.0000</span><canvas class="spark" id="sp-ask"></canvas></div>
                        <div class="mrow"><span class="mname">Trade Entropy</span><span class="mval" id="z-te">0.0000</span><canvas class="spark" id="sp-te"></canvas></div>
                        </article>
                        <article class="zone" id="zone-c">
                        <h4>Zone C • System Health</h4>
                        <div class="mrow"><span class="mname">Sync_S</span><span class="mval" id="z-sync">--</span><canvas class="spark" id="sp-sync"></canvas></div>
                        <div class="mrow"><span class="mname">Joint Entropy</span><span class="mval" id="z-hj">0.0000</span><canvas class="spark" id="sp-hj"></canvas></div>
                        <div class="mrow"><span class="mname">Mutual Info</span><span class="mval" id="z-mi">0.0000</span><canvas class="spark" id="sp-mi"></canvas></div>
                        </article>
                        <article class="energy">
                        <div class="sub" style="width:100%;text-align:center;font-family:'Georgia',serif;font-size:12px;letter-spacing:0.6px">made by DD</div>
                        </article>
                    </section>

                    <div class="foot">Midnight terminal layout • dual meters • smooth trend lines</div>
                    </main>

                    <script>
                    const chart = new Chart(document.getElementById('lineChart').getContext('2d'), {
                    type:'line',
                    data:{ labels:Array(20).fill(''), datasets:[
                        {label:'Joint Entropy',data:[],borderColor:'#ff5c8a',borderWidth:2,pointRadius:0,tension:.35},
                        {label:'Mutual Info',data:[],borderColor:'#4da8ff',borderWidth:2,pointRadius:0,tension:.35}
                    ]},
                    options:{ responsive:true, maintainAspectRatio:false, animation:false,
                        plugins:{ legend:{ labels:{ color:'#c2d6f3', boxWidth:10, font:{size:10}, usePointStyle:true, pointStyle:'rect' } } },
                        scales:{ x:{display:false}, y:{ ticks:{color:'#b9cff0',font:{size:10,weight:'600'}}, grid:{color:'rgba(98,126,168,.24)'} } }
                    }
                    });

                    const hist = { g:[], internal:[], slope:[], bid:[], ask:[], te:[], sync:[], hj:[], mi:[] };
                    const maxHist = 24;
                    function pushHist(key,val){ hist[key].push(Number(val)||0); if(hist[key].length>maxHist) hist[key].shift(); }
                    function drawSpark(id, arr, color){ const c=document.getElementById(id),ctx=c.getContext('2d'); const w=c.width=70,h=c.height=16; ctx.clearRect(0,0,w,h); if(arr.length<2) return; const min=Math.min(...arr),max=Math.max(...arr),span=(max-min)||1; ctx.strokeStyle=color; ctx.lineWidth=1.3; ctx.beginPath(); arr.forEach((v,i)=>{ const x=(i/(arr.length-1))*(w-2)+1; const y=h-1-((v-min)/span)*(h-2); i?ctx.lineTo(x,y):ctx.moveTo(x,y); }); ctx.stroke(); }
                    function colorState(s){ if(s==='ORDER BUILDING') return 'var(--up)'; if(s==='DECAYING') return 'var(--down)'; if(s==='STABLE') return 'var(--warn)'; return '#8eaed9'; }
                    function fmt(v,d=4){ const n=Number(v||0); if(Math.abs(n)>=1e6) return (n/1e6).toFixed(2)+'M'; if(Math.abs(n)>=1e3) return (n/1e3).toFixed(2)+'k'; return n.toFixed(d); }
                    function to12h(hms){ if(!hms||hms.indexOf(':')===-1) return '--:--:--'; const [h,m,s]=hms.split(':').map(Number); const ampm=h>=12?'PM':'AM'; const hh=((h+11)%12)+1; return `${String(hh).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')} ${ampm}`; }

                    async function getRecord(){ const BIN_ID='69c3f2eeaa77b81da91ad9f7',MASTER_KEY='$2a$10$2DYlbo.m2VpFI6hg8cNrdeVP4XB/lVJ1R4v0bvL7W4hw6bDzvAbPq'; try{ const r=await fetch(`https://api.jsonbin.io/v3/b/${BIN_ID}/latest`,{headers:{'X-Master-Key':MASTER_KEY}}); const b=await r.json(); if(b&&b.record) return b.record; }catch(_){ } if(location.protocol!=='file:'){ try{ const l=await fetch(`live_data.json?t=${Date.now()}`); return await l.json(); }catch(_){ } } return {}; }

                    async function updateDashboard(){
                    const d=await getRecord();
                    const g=Number(d.G||0), mi=Number(d.MI||0), hj=Number(d.H_joint||0), slope=Number(d.Slope||0);
                    const te=Number(d.TE||0), bid=Number(d.Bid_E||0), ask=Number(d.Ask_E||0), ie=Number(d.Internal_E||0), ieusd=Number(d.IE_USD||0), price=Number(d.Price||0);

                    document.getElementById('ui-time').textContent=to12h(d.Last_Update);
                    document.getElementById('ui-price').textContent=price?`BTC ${price.toFixed(2)}`:'BTC --';
                    document.getElementById('ui-state').textContent=d.State||'WAITING'; document.getElementById('ui-state').style.color=colorState(d.State);
                    document.getElementById('state-led').style.color=colorState(d.State);
                    document.getElementById('ui-energy-trend').textContent=d.Energy_T||'--'; document.getElementById('ui-energy-trend').style.color=d.Energy_C||'#8eaed9';

                    document.getElementById('ui-g').textContent=g.toFixed(4); document.getElementById('ui-g').style.color=g>=0?'var(--up)':'var(--down)';
                    document.getElementById('free-box').classList.toggle('entry-alert', g > 0.8);
                    document.getElementById('ui-energy-trend-chip').textContent=d.Energy_T||'--'; document.getElementById('ui-energy-trend-chip').style.color=d.Energy_C||'#8eaed9';
                    document.getElementById('ui-energy-color-text').textContent=d.Energy_S||'--'; document.getElementById('ui-energy-color-text').style.color=d.Energy_C||'#8eaed9';
                    const clampedG=Math.max(-5,Math.min(5,g));
                    const pct=(Math.abs(clampedG)/5)*50;
                    document.getElementById('free-neg').style.width=clampedG<0?`${pct}%`:'0%';
                    document.getElementById('free-pos').style.width=clampedG>0?`${pct}%`:'0%';
                    const energyBar = (d.Energy_T==='UP') ? 100 : (d.Energy_T==='DOWN' ? 20 : 50);
                    document.getElementById('bar-energy-state').style.width = `${energyBar}%`;

                    document.getElementById('ui-ieusd-top').textContent='$'+Number(ieusd||0).toLocaleString(undefined,{minimumFractionDigits:0,maximumFractionDigits:0}); document.getElementById('ui-sync').textContent=d.Sync_S||'--'; document.getElementById('ui-sync').style.color=d.Sync_C||'#8eaed9';

                    document.getElementById('z-g').textContent=g.toFixed(4); document.getElementById('z-internal').textContent=fmt(ie,4); document.getElementById('z-slope').textContent=slope.toFixed(6);
                    document.getElementById('z-bid').textContent=bid.toFixed(4); document.getElementById('z-ask').textContent=ask.toFixed(4); document.getElementById('z-te').textContent=te.toFixed(4);
                    document.getElementById('z-sync').textContent=d.Sync_S||'--'; document.getElementById('z-hj').textContent=hj.toFixed(4); document.getElementById('z-mi').textContent=mi.toFixed(4);

                    pushHist('g',g); pushHist('internal',ie); pushHist('slope',slope); pushHist('bid',bid); pushHist('ask',ask); pushHist('te',te); pushHist('sync',(d.Sync_S==='HIGH'?3:d.Sync_S==='MEDIUM'?2:d.Sync_S==='LOW'?1:0)); pushHist('hj',hj); pushHist('mi',mi);
                    drawSpark('sp-g',hist.g,'#4da8ff'); drawSpark('sp-internal',hist.internal,'#4da8ff'); drawSpark('sp-slope',hist.slope,'#ffcb52');
                    drawSpark('sp-bid',hist.bid,'#39d98a'); drawSpark('sp-ask',hist.ask,'#ff5c6a'); drawSpark('sp-te',hist.te,'#ffcb52');
                    drawSpark('sp-sync',hist.sync,'#8eaed9'); drawSpark('sp-hj',hist.hj,'#ff5c8a'); drawSpark('sp-mi',hist.mi,'#4da8ff');

                    chart.data.datasets[0].data.push(hj); chart.data.datasets[1].data.push(mi); if(chart.data.datasets[0].data.length>20){ chart.data.datasets[0].data.shift(); chart.data.datasets[1].data.shift(); }
                    chart.update('none');
                    }
                    setInterval(updateDashboard,1200); updateDashboard();
                    </script>
                    </body>
                    </html>

            """
            # Save it as a webpage
                    with open("dashboard.html", "w", encoding = "utf-8") as f:
                        f.write(html_content)
        except Exception as e:
            print(f"Websocket reconnecting after error: {e}")
            await asyncio.sleep(3)

asyncio.run(listen())
