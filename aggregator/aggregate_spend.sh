#!/bin/bash
# AI Spend aggregator — runs every 5 min, silent on success
LOGFILE=/opt/hermes/logs/aggregate_spend.log
/usr/bin/python3 /opt/hermes/scripts/aggregate_spend.py /opt/hermes/public/ai-spend.json > /dev/null 2>> "$LOGFILE" && exit 0
echo "ERROR: aggregator failed — see $LOGFILE" >> "$LOGFILE"
exit 1
