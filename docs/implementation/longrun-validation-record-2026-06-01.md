# Longrun Validation Record

- Date: 2026-06-01 (JST)
- Operator: komug + Codex
- Method: 短時間ドライラン（runtime連携確認 + orchestrator実行）

## Current Status (Latest)
- 8h+ continuous run: `completed`
- Latest checklist alignment: `Go-Live Ready (notification hold)` on 2026-06-01
- Source of truth:
  - `docs/implementation/trading-go-live-checklist.md`
  - `data/validation/longrun_checkpoints.jsonl`
  - `data/validation/runtime_metrics_health_report.json`
- Note:
  - 下記の初期セクション（短時間ドライラン）は当日の初期記録であり、後半の `Auto Appended Longrun Summary` が最新連続運転結果。

## Window
- 2026-05-31T08:44:07Z - 2026-05-31T08:44:07Z

## Scope
- runtime control bridge (`control_events.jsonl` -> `control_state.json`)
- dry-run orchestrator (`python -m auto_trader.orchestrator --dry-run`)
- ops alert pipeline
- notify test (設定未投入のため skip 確認)

## Scenario Results
- Runtime linkage: `pass`
  - `START` イベント処理: `processed=1`
  - runtime state 更新: 確認済み
- Dry-run orchestrator: `pass`
  - `overall_status`: `pass`
  - `e2e_smoke`: `pass`
  - `ops_alert`: `pass`（`count=2`）
  - `notify_test`: `pass`（`skipped=true`, `reason=notifier_not_configured`）

## Evidence
- Command:
```bash
python -m auto_trader.orchestrator \
  --dry-run \
  --signals-path data/signals/BTCUSDT_1m_range_signals.parquet \
  --risk-eval-path data/risk/risk_eval.parquet \
  --runtime-state-path data/runtime/control_state.json \
  --output-dir data/orchestrator
```
- Output artifacts:
  - `data/orchestrator/dryrun_report.json`
  - `data/orchestrator/e2e/smoke_report.json`
  - `data/orchestrator/e2e/smoke_events.jsonl`
  - `data/orchestrator/ops/alerts.parquet`
  - `data/orchestrator/ops/alerts.jsonl`

## Notes
- Notify watcher は本記録では対象外（Phase 15/16 follow-up）。
- 本セクションは初期ドライラン時点の記録（履歴）。
- Futures testnet 注文送信の疎通確認を追加実施（下記 Evidence 追記）。

## Decision
- Conditional Go（初期ドライラン時点の判定。最新判定は `Current Status` および Go-Live checklist を参照）

## Additional Evidence (Futures Testnet)
- Command:
```bash
python -m auto_trader.exchange \
  --mode testnet-futures-live \
  --symbol BTCUSDT --side buy --qty 0.001 --pass-filter \
  --runtime-state-path data/runtime/control_state.json \
  --state-path data/exchange/gateway_state.json
```
- Result:
  - `status=ack`
  - `reason=accepted:NEW`
  - `order_id=13595992753`
- Interpretation:
  - Futures testnet 向け認証・送信・runtime gate 連携が成立。

## Additional Evidence (Runtime Gate on Futures Testnet)
- Scenario:
  - `STOP` -> 注文拒否を確認
  - `EMERGENCY_STOP` -> 注文拒否を確認
  - `START` -> 注文受理を確認
- Runtime processing:
  - `{"processed": 1, "actions": ["STOP"]}`
  - `{"processed": 1, "actions": ["EMERGENCY_STOP"]}`
  - `{"processed": 1, "actions": ["START"]}`
- Order results:
  - `status=rejected reason=RUNTIME_TRADING_DISABLED order_id=`
  - `status=rejected reason=RUNTIME_EMERGENCY_STOP order_id=`
  - `status=ack reason=accepted:NEW order_id=13596252848`
- Interpretation:
  - runtime state による注文ゲート（停止・緊急停止・再開）が意図どおり機能。

## Additional Evidence (Automated Futures Runtime Gate Check)
- Command:
```bash
./scripts/futures_runtime_gate_check.sh
```
- Result path:
  - `data/validation/futures_runtime_gate_check.jsonl`
- Console summary:
  - `[STOP] {"processed": 1, "actions": ["STOP"]}`
  - `[STOP] status=rejected reason=RUNTIME_TRADING_DISABLED order_id=`
  - `[EMERGENCY_STOP] {"processed": 1, "actions": ["EMERGENCY_STOP"]}`
  - `[EMERGENCY_STOP] status=rejected reason=RUNTIME_EMERGENCY_STOP order_id=`
  - `[START] {"processed": 1, "actions": ["START"]}`
  - `[START] status=ack reason=accepted:NEW order_id=13596739628`
