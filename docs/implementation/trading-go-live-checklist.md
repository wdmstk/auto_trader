# 取引運用 Go-Live チェックリスト（通知保留）

- Date: 2026-06-01
- Scope: Runtime Gate / Dry-Run / Futures Testnet / Longrun
- Out of Scope: Notification production rollout（運用開始後に段階投入）

## 1. Runtime Gate
- [x] GUI event -> runtime state 反映が成立
  - 証跡: `data/gui/control_events.jsonl`, `data/runtime/control_state.json`
- [x] `STOP` 時に注文拒否される
  - 証跡: `reason=RUNTIME_TRADING_DISABLED`
- [x] `EMERGENCY_STOP` 時に注文拒否される
  - 証跡: `reason=RUNTIME_EMERGENCY_STOP`
- [x] `START` で注文再開できる
  - 証跡: `status=ack reason=accepted:NEW`

## 2. Dry-Run / E2E
- [x] dry-run orchestrator が pass
  - 証跡: `data/orchestrator/dryrun_report.json`
- [x] e2e smoke 全ステージ pass
  - 証跡: `data/orchestrator/e2e/smoke_report.json`

## 3. Futures Testnet Connectivity
- [x] futures testnet キーで認証成功
  - 証跡: `status=ack reason=accepted:NEW`
- [x] runtime gate 自動検証スクリプトが成立
  - 証跡: `data/validation/futures_runtime_gate_check.jsonl`
- [x] preflight チェック運用を整備
  - 証跡: `scripts/preflight_check.sh`

## 3.5 Parallel Walkforward (Phase D)
- [x] 逐次 vs 並列のTAT比較を取得
  - 証跡: `data/validation/parallel_walkforward_benchmark.json`
  - 実測: `7 sec -> 3 sec`（`2.33x`）

## 3.6 Runtime Metrics Health (Phase E)
- [x] monitor でメトリクス採取できる
  - コマンド: `python -m auto_trader.monitor --watch --interval-sec 5 --output-jsonl data/validation/runtime_metrics.jsonl`
  - 証跡: `data/validation/runtime_metrics.jsonl`
- [x] GUIで Health 判定表示できる
  - 画面: `Runtime Metrics`（`Health: OK/WARNING/CRITICAL`）
- [x] しきい値自動採点ができる
  - コマンド: `./scripts/runtime_metrics_health_check.sh`
  - 証跡: `data/validation/runtime_metrics_health_report.json`
- [x] Go-Live時のしきい値基準を満たす（最終判定）
  - `runtime_emergency_stop = false`
  - `runtime_trading_enabled = true`
  - `gateway_pending_orders < 3`（`>=10` は No-Go）
  - `order_latency_p95_ms < 500`（`>=2000` は No-Go）
  - `system_loadavg_1m < 4.0`（`>=8.0` は No-Go）
  - `risk_block_count` が継続増加していない（急増時は原因確認）

## 3.7 Timeframe Policy Validation
- [x] `1m/5m/15m` の比較評価を実施
  - コマンド: `./scripts/timeframe_comparison.sh`
  - 証跡: `data/validation/timeframe_eval/timeframe_comparison_summary.json`
- [x] 運用方針を `15m(regime) + 5m(signal) + 1m(execution)` に暫定決定
  - 記録: `docs/implementation/timeframe-evaluation-2026-06-01.md`
- [x] 長期データ（3か月・5銘柄）で再評価して方針確定
  - コマンド: `FROM_TS=2026-01-01T00:00:00+00:00 TO_TS=2026-04-01T00:00:00+00:00 TIMEFRAME=1m ./scripts/multi_symbol_data_pipeline.sh`
  - 結果: trend集計で `15m` が `PF/DD/WinRate` バランス最良（詳細は評価記録参照）
- [x] range閾値調整でシグナル成立不足を解消
  - コマンド: `RANGE_REQUIRE_REVERSAL_CANDLE=false RANGE_WICK_RATIO_MIN=0.3 ./scripts/timeframe_comparison.sh`
  - 結果: range集計で全時間足に有効シグナルを確認（詳細は評価記録参照）
  - follow-up: `docs/implementation/weekly-revalidation-operations.md` の `range` / `trend` 推奨モードも参照

## 4. Longrun (8h+)
- [x] 8時間以上の連続運転証跡
  - 証跡: `data/validation/longrun_checkpoints.jsonl`
- [x] Runtime Metrics 自動採点レポートを取得
  - 証跡: `data/validation/runtime_metrics_health_report.json`
- [x] Longrun record へサマリ追記
  - コマンド: `./scripts/longrun_8h_check.sh`（完了時に自動追記）
  - 手動実行: `./scripts/append_longrun_record.sh`
  - 証跡: `docs/implementation/longrun-validation-record-YYYY-MM-DD.md`
- [x] `.lock` 長時間残留なし
- [x] `updated_at` 更新継続
- [x] watcher 生存継続

