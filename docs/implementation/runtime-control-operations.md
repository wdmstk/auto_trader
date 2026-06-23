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
- GUI の Exchange Position Sync: Binance Futures testnet の `fapi/v2/account` を直接参照して現在ポジションを表示する
- Position refresh: `scripts/refresh_positions_from_order_events.sh`
- Risk input refresh: `scripts/refresh_risk_input_from_positions.sh`
- Risk refresh: `python -m auto_trader.risk --input-path data/risk/risk_input.parquet --output-path data/risk/risk_eval.parquet`

## Durability方針
- `control_state.json` は `atomic write + lock file + backup recovery` で更新される。
- lock取得失敗時はタイムアウトで失敗し、破壊的上書きはしない。
- stale な `.lock` は PID / 経過時間で回収して再試行する。
- primary破損時は `control_state.json.bak` から復旧を試行する。
- `refresh_risk_input_from_positions.sh` は `data/features/*_features.parquet` から latest `atr` を拾い、`volatility` を補完する。

## 実行方法
1. 単発処理（デバッグ）
```bash
python -m auto_trader.runtime
```

2. 常駐処理（推奨）
```bash
python -m auto_trader.runtime --watch --interval-sec 2
```

### runtime workspace を初期化する場合
local に stale な `worker_state` / `positions` / `order_events` / `runtime_metrics` が残っていて、
testnet 側はノーポジ前提でやり直したい場合は次を使う。

```bash
./scripts/reset_runtime_workspace.sh
```

この reset は次を行う。

- `data/runtime/control_state.json` を `Trading OFF` に戻す
- `data/runtime/worker_state.json` を空に戻す
- `data/exchange/gateway_state.json` / `order_events.jsonl` を初期化する
- `data/positions/positions.parquet` / `data/risk/*.parquet` を空に戻す
- `data/validation/runtime_metrics.jsonl` と watch log を空にする

`weekly_autotune` や `route_selection_runtime.env` は消さない。

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

repo 管理の unit 例:

- [auto-trader-runtime.user.service.example](/home/komug/projects/auto_trader/ops/systemd/auto-trader-runtime.user.service.example:1)
- [auto-trader-worker.user.service.example](/home/komug/projects/auto_trader/ops/systemd/auto-trader-worker.user.service.example:1)

配置:

