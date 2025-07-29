import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime
import requests

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1399849142116814868/I-PCwu9QNdUYTEIJhAdoZQwX1gjt-mwntbQI2c5X4g6nzX9R8Q1eKUwmysOwJDEfESxk"

def send_discord_alert(message):
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send alert: {e}")

def get_stock_data(ticker, period="5d", interval="5m"):
    print(f"📥 Downloading historical data for {ticker}...")
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, group_by='ticker')

    if isinstance(df.columns, pd.MultiIndex):
        df = df[ticker]

    if df.empty or "Close" not in df.columns:
        print(f"⚠️ No usable 'Close' data for {ticker}")
        return pd.DataFrame()

    if "Volume" not in df.columns or df["Volume"].iloc[-1] < 500000:
        print(f"⚠️ Low volume for {ticker} ({df['Volume'].iloc[-1] if 'Volume' in df.columns else 'N/A'}), skipping")
        return pd.DataFrame()

    try:
        df["RSI"] = ta.rsi(df["Close"], length=14)
        macd = ta.macd(df["Close"])
        df["MACD_Hist"] = macd["MACDh_12_26_9"] if macd is not None else pd.NA
        df["EMA_50"] = ta.ema(df["Close"], length=50)
        bb = ta.bbands(df["Close"], length=20)
        df["BB_Lower"] = bb["BBL_20_2.0"]
        df["BB_Upper"] = bb["BBU_20_2.0"]
        stoch = ta.stoch(df["High"], df["Low"], df["Close"])
        df["Stoch_K"] = stoch["STOCHk_14_3_3"]
        df["Stoch_D"] = stoch["STOCHd_14_3_3"]
        df.dropna(inplace=True)
        return df

    except Exception as e:
        print(f"❌ Error calculating indicators for {ticker}: {e}")
        return pd.DataFrame()

def is_data_fresh(df, tolerance_days=2):
    last_date = df.index[-1].date()
    today = datetime.date.today()
    return (today - last_date).days <= tolerance_days

def check_signal(df):
    latest = df.iloc[-1]
    close = latest["Close"]

    conditions_buy = [
        latest["RSI"] < 40,
        latest["MACD_Hist"] >= 0,
        close >= latest["EMA_50"],
        close <= latest["BB_Lower"] * 1.02,
        latest["Stoch_K"] < 30
    ]

    conditions_short = [
        latest["RSI"] > 60,
        latest["MACD_Hist"] <= 0,
        close <= latest["EMA_50"],
        close >= latest["BB_Upper"] * 0.98,
        latest["Stoch_K"] > 70
    ]

    buy_count = sum(conditions_buy)
    short_count = sum(conditions_short)

    if buy_count >= 2:
        return "BUY", latest, buy_count
    elif short_count >= 2:
        return "SHORT", latest, short_count
    else:
        return None, latest, 0

def detect_support_resistance(df, lookback=60):
    support_levels = []
    resistance_levels = []

    for i in range(lookback, len(df) - lookback):
        if df['Low'].iloc[i] < min(df['Low'].iloc[i - lookback:i]) and df['Low'].iloc[i] < min(df['Low'].iloc[i+1:i+lookback+1]):
            support_levels.append(df['Low'].iloc[i])
        if df['High'].iloc[i] > max(df['High'].iloc[i - lookback:i]) and df['High'].iloc[i] > max(df['High'].iloc[i+1:i+lookback+1]):
            resistance_levels.append(df['High'].iloc[i])

    def filter_levels(levels, threshold=0.02):
        filtered = []
        for lvl in levels:
            if all(abs(lvl - f) / f > threshold for f in filtered):
                filtered.append(lvl)
        return sorted(filtered)

    return filter_levels(support_levels), filter_levels(resistance_levels)

def run_equities_bot(tickers):
    for ticker in tickers:
        print(f"\n🔍 Scanning {ticker}...")

        try:
            df_stock = get_stock_data(ticker)
            if df_stock.empty or not is_data_fresh(df_stock):
                print(f"⚠️ Skipping {ticker}: No fresh or valid stock data.")
                continue

            signal, latest, confidence = check_signal(df_stock)
            if not signal:
                print(f"⛔ No signal for {ticker}")
                continue

            spot_price = latest["Close"]
            support_levels, resistance_levels = detect_support_resistance(df_stock)

            nearest_support = max([lvl for lvl in support_levels if lvl < spot_price], default=None)
            nearest_resistance = min([lvl for lvl in resistance_levels if lvl > spot_price], default=None)

            stop, target = None, None
            if signal == "BUY":
                if nearest_support:
                    stop = nearest_support * 0.98
                if nearest_resistance:
                    target = nearest_resistance
            elif signal == "SHORT":
                if nearest_resistance:
                    stop = nearest_resistance * 1.02
                if nearest_support:
                    target = nearest_support

            msg = (
                f"📢 **{signal} SIGNAL** for `{ticker}`\n"
                f"> Spot Price: **${spot_price:.2f}**\n"
                f"> RSI: {latest['RSI']:.2f}, MACD Hist: {latest['MACD_Hist']:.2f}, "
                f"Stoch %K: {latest['Stoch_K']:.2f}\n"
                f"> Confidence Score: `{confidence}/5`\n"
            )

            if nearest_support:
                msg += f"> 📉 Support: **${nearest_support:.2f}**\n"
            else:
                msg += "> 📉 Support: _Not detected in recent range_\n"

            if nearest_resistance:
                msg += f"> 📈 Resistance: **${nearest_resistance:.2f}**\n"
            else:
                msg += "> 📈 Resistance: _Not detected in recent range_\n"

            if stop and target:
                msg += f"> 🛑 Stop: **${stop:.2f}**, 🎯 Target: **${target:.2f}**\n"
            else:
                msg += "> 🚫 Stop/Target not available due to lack of clear support/resistance\n"

            msg += f"> 🕒 Signal Time: {latest.name.strftime('%Y-%m-%d %H:%M:%S')}"
            send_discord_alert(msg)

        except Exception as e:
            print(f"❌ Error processing {ticker}: {e}")

# Example stock watchlist
stock_watchlist = [
    "AAPL", "TSLA", "NVDA", "AMZN", "SPY", "MSFT", "META", "GOOGL", "NFLX", "AMD",
    "INTC", "BABA", "QQQ", "IWM", "SOFI", "PLTR", "ROKU", "F",
    "GM", "PINS", "DKNG", "CHPT", "NIO", "RIOT", "MARA", "CVNA",
    "UPST", "LCID", "AFRM", "T", "PFE", "BBD", "DNA"
]

run_equities_bot(stock_watchlist)
