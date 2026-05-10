import asyncio
import logging
import ccxt.pro as ccxtpro
import aiohttp
import sys
from datetime import datetime, timezone

# ==============================================================================
# ⚙️ INSTITUTIONAL CONFIGURATION
# ==============================================================================
TELEGRAM_BOT_TOKEN = "8680552437:AAEi2snvFkrCntcUnqA1_prKpwj1pt5v0J4"
TELEGRAM_CHAT_ID = "6704198398"

SYMBOL = 'BTC/USDT'
EXCHANGES = ['binance', 'bybit', 'okx']

# Sweep Threshold: How many BTC must be swept in a single millisecond to trigger?
WHALE_THRESHOLD_BTC = 5.0  

# ==============================================================================
# 📊 LOGGING & STATE SETUP
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("WhaleRadar")

# Decoupled queue for Telegram to ensure WebSocket data never lags
alert_queue = asyncio.Queue()

# Global state to store live Level 2 Order Book data
order_book_state = {ex: {'bids': 0, 'asks': 0} for ex in EXCHANGES}

# ==============================================================================
# 🛡️ PRE-FLIGHT NETWORK & SSL CHECK (UPGRADED)
# ==============================================================================
async def test_connections():
    """Tests APIs. If one fails, it removes it from the list instead of crashing."""
    global EXCHANGES
    logger.info("Running pre-flight network and SSL checks...")
    
    working_exchanges = []
    
    for ex_name in EXCHANGES:
        exchange_class = getattr(ccxtpro, ex_name)
        exchange = exchange_class({'enableRateLimit': True})
        try:
            await exchange.load_markets()
            logger.info(f"✅ {ex_name.upper()} API reachable.")
            working_exchanges.append(ex_name)
        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"❌ {ex_name.upper()} Connection Failed! Skipping this exchange.")
            
            # Diagnose the exact issue
            if "certificate verify failed" in error_msg or "ssl" in error_msg:
                logger.error("👉 DIAGNOSIS: SSL Error. Your Windows Clock is wrong (Year is not 2024).")
            elif "451" in error_msg or "restricted" in error_msg:
                logger.error("👉 DIAGNOSIS: Geo-Block. Your IP is blocked by this exchange (e.g. US IP).")
            else:
                logger.error(f"👉 DIAGNOSIS: {type(e).__name__}: {e}")
        finally:
            await exchange.close()
            
    if not working_exchanges:
        logger.critical("🚨 ALL EXCHANGES FAILED! Please fix your internet/clock/VPN and try again.")
        sys.exit(1)
        
    # Update the global list to ONLY use the ones that actually work
    EXCHANGES = working_exchanges

# ==============================================================================
# 🚀 WORKER 1: TELEGRAM DISPATCHER
# ==============================================================================
async def telegram_worker():
    """Consumes alerts from the queue and sends them to Telegram asynchronously."""
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        while True:
            message = await alert_queue.get()
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            try:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Telegram API Error: {await response.text()}")
            except Exception as e:
                logger.error(f"Telegram Network Error: {e}")
            finally:
                alert_queue.task_done()

# ==============================================================================
# 🚀 WORKER 2: LEVEL 2 ORDER BOOK TRACKER
# ==============================================================================
async def watch_order_book(exchange_name, exchange):
    """Maintains a live view of the top 10 levels of the order book."""
    while True:
        try:
            orderbook = await exchange.watch_order_book(SYMBOL, limit=10)
            
            # Sum the volume of the top 10 bids and asks
            bid_vol = sum(bid[1] for bid in orderbook['bids'])
            ask_vol = sum(ask[1] for ask in orderbook['asks'])
            
            # Update global state silently
            if exchange_name not in order_book_state:
                order_book_state[exchange_name] = {'bids': 0, 'asks': 0}
                
            order_book_state[exchange_name]['bids'] = bid_vol
            order_book_state[exchange_name]['asks'] = ask_vol
            
        except Exception as e:
            logger.warning(f"[{exchange_name.upper()}] L2 Book Error: {e}. Retrying in 2s...")
            await asyncio.sleep(2)

