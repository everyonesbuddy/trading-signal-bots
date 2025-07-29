import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import datetime

# 🔗 Your Discord webhook URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1399850966731194509/p6h6_E-ZSKvY-NoO8UXzSsXhqEqPKd1JNPUxrSkakQzesH4tKInqWs4Yid_dW7x7I6uB"

# ✅ Recommended: Use Binance for more pairs and better OHLCV support
# exchange = ccxt.binance()
exchange = ccxt.kraken()

def send_discord_alert(message):
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send alert: {e}")

def get_crypto_data(symbol="BTC/USDT", timeframe="1h", limit=200):
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
    df["BBM"] = bbands["BBM_20_2.0"]
    df["BBU"] = bbands["BBU_20_2.0"]
    stochrsi = ta.stochrsi(df["close"], length=14)
    df["StochRSI_K"] = stochrsi.iloc[:, 0]
    df["StochRSI_D"] = stochrsi.iloc[:, 1]
    df.dropna(inplace=True)
    return df

def check_signals(df):
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
        return "BUY", latest, buy_score
    elif short_score >= 3:
        return "SHORT", latest, short_score
    else:
        return None, latest, 0

def run_crypto_bot(crypto_watchlist):
    for symbol in crypto_watchlist:
        try:
            df = get_crypto_data(symbol)
            if df.empty:
                print(f"⚠️ No data for {symbol}")
                continue

            df = calculate_indicators(df)
            if df.empty:
                print(f"⚠️ Indicators could not be calculated for {symbol}")
                continue

            signal, latest, score = check_signals(df)

            if latest["volume"] < 10:
                print(f"⚠️ Low volume for {symbol} — skipping")
                continue

            if signal == "BUY":
                msg = (
                    f"🚨 **BUY SIGNAL** for `{symbol}`\n"
                    f"> Price: **${latest['close']:.4f}**\n"
                    f"> RSI: {latest['RSI']:.2f}, MACD Hist: {latest['MACD_Hist']:.2f}\n"
                    f"> StochRSI: K={latest['StochRSI_K']:.2f}, D={latest['StochRSI_D']:.2f}\n"
                    f"> ATR: {latest['ATR_14']:.2f}, EMA50: {latest['EMA_50']:.2f}\n"
                    f"> Bollinger Lower Band: {latest['BBL']:.2f}\n"
                    f"> 🔍 Confidence Score: {score}/6\n"
                    f"> Time: {latest.name.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                send_discord_alert(msg)

            elif signal == "SHORT":
                msg = (
                    f"⚠️ **SHORT SIGNAL** for `{symbol}`\n"
                    f"> Price: **${latest['close']:.4f}**\n"
                    f"> RSI: {latest['RSI']:.2f}, MACD Hist: {latest['MACD_Hist']:.2f}\n"
                    f"> StochRSI: K={latest['StochRSI_K']:.2f}, D={latest['StochRSI_D']:.2f}\n"
                    f"> ATR: {latest['ATR_14']:.2f}, EMA50: {latest['EMA_50']:.2f}\n"
                    f"> Bollinger Upper Band: {latest['BBU']:.2f}\n"
                    f"> 🔍 Confidence Score: {score}/6\n"
                    f"> Time: {latest.name.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                send_discord_alert(msg)

            else:
                print(f"⛔ No signal for {symbol} at {df.index[-1]}")

        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")

# 👇 You can expand or adjust the list freely
# crypto_watchlist = [
#     "BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT",
#     "SHIB/USDT", "AVAX/USDT", "MATIC/USDT", "PEPE/USDT",
#     "WIF/USDT", "FET/USDT", "TIA/USDT", "LDO/USDT",
#     "OP/USDT", "INJ/USDT", "ARB/USDT", "SUI/USDT"
# ]
# crypto_watchlist = ["BTC/USD", "ETH/USD", "SOL/USD"]

crypto_watchlist = [
    "BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD",
    "DOGE/USD", "SHIB/USD", "XRP/USD", "ADA/USD", "ARB/USD",
    "INJ/USD", "TIA/USD", "OP/USD", "FET/USD", "PEPE/USD",
    "APT/USD", "WIF/USD"
]



run_crypto_bot(crypto_watchlist)
