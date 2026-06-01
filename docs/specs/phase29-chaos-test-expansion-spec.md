# Phase 29 Spec: Chaos Test Expansion (Partial Fill / Silent WS Stale)

- Version: 1.0
- Date: 2026-06-01
- Related ADR: 0001, 0002

## 目的
実運用事故を減らすため、API timeout 以外の意地悪ケースを
自動テストで再現し、停止までの挙動を検証する。

## 入力（I/O契約）
- 注文イベントストリーム
- websocket受信イベントストリーム
- 異常シナリオ設定（partial fill率、silent stale秒数）

## 出力（I/O契約）
- シナリオ別検証結果: `pass|warn|fail`
- 状態整合レポート（order state / position state）
- stale検知レイテンシ（秒）
- 緊急停止発火有無

## 前提条件
- 既存 stress test は維持し、本Phaseは運用系異常の追加検証。
- 本番コード改修前にシミュレーションで再現性を確認する。

## 仕様
1. Partial Fill シナリオ
- 例: 10%約定後に残数量キャンセル。
- 期待動作: 約定数量のみ position 反映、残数量は未約定でクローズ。

2. Silent WebSocket Stale シナリオ
- エラーなしでデータ更新停止を再現。
- 期待動作: stale検知 -> warn/critical -> 緊急停止までの時間を記録。

3. 判定
- 状態不整合発生時は fail。
- stale検知遅延が閾値超過時は warn/fail。

## 失敗モードと対策
- 部分約定後の二重計上: 状態遷移テーブルの厳密化。
- 無言切断未検知: heartbeat/stale watchdog を併用。
- 停止遅延: emergency path を最短経路で呼び出す。

## テスト観点
- partial fill 後の数量整合が保証される。
- stale検知から緊急停止までのレイテンシが閾値内。
- 既存e2eスモークを壊さない。
