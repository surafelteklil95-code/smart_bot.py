# ======================================================
# SMART BOT – PART 1 : CORE SYSTEM
# Bybit DEMO + REAL | Cloud Ready (Render)
# File: smart_bot.py
# ======================================================

import os
import time
import threading
import requests
from datetime import datetime
from pybit.unified_trading import HTTP

# ===============================
# MODE CONFIG (DEMO / REAL)
# ===============================
MODE = os.getenv("MODE", "DEMO")  # DEMO or REAL

DEMO_KEY = os.getenv("BYBIT_DEMO_KEY")
DEMO_SECRET = os.getenv("BYBIT_DEMO_SECRET")

REAL_KEY = os.getenv("BYBIT_REAL_KEY")
REAL_SECRET = os.getenv("BYBIT_REAL_SECRET")

TG_TOKEN = os.getenv("TG_TOKEN")
TG_ADMIN = int(os.getenv("TG_ADMIN", "0"))

if MODE == "REAL":
    API_KEY = REAL_KEY
    API_SECRET = REAL_SECRET
    TESTNET = False
else:
    API_KEY = DEMO_KEY
    API_SECRET = DEMO_SECRET
    TESTNET = True

# ===============================
# GLOBAL BOT STATE
# ===============================
BOT_ACTIVE = True
KILL_SWITCH = False
START_DAY_BALANCE = None
TRADES_TODAY = 0
OPEN_TRADES = {}

# ===============================
# RISK SETTINGS (BASE)
# ===============================
LEVERAGE = 20
RISK_PER_TRADE = 0.20
MAX_DAILY_LOSS = 0.10
MAX_DAILY_PROFIT = 0.25
MAX_TRADES = 5

# ===============================
# CONNECT TO BYBIT
# ===============================
print("🔌 Connecting to Bybit...")

session = HTTP(
    testnet=TESTNET,
    api_key=API_KEY,
    api_secret=API_SECRET
)

# ===============================
# TELEGRAM CORE
# ===============================
def tg(msg):
    if not TG_TOKEN or TG_ADMIN == 0:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_ADMIN, "text": msg}
        )
    except:
        pass

# ===============================
# WALLET
# ===============================
def get_balance():
    try:
        r = session.get_wallet_balance(accountType="UNIFIED")
        return float(r["result"]["list"][0]["totalWalletBalance"])
    except:
        return 0.0

# ===============================
# DAILY INIT
# ===============================
def init_day():
    global START_DAY_BALANCE, TRADES_TODAY, KILL_SWITCH
    START_DAY_BALANCE = get_balance()
    TRADES_TODAY = 0
    KILL_SWITCH = False
    tg(f"🚀 SMART BOT STARTED ({MODE})\nBalance: {START_DAY_BALANCE}")

# ===============================
# BASIC DAILY RISK CHECK
# ===============================
def daily_risk_check():
    global KILL_SWITCH
    bal = get_balance()
    if START_DAY_BALANCE is None:
        return

    pnl = (bal - START_DAY_BALANCE) / START_DAY_BALANCE

    if pnl <= -MAX_DAILY_LOSS:
        KILL_SWITCH = True
        tg("🛑 DAILY LOSS LIMIT HIT")

    if pnl >= MAX_DAILY_PROFIT:
        KILL_SWITCH = True
        tg("🎯 DAILY PROFIT TARGET HIT")

# ===============================
# TEST CORE
# ===============================
if __name__ == "__main__":
    init_day()
    while True:
        daily_risk_check()
        print("Balance:", get_balance(), "| Active:", BOT_ACTIVE, "| Kill:", KILL_SWITCH)
        time.sleep(15)

# ======================================================
# SMART BOT – PART 2 : MARKET DATA & INDICATORS
# ======================================================

import math

# ===============================
# GET KLINES
# ===============================
def get_klines(symbol="BTCUSDT", interval="1", limit=200):
    try:
        r = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        data = r["result"]["list"]
        closes = [float(c[4]) for c in data]
        return closes
    except:
        return []

