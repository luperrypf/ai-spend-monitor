# ai-spend-monitor

AI spend monitoring dashboard for Hermes Agent. Tracks LiteLLM API costs across providers with a Raspberry Pi LCD display.

## Architecture

```
LiteLLM API (CT205:4000)
    │
    ▼
aggregator/aggregate_spend.py  ← cron every 5min on Hermes server
    │
    ▼
/opt/hermes/ai-spend.json
    │
    ▼
ai-spend-http.service  ← Python HTTP server on :9876
    │
    ▼
display/lcd_display.py  ← Raspberry Pi fetches JSON + shows on 16×2 LCD
```

## Components

### aggregator/

Runs on the Hermes server (CT211). Fetches LiteLLM spend logs, aggregates by provider and period, outputs JSON.

- **aggregate_spend.py** — Main aggregator. Handles UTC→JST conversion, cache savings calculation.
- **aggregate_spend.sh** — Cron wrapper. Silent on success, alerts on failure.
- **systemd/ai-spend-http.service** — Serves `ai-spend.json` via HTTP on port 9876.

### display/

Runs on Raspberry Pi (Model B, ARMv6). Fetches JSON from Hermes and displays on 16×2 LCD with button controls.

- **lcd_display.py** — 3-mode auto-rotate (cost / tokens / cache savings). 5-button navigation.

## Setup

### Hermes Server

```bash
# Cron job (every 5 minutes)
*/5 * * * * /opt/hermes/scripts/aggregate_spend.sh

# HTTP server
sudo cp aggregator/systemd/ai-spend-http.service /etc/systemd/system/
sudo systemctl enable --now ai-spend-http
```

### Raspberry Pi

```bash
# Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install adafruit-circuitpython-charlcd adafruit-blinka

# Configure JSON_URL in lcd_display.py to point to Hermes server
# Run
python3 lcd_display.py
```

## LCD Modes

| Mode | Display | Button |
|------|---------|--------|
| Cost | `Cst $X.XX #reqs` | SELECT cycles modes |
| Tokens | `I:12k O:5k` | LEFT/RIGHT cycles periods |
| Cache | `Svd $1.23 45%` | UP/DOWN cycles providers |

Periods: Total → 30days → Today