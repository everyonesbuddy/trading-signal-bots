import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import datetime

# ✅ Use Binance Futures
# exchange = ccxt.binance({
#     'options': {'defaultType': 'future'}
# })

# exchange = ccxt.deribit({
#     'enableRateLimit': True,
# })

# exchange = ccxt.mexc({
#     'enableRateLimit': True,
#     'options': { 'defaultType': 'swap' },  # for perpetuals
# })

# exchange = ccxt.bybit({
#     'options': {'defaultType': 'future'}
# })

exchange = ccxt.okx({
    'enableRateLimit': True,
    'options': { 'defaultType': 'futures' },  # or 'swap'
})

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1399851296349094120/DFIeqQyYyeZZ_1AJbJmI8JP39mqJAQLgSuWdreYyoCqvT1azw4YxAjJqbKGVtxn8l9Py"

def send_discord_alert(message):
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send alert: {e}")

def get_futures_data(symbol="BTC/USDT", timeframe="1h", limit=200):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df

def calculate_indicators(df):
    df["RSI"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"])
    df["MACD_Hist"] = macd["MACDh_12_26_9"]
    df["EMA_50"] = ta.ema(df["close"], length=50)
    df["ATR_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    bbands = ta.bbands(df["close"], length=20, std=2)
    df["BBL"] = bbands["BBL_20_2.0"]
    df["BBU"] = bbands["BBU_20_2.0"]
    stochrsi = ta.stochrsi(df["close"], length=14)
    df["StochRSI_K"] = stochrsi.iloc[:, 0]
    df["StochRSI_D"] = stochrsi.iloc[:, 1]
    df.dropna(inplace=True)
    return df

def check_futures_signals(df):
    latest = df.iloc[-1]
    buy_conditions = [
        latest["RSI"] < 40,
        latest["MACD_Hist"] > 0,
        latest["close"] > latest["EMA_50"],
        latest["StochRSI_K"] > latest["StochRSI_D"],
        latest["close"] < latest["BBL"],
        latest["ATR_14"] > 0
    ]
    short_conditions = [
        latest["RSI"] > 60,
        latest["MACD_Hist"] < 0,
        latest["close"] < latest["EMA_50"],
        latest["StochRSI_K"] < latest["StochRSI_D"],
        latest["close"] > latest["BBU"],
        latest["ATR_14"] > 0
    ]
    buy_score = sum(buy_conditions)
    short_score = sum(short_conditions)

    if buy_score >= 3:
        return "LONG", latest, buy_score
    elif short_score >= 3:
        return "SHORT", latest, short_score
    else:
        return None, latest, 0

def get_funding_rate(symbol):
    try:
        rates = exchange.fapiPublic_get_premiumindex({'symbol': symbol.replace('/', '')})
        return float(rates['lastFundingRate'])
    except Exception:
        return None

def run_futures_bot(symbols):
    for symbol in symbols:
        try:
            df = get_futures_data(symbol)
            if df.empty:
                continue
            df = calculate_indicators(df)
            signal, latest, score = check_futures_signals(df)

            if latest["volume"] < 10:
                continue

            funding_rate = get_funding_rate(symbol)
            funding_msg = f"{funding_rate * 100:.4f}%" if funding_rate is not None else "N/A"

            if signal in ["LONG", "SHORT"]:
                msg = (
                    f"📊 **{signal} SIGNAL (Futures)** for `{symbol}`\n"
                    f"> Price: **${latest['close']:.4f}**\n"
                    f"> RSI: {latest['RSI']:.2f}, MACD Hist: {latest['MACD_Hist']:.2f}\n"
                    f"> StochRSI: K={latest['StochRSI_K']:.2f}, D={latest['StochRSI_D']:.2f}\n"
                    f"> EMA50: {latest['EMA_50']:.2f}, ATR: {latest['ATR_14']:.2f}\n"
                    f"> 📉 BB Bands: [{latest['BBL']:.2f} - {latest['BBU']:.2f}]\n"
                    f"> 🔍 Confidence Score: `{score}/6`\n"
                    f"> ⏱ Funding Rate: `{funding_msg}`\n"
                    f"> Time: {latest.name.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                send_discord_alert(msg)
            else:
                print(f"⛔ No futures signal for {symbol} at {df.index[-1]}")

        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")

# ✅ Recommended Futures Pairs
futures_watchlist = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "AVAX/USDT", "XRP/USDT",
    "PEPE/USDT", "WIF/USDT", "INJ/USDT", "ARB/USDT", "FET/USDT", "OP/USDT"
]

run_futures_bot(futures_watchlist)