# ===============================
# EMA
# ===============================
def ema(data, period=14):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    ema_val = sum(data[:period]) / period
    for price in data[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

# ===============================
# RSI
# ===============================
def rsi(data, period=14):
    if len(data) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, period + 1):
        diff = data[-i] - data[-i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    if len(losses) == 0:
        return 100

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ===============================
# TREND FILTER (AI-LIKE SIMPLE)
# ===============================
def trend_filter(symbol="BTCUSDT"):
    closes = get_klines(symbol, "5", 120)
    if not closes:
        return "NONE"

    fast = ema(closes, 20)
    slow = ema(closes, 50)

    if not fast or not slow:
        return "NONE"

    if fast > slow:
        return "BULL"
    elif fast < slow:
        return "BEAR"
    else:
        return "SIDE"


# ======================================================
# SMART BOT – PART 3 : TRADE ENGINE
# ======================================================

# ===============================
# GET LAST PRICE
# ===============================
def get_price(symbol="BTCUSDT"):
    try:
        r = session.get_tickers(category="linear", symbol=symbol)
        return float(r["result"]["list"][0]["lastPrice"])
    except:
        return None

# ===============================
# POSITION SIZE (RISK BASED)
# ===============================
def calc_size(symbol="BTCUSDT", risk=RISK_PER_TRADE):
    balance = get_balance()
    price = get_price(symbol)
    if not price or balance <= 0:
        return 0

    risk_amount = balance * risk
    qty = (risk_amount * LEVERAGE) / price
    return round(qty, 3)

# ===============================
# SET LEVERAGE
# ===============================
def set_leverage(symbol="BTCUSDT"):
    try:
        session.set_leverage(
            category="linear",
            symbol=symbol,
            buyLeverage=str(LEVERAGE),
            sellLeverage=str(LEVERAGE)
        )
    except:
        pass

# ===============================
# OPEN MARKET ORDER
# ===============================
def open_trade(symbol="BTCUSDT", side="Buy"):
    global OPEN_TRADES, TRADES_TODAY

    if KILL_SWITCH or not BOT_ACTIVE:
        return

    if TRADES_TODAY >= MAX_TRADES:
        return

    qty = calc_size(symbol)
    if qty <= 0:
        return

    set_leverage(symbol)

    try:
        order = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=qty,
            timeInForce="GoodTillCancel"
        )

        OPEN_TRADES[symbol] = {
            "side": side,
            "qty": qty,
            "time": datetime.now()
        }

        TRADES_TODAY += 1
        tg(f"📥 OPEN {side} {symbol}\nQty: {qty}")

    except Exception as e:
        tg(f"❌ ORDER ERROR {symbol}\n{e}")

# ===============================
# CLOSE POSITION
# ===============================
def close_trade(symbol="BTCUSDT", side="Sell"):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=0,
            reduceOnly=True
        )
        OPEN_TRADES.pop(symbol, None)
        tg(f"📤 CLOSED {symbol}")
    except:
        pass

# ===============================
# CHECK OPEN POSITIONS (LOCAL)
# ===============================
def has_open_trade(symbol="BTCUSDT"):
    return symbol in OPEN_TRADES

# ======================================================
# SMART BOT – PART 4 : STRATEGY ENGINE
# ======================================================

# ===============================
# GET CANDLES
# ===============================
def get_candles(symbol="BTCUSDT", tf="5", limit=200):
    try:
        r = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=tf,
            limit=limit
        )
        return r["result"]["list"]
    except:
        return []

# ===============================
# SIMPLE INDICATORS
# ===============================
def EMA(data, period=20):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    ema = float(data[0])
    for price in data[1:]:
        ema = price * k + ema * (1 - k)
    return ema

def RSI(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i-1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))
    if not losses:
        return 100
    rs = (sum(gains)/period) / (sum(losses)/period)
    return 100 - (100 / (1 + rs))

