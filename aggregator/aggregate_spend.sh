#!/bin/bash
# AI Spend aggregator — runs every 5 min, silent on success
/usr/bin/python3 /opt/hermes/scripts/aggregate_spend.py /opt/hermes/ai-spend.json > /dev/null 2>&1 && exit 0
echo "ERROR: aggregator failed"
exit 1