# ==============================================================================
# 🚀 WORKER 3: TAPE AGGREGATOR (SWEEP DETECTOR)
# ==============================================================================
async def watch_trades(exchange_name, exchange):
    """Watches the live tape and aggregates trades occurring in the exact same millisecond."""
    logger.info(f"[{exchange_name.upper()}] WebSocket Tape Pipeline Active.")

    while True:
        try:
            trades = await exchange.watch_trades(SYMBOL)
            
            # AGGREGATION LOGIC: Group trades by exact timestamp and side
            aggregated_trades = {}
            
            for t in trades:
                ts = t['timestamp']
                side = str(t.get('side')).upper()
                key = f"{ts}_{side}" 
                
                if key not in aggregated_trades:
                    aggregated_trades[key] = {
                        'amount': 0.0,
                        'price': t.get('price', 0),
                        'side': side,
                        'timestamp': ts,
                        'count': 0
                    }
                
                aggregated_trades[key]['amount'] += t.get('amount', 0)
                aggregated_trades[key]['count'] += 1

            # Process aggregated blocks that exceed our threshold
            for key, block in aggregated_trades.items():
                if block['amount'] >= WHALE_THRESHOLD_BTC:
                    await process_whale_block(exchange_name, block)

        except Exception as e:
            logger.error(f"[{exchange_name.upper()}] Tape Error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

# ==============================================================================
# 🧠 ANALYTICS ENGINE: PROCESS & FORMAT ALERTS
# ==============================================================================
async def process_whale_block(exchange_name, block):
    """Analyzes the block against the L2 order book and triggers alerts."""
    amount = block['amount']
    price = block['price']
    side = block['side']
    count = block['count']
    usd_value = amount * price
    
    # Get L2 Order Book Context
    bids = order_book_state.get(exchange_name, {}).get('bids', 0)
    asks = order_book_state.get(exchange_name, {}).get('asks', 0)
    total_liquidity = bids + asks
    
    # Calculate Order Book Imbalance (OBI)
    obi = ((bids - asks) / total_liquidity) if total_liquidity > 0 else 0
    obi_percentage = obi * 100
    
    if obi > 20:
        book_context = "🟢 Heavy Bid Support (Buyers stacking)"
    elif obi < -20:
        book_context = "🔴 Heavy Ask Resistance (Sellers stacking)"
    else:
        book_context = "⚪ Balanced Book"

    # UI Formatting
    action_emoji = "🟢" if side == "BUY" else "🔴"
    action_text = "AGGRESSIVE MARKET BUY" if side == "BUY" else "AGGRESSIVE MARKET SELL"
    timestamp_str = datetime.fromtimestamp(block['timestamp'] / 1000, tz=timezone.utc).strftime('%H:%M:%S.%f')[:-3]
    
    terminal_msg = (f"{action_emoji} [{timestamp_str}] {exchange_name.upper():<7} | "
                    f"{side:<4} {amount:>6.2f} BTC @ ${price:,.2f} | "
                    f"Swept {count} orders | OBI: {obi_percentage:+.1f}%")
    
    # Print to terminal with color
    if side == "BUY":
        print(f"\033[92m{terminal_msg}\033[0m")
    else:
        print(f"\033[91m{terminal_msg}\033[0m")
        
    # Telegram Formatting
    tg_msg = (
        f"{action_emoji} <b>INSTITUTIONAL SWEEP DETECTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Exchange:</b> {exchange_name.upper()}\n"
        f"<b>Action:</b> {action_text}\n"
        f"<b>True Size:</b> {amount:,.2f} BTC\n"
        f"<b>Notional:</b> ${usd_value:,.0f}\n"
        f"<b>Execution:</b> Swept {count} resting orders\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📊 Level 2 Book Context:</b>\n"
        f"Order Book Imbalance: {obi_percentage:+.2f}%\n"
        f"State: {book_context}\n"
        f"<i>Time: {timestamp_str} UTC</i>"
    )
    
    # Push to Telegram queue
    await alert_queue.put(tg_msg)

# ==============================================================================
# ⚙️ MAIN ENGINE SUPERVISOR
# ==============================================================================
async def main():
    print("\n" + "="*80)
    print(" 📡 ADVANCED L2 & TAPE MICROSTRUCTURE ENGINE | ASYNC PIPELINE")
    print(f" Target: {SYMBOL} | Sweep Threshold: {WHALE_THRESHOLD_BTC} BTC")
    print("="*80 + "\n")
    
    # 1. Run Pre-Flight Checks (Will skip broken exchanges)
    await test_connections()
    print("-" * 80)
    
    # 2. Start Telegram Background Worker
    asyncio.create_task(telegram_worker())
    
    tasks = []
    exchanges_to_close = []

    # 3. Initialize Exchange Connections and Workers
    for ex_name in EXCHANGES:
        exchange_class = getattr(ccxtpro, ex_name)
        exchange = exchange_class({
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        exchanges_to_close.append(exchange)
        
        # Add Tape and L2 Book tasks for this exchange
        tasks.append(watch_trades(ex_name, exchange))
        tasks.append(watch_order_book(ex_name, exchange))
        
    try:
        # 4. Run everything concurrently
        if tasks:
            await asyncio.gather(*tasks)
        else:
            logger.error("No valid exchanges left to monitor. Exiting.")
    finally:
        logger.info("Shutting down exchange connections gracefully...")
        for exchange in exchanges_to_close:
            await exchange.close()

if __name__ == "__main__":
    # Windows Asyncio Policy Fix
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Engine Shutdown by Operator.")