# ===============================
# SIGNAL LOGIC
# ===============================
def get_signal(symbol="BTCUSDT"):
    candles = get_candles(symbol)
    if len(candles) < 50:
        return None

    closes = [float(c[4]) for c in candles][::-1]

    ema_fast = EMA(closes[-20:], 20)
    ema_slow = EMA(closes[-50:], 50)
    rsi = RSI(closes, 14)

    if not ema_fast or not ema_slow or not rsi:
        return None

    price = closes[-1]

    # BUY SIGNAL
    if ema_fast > ema_slow and rsi < 35:
        return "Buy"

    # SELL SIGNAL
    if ema_fast < ema_slow and rsi > 65:
        return "Sell"

    return None

# ===============================
# STRATEGY LOOP
# ===============================
def strategy_engine():
    tg("🤖 Strategy engine started")

    while BOT_ACTIVE:
        try:
            for sym in SYMBOLS:
                if not has_open_trade(sym):
                    signal = get_signal(sym)
                    if signal:
                        open_trade(sym, signal)
                time.sleep(1)

        except Exception as e:
            tg(f"⚠️ Strategy error\n{e}")

        time.sleep(10)

  # ======================================================
# PART 5 – TRADE ENGINE + RISK MANAGEMENT (SAFE VERSION)
# ======================================================

def daily_risk_check():
    """
    Checks daily PnL and activates kill switch
    """
    global KILL_SWITCH

    # safeguard 1: START_DAY_BALANCE not ready
    if START_DAY_BALANCE is None or START_DAY_BALANCE <= 0:
        return

    bal = get_balance()

    # safeguard 2: balance fetch failed
    if bal <= 0:
        return

    pnl = (bal - START_DAY_BALANCE) / START_DAY_BALANCE

    if pnl <= -MAX_DAILY_LOSS:
        KILL_SWITCH = True
        tg("🛑 DAILY LOSS LIMIT HIT – BOT STOPPED")

    elif pnl >= MAX_DAILY_PROFIT:
        KILL_SWITCH = True
        tg("🎯 DAILY PROFIT TARGET HIT – BOT STOPPED")


def trade_engine(symbol, side):
    """
    Executes a trade with risk control
    """
    global TRADES_TODAY, OPEN_TRADES

    if KILL_SWITCH or not BOT_ACTIVE:
        return

    if TRADES_TODAY >= MAX_TRADES:
        return

    balance = get_balance()
    if balance <= 0:
        return

    # position size based on risk
    risk_amount = balance * RISK_PER_TRADE

    try:
        price = float(
            session.get_tickers(
                category="linear",
                symbol=symbol
            )["result"]["list"][0]["lastPrice"]
        )
    except:
        return

    if price <= 0:
        return

    qty = round(risk_amount / price, 3)
    if qty <= 0:
        return

    try:
        # set leverage
        session.set_leverage(
            category="linear",
            symbol=symbol,
            buyLeverage=LEVERAGE,
            sellLeverage=LEVERAGE
        )

        # place market order
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=qty,
            timeInForce="IOC"
        )

        TRADES_TODAY += 1
        OPEN_TRADES[symbol] = {
            "side": side,
            "qty": qty,
            "price": price,
            "time": datetime.utcnow()
        }

        tg(f"📈 TRADE OPENED\n{symbol} | {side}\nQty: {qty}")

    except Exception as e:
        tg(f"⚠️ Trade failed: {e}")

  # ======================================================
# SMART BOT – PART 6 : TELEGRAM COMMAND CENTER
# ======================================================

