from flask import Flask
import smart_bot

app = Flask(__name__)

@app.route("/")
def home():
    status = "ON 🟢" if smart_bot.BOT_ACTIVE else "OFF 🔴"
    balance = smart_bot.get_balance()
    trades = smart_bot.TRADES_TODAY

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SMART BOT</title>

<style>
body {{
    margin:0;
    font-family: Arial, sans-serif;
    background: #0f172a;
    color: white;
}}

.header {{
    background: linear-gradient(135deg,#2563eb,#06b6d4);
    padding: 25px;
    text-align:center;
    font-size: 24px;
    font-weight:bold;
}}

.card {{
    background:#020617;
    margin:15px;
    padding:20px;
    border-radius:16px;
    box-shadow:0 0 15px rgba(0,0,0,0.5);
}}

.big {{
    font-size:28px;
    font-weight:bold;
}}

.btn {{
    display:block;
    width:100%;
    margin-top:12px;
    padding:16px;
    border-radius:14px;
    border:none;
    font-size:18px;
    font-weight:bold;
}}

.start {{ background:#16a34a; color:white; }}
.stop {{ background:#dc2626; color:white; }}
.refresh {{ background:#2563eb; color:white; }}

.footer {{
    text-align:center;
    opacity:0.6;
    margin:20px;
    font-size:12px;
}}
</style>
</head>

<body>

<div class="header">🤖 SMART BOT MINI APP</div>

<div class="card">
    <p>Status</p>
    <p class="big">{status}</p>
</div>

<div class="card">
    <p>Balance</p>
    <p class="big">${balance}</p>
</div>

<div class="card">
    <p>Trades Today</p>
    <p class="big">{trades}</p>
</div>

<div class="card">
    <button class="btn start" onclick="location.href='/start'">▶ START BOT</button>
    <button class="btn stop" onclick="location.href='/stop'">⛔ STOP BOT</button>
    <button class="btn refresh" onclick="location.href='/'">🔄 REFRESH</button>
</div>

<div class="footer">
SMART BOT • Mobile Dashboard
</div>

</body>
</html>
"""

@app.route("/start")
def start():
    smart_bot.BOT_ACTIVE = True
    smart_bot.KILL_SWITCH = False
    return "<script>location.href='/'</script>"

@app.route("/stop")
def stop():
    smart_bot.BOT_ACTIVE = False
    return "<script>location.href='/'</script>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
