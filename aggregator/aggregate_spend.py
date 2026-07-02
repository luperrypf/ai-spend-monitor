#!/usr/bin/env python3
"""Aggregate LiteLLM spend by provider and date. Output JSON for Pi display.
Includes cache savings calculation: what we'd pay at full price vs actual spend."""
import json, urllib.request, sys, os
from datetime import datetime, date, timedelta, timezone

LITELLM_KEY_PATH = "/opt/hermes/.litellm_key"
LITELLM_API_URL = "http://192.168.68.205:4000/spend/logs"

PROVIDER_MAP = {
    "mimo": "xiaomi", "xiaomi": "xiaomi",
    "deepseek": "deepseek", "gemini": "gemini",
    "openai": "openai", "gpt-": "openai",
    "o1": "openai", "o3": "openai", "o4": "openai",
    "claude": "anthropic", "anthropic": "anthropic",
    "moonshot": "moonshot", "kimi": "moonshot",
}
ALL_PROVIDERS = ["all"] + sorted(set(PROVIDER_MAP.values())) + ["other", "unknown"]

# Full input rate (cache miss) and output rate for cache-capable models
CACHE_RATES = {
    "deepseek-v4-pro":  (4.35e-07, 8.7e-07),
    "deepseek-v4-flash": (1.4e-07, 2.8e-07),
    "mimo-v2.5-pro":    (4.35e-07, 8.7e-07),
    "mimo-v2.5":        (1.4e-07, 2.8e-07),
}

def get_api_key():
    try:
        return open(LITELLM_KEY_PATH).read().strip()
    except FileNotFoundError:
        print(f"ERROR: {LITELLM_KEY_PATH} not found")
        sys.exit(1)

def get_provider(model):
    if not model:
        return "unknown"
    ml = model.lower()
    for prefix, provider in PROVIDER_MAP.items():
        if ml.startswith(prefix) or prefix in ml:
            return provider
    return "other"

def get_cache_rates(model):
    """Return (input_rate, output_rate) for a model, or None."""
    if not model:
        return None
    ml = model.lower()
    for model_key, rates in CACHE_RATES.items():
        if model_key in ml:
            return rates
    return None

def calc_savings(model, prompt_tokens, completion_tokens, spend):
    """Calculate savings: full_price (no cache) - actual spend."""
    rates = get_cache_rates(model)
    if not rates:
        return 0.0
    input_rate, output_rate = rates
    full_price = prompt_tokens * input_rate + completion_tokens * output_rate
    return max(0, full_price - spend)

def fetch_spend_logs(api_key):
    req = urllib.request.Request(LITELLM_API_URL, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data.get("data", data) if isinstance(data, dict) else data

def make_periods():
    return {
        "all_time": 0.0, "month": 0.0, "daily": 0.0,
        "all_time_in": 0, "month_in": 0, "daily_in": 0,
        "all_time_out": 0, "month_out": 0, "daily_out": 0,
        "all_time_req": 0, "month_req": 0, "daily_req": 0,
        "all_time_saved": 0.0, "month_saved": 0.0, "daily_saved": 0.0,
    }

def aggregate(entries):
    today = (datetime.now(timezone.utc) + timedelta(hours=9)).date()  # JST (UTC+9)
    cutoff = today - timedelta(days=30)
    result = {"updated": datetime.now(timezone.utc).isoformat() + "Z", "providers": {}}
    for p in ALL_PROVIDERS:
        if p != "all":
            result["providers"][p] = make_periods()
    result["providers"]["all"] = make_periods()

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model = entry.get("model", "") or ""
        spend = float(entry.get("spend", 0) or 0)
        pt = entry.get("prompt_tokens", 0) or 0
        ct = entry.get("completion_tokens", 0) or 0
        if spend < 0:
            continue

        try:
            provider = get_provider(model)
            savings = calc_savings(model, pt, ct, spend)
        except (ValueError, TypeError):
            continue

        ts_str = entry.get("startTime") or entry.get("created_at") or ""
        entry_date = None
        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(ts_str[:19] if len(ts_str) >= 19 else ts_str[:10], fmt)
                entry_date = (dt + timedelta(hours=9)).date()  # UTC→JST
                break
            except (ValueError, TypeError):
                continue

        prov = result["providers"][provider]
        allp = result["providers"]["all"]
        for period, cond in [
            ("all_time", True),
            ("month", entry_date and entry_date >= cutoff),
            ("daily", entry_date and entry_date == today),
        ]:
            if cond:
                prov[period] += spend
                prov[f"{period}_in"] += pt
                prov[f"{period}_out"] += ct
                prov[f"{period}_req"] += 1
                allp[period] += spend
                allp[f"{period}_in"] += pt
                allp[f"{period}_out"] += ct
                allp[f"{period}_req"] += 1
                if savings > 0:
                    prov[f"{period}_saved"] += savings
                    allp[f"{period}_saved"] += savings

    for prov_name in result["providers"]:
        for k, v in result["providers"][prov_name].items():
            if k.endswith(("_in", "_out", "_req")):
                result["providers"][prov_name][k] = int(v)
            else:
                result["providers"][prov_name][k] = round(v, 2)
    return result

if __name__ == "__main__":
    api_key = get_api_key()
    try:
        entries = fetch_spend_logs(api_key)
    except Exception as e:
        print(f"ERROR: Failed to fetch spend logs: {e}")
        sys.exit(1)

    data = aggregate(entries)
    output_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/hermes/public/ai-spend.json"

    # Atomic write: write to tmp then rename
    tmp_path = f"{output_path}.{os.getpid()}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.rename(tmp_path, output_path)

    a = data["providers"]["all"]
    print(f"Written {len(entries)} entries to {output_path}")
    print(f"Total all-time: ${a['all_time']:.2f}")
    print(f"Total 30d:     ${a['month']:.2f}")
    print(f"Total today:   ${a['daily']:.2f}")
    if a["all_time_saved"] > 0:
        print(f"Saved all-time: ${a['all_time_saved']:.2f}")