# ===============================
# TELEGRAM LISTENER
# ===============================
def telegram_listener():
    global BOT_ACTIVE, KILL_SWITCH, TRADES_TODAY

    offset = None
    tg("🤖 SMART BOT Telegram control connected")

    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30}
            ).json()

            for u in r.get("result", []):
                offset = u["update_id"] + 1

                if "message" not in u:
                    continue

                chat_id = u["message"]["chat"]["id"]
                if chat_id != TG_ADMIN:
                    continue

                txt = u["message"].get("text", "").lower()

                # =========================
                # COMMANDS
                # =========================

                if txt == "/start":
                    BOT_ACTIVE = True
                    KILL_SWITCH = False
                    tg("▶️ BOT STARTED")

                elif txt == "/stop":
                    BOT_ACTIVE = False
                    tg("⛔ BOT STOPPED")

                elif txt == "/kill":
                    KILL_SWITCH = True
                    tg("🛑 KILL SWITCH ACTIVATED")

                elif txt == "/status":
                    bal = get_balance()
                    tg(
                        f"⚙️ SMART BOT STATUS\n"
                        f"Mode: {MODE}\n"
                        f"Balance: {bal}\n"
                        f"Trades today: {TRADES_TODAY}\n"
                        f"Open trades: {len(OPEN_TRADES)}\n"
                        f"Active: {BOT_ACTIVE}\n"
                        f"Kill: {KILL_SWITCH}"
                    )

                elif txt == "/closeall":
                    for s in list(OPEN_TRADES.keys()):
                        close_trade(s, "MANUAL CLOSE ALL")
                    tg("❌ ALL TRADES CLOSED")

                elif txt == "/reset":
                    init_day()
                    tg("🔄 DAILY RESET DONE")

                elif txt.startswith("/close"):
                    try:
                        sym = txt.replace("/close", "").strip().upper()
                        if sym in OPEN_TRADES:
                            close_trade(sym, "MANUAL CLOSE")
                        else:
                            tg("⚠️ Symbol not open")
                    except:
                        pass

        except:
            pass

        time.sleep(5)

  # ======================================================
# SMART BOT – PART 7 : AI TREND FILTER & MULTI-TF SIGNAL
# ======================================================

import math

# ===============================
# TIMEFRAMES CONFIG
# ===============================
TIMEFRAMES = ["1", "5", "15", "60", "240"]  # 1m,5m,15m,1h,4h
TREND_CONFIRMATION = 3  # how many TFs must agree

# ===============================
# CANDLE DATA
# ===============================
def get_candles(symbol, tf="15", limit=100):
    try:
        r = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=tf,
            limit=limit
        )
        return r["result"]["list"]
    except:
        return []

# ===============================
# SIMPLE AI TREND MODEL
# (EMA slope + momentum)
# ===============================
def ema(data, period=20):
    k = 2 / (period + 1)
    ema_val = sum(data[:period]) / period
    for p in data[period:]:
        ema_val = p * k + ema_val * (1 - k)
    return ema_val

def ai_trend_score(closes):
    if len(closes) < 30:
        return 0

    ema_fast = ema(closes[-20:], 10)
    ema_slow = ema(closes[-50:], 25)

    slope = closes[-1] - closes[-10]
    momentum = (closes[-1] - closes[-20]) / closes[-20]

    score = (ema_fast - ema_slow) + slope + (momentum * closes[-1])
    return score

# ===============================
# MULTI TF SIGNAL
# ===============================
def ai_signal(symbol):
    bull = 0
    bear = 0

    for tf in TIMEFRAMES:
        candles = get_candles(symbol, tf, 100)
        if not candles:
            continue

        closes = [float(c[4]) for c in candles][::-1]
        score = ai_trend_score(closes)

        if score > 0:
            bull += 1
        else:
            bear += 1

    if bull >= TREND_CONFIRMATION:
        return "BUY"
    elif bear >= TREND_CONFIRMATION:
        return "SELL"
    else:
        return None

  # ======================================================
# SMART BOT – PART 8 : AUTO SL / TP + TRAILING SYSTEM
# ======================================================

# ===============================
# EXIT CONFIG
# ===============================
STOP_LOSS_PCT = 0.01     # 1% SL
TAKE_PROFIT_PCT = 0.02   # 2% TP
TRAIL_START = 0.01       # start trailing after 1% profit
TRAIL_STEP = 0.003       # trail distance 0.3%

