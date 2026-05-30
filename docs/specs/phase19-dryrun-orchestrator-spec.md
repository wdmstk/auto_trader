# Phase 19 Spec: Dry-Run Orchestrator

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002, 0003

## 目的
運用前確認をワンコマンド化し、横断導線（E2E/ops/notify）の手動実行ミスを削減する。

## 入力（I/O契約）
- signals: `data/signals/*.parquet`
- risk: `data/risk/risk_eval.parquet`
- runtime: `data/runtime/control_state.json`
- notification設定（任意）: 環境変数

## 出力（I/O契約）
- dry-run レポート: `data/orchestrator/dryrun_report.json`
  - `step, success, details, started_at, finished_at`

## 前提条件
- `--dry-run` は外部取引所へ発注しない。
- fail-fast で最初の失敗で停止する。
- 通知設定がない場合は notify step を skip する。

## 仕様
1. 実行順
- e2e smoke
- ops alert pipeline
- notify test（設定時のみ）

2. 終了コード
- 全成功: 0
- いずれか失敗: 1

3. 可観測性
- 各stepの開始/終了時刻を記録。
- 失敗時は `details.error_reason` を必須出力。

## 失敗モードと対策
- 入力不足: stepごとの入力バリデーションで即時失敗。
- 通知未設定: skip扱いで継続。
- 部分成功: レポートに成功/失敗を混在記録し原因追跡可能にする。

## テスト観点
- dry-run 正常系で report が作成されること。
- e2e失敗時に後続stepへ進まないこと。
- notify未設定時に skip されること。
