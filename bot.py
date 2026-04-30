import os
import time
import pandas as pd
import ccxt
import requests
from datetime import datetime

# ========================= CONFIG =========================
SYMBOL       = os.getenv('SYMBOL', 'BTC/USDT:USDT')
TIMEFRAME    = os.getenv('TIMEFRAME', '15m')
LEVERAGE     = int(os.getenv('LEVERAGE', '10'))
POSITION_PCT = float(os.getenv('POSITION_PCT', '80'))

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# =========================================================

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=10)
    except:
        pass  # Don't crash bot if Telegram fails

exchange = ccxt.okx({
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSPHRASE'),
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True,
})

# DEMO MODE
exchange.set_sandbox_mode(True)
print("✅ DEMO MODE ENABLED")
send_telegram("🚀 <b>OKX SMA 14/28 Bot STARTED</b>\nMode: <b>DEMO</b> | TF: " + TIMEFRAME + " | Lev: " + str(LEVERAGE) + "x")

try:
    exchange.set_position_mode(True, SYMBOL)
    print("✅ Hedge mode set")
except:
    pass

try:
    exchange.set_leverage(LEVERAGE, SYMBOL)
    print(f"✅ Leverage set to {LEVERAGE}x")
except:
    pass

print(f"🚀 OKX SMA 14/28 Bot STARTED | {SYMBOL} | {TIMEFRAME} | Leverage {LEVERAGE}x | DEMO MODE")

last_bar_time = None

while True:
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        current_bar_time = df['timestamp'].iloc[-1]

        if last_bar_time == current_bar_time:
            time.sleep(10)
            continue

        last_bar_time = current_bar_time

        df['sma14'] = df['close'].rolling(window=14).mean()
        df['sma28'] = df['close'].rolling(window=28).mean()
        df = df.dropna()

        if len(df) < 2:
            time.sleep(60)
            continue

        prev_sma14 = df['sma14'].iloc[-2]
        prev_sma28 = df['sma28'].iloc[-2]
        curr_sma14 = df['sma14'].iloc[-1]
        curr_sma28 = df['sma28'].iloc[-1]

        long_condition  = (prev_sma14 <= prev_sma28) and (curr_sma14 > curr_sma28)
        short_condition = (prev_sma14 >= prev_sma28) and (curr_sma14 < curr_sma28)

        positions = exchange.fetch_positions([SYMBOL])
        position = next((p for p in positions if p['symbol'] == SYMBOL and float(p['contracts']) != 0), None)

        current_side = position['side'] if position else None
        current_contracts = float(position['contracts']) if position else 0

        ticker = exchange.fetch_ticker(SYMBOL)
        price = ticker['last']

        balance = exchange.fetch_balance()
        usdt_balance = float(balance.get('USDT', {}).get('total', 0))
        notional_usdt = (usdt_balance * POSITION_PCT / 100) * LEVERAGE
        amount = notional_usdt / price
        amount = float(exchange.amount_to_precision(SYMBOL, amount))

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bar closed | Price: {price:.2f} | Long: {long_condition} | Short: {short_condition} | Position: {current_side or 'FLAT'}")

        if long_condition and current_side != 'long':
            if current_side == 'short':
                msg = f"🔄 <b>REVERSAL</b>\nClosing SHORT → Opening LONG\nPrice: <b>{price:.2f}</b>"
                print("🔄 Closing SHORT to reverse...")
                exchange.create_order(SYMBOL, 'market', 'buy', current_contracts, None, {'tdMode': 'cross', 'posSide': 'short'})
                send_telegram(msg)

            msg = f"🟢 <b>LONG ENTRY</b>\nPrice: <b>{price:.2f}</b>\nSize: <b>{amount}</b> | Lev: {LEVERAGE}x"
            print(f"🟢 ENTERING LONG | Size: {amount}")
            exchange.create_order(SYMBOL, 'market', 'buy', amount, None, {'tdMode': 'cross', 'posSide': 'long'})
            send_telegram(msg)

        elif short_condition and current_side != 'short':
            if current_side == 'long':
                msg = f"🔄 <b>REVERSAL</b>\nClosing LONG → Opening SHORT\nPrice: <b>{price:.2f}</b>"
                print("🔄 Closing LONG to reverse...")
                exchange.create_order(SYMBOL, 'market', 'sell', current_contracts, None, {'tdMode': 'cross', 'posSide': 'long'})
                send_telegram(msg)

            msg = f"🔴 <b>SHORT ENTRY</b>\nPrice: <b>{price:.2f}</b>\nSize: <b>{amount}</b> | Lev: {LEVERAGE}x"
            print(f"🔴 ENTERING SHORT | Size: {amount}")
            exchange.create_order(SYMBOL, 'market', 'sell', amount, None, {'tdMode': 'cross', 'posSide': 'short'})
            send_telegram(msg)

        time.sleep(60)

    except Exception as e:
        error_msg = f"❌ Error: {e}"
        print(error_msg)
        send_telegram(error_msg)
        time.sleep(30)