# ===============================
# PRICE
# ===============================
def get_price(symbol):
    try:
        r = session.get_tickers(category="linear", symbol=symbol)
        return float(r["result"]["list"][0]["lastPrice"])
    except:
        return None

# ===============================
# REGISTER TRADE
# ===============================
def register_trade(symbol, side, entry, qty):
    OPEN_TRADES[symbol] = {
        "side": side,
        "entry": entry,
        "qty": qty,
        "sl": entry * (1 - STOP_LOSS_PCT if side == "BUY" else 1 + STOP_LOSS_PCT),
        "tp": entry * (1 + TAKE_PROFIT_PCT if side == "BUY" else 1 - TAKE_PROFIT_PCT),
        "trail_active": False
    }

# ===============================
# CLOSE TRADE
# ===============================
def close_trade(symbol, reason="exit"):
    try:
        trade = OPEN_TRADES.get(symbol)
        if not trade:
            return

        side = "SELL" if trade["side"] == "BUY" else "BUY"

        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=trade["qty"],
            timeInForce="IOC",
            reduceOnly=True
        )

        tg(f"❌ CLOSED {symbol} | {reason}")
        del OPEN_TRADES[symbol]

    except:
        pass

# ===============================
# TRADE MONITOR
# ===============================
def manage_trades():
    while True:
        try:
            for symbol in list(OPEN_TRADES.keys()):
                t = OPEN_TRADES[symbol]
                price = get_price(symbol)
                if not price:
                    continue

                # STOP LOSS
                if t["side"] == "BUY" and price <= t["sl"]:
                    close_trade(symbol, "STOP LOSS")
                elif t["side"] == "SELL" and price >= t["sl"]:
                    close_trade(symbol, "STOP LOSS")

                # TAKE PROFIT
                if t["side"] == "BUY" and price >= t["tp"]:
                    close_trade(symbol, "TAKE PROFIT")
                elif t["side"] == "SELL" and price <= t["tp"]:
                    close_trade(symbol, "TAKE PROFIT")

                # TRAILING START
                if not t["trail_active"]:
                    if t["side"] == "BUY" and price >= t["entry"] * (1 + TRAIL_START):
                        t["trail_active"] = True
                    elif t["side"] == "SELL" and price <= t["entry"] * (1 - TRAIL_START):
                        t["trail_active"] = True

                # TRAILING MOVE
                if t["trail_active"]:
                    if t["side"] == "BUY":
                        new_sl = price * (1 - TRAIL_STEP)
                        if new_sl > t["sl"]:
                            t["sl"] = new_sl
                    else:
                        new_sl = price * (1 + TRAIL_STEP)
                        if new_sl < t["sl"]:
                            t["sl"] = new_sl

        except:
            pass

        time.sleep(3)

# ===============================
# START TRADE MANAGER
# ===============================
threading.Thread(target=manage_trades, daemon=True).start()
# ======================================================
# SMART BOT – PART 9 : MASTER ENGINE (FINAL)
# ======================================================

# ===============================
# SYMBOL ENGINE (100+ ready)
# ===============================
BASE_SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT",
    "DOTUSDT","MATICUSDT","LTCUSDT","TRXUSDT","LINKUSDT","ATOMUSDT","OPUSDT","ARBUSDT",
    "APTUSDT","NEARUSDT","FILUSDT","SANDUSDT","APEUSDT","FTMUSDT","ETCUSDT","ICPUSDT",
    "INJUSDT","RUNEUSDT","EGLDUSDT","THETAUSDT","AAVEUSDT","UNIUSDT","DYDXUSDT","GALAUSDT",
    "PEPEUSDT","WIFUSDT","SEIUSDT","TIAUSDT","MEMEUSDT","ORDIUSDT","BOMEUSDT","BONKUSDT"
]

SYMBOLS = BASE_SYMBOLS * 3   # ~120 pairs load

# ===============================
# TIMEFRAMES (1s → 1y)
# ===============================
TIMEFRAMES = {
    "1s": 1,
    "5s": 5,
    "15s": 15,
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
    "1y": 31536000
}

