# Phase 14 Spec: Operations Runbook and Alerting

- Version: 1.0
- Date: 2026-05-31
- Related ADR: 0001, 0002

## 目的
本番運用時の監視・停止・復旧判断を標準化し、異常時に迷わず安全側へ倒せる運用Runbookを定義する。

## 入力（I/O契約）
- runtime状態: `data/runtime/control_state.json`
- runtimeイベントカーソル: `data/runtime/control_cursor.json`
- GUI操作ログ: `data/gui/control_events.jsonl`
- リスク評価: `data/risk/risk_eval.parquet`
- 発注イベント（将来拡張含む）: `status, reason, latency_ms`

## 出力（I/O契約）
- 運用Runbook文書
  - 監視項目、閾値、初動、復旧条件、エスカレーション先
- アラート契約
  - `alert_code, severity, detected_at, source, summary, action_required`

## 前提条件
- `HIGH_VOL=NO TRADE` と `EMERGENCY_STOP` は常に最優先。
- stale/欠損時は「不明」ではなく「危険」として扱う。
- 手動オペレーションは監査ログへ残す。

## 仕様
1. 監視カテゴリ
- `RISK_DD_BREACH`: DD上限超過（critical）
- `RUNTIME_STALE`: runtime state 更新遅延（warning/critical）
- `RISK_DATA_STALE`: risk評価遅延（warning/critical）
- `ORDER_REJECT_SPIKE`: 発注 reject 急増（warning）
- `EMERGENCY_ACTIVE`: emergency_stop 有効化中（critical）

2. 既定閾値
- `runtime_stale_sec >= 30` で warning、`>= 120` で critical
- `risk_stale_sec >= 30` で warning、`>= 120` で critical
- `reject_rate_5m >= 0.2` で warning
- `current_dd_pct > max_dd_pct` で critical

3. 初動手順
- critical は `EMERGENCY_STOP` を第一選択とする。
- warning は再観測を1回実施し、継続時に停止判断する。
- `CLOSE_ALL` は `EMERGENCY_STOP` 後に順次実行する。

4. 復旧条件
- stale系は連続3サイクル正常化で復旧。
- DD超過は人手承認なしに自動再開しない。
- emergency解除は `EMERGENCY_CANCEL` 実行ログ必須。

## 失敗モードと対策
- アラート過多: warningとcriticalを分離し通知チャンネルを分ける。
- アラート欠落: 心拍監視（watcher alive）を追加する。
- 誤復旧: 復旧判定にヒステリシス（連続正常回数）を導入する。

## テスト観点
- stale閾値を跨いだとき severity が正しく遷移すること。
- emergency active 中は再開系操作が制限されること。
- DD超過時に停止優先のRunbook導線が出ること。
- アラート契約フィールドが欠落しないこと。
