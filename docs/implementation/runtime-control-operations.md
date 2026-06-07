# Runtime Control 運用ガイド

- Version: 1.2
- Date: 2026-06-05
- Related Spec: phase13-streamlit-gui-spec.md

## 目的
GUI操作イベントを runtime state へ継続反映し、発注ゲートへ確実に伝播させる。

## 対象コンポーネント
- GUIイベントログ: `data/gui/control_events.jsonl`
- Runtime cursor: `data/runtime/control_cursor.json`
- Runtime state: `data/runtime/control_state.json`
- Runtime runner: `python -m auto_trader.runtime --watch`
- Runtime metrics watcher: `python -m auto_trader.monitor --watch`
- Position refresh: `scripts/refresh_positions_from_order_events.sh`
- Risk input refresh: `scripts/refresh_risk_input_from_positions.sh`
- Risk refresh: `python -m auto_trader.risk --input-path data/risk/risk_input.parquet --output-path data/risk/risk_eval.parquet`

## Durability方針
- `control_state.json` は `atomic write + lock file + backup recovery` で更新される。
- lock取得失敗時はタイムアウトで失敗し、破壊的上書きはしない。
- primary破損時は `control_state.json.bak` から復旧を試行する。

## 実行方法
1. 単発処理（デバッグ）
```bash
python -m auto_trader.runtime
```

2. 常駐処理（推奨）
```bash
python -m auto_trader.runtime --watch --interval-sec 2
```

## systemd サンプル
`/etc/systemd/system/auto-trader-runtime.service`

```ini
[Unit]
Description=Auto Trader Runtime Control Watcher
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/komug/projects/auto_trader
ExecStart=/home/komug/projects/auto_trader/.venv/bin/python -m auto_trader.runtime --watch --interval-sec 2
Restart=always
RestartSec=3
User=komug

[Install]
WantedBy=multi-user.target
```

反映:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now auto-trader-runtime.service
sudo systemctl status auto-trader-runtime.service
```

確認ログ:
```bash
sudo journalctl -u auto-trader-runtime.service -f
```

### user service で試す場合（推奨）
root 権限なしで試すなら `~/.config/systemd/user/` を使う。

```ini
# ~/.config/systemd/user/auto-trader-runtime.service
[Unit]
Description=Auto Trader Runtime Control Watcher

[Service]
Type=simple
WorkingDirectory=/home/komug/projects/auto_trader
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/home/komug/projects/auto_trader/.env
ExecStart=/home/komug/projects/auto_trader/.venv/bin/python -m auto_trader.runtime --watch --interval-sec 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

```ini
# ~/.config/systemd/user/auto-trader-worker.service
[Unit]
Description=Auto Trader Live Trading Worker
After=auto-trader-runtime.service
Requires=auto-trader-runtime.service

[Service]
Type=simple
WorkingDirectory=/home/komug/projects/auto_trader
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/home/komug/projects/auto_trader/.env
Environment=WEEKLY_REVALIDATION_REPORT_PATH=data/validation/weekly_revalidation/weekly_revalidation_report.json
Environment=AUTO_SYNC_WEEKLY_SYMBOLS=1
ExecStart=/home/komug/projects/auto_trader/.venv/bin/python -m auto_trader.worker --watch --interval-sec 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

反映:
```bash
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-runtime.service
systemctl --user enable --now auto-trader-worker.service
systemctl --user status auto-trader-runtime.service
systemctl --user status auto-trader-worker.service
```

`worker` は `testnet-futures-live` の認証情報を読むため、`EnvironmentFile` か `source .env` のどちらかで
`BINANCE_FUTURES_TESTNET_API_KEY` / `BINANCE_FUTURES_TESTNET_API_SECRET` を必ず渡す。

`AUTO_SYNC_WEEKLY_SYMBOLS=0` にすると、worker は起動時に渡した `TREND_ENABLED_SYMBOLS` / `RANGE_ENABLED_SYMBOLS` を固定で使い、週次レポートの live 反映を止められる。

確認ログ:
```bash
journalctl --user -u auto-trader-runtime.service -f
journalctl --user -u auto-trader-worker.service -f
```

### 監視メトリクス watcher を常駐化する場合
`runtime_metrics.jsonl` を常に fresh に保つには monitor を常駐化する。

```ini
# ~/.config/systemd/user/auto-trader-monitor.service
[Unit]
Description=Auto Trader Runtime Metrics Watcher
After=auto-trader-runtime.service auto-trader-worker.service

