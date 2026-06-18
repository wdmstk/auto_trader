#!/bin/bash
# Real-time worker monitoring script

cd "$(dirname "$0")/.." || exit 1

echo "=== Worker Status Monitor ==="
echo "Press Ctrl+C to stop"
echo ""

while true; do
    clear
    echo "=== Worker Status: $(date) ==="
    echo ""

    # Check worker process
    echo "📊 Worker Process:"
    if pgrep -f "auto_trader.worker" > /dev/null; then
        echo "  ✅ Worker process running"
        pgrep -f "auto_trader.worker" -a
    else
        echo "  ❌ No worker process running"
    fi
    echo ""

    # Check worker state
    echo "📋 Last Processed Bars:"
    if [ -f "data/runtime/worker_state.json" ]; then
        .venv/bin/python -c "
import json
with open('data/runtime/worker_state.json', 'r') as f:
    data = json.load(f)
    if 'last_processed_bars' in data:
        for route, ts in data['last_processed_bars'].items():
            print(f'  {route}: {ts}')
    else:
        print('  No processed bars info')
"
    else
        echo "  ❌ No worker state file"
    fi
    echo ""

    # Check signal status
    echo "📡 Signal Status (Latest):"
    if [ -f "data/runtime/worker_state.json" ]; then
        .venv/bin/python -c "
import json
with open('data/runtime/worker_state.json', 'r') as f:
    data = json.load(f)
    if 'last_results' in data:
        for route, info in data['last_results'].items():
            signal = info.get('signal', {})
            regime = signal.get('regime', 'N/A')
            entry = signal.get('entry_signal', False)
            reason = signal.get('reason_codes', [])
            print(f'  {route}:')
            print(f'    Regime: {regime}, Entry: {entry}')
            if reason:
                print(f'    Reason: {reason}')
    else
        print('  No signal info')
"
    else
        echo "  ❌ No worker state file"
    fi
    echo ""

    # Check positions
    echo "💰 Current Positions:"
    if [ -f "data/positions/positions.parquet" ]; then
        .venv/bin/python -c "
import pandas as pd
df = pd.read_parquet('data/positions/positions.parquet')
if len(df) > 0 and (df['qty'] > 0).any():
    active = df[df['qty'] > 0]
    print(active[['symbol', 'strategy', 'side', 'qty', 'avg_entry', 'unrealized_pnl_pct']].to_string(index=False))
else:
    print('  No active positions')
"
    else
        echo "  ❌ No positions data"
    fi
    echo ""

    # Check system metrics
    echo "⚙️  System Metrics:"
    if [ -f "data/validation/runtime_metrics.jsonl" ]; then
        tail -1 data/validation/runtime_metrics.jsonl | .venv/bin/python -c "
import sys, json
data = json.load(sys.stdin)
print(f'  Trading Enabled: {data.get(\"runtime_trading_enabled\", False)}')
print(f'  Emergency Stop: {data.get(\"runtime_emergency_stop\", False)}')
print(f'  Pending Orders: {data.get(\"gateway_pending_orders\", 0)}')
print(f'  Order Latency P95: {data.get(\"order_latency_p95_ms\", 0):.2f}ms')
print(f'  System Load: {data.get(\"system_loadavg_1m\", 0):.2f}')
print(f'  Current Exposure: {data.get(\"risk_latest_exposure_pct\", 0):.2f}%')
"
    else
        echo "  ❌ No metrics data"
    fi
    echo ""

    echo "🔄 Refreshing in 10 seconds..."
    sleep 10
done
