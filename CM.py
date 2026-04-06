import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
from scipy.stats import skew

exchange = ccxt.binance()

def fetch_live_data(symbol='BTC/USDT', timeframe='15m', days=12):
    limit = days * 24 * 4
    print(f"fetching last {days} days of {symbol} data...")
    bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def smooth_and_find_nodes(profile_df, sigma_val=2.0):
    raw_volume = profile_df['volume'].values
    smoothed_vol = gaussian_filter1d(raw_volume, sigma=sigma_val)
    peaks, _ = find_peaks(smoothed_vol, distance=5)
    return smoothed_vol, peaks

def calculate_hvn_intensity(profile_df, peak_indices, smoothed_vol):
    hvn_data = []
    for peak in peak_indices:
        start = max(0, peak - 5)
        end = min(len(profile_df) - 1, peak + 5)
        node_slice = smoothed_vol[start:end]

        tilt_val = skew(node_slice)
        
        peak_volume = smoothed_vol[peak]
        max_volume = np.max(smoothed_vol)
        intensity = (peak_volume / max_volume) * 10

        hvn_data.append({
            'price': profile_df.iloc[peak]['price_bin'],
            'intensity': round(intensity, 2),
            'tilt': round(tilt_val, 3),
            'type': "Main HVN" if intensity > 8 else "Macro HVN"
        })
    return pd.DataFrame(hvn_data)

def fetch_tradinglite_magnets(symbol='BTC/USDT', min_volume=400):
    depth = exchange.fetch_order_book(symbol, limit=100)
    bids = np.array(depth['bids'])
    asks = np.array(depth['asks'])

    big_bids = bids[bids[:, 1] >= min_volume]
    big_asks = asks[asks[:, 1] >= min_volume]
    return big_bids, big_asks

def calculate_magnet_strength_zone(hvn_price, big_bids, big_asks, zone_percentage = 0.0015):
    padding = hvn_price * zone_percentage
    lower_bound = hvn_price - padding
    upper_bound = hvn_price + padding

    zone_bids = big_bids[(big_bids[:, 0] >= lower_bound) & (big_bids[:, 0] <= upper_bound)]
    zone_asks = big_asks[(big_asks[:, 0] >= lower_bound) & (big_asks[:, 0] <= upper_bound)]

    max_bid = np.max(zone_bids[:, 1]) if len(zone_bids) > 0 else 0
    max_ask = np.max(zone_asks[:, 1]) if len(zone_asks) > 0 else 0

    if max_bid >= max_ask:
        return max_bid, "Bid"
    return max_ask, "Ask"

def calculate_liquidity_pull(current_price, hvn_reports, big_bids, big_asks):
    cm_results = []

    for index, row in hvn_reports.iterrows():
        hvn_price = row['price']
        base_intensity = row['intensity']
        tilt = row['tilt']

        mag_size, mag_type = calculate_magnet_strength_zone(hvn_price, big_bids, big_asks, zone_percentage = 0.0015)

        final_score = base_intensity

        if mag_size >= 400:
            final_score += 3.0
        if mag_size >= 600:
            final_score += 5.0
        
        if tilt > 0.8:
            final_score += 1.0

        cm_results.append({
            'price': hvn_price,
            'cm_score': min(round(final_score, 2), 15.0),
            'type': row['type'],
            'wall_size': mag_size,
            'conical_tilt': "UP_tilt" if tilt > 0 else "DOWN-tilt"
        })

    return pd.DataFrame(cm_results)

def get_institutional_heatmap(current_price, range_val = 3000, min_orders = 50):
    depth = exchange.fetch_order_book('BTC/USDT', limit = 1000)

    upper_limit = current_price + range_val
    lower_limit = current_price - range_val

    heatmap_data = []

    for price, size in depth['bids']:
        if lower_limit <= price <= upper_limit and size >= min_orders:
            heatmap_data.append({'price': price, 'total_size': size,'bids': size, 'asks': 0, 'type': 'BID_WALL'})

    for price, size in depth['asks']:
        if lower_limit <= price <= upper_limit and size >= min_orders:
            heatmap_data.append({'price': price, 'total_size': size ,'bids': 0, 'asks': size, 'type': 'ASK_WALL' })

    df_heatmap = pd.DataFrame(heatmap_data)
    if df_heatmap.empty:
        return df_heatmap
    return df_heatmap.sort_values(by='price', ascending = False)

while True:
    try:
        print(f"\n---SCANNING MARKET: {datetime.now().strftime('%H:%M:%S')} ---")
        
        df = fetch_live_data()
        current_price = df['close'].iloc[-1]

        bin_size = 20
        df['price_bin'] = (df['close'] / bin_size).round() * bin_size
        volume_profile = df.groupby('price_bin')['volume'].sum().reset_index()
        
        smoothed_data, peak_indices = smooth_and_find_nodes(volume_profile)
        volume_profile['smoothed_volume'] = smoothed_data
        
        hvn_report = calculate_hvn_intensity(volume_profile, peak_indices, smoothed_data)

        big_bids, big_asks = fetch_tradinglite_magnets()
        
        final_signals = calculate_liquidity_pull(current_price, hvn_report, big_bids, big_asks)
        print("\n[ RADAR A: INSTITUTI0ONAL FORTRESSES (SCM)]")                                                  
        print(final_signals[final_signals['cm_score'] >= 5.0].sort_values(by='cm_score', ascending=False))
        
        heatmap_signals = get_institutional_heatmap(current_price, range_val = 3000, min_orders = 50)
        
        print("\n [ RADAR B: LIVE HEATMAP MAGNETS (300+ BTC) ]")
        if not heatmap_signals.empty:
            print(heatmap_signals)
        else:
            print("NO Major Institutional Wall is present within range")
        print("\n" + "-"*50)
        time.sleep(300)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(10)