## 4.5 Statistical Qualification
- [ ] routeごとの最終OOS closed tradesが30件以上
- [ ] trend/rangeごとの最終OOS closed tradesが100件以上
- [ ] 最終OOSが30日以上かつ全期間の20%以上
- [ ] 95% bootstrap CI下限が `PF > 1.0` かつ `ExpectancyBps > 0`
- [ ] Monte CarloでDD 95 percentileが8%以下かつ終了損失確率が5%以下
- [ ] frozen manifestとデータリーク監査がpass
  - 証跡: `data/validation/statistical_qualification/qualification_report.json`
  - manifest: `data/validation/statistical_qualification/frozen_manifest.json`

## 5. Open Items
- [ ] route-centric worker変更後の運用証跡を再取得する
  - 残件:
    - 2026-06-07のroute/position/worker変更後に8h longrunとFutures Testnetを再実行する
    - 品質ゲート: `ruff` / `mypy` / full 191件 / smoke 18件はpass
    - range/trendの継続最適化（週次再評価）
      - runbook: `docs/implementation/weekly-revalidation-operations.md`
      - command: `./scripts/weekly_strategy_revalidation_with_core.sh`
      - 暫定運用symbol:
        - `trend(limit)`: `ETHUSDT,XRPUSDT`
        - `range(market)`: `XRPUSDT`
    - 通知運用投入（運用開始後）

## 判定
- [ ] Go-Live Ready（通知保留条件付き）
- [x] Conditional Go（route-centric変更後の運用再検証待ち）
- 条件:
  - route-centric変更後の8h longrun完了
  - Futures Testnetで複数routeのposition/order整合を確認
  - Runtime Metricsしきい値を連続運転で満たす
- 判定者: auto
- 判定日: 2026-06-14

最新判定の正本:
- 本チェックリスト末尾の `Auto Decision Notes` と `判定日` を正本とする。
- 本文中の過去記録（例: Conditional Go）は履歴として保持し、矛盾時は正本を優先する。

補足:
- `./scripts/update_go_live_checklist.sh` で Longrun/Runtime Metrics/Weekly Revalidation 証跡から
  チェック状態と判定者・判定日を自動更新できます。

<!-- AUTO_DECISION_NOTES_START -->
### Auto Decision Notes
- go_live_ready: false
- health_status: fail
- weekly_status: warn
- statistical_status: fail
- longrun_rows: 34
- runtime_env_path: data/validation/weekly_autotune/route_selection_runtime.env
- pipeline_summary_path: data/validation/weekly_autotune/pipeline_summary.json
- weekly_report_path: data/validation/weekly_autotune/weekly_revalidation/weekly_revalidation_report.json
- weekly_report_path_source: explicit_weekly_report_path
- weekly_report_run_id: weekly-autotune-20260613T205857Z
- weekly_report_generated_at: 2026-06-13T20:58:57.904260+00:00
- weekly_report_age_hours: 13.65
- statistical_report_path: data/validation/statistical_qualification/qualification_report.json
- statistical_report_run_id: weekly-autotune-20260613T150841Z
- statistical_report_generated_at: 2026-06-13T15:59:40.717928+00:00
- statistical_report_age_hours: 18.63
- strategy_report_path: data/validation/weekly_autotune/weekly_revalidation/strategy_quality_report.md
- strategy_report_run_id: weekly-autotune-20260613T205857Z
- strategy_report_generated_at: 2026-06-14T10:37:31.609394+00:00
- strategy_report_age_hours: 0.00
- strategy_report_json_path: data/validation/weekly_autotune/weekly_revalidation/strategy_quality_report.json
- strategy_report_json_run_id: weekly-autotune-20260613T205857Z
- strategy_report_json_generated_at: 2026-06-14T10:37:31.699132+00:00
- strategy_report_json_age_hours: 0.00
- ai_progress_report_path: data/validation/weekly_autotune/weekly_revalidation/ai_strategy_progress_report.json
- ai_progress_report_run_id: weekly-autotune-20260613T205857Z
- ai_progress_report_generated_at: 2026-06-14T10:37:31.825518+00:00
- ai_progress_report_age_hours: 0.00
- strategy_quality_range_recommendation: drop_or_retune
- strategy_quality_trend_recommendation: drop_or_retune
- health_report_path: data/validation/runtime_metrics_health_report.json
- health_report_run_id: weekly-autotune-20260613T150841Z
- health_report_generated_at: 2026-06-14T04:53:46.619613+00:00
- health_report_age_hours: 5.73
- unmet_reasons:
  - runtime metrics が fail（No-Go）
  - weekly strategy revalidation が warn（要調整）
  - statistical qualification が fail（No-Go）
<!-- AUTO_DECISION_NOTES_END -->

<!-- AUTO_OPEN_ITEMS_START -->
### Auto Open Items
- [ ] runtime metrics が fail（No-Go）
- [ ] weekly strategy revalidation が warn（要調整）
- [ ] statistical qualification が fail（No-Go）
<!-- AUTO_OPEN_ITEMS_END -->
