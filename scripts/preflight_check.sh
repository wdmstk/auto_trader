#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-dry-run}"
RUNTIME_STATE_PATH="${RUNTIME_STATE_PATH:-data/runtime/control_state.json}"
RISK_EVAL_PATH="${RISK_EVAL_PATH:-data/risk/risk_eval.parquet}"
SIGNALS_PATH="${SIGNALS_PATH:-data/signals/BTCUSDT_1m_range_signals.parquet}"

ok=true

check_file() {
  local path="$1"
  if [[ -f "$path" ]]; then
    echo "[OK] file exists: $path"
  else
    echo "[NG] file missing: $path"
    ok=false
  fi
}

check_env_nonempty() {
  local key="$1"
  local val="${!key:-}"
  if [[ -n "$val" ]]; then
    echo "[OK] env set: $key (len=${#val})"
  else
    echo "[NG] env missing: $key"
    ok=false
  fi
}

check_runtime_state() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "[NG] runtime state missing: $path"
    ok=false
    return 0
  fi
  python - "$path" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    raw = json.loads(p.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"[NG] runtime state invalid json: {exc}")
    raise SystemExit(2)
if not isinstance(raw, dict):
    print("[NG] runtime state is not object")
    raise SystemExit(2)
trading_enabled = bool(raw.get("trading_enabled", False))
emergency_stop = bool(raw.get("emergency_stop", False))
updated_at = str(raw.get("updated_at", ""))
print(f"[OK] runtime trading_enabled={trading_enabled} emergency_stop={emergency_stop} updated_at={updated_at}")
PY
}

echo "== preflight check =="
echo "mode=$MODE"

check_file "$RUNTIME_STATE_PATH"
check_runtime_state "$RUNTIME_STATE_PATH" || ok=false

case "$MODE" in
  dry-run)
    check_file "$RISK_EVAL_PATH"
    check_file "$SIGNALS_PATH"
    ;;
  testnet-live)
    check_env_nonempty "BINANCE_TESTNET_API_KEY"
    check_env_nonempty "BINANCE_TESTNET_API_SECRET"
    ;;
  testnet-futures-live)
    check_env_nonempty "BINANCE_FUTURES_TESTNET_API_KEY"
    check_env_nonempty "BINANCE_FUTURES_TESTNET_API_SECRET"
    ;;
  production)
    check_env_nonempty "BINANCE_API_KEY"
    check_env_nonempty "BINANCE_API_SECRET"
    ;;
  *)
    echo "[NG] unknown mode: $MODE"
    ok=false
    ;;
esac

if [[ "$ok" == "true" ]]; then
  echo "preflight: PASS"
  exit 0
fi

echo "preflight: FAIL"
exit 1
