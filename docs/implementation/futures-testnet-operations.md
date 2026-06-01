# Futures Testnet 運用ガイド

- Version: 1.0
- Date: 2026-06-01

## 目的
Futures testnet での実送信検証を、同じ手順で再現できるようにする。

## 前提
- `.venv` 作成済み
- `.env` に以下を設定済み
  - `BINANCE_FUTURES_TESTNET_API_KEY`
  - `BINANCE_FUTURES_TESTNET_API_SECRET`
- runtime state が利用可能
  - `data/runtime/control_state.json`

## 1. 環境読込
```bash
set -a
source .env
set +a
```

## 2. プレフライト
```bash
./scripts/preflight_check.sh testnet-futures-live
```

## 3. 単発注文（疎通確認）
```bash
python -m auto_trader.exchange \
  --mode testnet-futures-live \
  --symbol BTCUSDT --side buy --qty 0.001 --pass-filter \
  --runtime-state-path data/runtime/control_state.json \
  --state-path data/exchange/gateway_state.json
```

期待:
- `status=ack reason=accepted:NEW order_id=...`

## 4. runtime gate 自動検証
```bash
./scripts/futures_runtime_gate_check.sh
```

成果物:
- `data/validation/futures_runtime_gate_check.jsonl`

期待:
- `STOP`: `RUNTIME_TRADING_DISABLED`
- `EMERGENCY_STOP`: `RUNTIME_EMERGENCY_STOP`
- `START`: `accepted:NEW`

## 5. 失敗時の切り分け
1. `credentials_missing`
- `.env` 読込漏れまたは変数名ミスを確認。

2. `http_error:401:code=-2015`
- Futures testnet キー種別/権限/IP制限を確認。

3. `RUNTIME_TRADING_DISABLED` / `RUNTIME_EMERGENCY_STOP`
- `data/runtime/control_state.json` を確認し、必要なら `START` / `EMERGENCY_CANCEL` を反映。

## 6. 証跡化
- 実行ログと `order_id` を
  - `docs/implementation/longrun-validation-record-2026-06-01.md`
  に追記する。