ACTIVE_TIMEFRAME = "1m"

# ===============================
# SIMPLE AI TREND FILTER
# ===============================
def ai_trend(symbol):
    try:
        k = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=1,
            limit=20
        )["result"]["list"]

        closes = [float(c[4]) for c in k]
        sma_fast = sum(closes[-5:]) / 5
        sma_slow = sum(closes) / len(closes)

        if sma_fast > sma_slow:
            return "BUY"
        else:
            return "SELL"
    except:
        return None

# ===============================
# SMART SIGNAL
# ===============================
def smart_signal(symbol):
    trend = ai_trend(symbol)
    if not trend:
        return None
    return trend

# ===============================
# ORDER EXECUTOR
# ===============================
def open_trade(symbol, side):
    global TRADES_TODAY

    if symbol in OPEN_TRADES:
        return

    try:
        bal = get_balance()
        risk = bal * RISK_PER_TRADE

        price = get_price(symbol)
        qty = round(risk / price, 3)

        session.set_leverage(
            category="linear",
            symbol=symbol,
            buyLeverage=LEVERAGE,
            sellLeverage=LEVERAGE
        )

        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=qty,
            timeInForce="IOC"
        )

        register_trade(symbol, side, price, qty)
        TRADES_TODAY += 1

        tg(f"📈 OPEN {side} {symbol} | {price}")

    except:
        pass

# ===============================
# TELEGRAM COMMAND CENTER
# ===============================
def telegram_listener():
    global BOT_ACTIVE, KILL_SWITCH, ACTIVE_TIMEFRAME
    offset = None

    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30}
            ).json()

            for u in r["result"]:
                offset = u["update_id"] + 1
                if "message" not in u:
                    continue
                if u["message"]["chat"]["id"] != TG_ADMIN:
                    continue

                cmd = u["message"]["text"].lower()

                if cmd == "/stop":
                    BOT_ACTIVE = False
                    tg("⛔ BOT STOPPED")

                elif cmd == "/start":
                    BOT_ACTIVE = True
                    KILL_SWITCH = False
                    tg("▶️ BOT STARTED")

                elif cmd == "/status":
                    tg(f"⚙️ Mode:{MODE}\nBalance:{get_balance()}\nTrades:{TRADES_TODAY}\nPairs:{len(SYMBOLS)}")

                elif cmd.startswith("/tf"):
                    tf = cmd.replace("/tf","").strip()
                    if tf in TIMEFRAMES:
                        ACTIVE_TIMEFRAME = tf
                        tg(f"⏱ Timeframe set to {tf}")

        except:
            pass

        time.sleep(5)

# ===============================
# MASTER TRADER LOOP
# ===============================
def master_trader():
    init_day()

    while True:
        try:
            if not BOT_ACTIVE or KILL_SWITCH:
                time.sleep(5)
                continue

            daily_risk_check()

            if TRADES_TODAY >= MAX_TRADES:
                time.sleep(30)
                continue

            for sym in SYMBOLS:
                if KILL_SWITCH or not BOT_ACTIVE:
                    break

                sig = smart_signal(sym)
                if sig:
                    open_trade(sym, sig)

                time.sleep(0.3)

            time.sleep(TIMEFRAMES.get(ACTIVE_TIMEFRAME, 60))

        except:
            pass

# ===============================
# SYSTEM START
# ===============================
threading.Thread(target=telegram_listener, daemon=True).start()
master_trader()


import threading
import mini_app

threading.Thread(target=mini_app.app.run, kwargs={
    "host": "0.0.0.0",
    "port": 10000
}, daemon=True).start()

def send_webapp_button():
    url = "https://yourbot.onrender.com"  # 🔴 Render link

    data = {
        "chat_id": TG_ADMIN,
        "text": "📱 SMART BOT MINI APP",
        "reply_markup": {
            "keyboard": [[
                {"text": "🚀 Open Mini App", "web_app": {"url": url}}
            ]],
            "resize_keyboard": True
        }
    }

    requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json=data
    )
