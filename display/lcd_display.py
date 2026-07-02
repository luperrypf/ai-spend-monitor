#!/usr/bin/env python3
"""LCD Display Template — 3-mode auto-rotate for Pi Model B ARMv6.
LEFT/RIGHT=period, UP/DOWN=provider, SELECT=manual cycle.
Auto-rotates cost→tokens→cache every 10s. Button press resets timer.

Modes: cost (Cst $X.XX #req), tokens (I:XX O:XX), cache (Svd $X XX%).
"""
import sys, types, time, json, urllib.request, socket

# ── RPi.GPIO Mock (required for Pi Model B old revision code) ──
_RPI = types.ModuleType("RPi.GPIO")
_RPI.RPI_INFO = {"P1_REVISION": 2, "REVISION": "000e"}
for a in ["BCM","BOARD","OUT","IN","HIGH","LOW","PUD_UP","PUD_DOWN"]:
    setattr(_RPI, a, 0)
for m in ["setmode","setup","output","cleanup","setwarnings","gpio_function"]:
    setattr(_RPI, m, lambda *a, **k: None)
_RPI.input = lambda *a: 0
sys.modules["RPi"] = type(sys)("RPi")
sys.modules["RPi"].GPIO = _RPI
sys.modules["RPi.GPIO"] = _RPI

import board, busio
from adafruit_character_lcd.character_lcd_rgb_i2c import Character_LCD_RGB_I2C

socket.setdefaulttimeout(8)
JSON_URL = "http://192.168.68.211:9876/ai-spend.json"  # ← configure
AUTO_ROTATE_SECS = 10
FETCH_INTERVAL_SECS = 300
BUTTON_DEBOUNCE_SECS = 0.5

PERIODS = ["all_time", "month", "daily"]
PERIOD_LABELS = {"all_time": "Total", "month": "30days", "daily": "Today"}
PROVIDERS = ["All Models", "Deepseek", "Gemini", "OpenAI", "Anthropic", "Moonshot", "Xiaomi"]
PROVIDER_KEYS = ["all", "deepseek", "gemini", "openai", "anthropic", "moonshot", "xiaomi"]
VIEW_MODES = ["cost", "tokens", "cache"]


def fmt_tok(n):
    if n >= 1_000_000: return f"{n / 1_000_000:.1f}M"
    if n >= 1_000: return f"{n / 1_000:.0f}k"
    return str(int(n))


def fmt_money(n):
    if n >= 1000: return f"${n / 1000:.1f}k"
    if n >= 100: return f"${n:.0f}"
    return f"${n:.2f}"


i2c = busio.I2C(board.SCL, board.SDA)
lcd = Character_LCD_RGB_I2C(i2c, 16, 2, address=0x20)
lcd.color = (2, 2, 2)  # CRITICAL: must be >1 for LOW=ON

period_idx = 2  # default: Today
provider_idx = 0
view_idx = 0
data = None
last_fetch = 0
last_btn = 0
last_rotate = time.time()  # NOT 0 — prevents immediate rotate on startup
last_label = ""


def fetch():
    global data
    try:
        req = urllib.request.Request(JSON_URL)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        return True
    except Exception:
        return False


def show():
    if not data or "providers" not in data:
        lcd.message = "No data yet".ljust(16) + "\n" + "Press SELECT".ljust(16)
        return

    pkey = PROVIDER_KEYS[provider_idx]
    pname = PROVIDERS[provider_idx]
    period = PERIODS[period_idx]
    plabel = PERIOD_LABELS[period]
    mode = VIEW_MODES[view_idx]
    p = data["providers"].get(pkey, {})

    label = f"{pname} {plabel}"
    global last_label
    if label != last_label:
        lcd.clear()
        last_label = label

    if mode == "cost":
        amount = p.get(period, 0)
        reqs = p.get(f"{period}_req", 0)
        lcd.message = f"{pname} {plabel}".ljust(16) + "\n" + f"Cst ${amount:.2f} #{reqs}".ljust(16)
    elif mode == "tokens":
        tin = p.get(f"{period}_in", 0)
        tout = p.get(f"{period}_out", 0)
        lcd.message = f"{pname} {plabel}".ljust(16) + "\n" + f"I:{fmt_tok(tin)} O:{fmt_tok(tout)}".ljust(16)
    elif mode == "cache":
        spend = p.get(period, 0)
        saved = p.get(f"{period}_saved", 0)
        total = spend + saved
        if total > 0:
            pct = saved / total * 100
            lcd.message = f"{pname} {plabel}".ljust(16) + "\n" + f"Svd {fmt_money(saved)} {pct:.0f}%".ljust(16)
        else:
            lcd.message = f"{pname} {plabel}".ljust(16) + "\n" + "No savings".ljust(16)


def check_buttons():
    buttons = [("left", lambda: lcd.left_button), ("right", lambda: lcd.right_button),
               ("up", lambda: lcd.up_button), ("down", lambda: lcd.down_button),
               ("select", lambda: lcd.select_button)]
    for name, getter in buttons:
        if getter():
            time.sleep(0.03)
            if getter():
                return name
    return None


lcd.clear()
lcd.message = "Loading...".ljust(16) + "\n" + "LCD Display".ljust(16)
if fetch():
    show()
else:
    lcd.message = "Fetch failed".ljust(16) + "\n" + "Check server".ljust(16)

while True:
    now = time.time()

    # Periodic data refresh
    if now - last_fetch > FETCH_INTERVAL_SECS:
        fetch()
        last_fetch = now

    # Button handling (independent of auto-rotate)
    # IMPORTANT: do NOT use elif for auto-rotate — the debounce if is almost
    # always True, so elif never fires. Use btn_pressed flag instead.
    btn_pressed = False
    if now - last_btn > BUTTON_DEBOUNCE_SECS:
        btn = check_buttons()
        if btn:
            btn_pressed = True
            if btn == "left":
                period_idx = (period_idx - 1) % len(PERIODS)
            elif btn == "right":
                period_idx = (period_idx + 1) % len(PERIODS)
            elif btn == "up":
                provider_idx = (provider_idx - 1) % len(PROVIDERS)
            elif btn == "down":
                provider_idx = (provider_idx + 1) % len(PROVIDERS)
            elif btn == "select":
                view_idx = (view_idx + 1) % len(VIEW_MODES)
            show()
            last_btn = now
            last_rotate = now  # reset rotate timer on any button

    # Auto-rotate view modes (independent check)
    if not btn_pressed and now - last_rotate > AUTO_ROTATE_SECS:
        view_idx = (view_idx + 1) % len(VIEW_MODES)
        show()
        last_rotate = now

    time.sleep(0.3)
