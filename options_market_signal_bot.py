import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime
import requests

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1383524121035538543/RvpjHOfrbtH0wmdVdgph9uZpDDlaYKchi5VZ65TZy1Lb2XSNxmt82895wJ73RGBxlEat"

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
        print("📈 Calculating indicators...")

        df["RSI"] = ta.rsi(df["Close"], length=14)
        macd = ta.macd(df["Close"])
        if macd is not None and "MACDh_12_26_9" in macd.columns:
            df["MACD_Hist"] = macd["MACDh_12_26_9"]
        else:
            df["MACD_Hist"] = pd.NA
        df["EMA_50"] = ta.ema(df["Close"], length=50)

        bbands = ta.bbands(df["Close"], length=20)
        df["BB_Lower"] = bbands["BBL_20_2.0"]
        df["BB_Upper"] = bbands["BBU_20_2.0"]

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

def get_option_chain(ticker):
    stock = yf.Ticker(ticker)
    expirations = stock.options
    if not expirations:
        return None, None, None

    expiration = expirations[0]
    option_chain = stock.option_chain(expiration)
    spot_price = stock.history(period="1d")["Close"].iloc[-1]

    return option_chain.calls, option_chain.puts, spot_price

def find_trade_ideas(calls, puts, spot_price, signal_type):
    df = calls if signal_type == "BUY" else puts
    df = df.copy()
    df["abs_diff"] = abs(df["strike"] - spot_price)
    df = df[df["inTheMoney"] == False]
    df = df.sort_values("abs_diff")
    df = df[df["volume"] > 0]
    return df.iloc[0] if not df.empty else None

def parse_expiration_from_symbol(symbol):
    try:
        date_str = symbol[-15:-9]
        return datetime.datetime.strptime(date_str, "%y%m%d").date()
    except Exception as e:
        print(f"❌ Could not parse expiration from {symbol}: {e}")
        return None

def send_discord_alert(message):
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send alert: {e}")

def run_options_bot(tickers):
    for ticker in tickers:
        print(f"\n🔍 Screening options for {ticker}...")

        try:
            df_stock = get_stock_data(ticker)
            if df_stock.empty or not is_data_fresh(df_stock):
                print(f"⚠️ Skipping {ticker}: No fresh or valid stock data.")
                continue

            signal, latest, confidence = check_signal(df_stock)
            if not signal:
                print(f"⛔ No signal for {ticker}")
                continue

            calls, puts, spot_price = get_option_chain(ticker)
            if calls is None or puts is None:
                print(f"⚠️ Skipping {ticker}: No option chain available.")
                continue

            option = find_trade_ideas(calls, puts, spot_price, signal)
            if option is None:
                print(f"⚠️ No suitable option found for {signal} on {ticker}")
                continue

            exp_date = parse_expiration_from_symbol(option["contractSymbol"])
            last_traded = option["lastTradeDate"].date()

            # Support and resistance logic
            support_levels, resistance_levels = detect_support_resistance(df_stock)
            nearest_support = max([lvl for lvl in support_levels if lvl < spot_price], default=None)
            nearest_resistance = min([lvl for lvl in resistance_levels if lvl > spot_price], default=None)

            # Stop-loss and target logic (independent)
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
            # Build message
            msg = (
                f"📢 **{signal} SIGNAL** for `{ticker}`\n"
                f"> Spot Price: **${spot_price:.2f}**\n"
                f"> Option: `{option['contractSymbol']}`\n"
                f"> Strike: **${option['strike']:.2f}**, Premium: **${option['lastPrice']:.2f}**, Volume: `{option['volume']}`\n"
                f"> 🗓️ Expiration: **{exp_date}**, Last traded on: **{last_traded}**\n"
                f"> RSI: {latest['RSI']:.2f}, MACD Hist: {latest['MACD_Hist']:.2f}, Stoch %K: {latest['Stoch_K']:.2f}\n"
                f"> Confidence Score: `{confidence}/5`"
            )

            if nearest_support:
                msg += f"\n> 📉 Support: **${nearest_support:.2f}**"
            else:
                msg += "\n> 📉 Support: _Not detected in recent range_"

            if nearest_resistance:
                msg += f"\n> 📈 Resistance: **${nearest_resistance:.2f}**"
            else:
                msg += "\n> 📈 Resistance: _Not detected in recent range_"
            if stop and target:
                msg += (
                    f"\n> 🛑 Suggested Stop: **${stop:.2f}**"
                    f"\n> 🎯 Suggested Target: **${target:.2f}**"
                )
            elif not stop and target:
                msg += f"\n> 🎯 Suggested Target: **${target:.2f}**, 🛑 Stop: _Not available_"
            elif stop and not target:
                msg += f"\n> 🛑 Suggested Stop: **${stop:.2f}**, 🎯 Target: _Not available_"
            else:
                msg += "\n> 🚫 Stop & Target: _Not available due to lack of support/resistance_"


            msg += f"\n> Signal Time: {latest.name.strftime('%Y-%m-%d')}"
            send_discord_alert(msg)

        except Exception as e:
            print(f"❌ Error processing {ticker}: {e}")

# Combined watchlist: Large-cap + cheaper stocks (LCID prioritized)
stock_watchlist = [
    # Large-cap / Tech / ETFs
    "AAPL", "TSLA", "NVDA", "AMZN", "SPY", "MSFT", "META", "GOOGL", "NFLX", "AMD",
    "INTC", "BABA", "QQQ", "IWM",

    # Mid / Smaller-cap cheaper stocks (LCID first)
    "LCID", "F", "SOFI", "NIO", "PLTR", "UPST", "AMC", "SNDL", "SIRI", "RBLX",
    "PFE", "DNA", "ZNGA", "RIOT", "MARA", "FCEL", "SBLK",
    "RCL", "UAL", "CCL", "FUBO", "WORK", "CLNE", "VYGR", "VGZ"
]


run_options_bot(stock_watchlist)
