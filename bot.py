import os
import time
import pandas as pd
import ccxt
from datetime import datetime

# ========================= CONFIG =========================
SYMBOL       = os.getenv('SYMBOL', 'BTC/USDT:USDT')
TIMEFRAME    = os.getenv('TIMEFRAME', '15m')
LEVERAGE     = int(os.getenv('LEVERAGE', '10'))
POSITION_PCT = float(os.getenv('POSITION_PCT', '80'))

# =========================================================

exchange = ccxt.okx({
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSPHRASE'),
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True,
})

# Set hedge mode
try:
    exchange.set_position_mode(True, SYMBOL)
except:
    pass

# Set leverage
exchange.set_leverage(LEVERAGE, SYMBOL)

print(f"🚀 OKX SMA 14/28 Bot STARTED | {SYMBOL} | {TIMEFRAME} | Leverage {LEVERAGE}x")

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
                print("🔄 Closing SHORT to reverse...")
                exchange.create_order(SYMBOL, 'market', 'buy', current_contracts, None, {'tdMode': 'cross', 'posSide': 'short'})
            print(f"🟢 ENTERING LONG | Size: {amount}")
            exchange.create_order(SYMBOL, 'market', 'buy', amount, None, {'tdMode': 'cross', 'posSide': 'long'})

        elif short_condition and current_side != 'short':
            if current_side == 'long':
                print("🔄 Closing LONG to reverse...")
                exchange.create_order(SYMBOL, 'market', 'sell', current_contracts, None, {'tdMode': 'cross', 'posSide': 'long'})
            print(f"🔴 ENTERING SHORT | Size: {amount}")
            exchange.create_order(SYMBOL, 'market', 'sell', amount, None, {'tdMode': 'cross', 'posSide': 'short'})

        time.sleep(60)

    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(30)
