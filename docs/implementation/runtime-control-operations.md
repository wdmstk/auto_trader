# Runtime Control 運用ガイド

- Version: 1.0
- Date: 2026-05-31
- Related Spec: phase13-streamlit-gui-spec.md

## 目的
GUI操作イベントを runtime state へ継続反映し、発注ゲートへ確実に伝播させる。

## 対象コンポーネント
- GUIイベントログ: `data/gui/control_events.jsonl`
- Runtime cursor: `data/runtime/control_cursor.json`
- Runtime state: `data/runtime/control_state.json`
- Runtime runner: `python -m auto_trader.runtime --watch`

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