[Service]
Type=simple
WorkingDirectory=/home/komug/projects/auto_trader
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/komug/projects/auto_trader/.venv/bin/python -m auto_trader.monitor --watch --interval-sec 5 --output-jsonl data/validation/runtime_metrics.jsonl
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-monitor.service
systemctl --user status auto-trader-monitor.service
journalctl --user -u auto-trader-monitor.service -f
```

### risk を timer で定期更新する場合
`risk_eval.parquet` は常駐プロセスよりも timer の定期実行が扱いやすい。
GUI の stale 警告を避けたいなら、`OnUnitActiveSec` は 30 秒以下にする。

```ini
# ~/.config/systemd/user/auto-trader-risk-refresh.service
[Unit]
Description=Auto Trader Risk Refresh
After=auto-trader-worker.service

[Service]
Type=oneshot
WorkingDirectory=/home/komug/projects/auto_trader
Environment=PYTHONUNBUFFERED=1
ExecStart=/bin/bash -lc 'scripts/refresh_positions_from_order_events.sh && scripts/refresh_risk_input_from_positions.sh && ./.venv/bin/python -m auto_trader.risk --input-path data/risk/risk_input.parquet --output-path data/risk/risk_eval.parquet'
StandardOutput=journal
StandardError=journal
```

```ini
# ~/.config/systemd/user/auto-trader-risk-refresh.timer
[Unit]
Description=Auto Trader Risk Refresh Timer

[Timer]
OnBootSec=20s
OnUnitActiveSec=20s
AccuracySec=1s
Unit=auto-trader-risk-refresh.service

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-risk-refresh.timer
systemctl --user status auto-trader-risk-refresh.timer
systemctl --user start auto-trader-risk-refresh.service
journalctl --user -u auto-trader-risk-refresh.service -f
```

> `positions.parquet` は `order_events.jsonl` の ACK 取引から再構成できる。
> その後 `risk_input` を再生成し、最後に `risk_eval` を更新する。

## cron サンプル
常駐でなく1分毎実行する場合:

```cron
* * * * * cd /home/komug/projects/auto_trader && ./.venv/bin/python -m auto_trader.runtime >> data/runtime/runtime_cron.log 2>&1
```

## 監視ポイント
- `control_events.jsonl` の追記が増えていること
- `control_cursor.json` の `last_processed_line` が進むこと
- `control_state.json` の `updated_at` が更新されること
- 緊急停止時に `emergency_stop=true` になること
- `control_state.json.lock` が長時間残留していないこと
- `control_state.json.bak` が存在し、更新追従していること

## 実行頻度の目安

### 常駐
- `auto-trader-runtime.service`
  - runtime control の常駐 watcher
- `auto-trader-worker.service`
  - 売買判断の常駐 worker
- `auto-trader-monitor.service`
  - `runtime_metrics.jsonl` を継続更新する監視 watcher

### 定期実行
- `auto-trader-risk-refresh.timer`
  - `positions -> risk_input -> risk_eval` を定期再計算する
  - stale 回避目的では 20〜30 秒程度が目安

### 日次
- `python -m auto_trader.backtest ...`
  - 単発 backtest の TAT が 5 分未満なら日次で回す
  - `ohlcv` / `signals` が更新された後の軽量な再確認に使う
  - `data/backtest/portfolio.parquet` を更新して Analysis の Backtest Snapshot に反映する
- `./scripts/backtest_symbol_rotation.sh`
  - `weekly_revalidation_report.json` の `selection.trade_routes` を起点に、live の自動売買対象だけを backtest する
  - `SYMBOLS=...` を明示した場合は手動上書きを優先する
  - 日次の対象確認や live route の崩れ検知に使う

### 週次
- `./scripts/weekly_strategy_revalidation.sh`
  - `timeframe_comparison`
  - `backtest_cost_grid`
  - drift / symbol gating 連携
  - 戦略の健全性確認用の本線
  - 詳細な `range` / `trend` の推奨モードは `docs/implementation/weekly-revalidation-operations.md` を参照する
- `./scripts/backtest_cost_grid.sh`
  - 単発 backtest の TAT が 5 分以上、または複数 symbol / timeframe / parameter を振る検証は週次に集約する
  - `market` / `limit` やコスト感度をまとめて比較したいときに使う
- `./scripts/weekly_strategy_revalidation_with_core.sh`
  - `weekly_core_feedback.env` を自動で読み込み、週次定期実行に core 候補を反映する入口
  - `result_list.md` と `range_probe_result_list.md` を補助生成する
  - 手動ではなく timer / cron 側で使う
  - 定期実行を設定する場合の推奨入口
- `auto-trader-worker.service`
  - 起動時および各サイクルで `weekly_revalidation_report.json` を読み直し、`selection.trade_routes` を live 反映できる
  - 古いレポートは `selection.trend_enabled_symbols` / `selection.range_enabled_symbols` を 15m の legacy route として扱う
  - 読み込み失敗時は前回の有効な symbol set を維持する
  - 自動反映を止める場合は `AUTO_SYNC_WEEKLY_SYMBOLS=0` を設定する

### 必要時
- `./scripts/timeframe_comparison.sh`
  - 足種や候補比較を個別に見直したいとき
- `./scripts/backtest_cost_grid.sh`
  - コスト感度を詰めたいとき
- `./scripts/parallel_walkforward.sh`
  - walkforward を銘柄×戦略で並列評価したいとき
- `./scripts/chaos_test.sh`
  - 障害耐性や異常系をまとめて確認したいとき
- `python -m auto_trader.analysis ...`
  - walkforward visual report を再生成したいとき

### 自動化済みの検証
- `./scripts/weekly_strategy_revalidation.sh`
  - `timeframe_comparison`
  - `backtest_cost_grid`
- `./scripts/prepare_long_window_visual_data.sh`
  - `walkforward_visual_check`
- `./scripts/runtime_control_validation_suite.sh`
  - `prepare_long_window_visual_data`
  - `weekly_strategy_revalidation`
  - `parallel_walkforward`
  - `chaos_test`

上記は検証ジョブであり、ライブ常駐ではありません。
- 週次本線: `weekly_strategy_revalidation.sh`
  - `data/validation/timeframe_candidates` と `data/validation/weekly_revalidation` を生成する運用本線
- 監査・拡張検証: `runtime_control_validation_suite.sh`
  - `weekly_strategy_revalidation` に加え、`parallel_walkforward` / `chaos_test` もまとめて回す上位ラッパー
  - 必要なら user systemd timer か cron で回す

#### user service で定期実行する例（監査用）
`runtime_control_validation_suite.sh` を定期実行したい場合のみ使う。

`~/.config/systemd/user/auto-trader-runtime-validation.service`

```ini
[Unit]
Description=Auto Trader Runtime Validation Suite

