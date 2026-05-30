# Phase 17 Spec: End-to-End Smoke Pipeline

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002, 0003

## 目的
signal -> position/risk -> order gate -> ops alert までの主要導線を単一ジョブで検証し、フェーズ間の接続不整合を早期に検知する。

## 入力（I/O契約）
- features/regime/signal（Phase 2/3/5/6）
- position/risk 入力データ（Phase 11/12）
- runtime control state（Phase 13）
- order request（Phase 10）

## 出力（I/O契約）
- E2E 実行結果サマリ
  - `stage, success, records, error_reason`
- スモーク成果物
  - `data/e2e/smoke_report.json`
- 検証ログ
  - `data/e2e/smoke_events.jsonl`

## 前提条件
- `HIGH_VOL=NO TRADE` と `risk_blocked` が最優先ゲートとして機能する。
- runtime state が `trading_enabled=false` の場合は発注しない。
- 失敗時は後段を継続せず fail-fast とする。

## 仕様
1. ステージ順序
- `strategy_signal_check`
- `position_apply_check`
- `risk_eval_check`
- `order_gate_check`
- `ops_alert_check`

2. ゲート条件
- `pass_filter=false` は注文拒否。
- `HIGH_VOL` は注文拒否。
- `risk_blocked=true` は注文拒否。
- runtime `emergency_stop=true` は注文拒否。

3. レポート
- 各ステージの `success/records/error_reason` を記録。
- 最終 `overall_status` を `pass/fail` で出力。

## 失敗モードと対策
- スキーマ不一致: 入力検証で即時停止。
- 途中ステージ失敗: 失敗ステージ名を明示して停止。
- サイレント失敗: 必須成果物不在を失敗判定に含める。

## テスト観点
- 正常系で `overall_status=pass` となること。
- `HIGH_VOL` / `risk_blocked` / `runtime_emergency_stop` で `order_gate_check` が失敗扱いになること。
- レポートに全ステージ結果が記録されること。