```bash
cp ops/systemd/auto-trader-runtime.user.service.example ~/.config/systemd/user/auto-trader-runtime.service
cp ops/systemd/auto-trader-worker.user.service.example ~/.config/systemd/user/auto-trader-worker.service
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

GUI の `Exchange Position Sync` も同じ Futures testnet 認証情報を使う。これは read-only 参照であり、
local `positions.parquet` を直接上書きしない。route metadata は REST に含まれないため、比較用の symbol net 表示として扱う。

安全運用の初期値として、live worker は `TREND_ORDER_MODE=market` / `RANGE_ORDER_MODE=market` を推奨する。
現状の `LIMIT` は `IOC` 固定で、取引所側の `expired/canceled/partial` を local position へ完全反映していないため、

`ROUTE_SELECTION_PATH` は worker が live route を読み込む正本 path で、`weekly_revalidation_report.json`
や `autotune_full_route_manifest.json` のような `selection.trade_routes` 互換 JSON を指定できる。
正式運用で `./scripts/weekly_autotune_pipeline.sh` を使う場合は、pipeline 完了後に
`ROUTE_SELECTION_PATH` が `weekly_revalidation_report.json` へ自動で切り替わる。
その current 値は `data/validation/weekly_autotune/route_selection_runtime.env` に出力される。
既存の `WEEKLY_REVALIDATION_REPORT_PATH` は後方互換として残している。
本番系の自動売買では診断用途に留める。
2026-06-09 時点では、OHLCV 修復後の週次再評価でも `limit` 優位の根拠は薄く、
cost-grid は route 選定より execution 前提比較の色が強いため、運用既定は `market` 優先とする。

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

### execution stream collector を常駐化する場合
`order_events` と `positions` を取引所の終端状態へ寄せるには、user data stream collector を常駐化する。

```ini
# ~/.config/systemd/user/auto-trader-execution-stream.service
[Unit]
Description=Auto Trader Execution Stream Collector
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/komug/projects/auto_trader
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/home/komug/projects/auto_trader/.env
ExecStart=/home/komug/projects/auto_trader/.venv/bin/python -m auto_trader.exchange.user_stream --output-path data/exchange/execution_events.jsonl
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-execution-stream.service
systemctl --user status auto-trader-execution-stream.service
journalctl --user -u auto-trader-execution-stream.service -f
```

確認ポイント:
- `data/exchange/execution_events.jsonl` が更新されること
- worker summary の `execution_sync.applied` が 0 のまま張り付かないこと
- `order_events.jsonl` に `sync_source=execution_report` 行が追記されること

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

### LivePnL 用 OHLCV 更新
GUI の LivePnL 計算で使用する最新価格を取得するための定期更新です。
専用ディレクトリ `data/live_pnl/ohlcv/` に保存し、既存の `data/parquet/` との整合性問題を回避します。

テンプレート:
- [auto-trader-ohlcv-refresh.user.service.example](/home/komug/projects/auto_trader/ops/systemd/auto-trader-ohlcv-refresh.user.service.example:1)
- [auto-trader-ohlcv-refresh.user.timer.example](/home/komug/projects/auto_trader/ops/systemd/auto-trader-ohlcv-refresh.user.timer.example:1)

```bash
cp ops/systemd/auto-trader-ohlcv-refresh.user.service.example ~/.config/systemd/user/auto-trader-ohlcv-refresh.service
cp ops/systemd/auto-trader-ohlcv-refresh.user.timer.example ~/.config/systemd/user/auto-trader-ohlcv-refresh.timer
systemctl --user daemon-reload
systemctl --user enable --now auto-trader-ohlcv-refresh.timer
systemctl --user status auto-trader-ohlcv-refresh.timer
systemctl --user start auto-trader-ohlcv-refresh.service
journalctl --user -u auto-trader-ohlcv-refresh.service -f
```

> LivePnL 専用ディレクトリ構成:
> - `data/live_pnl/ohlcv/{symbol}_{timeframe}.parquet` - LivePnL 用最新価格
> - GUI はこのディレクトリを優先し、なければ `data/parquet/` をフォールバック
> - 既存の signals/regime データとの整合性チェックに影響しない

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
- `data/live_pnl/ohlcv/` のファイルが5分間隔で更新されていること（LivePnL用）

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
- `auto-trader-ohlcv-refresh.timer`
  - LivePnL 計算用の最新価格を定期取得する
  - デフォルトは5分間隔、`data/live_pnl/ohlcv/` に保存

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
  - drift / symbol gating 連携
  - 戦略の健全性確認用の本線
  - 既定では `RUN_COST_GRID=0` で動かし、重い cost-grid は含めない
  - 詳細な `range` / `trend` の推奨モードは `docs/implementation/weekly-revalidation-operations.md` を参照する
- `./scripts/backtest_cost_grid.sh`
  - 単発 backtest の TAT が 5 分以上、または複数 symbol / timeframe / parameter を振る診断に使う
  - `market` / `limit` やコスト感度をまとめて比較したいときに使う
  - 本線に含める場合は `RUN_COST_GRID=1 ./scripts/weekly_strategy_revalidation.sh`
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
- `./scripts/ohlcv_coverage_check.sh`
  - `data/parquet/*_1m.parquet` の coverage / gap を点検したいとき
  - 週次再評価の前に、OHLCV の期間不足や大きな欠損がないかを確認する
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

#### OHLCV coverage 点検
週次再評価の前提として、`data/parquet/*_1m.parquet` の期間と gap を確認する。

```bash
./scripts/ohlcv_coverage_check.sh
cat data/validation/ohlcv_coverage_1m.md
cat data/validation/ohlcv_gaps_1m.md
```

- `Span Days` が短い場合:
  - `FROM_TS` を過去に伸ばして `./scripts/multi_symbol_data_pipeline.sh` を再実行する
- `Gaps > Warn` が多い場合:
  - `ohlcv_gaps_1m.md` で gap 区間を確認し、同じ期間を再取得して coverage を再確認する
- TAT 比較をしたい場合:
  - `./scripts/multi_symbol_data_pipeline_benchmark.sh`
  - `data/validation/multi_symbol_data_pipeline_benchmark.json` に逐次/並列の秒数と speedup を保存する
- 目安:
  - 統計検証を意識するなら 30 日超の OOS を取れるだけの連続した 1m 履歴を確保する

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