[Service]
Type=simple
WorkingDirectory=/home/komug/projects/auto_trader
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/komug/projects/auto_trader/scripts/runtime_control_validation_suite.sh
StandardOutput=journal
StandardError=journal
```

`~/.config/systemd/user/auto-trader-runtime-validation.timer`

```ini
[Unit]
Description=Auto Trader Runtime Validation Suite Timer

[Timer]
OnCalendar=Sun *-*-* 03:00:00
RandomizedDelaySec=30m
Unit=auto-trader-runtime-validation.service

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-runtime-validation.timer
systemctl --user status auto-trader-runtime-validation.timer
journalctl --user -u auto-trader-runtime-validation.service -f
```

#### 不要になった設定を削除するコマンド
`runtime_control_validation_suite.sh` の定期実行をやめて、`weekly_strategy_revalidation.sh` に一本化する場合は以下を実行する。

```bash
systemctl --user disable --now auto-trader-runtime-validation.timer auto-trader-runtime-validation.service
rm -f ~/.config/systemd/user/auto-trader-runtime-validation.timer \
      ~/.config/systemd/user/auto-trader-runtime-validation.service
systemctl --user daemon-reload
systemctl --user reset-failed auto-trader-runtime-validation.timer auto-trader-runtime-validation.service
```

## 障害時切り分け
1. runtimeプロセスが動作しているか確認
2. `control_events.jsonl` がJSONLとして破損していないか確認
3. `control_state.json` に反映されるか単発実行で確認
4. 発注側 `GatewayConfig.runtime_state_path` が正しいパスを参照しているか確認

## ロールバック
- runtime watcher停止:
```bash
sudo systemctl stop auto-trader-runtime.service
```
- 発注ゲートのみ残す場合は `runtime_state_path` を維持し、`trading_enabled=false` で安全停止する。

## 訓練シナリオ（最低月次）
1. Runtime stale 発生
- 想定: watcher停止で `RUNTIME_STALE` がwarning→criticalへ遷移。
- 期待: `EMERGENCY_STOP` 実施、復旧後3サイクル正常確認。

2. DD breach 発生
- 想定: `RISK_DD_BREACH` critical発火。
- 期待: 新規建て停止、手動承認なしで再開しない。

3. Emergency active 継続
- 想定: `EMERGENCY_ACTIVE` 継続中に通常再開要求が来る。
- 期待: `EMERGENCY_CANCEL` 監査ログ確認後のみ再開判断。