- Interpretation:
  - 手動手順と同等の runtime gate 検証を自動化し、再現可能な証跡として取得できた。

---

## 8h Continuous Run Template

- Date: YYYY-MM-DD (JST)
- Operator: <name>
- Window: HH:MM-HH:MM (JST, 8h+)
- Scope: runtime / notify / ops

### 30min Checkpoints
- [ ] `control_state.json.updated_at` が更新
- [ ] `notify_state.json.updated_at` が更新
- [ ] `.lock` 長時間残留なし
- [ ] `.bak` 存在・更新追従あり
- [ ] watcher プロセス生存（runtime/notify/ops）

### Scenario Results
- Normal run: pass/fail
- Corruption recovery: pass/fail
- Lock contention: pass/fail

### Evidence
- CI run:
- Log files:
- Artifacts:
  - `data/runtime/control_state.json(.bak/.lock)`
  - `data/ops/notify_state.json(.bak/.lock)`
  - `data/orchestrator/dryrun_report.json`

### Incidents
- none / details

### Decision
- Go / Conditional Go / No-Go

---

## Auto Appended Longrun Summary
- generated_at: 2026-05-31T18:05:03.134374+00:00
- checkpoints_window: 2026-05-31T09:03:05Z - 2026-05-31T17:38:16Z
- checkpoints_rows: 8
- runtime_updated_progress pass-rate: 1/8
- notify_updated_progress pass-rate: 0/8
- runtime_lock_residual clear-rate: 8/8
- notify_lock_residual clear-rate: 8/8
- runtime_alive pass-rate: 8/8
- notify_alive pass-rate: 0/8
- ops_alive pass-rate: 0/8
- runtime_metrics_health: warn
- runtime_metrics_no_go_hits: 0

### Evidence
- checkpoints: `data/validation/longrun_checkpoints.jsonl`
- runtime metrics health: `data/validation/runtime_metrics_health_report.json`

---

## Auto Appended Longrun Summary
- generated_at: 2026-05-31T18:05:58.847783+00:00
- checkpoints_window: 2026-05-31T09:03:05Z - 2026-05-31T17:38:16Z
- checkpoints_rows: 8
- runtime_updated_progress pass-rate: 1/8
- notify_updated_progress pass-rate: 0/8
- runtime_lock_residual clear-rate: 8/8
- notify_lock_residual clear-rate: 8/8
- runtime_alive pass-rate: 8/8
- notify_alive pass-rate: 0/8
- ops_alive pass-rate: 0/8
- runtime_metrics_health: warn
- runtime_metrics_no_go_hits: 0

### Evidence
- checkpoints: `data/validation/longrun_checkpoints.jsonl`
- runtime metrics health: `data/validation/runtime_metrics_health_report.json`

---

## Auto Appended Longrun Summary
- generated_at: 2026-05-31T18:09:36.279234+00:00
- checkpoints_window: 2026-05-31T18:09:34Z - 2026-05-31T18:09:34Z
- checkpoints_rows: 1
- runtime_updated_progress pass-rate: 0/1
- notify_updated_progress pass-rate: 0/1
- runtime_lock_residual clear-rate: 1/1
- notify_lock_residual clear-rate: 1/1
- runtime_alive pass-rate: 0/1
- notify_alive pass-rate: 0/1
- ops_alive pass-rate: 0/1
- runtime_metrics_health: warn
- runtime_metrics_no_go_hits: 0

### Evidence
- checkpoints: `data/validation/longrun_smoke2/longrun_checkpoints.jsonl`
- runtime metrics health: `data/validation/longrun_smoke2/runtime_metrics_health_report.json`

---

## Auto Appended Longrun Summary
- generated_at: 2026-05-31T18:29:35.046844+00:00
- checkpoints_window: 2026-05-31T09:03:05Z - 2026-05-31T18:27:55Z
- checkpoints_rows: 16
- runtime_updated_progress pass-rate: 1/16
- notify_updated_progress pass-rate: 0/16
- runtime_lock_residual clear-rate: 16/16
- notify_lock_residual clear-rate: 16/16
- runtime_alive pass-rate: 16/16
- notify_alive pass-rate: 0/16
- ops_alive pass-rate: 0/16
- runtime_metrics_health: warn
- runtime_metrics_no_go_hits: 0

### Evidence
- checkpoints: `data/validation/longrun_checkpoints.jsonl`
- runtime metrics health: `data/validation/runtime_metrics_health_report.json`
