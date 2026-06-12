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
- execution stream collector が利用可能
  - `python -m auto_trader.exchange.user_stream`
- 常駐プロセスは user service で起動できる
  - `auto-trader-runtime.service`
  - `auto-trader-worker.service`

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

## 2-1. 常駐サービス起動（推奨）
```bash
cp ops/systemd/auto-trader-runtime.user.service.example ~/.config/systemd/user/auto-trader-runtime.service
cp ops/systemd/auto-trader-worker.user.service.example ~/.config/systemd/user/auto-trader-worker.service
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-runtime.service
systemctl --user enable --now auto-trader-worker.service
systemctl --user status auto-trader-runtime.service
systemctl --user status auto-trader-worker.service
```

補足:
- `systemd` で起動する場合は、`~/.config/systemd/user/` の unit に `EnvironmentFile=/home/komug/projects/auto_trader/.env` を入れるか、
  `systemctl --user import-environment` 相当で `BINANCE_FUTURES_TESTNET_API_KEY` / `BINANCE_FUTURES_TESTNET_API_SECRET` を渡す。
- route 正本を pipeline 出力へ追従させる場合は、worker unit に
  `EnvironmentFile=/home/komug/projects/auto_trader/data/validation/weekly_autotune/route_selection_runtime.env`
  も追加する。
- repo 管理の unit 例は次を使う:
  - [auto-trader-runtime.user.service.example](/home/komug/projects/auto_trader/ops/systemd/auto-trader-runtime.user.service.example:1)
  - [auto-trader-worker.user.service.example](/home/komug/projects/auto_trader/ops/systemd/auto-trader-worker.user.service.example:1)

## 2-2. execution stream collector 起動
`order_events` と local position を実約定に追従させるには、user data stream collector を併用する。

```bash
python -m auto_trader.exchange.user_stream \
  --output-path data/exchange/execution_events.jsonl
```

期待:
- `data/exchange/execution_events.jsonl` に `ORDER_TRADE_UPDATE` が追記される
- worker cycle ごとに `execution_sync.applied` が増える
- `expired` / `canceled` / `filled` の終端状態が `order_events` に `sync_source=execution_report` として追記される

## 2-3. pipeline 出力を worker へ反映する場合

```bash
RUN_ROOT=data/validation/weekly_autotune \
./scripts/weekly_autotune_pipeline.sh

set -a
source data/validation/weekly_autotune/route_selection_runtime.env
set +a
```

期待:
- `ROUTE_SELECTION_PATH` が current 正本を指す
- 正式運用では `weekly_revalidation/weekly_revalidation_report.json` を指す
- `RUN_WEEKLY=0` の軽量実行では `manifest/route_selection_manifest.json` を指す

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

補足:
- `testnet-futures-live` は送信時にサーバ時刻へ同期するため、`-1021` の時刻ズレは通常は発生しない。
- `LIMIT` は `--order-type limit --limit-price <price>` を明示する。
- live worker の既定は `TREND_ORDER_MODE=market` / `RANGE_ORDER_MODE=market` を使う。
- `LIMIT` は `IOC` 固定のため、testnet での手動疎通・診断用途に限定する。

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

## テストネット自動売買の確認項目チェックリスト
- シグナルが出たときに、意図した注文が 1 回だけ出る
- `range` / `trend` ともに live では `market` を使っている
- 同一 symbol に `range` / `trend` の両 route がある場合、GUI / worker / order event で route key が一致している
- `pass_filter` / `risk_blocked` / `runtime gate` が想定どおりに効いている
- `partial` / `filled` / `canceled` / `expired` がログと画面の両方で追える
- `execution_events.jsonl` が更新され、`order_events.jsonl` に `sync_source=execution_report` 行が追記される
- 約定後に `position`、`cash`、`PnL` が正しく更新される
- `STOP` / `EMERGENCY_STOP` 中は新規注文が出ない
- 期待していない銘柄や時間帯で注文が出ていない

## GUI確認用のチェックリスト
- シグナル一覧で `entry_signal` / `exit_signal` が想定どおり点灯する
- `pass_filter` が OFF のときに発注されない
- 注文モードが `market` / `limit` に切り替わって見える
- 注文状態が `NEW` → `PARTIAL` / `FILLED` / `CANCELED` の順で追える
- `limit` のときに `limit_price` が画面に表示される
- 画面上の `position` と `PnL` がログと一致する
- runtime gate が `STOP` のとき、GUI 上でも注文が止まっている
- 再エントリーやクールダウンが想定どおり効いている

## テストネットで自動売買として正しく動くことを確認する手順（GUI操作）
1. `.env` を読み込み、`preflight_check.sh` を通す。
2. GUI を開き、`BTCUSDT` などの小ロット対象を 1 つだけ表示する。
3. `runtime gate` を `START` にして、GUI 上で新規発注が許可されていることを確認する。
4. `trend` / `range` ともに `market` 設定で動いていることを GUI 上でも確認する。
5. 同一 symbol の複数 route を使う場合、position 表示と emergency close が route 単位で崩れていないか確認する。
6. 小ロットで 1 回だけ注文を流し、GUI 上で `NEW` → `FILLED` / `PARTIAL` / `CANCELED` を追う。
7. `partial` が出た場合は、残数量がキャンセルされるか、ログと画面を突き合わせる。
8. 約定後に `position`、`cash`、`PnL` が更新されることを確認する。
8. `STOP` に切り替え、GUI 上で新規注文が止まることを確認する。
9. 画面のスクリーンショットと `order_id` を `docs/implementation/longrun-validation-record-2026-06-01.md` に残す。

補足:
- GUI の `START/STOP` は `runtime gate` を切り替えるだけで、`runtime` と `worker` 自体は user service で常駐している前提。
- `worker` が `trading_enabled=true` を見て自動発注し、`STOP` で新規発注停止になる。

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

## 追記（2026-06-02）
- `market` 疎通確認:
  - `status=ack reason=accepted:NEW order_id=13820487896`
- `limit` 疎通確認:
  - `status=ack reason=accepted:NEW order_id=13820490452`
- 実送信時の補足:
  - `testnet-futures-live` はサーバ時刻同期を有効化したため、初回の `-1021` は解消済み。
  - `LIMIT` は `--order-type limit --limit-price <price>` を明示して送信する。
  - `LIMIT` は `IOC` 固定のため、worker の既定運用には使わない。
  - runtime gate は `START` 状態で `accepted:NEW`、`STOP` / `EMERGENCY_STOP` では拒否されることを再確認済み。
