# Longrun Validation Record

---

## Auto Appended Longrun Summary
- generated_at: 2026-06-13T20:38:30.221123+00:00
- run_id: weekly-autotune-20260613T150841Z
- checkpoints_window: 2026-05-31T09:03:05Z - 2026-06-07T12:02:41Z
- checkpoints_rows: 17
- runtime_updated_progress pass-rate: 1/17
- notify_updated_progress pass-rate: 0/17
- runtime_lock_residual clear-rate: 17/17
- notify_lock_residual clear-rate: 17/17
- runtime_alive pass-rate: 17/17
- notify_alive pass-rate: 0/17
- ops_alive pass-rate: 0/17
- runtime_metrics_health: fail
- runtime_metrics_no_go_hits: 6

### Evidence
- checkpoints: `data/validation/longrun_checkpoints.jsonl`
- runtime metrics health: `data/validation/runtime_metrics_health_report.json`

## Additional Evidence (2026-06-13 weekly autotune rerun)
- run_id: `weekly-autotune-20260613T150841Z`
- pipeline_summary: `data/validation/weekly_autotune/pipeline_summary.json`
- weekly_revalidation_report: `data/validation/weekly_autotune/weekly_revalidation/weekly_revalidation_report.json`
- Futures Testnet gate check: `data/validation/futures_runtime_gate_check.jsonl`
- longrun append helper: `scripts/append_longrun_record.sh`
- Scenario results:
  - `STOP` -> `status=rejected reason=RUNTIME_TRADING_DISABLED`
  - `EMERGENCY_STOP` -> `status=rejected reason=RUNTIME_EMERGENCY_STOP`
  - `START` -> `status=ack reason=accepted:NEW order_id=15120704689`
- Interpretation:
  - runtime gate rejection paths remain valid under the current run_id.
  - the testnet START path now reaches order submission and returns a live `order_id`.
  - longrun/testnet evidence is now cross-linked to the same weekly autotune run_id.

---

## Auto Appended Longrun Summary
- generated_at: 2026-06-14T04:53:47.147410+00:00
- run_id: weekly-autotune-20260613T150841Z
- checkpoints_window: 2026-05-31T09:03:05Z - 2026-06-14T04:23:46Z
- checkpoints_rows: 34
- runtime_updated_progress pass-rate: 1/34
- notify_updated_progress pass-rate: 0/34
- runtime_lock_residual clear-rate: 34/34
- notify_lock_residual clear-rate: 34/34
- runtime_alive pass-rate: 33/34
- notify_alive pass-rate: 0/34
- ops_alive pass-rate: 0/34
- runtime_metrics_health: fail
- runtime_metrics_no_go_hits: 583

### Evidence
- checkpoints: `data/validation/longrun_checkpoints.jsonl`
- runtime metrics health: `data/validation/runtime_metrics_health_report.json`
